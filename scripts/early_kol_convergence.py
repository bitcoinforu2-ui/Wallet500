from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/early-kol-wallets.json"
STATE = ROOT / "data/early-kol-convergence-state.json"
REPORT = ROOT / "data/early-kol-convergence.json"
CANDIDATES = ROOT / "data/early-kol-candidates.json"

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
DEXSCREENER_TOKEN = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD1bDbZmQknmVfE3xuexHG"
DEFAULT_IGNORED_MINTS = {WSOL, USDC, USDT}
SWAP_LOG_MARKERS = (
    "instruction: swap",
    "instruction: route",
    "instruction: sharedaccountsroute",
    "instruction: exactoutroute",
    "swapbaseinput",
    "swapbaseoutput",
    "ray_log",
)


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_dt().isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def http_json(url: str, *, payload: Any = None, timeout: int = 15) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "Wallet500-EarlyKOL/1.0", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    response = http_json(
        rpc_url,
        payload={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=18,
    )
    if isinstance(response, dict) and response.get("error"):
        raise RuntimeError(f"RPC_{method}:{response['error']}")
    return response.get("result") if isinstance(response, dict) else None


def recent_signatures(rpc_url: str, wallet: str, limit: int) -> list[dict[str, Any]]:
    rows = rpc_call(rpc_url, "getSignaturesForAddress", [wallet, {"limit": int(limit), "commitment": "confirmed"}])
    return rows if isinstance(rows, list) else []


def transaction(rpc_url: str, signature: str) -> dict[str, Any] | None:
    return rpc_call(
        rpc_url,
        "getTransaction",
        [signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
    )


def has_swap_evidence(tx: dict[str, Any]) -> bool:
    meta = tx.get("meta") if isinstance(tx, dict) and isinstance(tx.get("meta"), dict) else {}
    logs = meta.get("logMessages") if isinstance(meta.get("logMessages"), list) else []
    joined = "\n".join(str(x or "").lower() for x in logs)
    return any(marker in joined for marker in SWAP_LOG_MARKERS)


def _raw_token_amount(balance: dict[str, Any]) -> tuple[int, int]:
    ui = balance.get("uiTokenAmount") if isinstance(balance.get("uiTokenAmount"), dict) else {}
    try:
        return int(ui.get("amount") or 0), int(ui.get("decimals") or 0)
    except (TypeError, ValueError):
        return 0, 0


def wallet_token_deltas(tx: dict[str, Any], wallet: str) -> dict[str, dict[str, Any]]:
    meta = tx.get("meta") if isinstance(tx.get("meta"), dict) else {}
    pre = meta.get("preTokenBalances") if isinstance(meta.get("preTokenBalances"), list) else []
    post = meta.get("postTokenBalances") if isinstance(meta.get("postTokenBalances"), list) else []
    by_mint: dict[str, dict[str, Any]] = {}

    def ingest(rows: list[dict[str, Any]], side: str) -> None:
        for row in rows:
            if not isinstance(row, dict) or str(row.get("owner") or "") != wallet:
                continue
            mint = str(row.get("mint") or "")
            if not mint:
                continue
            amount, decimals = _raw_token_amount(row)
            item = by_mint.setdefault(mint, {"pre": 0, "post": 0, "decimals": decimals})
            item[side] += amount
            item["decimals"] = decimals

    ingest(pre, "pre")
    ingest(post, "post")
    for mint, item in by_mint.items():
        item["delta_raw"] = int(item["post"]) - int(item["pre"])
        item["delta"] = item["delta_raw"] / (10 ** int(item["decimals"])) if int(item["decimals"]) >= 0 else 0.0
    return by_mint


def parse_wallet_buy(tx: dict[str, Any], wallet: str, ignored_mints: set[str] | None = None) -> dict[str, Any] | None:
    if not has_swap_evidence(tx):
        return None
    ignored = set(ignored_mints or DEFAULT_IGNORED_MINTS)
    deltas = wallet_token_deltas(tx, wallet)
    positives = [(mint, row) for mint, row in deltas.items() if int(row.get("delta_raw") or 0) > 0 and mint not in ignored]
    if not positives:
        return None
    positives.sort(key=lambda item: abs(float(item[1].get("delta") or 0.0)), reverse=True)
    mint, bought = positives[0]
    negatives = [(m, row) for m, row in deltas.items() if int(row.get("delta_raw") or 0) < 0]
    quote_mint = None
    quote_delta = None
    if negatives:
        negatives.sort(key=lambda item: abs(float(item[1].get("delta") or 0.0)), reverse=True)
        quote_mint, quote = negatives[0]
        quote_delta = float(quote.get("delta") or 0.0)
    return {
        "mint": mint,
        "token_delta": float(bought.get("delta") or 0.0),
        "quote_mint": quote_mint,
        "quote_delta": quote_delta,
    }


def base_symbol(pair: dict[str, Any]) -> str:
    token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
    return str(token.get("symbol") or "")


def exact_solana_market(rows: list[dict[str, Any]], mint: str, min_liquidity_usd: float) -> dict[str, Any] | None:
    exact: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("chainId") or "").lower() != "solana":
            continue
        base = row.get("baseToken") if isinstance(row.get("baseToken"), dict) else {}
        if str(base.get("address") or "") != mint:
            continue
        try:
            price = float(row.get("priceUsd") or 0)
            liquidity = float((row.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or liquidity <= 0:
            continue
        exact.append(row)
    if not exact:
        return None
    primary = max(exact, key=lambda x: float((x.get("liquidity") or {}).get("usd") or 0))
    liquidity = float((primary.get("liquidity") or {}).get("usd") or 0)
    price = float(primary.get("priceUsd") or 0)
    market_cap = primary.get("marketCap")
    fdv = primary.get("fdv")
    try:
        market_cap_value = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        market_cap_value = None
    try:
        fdv_value = float(fdv) if fdv is not None else None
    except (TypeError, ValueError):
        fdv_value = None
    cap = market_cap_value if market_cap_value and market_cap_value > 0 else fdv_value
    txns = primary.get("txns") if isinstance(primary.get("txns"), dict) else {}
    h1 = txns.get("h1") if isinstance(txns.get("h1"), dict) else {}
    return {
        "network": "solana",
        "contract": mint,
        "pair": str(primary.get("pairAddress") or ""),
        "dex_url": str(primary.get("url") or ""),
        "dex": str(primary.get("dexId") or ""),
        "symbol": str(base_symbol(primary) or "KOL"),
        "price_usd": price,
        "liquidity_usd": liquidity,
        "liquidity_pass": liquidity >= float(min_liquidity_usd),
        "market_cap_usd": cap,
        "market_cap_source": "marketCap" if market_cap_value and market_cap_value > 0 else "fdv" if fdv_value and fdv_value > 0 else None,
        "volume_h1_usd": float((primary.get("volume") or {}).get("h1") or 0),
        "volume_h24_usd": float((primary.get("volume") or {}).get("h24") or 0),
        "buys_h1": int(h1.get("buys") or 0),
        "sells_h1": int(h1.get("sells") or 0),
    }


def resolve_market(mint: str, min_liquidity_usd: float) -> dict[str, Any] | None:
    rows = http_json(DEXSCREENER_TOKEN.format(mint=mint), timeout=15)
    pairs = rows.get("pairs") if isinstance(rows, dict) else []
    return exact_solana_market(pairs if isinstance(pairs, list) else [], mint, min_liquidity_usd)


def parse_event_time(event: dict[str, Any]) -> datetime | None:
    block_time = event.get("block_time")
    if isinstance(block_time, (int, float)) and block_time > 0:
        return datetime.fromtimestamp(float(block_time), tz=timezone.utc)
    try:
        value = datetime.fromisoformat(str(event.get("observed_at") or "").replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def effective_groups(events: list[dict[str, Any]], wallet_meta: dict[str, dict[str, Any]]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    ids = sorted({str(e.get("wallet_id") or "") for e in events if e.get("wallet_id")})
    parent = {wid: wid for wid in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        if a not in parent or b not in parent:
            return
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    configured: dict[str, list[str]] = {}
    for wid in ids:
        group = str((wallet_meta.get(wid) or {}).get("independence_group") or wid)
        configured.setdefault(group, []).append(wid)
    for members in configured.values():
        for other in members[1:]:
            union(members[0], other)

    signature_wallets: dict[str, set[str]] = {}
    for event in events:
        sig = str(event.get("signature") or "")
        wid = str(event.get("wallet_id") or "")
        if sig and wid:
            signature_wallets.setdefault(sig, set()).add(wid)
    links = []
    for sig, members in signature_wallets.items():
        ordered = sorted(members)
        if len(ordered) < 2:
            continue
        for other in ordered[1:]:
            union(ordered[0], other)
        links.append({"reason": "SHARED_TRANSACTION_SIGNATURE", "signature": sig, "wallet_ids": ordered})

    roots: dict[str, list[str]] = {}
    for wid in ids:
        roots.setdefault(find(wid), []).append(wid)
    mapping: dict[str, str] = {}
    for members in roots.values():
        ordered = sorted(members)
        group_id = ordered[0] if len(ordered) == 1 else "AUTO_LINKED:" + "+".join(ordered)
        for wid in ordered:
            mapping[wid] = group_id
    return mapping, links


def convergence_for_mint(
    events: list[dict[str, Any]],
    mint: str,
    wallet_meta: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
    watch_market_cap_usd: float = 250_000.0,
    deep_market_cap_usd: float = 100_000.0,
    window_minutes: int = 60,
) -> dict[str, Any] | None:
    now = now or now_dt()
    relevant = []
    for event in events:
        if str(event.get("mint") or "") != mint or str(event.get("side") or "") != "BUY":
            continue
        dt = parse_event_time(event)
        if dt is None:
            continue
        age = (now - dt).total_seconds()
        if 0 <= age <= window_minutes * 60:
            relevant.append(event)
    if not relevant:
        return None
    relevant.sort(key=lambda e: parse_event_time(e) or datetime.min.replace(tzinfo=timezone.utc))
    group_map, links = effective_groups(relevant, wallet_meta)

    by_window: dict[str, int] = {}
    for minutes in (15, 30, 60):
        groups = set()
        for event in relevant:
            dt = parse_event_time(event)
            if dt and 0 <= (now - dt).total_seconds() <= minutes * 60:
                wid = str(event.get("wallet_id") or "")
                if wid:
                    groups.add(group_map.get(wid, wid))
        by_window[str(minutes)] = len(groups)

    early_groups: set[str] = set()
    watch_groups: set[str] = set()
    names: dict[str, set[str]] = {}
    for event in relevant:
        wid = str(event.get("wallet_id") or "")
        group = group_map.get(wid, wid)
        try:
            cap = float(event.get("entry_market_cap_usd"))
        except (TypeError, ValueError):
            cap = 0.0
        if cap > 0 and cap <= watch_market_cap_usd:
            watch_groups.add(group)
        if cap > 0 and cap <= deep_market_cap_usd:
            early_groups.add(group)
        names.setdefault(group, set()).add(str((wallet_meta.get(wid) or {}).get("name") or event.get("wallet_name") or wid))

    deep = len(early_groups) >= 3
    watch = len(watch_groups) >= 2
    if not watch and not deep:
        return None
    signal = "EARLY_KOL_DEEP_SCAN" if deep else "EARLY_KOL_CONVERGENCE_WATCH"
    latest = relevant[-1]
    return {
        "mint": mint,
        "signal_state": signal,
        "emergency_deep_scan": deep,
        "automatic_buy": False,
        "production_promotion_allowed": False,
        "requires_full_wallet500_gates": True,
        "independent_groups_15m": by_window["15"],
        "independent_groups_30m": by_window["30"],
        "independent_groups_60m": by_window["60"],
        "independent_groups_under_100k": len(early_groups),
        "independent_groups_under_250k": len(watch_groups),
        "wallet_ids": sorted({str(e.get("wallet_id") or "") for e in relevant if e.get("wallet_id")}),
        "wallet_names": sorted({name for group_names in names.values() for name in group_names}),
        "linked_wallet_evidence": links,
        "latest_event_at": (parse_event_time(latest) or now).isoformat(),
        "latest_signature": latest.get("signature"),
        "entry_market_caps_usd": [e.get("entry_market_cap_usd") for e in relevant],
        "event_count_60m": len(relevant),
        "independence_confidence": "PROVISIONAL_PUBLIC_ATTRIBUTION_WITH_SHARED_TX_DEDUPE",
    }


def state_template() -> dict[str, Any]:
    return {
        "version": 1,
        "mode": "FORWARD_ONLY_EXACT_MINT_RESEARCH",
        "updated_at": None,
        "wallet_boundaries": {},
        "events": [],
        "errors": [],
        "automatic_buy": False,
        "production_promotion_allowed": False,
    }


def main() -> int:
    config = load_json(CONFIG, {})
    state = load_json(STATE, state_template())
    if not isinstance(state, dict):
        state = state_template()
    wallets = [w for w in (config.get("wallets") or []) if isinstance(w, dict) and w.get("enabled", True)]
    wallet_meta = {str(w.get("id")): w for w in wallets if w.get("id")}
    boundaries = state.setdefault("wallet_boundaries", {})
    events = [e for e in state.get("events") or [] if isinstance(e, dict)]
    seen = {str(e.get("event_id") or "") for e in events}
    errors = []
    rpc_url = os.environ.get("SOLANA_RPC_URL", "").strip() or str(config.get("rpc_url") or DEFAULT_RPC)
    signature_limit = int(config.get("signature_limit_per_wallet") or 12)
    tx_limit = int(config.get("max_new_transactions_per_wallet") or 6)
    min_liquidity = float(config.get("minimum_pair_liquidity_usd") or 5000)
    ignored = set(DEFAULT_IGNORED_MINTS) | {str(x) for x in (config.get("ignored_mints") or []) if x}
    market_cache: dict[str, dict[str, Any] | None] = {}
    new_events = 0
    initialized = 0

    for wallet in wallets:
        wid = str(wallet.get("id") or "")
        address = str(wallet.get("address") or "")
        if not wid or not address:
            continue
        try:
            sigs = recent_signatures(rpc_url, address, signature_limit)
        except Exception as exc:
            errors.append({"wallet_id": wid, "stage": "SIGNATURES", "error": f"{type(exc).__name__}:{exc}"[:300]})
            continue
        boundary = str(boundaries.get(wid) or "")
        if not boundary:
            if sigs:
                boundaries[wid] = str(sigs[0].get("signature") or "")
                initialized += 1
            continue
        fresh = []
        for row in sigs:
            sig = str(row.get("signature") or "")
            if sig == boundary:
                break
            if sig:
                fresh.append(row)
        fresh = list(reversed(fresh[-tx_limit:]))
        for row in fresh:
            sig = str(row.get("signature") or "")
            if not sig:
                continue
            try:
                tx = transaction(rpc_url, sig)
                parsed = parse_wallet_buy(tx or {}, address, ignored)
                if not parsed:
                    continue
                mint = str(parsed["mint"])
                eid = f"{wid}:{sig}:{mint}:BUY"
                if eid in seen:
                    continue
                if mint not in market_cache:
                    try:
                        market_cache[mint] = resolve_market(mint, min_liquidity)
                    except Exception as exc:
                        market_cache[mint] = None
                        errors.append({"wallet_id": wid, "stage": "MARKET", "mint": mint, "error": f"{type(exc).__name__}:{exc}"[:300]})
                market = market_cache.get(mint)
                if not market or not market.get("pair"):
                    continue
                event = {
                    "event_id": eid,
                    "wallet_id": wid,
                    "wallet_name": wallet.get("name"),
                    "wallet_address": address,
                    "attribution_status": wallet.get("attribution_status"),
                    "signature": sig,
                    "block_time": (tx or {}).get("blockTime") or row.get("blockTime"),
                    "observed_at": now_iso(),
                    "side": "BUY",
                    "mint": mint,
                    "token_delta": parsed.get("token_delta"),
                    "quote_mint": parsed.get("quote_mint"),
                    "quote_delta": parsed.get("quote_delta"),
                    "entry_market_cap_usd": market.get("market_cap_usd"),
                    "entry_market_cap_source": market.get("market_cap_source"),
                    "entry_price_usd": market.get("price_usd"),
                    "entry_liquidity_usd": market.get("liquidity_usd"),
                    "pair": market.get("pair"),
                    "dex_url": market.get("dex_url"),
                    "symbol": market.get("symbol"),
                }
                events.append(event)
                seen.add(eid)
                new_events += 1
            except Exception as exc:
                errors.append({"wallet_id": wid, "stage": "TRANSACTION", "signature": sig, "error": f"{type(exc).__name__}:{exc}"[:300]})
        if sigs:
            boundaries[wid] = str(sigs[0].get("signature") or boundary)
        time.sleep(float(config.get("wallet_delay_seconds") or 0.03))

    retention_hours = float(config.get("event_retention_hours") or 24)
    cutoff = now_dt().timestamp() - retention_hours * 3600
    retained = []
    for event in events:
        dt = parse_event_time(event)
        if dt and dt.timestamp() >= cutoff:
            retained.append(event)
    events = retained[-2000:]

    mints = sorted({str(e.get("mint") or "") for e in events if e.get("mint")})
    convergences = []
    candidate_rows = []
    for mint in mints:
        convergence = convergence_for_mint(
            events,
            mint,
            wallet_meta,
            watch_market_cap_usd=float(config.get("watch_market_cap_usd") or 250000),
            deep_market_cap_usd=float(config.get("deep_scan_market_cap_usd") or 100000),
            window_minutes=int(config.get("convergence_window_minutes") or 60),
        )
        if not convergence:
            continue
        market = market_cache.get(mint)
        if market is None:
            try:
                market = resolve_market(mint, min_liquidity)
            except Exception as exc:
                market = None
                errors.append({"stage": "CONVERGENCE_MARKET", "mint": mint, "error": f"{type(exc).__name__}:{exc}"[:300]})
        if not market or not market.get("liquidity_pass"):
            convergence["market"] = market
            convergence["candidate_eligible"] = False
            convergence["blocked_reason"] = "MINIMUM_EXACT_PAIR_LIQUIDITY_NOT_VERIFIED"
            convergences.append(convergence)
            continue
        convergence["market"] = market
        convergence["candidate_eligible"] = True
        convergences.append(convergence)
        deep = bool(convergence.get("emergency_deep_scan"))
        signal_id = f"{mint}:{convergence.get('signal_state')}:{convergence.get('latest_signature') or convergence.get('latest_event_at')}"
        candidate_rows.append({
            "status": "GATED_RESEARCH_CANDIDATE",
            "candidate_type": "EARLY_KOL_CONVERGENCE",
            "signal_event_id": signal_id,
            "symbol": market.get("symbol") or "KOL",
            "network": "solana",
            "contract": mint,
            "pair": market.get("pair"),
            "dex_url": market.get("dex_url") or "",
            "source": "Wallet500 Early KOL Convergence",
            "first_seen_at": convergence.get("latest_event_at"),
            "observed_at": now_iso(),
            "price_usd": market.get("price_usd"),
            "market_cap_usd": market.get("market_cap_usd"),
            "liquidity_usd": market.get("liquidity_usd"),
            "independent_groups_15m": convergence.get("independent_groups_15m"),
            "independent_groups_30m": convergence.get("independent_groups_30m"),
            "independent_groups_60m": convergence.get("independent_groups_60m"),
            "independent_groups_under_100k": convergence.get("independent_groups_under_100k"),
            "wallet_names": convergence.get("wallet_names"),
            "signal_state": convergence.get("signal_state"),
            "emergency_deep_scan": deep,
            "deep_investigation": deep,
            "full_intelligence": deep,
            "priority": "HIGHEST" if deep else "HIGH",
            "research_only": True,
            "automatic_buy": False,
            "production_promotion_allowed": False,
            "requires_full_wallet500_gates": True,
            "exact_mint_required": True,
            "exact_pair_required": True,
            "attribution_semantics": "PUBLIC_THIRD_PARTY_ATTRIBUTION_NOT_OWNER_VERIFIED",
        })

    state.update({
        "version": 1,
        "mode": "FORWARD_ONLY_EXACT_MINT_RESEARCH",
        "updated_at": now_iso(),
        "wallet_boundaries": boundaries,
        "events": events,
        "errors": errors[-100:],
        "automatic_buy": False,
        "production_promotion_allowed": False,
    })
    report = {
        "version": 1,
        "generated_at": now_iso(),
        "mode": "EARLY_KOL_CONVERGENCE_FORWARD_ONLY",
        "wallets_configured": len(wallets),
        "wallets_initialized_this_run": initialized,
        "new_buy_events": new_events,
        "retained_buy_events": len(events),
        "active_convergences": len(convergences),
        "deep_scan_now": sum(bool(x.get("emergency_deep_scan")) for x in convergences),
        "candidate_count": len(candidate_rows),
        "errors": len(errors),
        "convergences": convergences,
        "truth_contract": {
            "forward_only": True,
            "exact_mint_only": True,
            "swap_log_required": True,
            "third_party_attribution_explicit": True,
            "three_independent_under_100k_triggers_deep_scan": True,
            "automatic_buy": False,
            "production_promotion_allowed": False,
        },
    }
    candidates = {
        "version": 1,
        "generated_at": now_iso(),
        "candidate_type": "EARLY_KOL_CONVERGENCE",
        "candidates": candidate_rows,
    }
    write_json(STATE, state)
    write_json(REPORT, report)
    write_json(CANDIDATES, candidates)
    print(json.dumps({
        "status": "OK",
        "wallets": len(wallets),
        "initialized": initialized,
        "new_buy_events": new_events,
        "active_convergences": len(convergences),
        "deep_scan_now": report["deep_scan_now"],
        "candidates": len(candidate_rows),
        "errors": len(errors),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
