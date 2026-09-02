from __future__ import annotations

import json
import os
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .cryptoyeezus_copy import parse_wallet_swap

DATA = Path("data")
CONFIG_PATH = Path("experiments/kol-revival-convergence-v1.json")
LEDGER_PATH = DATA / "kol-revival-convergence-ledger.json"
SUMMARY_PATH = DATA / "kol-revival-convergence-summary.json"
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _http_json(url: str, *, method: str = "GET", payload: Any = None, timeout: int = 20) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "Wallet500-KOLRevivalConvergence/1.0", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _rpc(rpc_url: str, method: str, params: list[Any]) -> Any:
    out = _http_json(rpc_url, method="POST", payload={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=25)
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(f"RPC {method}: {out['error']}")
    return out.get("result") if isinstance(out, dict) else None


def _recent_signatures(rpc_url: str, wallet: str, limit: int) -> list[dict[str, Any]]:
    rows = _rpc(rpc_url, "getSignaturesForAddress", [wallet, {"limit": int(limit), "commitment": "confirmed"}])
    return rows if isinstance(rows, list) else []


def _tx_for_signature(rpc_url: str, signature: str) -> dict[str, Any] | None:
    return _rpc(rpc_url, "getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])


def verified_swap_evidence(tx: dict[str, Any]) -> str | None:
    """Require explicit swap/route evidence in transaction logs; fail closed otherwise."""
    meta = tx.get("meta") if isinstance(tx, dict) and isinstance(tx.get("meta"), dict) else {}
    logs = meta.get("logMessages") if isinstance(meta.get("logMessages"), list) else []
    patterns = (
        "instruction: swap",
        "instruction: route",
        "instruction: sharedaccountsroute",
        "instruction: exactoutroute",
        "swapbaseinput",
        "swapbaseoutput",
    )
    for raw in logs:
        low = str(raw or "").lower()
        for pat in patterns:
            if pat in low:
                return pat.upper()
    return None


def _pair_created_ms(pair: dict[str, Any]) -> int | None:
    raw = pair.get("pairCreatedAt")
    try:
        val = int(float(raw))
    except Exception:
        return None
    # DexScreener uses milliseconds; tolerate seconds defensively.
    return val * 1000 if val < 10_000_000_000 else val


def verify_exact_mint_market(
    pairs: list[dict[str, Any]],
    mint: str,
    *,
    now_ms: int | None = None,
    min_age_days: float = 180.0,
    liquidity_floor_usd: float = 50_000.0,
) -> dict[str, Any]:
    """Pure exact-mint market verifier used by runtime and tests."""
    exact = []
    for p in pairs if isinstance(pairs, list) else []:
        if not isinstance(p, dict) or str(p.get("chainId") or "").lower() != "solana":
            continue
        base = p.get("baseToken") if isinstance(p.get("baseToken"), dict) else {}
        quote = p.get("quoteToken") if isinstance(p.get("quoteToken"), dict) else {}
        if mint not in {str(base.get("address") or ""), str(quote.get("address") or "")}:
            continue
        exact.append(p)
    if not exact:
        return {
            "exact_mint_verified": False,
            "market_age_verified": False,
            "liquidity_pass": False,
            "reason": "NO_EXACT_MINT_PAIR",
        }

    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    created = [x for x in (_pair_created_ms(p) for p in exact) if x and x <= now_ms]
    if not created:
        age_days = None
        age_ok = False
    else:
        age_days = (now_ms - min(created)) / 86_400_000.0
        age_ok = age_days >= float(min_age_days)

    def liq(p: dict[str, Any]) -> float:
        x = p.get("liquidity") if isinstance(p.get("liquidity"), dict) else {}
        try:
            return float(x.get("usd") or 0)
        except Exception:
            return 0.0

    primary = max(exact, key=liq)
    liquidity = liq(primary)
    try:
        price = float(primary.get("priceUsd") or 0)
    except Exception:
        price = 0.0
    pair_address = str(primary.get("pairAddress") or "")
    url = str(primary.get("url") or "")
    return {
        "exact_mint_verified": True,
        "market_age_verified": bool(age_ok),
        "market_age_min_days": round(age_days, 3) if age_days is not None else None,
        "market_age_evidence_source": "DEXSCREENER_OLDEST_CURRENT_EXACT_MINT_PAIR",
        "oldest_pair_created_at_ms": min(created) if created else None,
        "pair_address": pair_address,
        "pair_url": url,
        "dex": str(primary.get("dexId") or ""),
        "price_usd": price,
        "liquidity_usd": round(liquidity, 6),
        "liquidity_pass": liquidity >= float(liquidity_floor_usd),
        "reason": "VERIFIED" if age_ok else "MARKET_AGE_UNDER_180_OR_UNKNOWN",
    }


def resolve_market(mint: str, config: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.dexscreener.com/token-pairs/v1/solana/{mint}"
    rows = _http_json(url, timeout=20)
    return verify_exact_mint_market(
        rows if isinstance(rows, list) else [],
        mint,
        min_age_days=float(config.get("minimum_market_age_days") or 180),
        liquidity_floor_usd=float(config.get("hard_liquidity_floor_usd") or 50_000),
    )


def _event_dt(event: dict[str, Any]) -> datetime | None:
    bt = event.get("block_time")
    if isinstance(bt, (int, float)) and bt > 0:
        try:
            return datetime.fromtimestamp(float(bt), tz=timezone.utc)
        except Exception:
            pass
    raw = event.get("observed_at")
    try:
        d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _wallet_meta(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(x.get("id")): x for x in config.get("wallets") or [] if isinstance(x, dict) and x.get("id")}


def convergence_for_mint(
    events: list[dict[str, Any]],
    mint: str,
    config: dict[str, Any],
    market: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    rows = [x for x in events if isinstance(x, dict) and x.get("side") == "BUY" and str(x.get("mint")) == mint and _event_dt(x)]
    if not rows:
        return None
    rows.sort(key=lambda x: _event_dt(x) or datetime.min.replace(tzinfo=timezone.utc))
    last_t = _event_dt(rows[-1])
    if not last_t:
        return None
    meta = _wallet_meta(config)
    windows = sorted({int(x) for x in (config.get("convergence_windows_minutes") or [15, 30]) if int(x) > 0})
    counts: dict[str, int] = {}
    wallet_counts: dict[str, int] = {}
    groups_at_max: set[str] = set()
    wallets_at_max: set[str] = set()
    max_window = max(windows or [30])
    max_rows = []
    for row in rows:
        dt = _event_dt(row)
        if dt and 0 <= (last_t - dt).total_seconds() <= max_window * 60:
            max_rows.append(row)
    for row in max_rows:
        wid = str(row.get("wallet_id") or "")
        wallet_counts[wid] = wallet_counts.get(wid, 0) + 1
        wallets_at_max.add(wid)
        group = str((meta.get(wid) or {}).get("independence_group") or row.get("independence_group") or wid)
        if group:
            groups_at_max.add(group)
    for w in windows:
        groups = set()
        for row in rows:
            dt = _event_dt(row)
            if not dt or not (0 <= (last_t - dt).total_seconds() <= w * 60):
                continue
            wid = str(row.get("wallet_id") or "")
            group = str((meta.get(wid) or {}).get("independence_group") or row.get("independence_group") or wid)
            if group:
                groups.add(group)
        counts[str(w)] = len(groups)
    independent = max(counts.values(), default=0)
    thresholds = sorted(int(x) for x in (config.get("thresholds") or [2, 3, 4, 5]))
    reached = [x for x in thresholds if independent >= x]
    if not reached:
        return None
    level = max(reached)
    if level >= 5:
        signal = "KOL_REVIVAL_CONVERGENCE_EXCEPTIONAL"
    elif level >= 4:
        signal = "KOL_REVIVAL_CONVERGENCE_HIGH"
    elif level >= 3:
        signal = "KOL_REVIVAL_CONVERGENCE_STRONG"
    else:
        signal = "KOL_REVIVAL_CONVERGENCE_WATCH"
    if not market.get("market_age_verified"):
        signal = "AGE_BLOCKED"
    elif not market.get("liquidity_pass"):
        signal = "LIQUIDITY_BLOCKED"
    now = now or _now_dt()
    age_seconds = max(0.0, (now - last_t).total_seconds())
    names = [str((meta.get(w) or {}).get("name") or w) for w in sorted(wallets_at_max)]
    return {
        "mint": mint,
        "last_buy_at": last_t.isoformat(),
        "last_buy_age_seconds": round(age_seconds, 3),
        "independent_wallet_groups": independent,
        "independent_count_by_window": counts,
        "wallets": sorted(wallets_at_max),
        "wallet_names": names,
        "independence_groups": sorted(groups_at_max),
        "repeat_accumulators": sorted(w for w, c in wallet_counts.items() if c >= 2),
        "repeat_accumulator_count": sum(1 for c in wallet_counts.values() if c >= 2),
        "threshold_level": level,
        "signal_state": signal,
        "eligible_research_watch": bool(market.get("market_age_verified") and market.get("liquidity_pass")),
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "social_lag_state": "NOT_YET_MEASURED_FAIL_NEUTRAL",
        "market": market,
    }


def _threshold_cross_signature(events: list[dict[str, Any]], mint: str, config: dict[str, Any], threshold: int) -> str | None:
    rows = [x for x in events if x.get("side") == "BUY" and str(x.get("mint")) == mint and _event_dt(x)]
    rows.sort(key=lambda x: _event_dt(x) or datetime.min.replace(tzinfo=timezone.utc))
    meta = _wallet_meta(config)
    max_window = max(int(x) for x in (config.get("convergence_windows_minutes") or [30]))
    for i, row in enumerate(rows):
        end = _event_dt(row)
        if not end:
            continue
        groups = set()
        for prior in rows[: i + 1]:
            dt = _event_dt(prior)
            if not dt or not (0 <= (end - dt).total_seconds() <= max_window * 60):
                continue
            wid = str(prior.get("wallet_id") or "")
            groups.add(str((meta.get(wid) or {}).get("independence_group") or prior.get("independence_group") or wid))
        if len({x for x in groups if x}) >= threshold:
            return str(row.get("signature") or "") or None
    return None


def _relative_size(event: dict[str, Any], prior_events: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        raw = int(event.get("quote_amount_raw") or 0)
        decimals = int(event.get("quote_decimals") or 0)
        amount = raw / (10 ** decimals)
    except Exception:
        return {"quote_amount": None, "size_vs_wallet_median": None, "size_signal": "UNKNOWN"}
    same = []
    for x in prior_events:
        if x.get("wallet_id") != event.get("wallet_id") or x.get("quote_mint") != event.get("quote_mint"):
            continue
        try:
            same.append(int(x.get("quote_amount_raw") or 0) / (10 ** int(x.get("quote_decimals") or 0)))
        except Exception:
            continue
    same = [x for x in same if x > 0]
    if len(same) < 3:
        return {"quote_amount": round(amount, 9), "size_vs_wallet_median": None, "size_signal": "INSUFFICIENT_HISTORY"}
    med = statistics.median(same)
    ratio = amount / med if med > 0 else None
    return {
        "quote_amount": round(amount, 9),
        "size_vs_wallet_median": round(ratio, 4) if ratio is not None else None,
        "size_signal": "LARGE_RELATIVE_BUY" if ratio is not None and ratio >= 2 else "NORMAL_RELATIVE_BUY",
    }


def _new_state(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "KOL_REVIVAL_CONVERGENCE_V1",
        "mode": "FORWARD_ONLY_WALLET_FIRST_RESEARCH",
        "created_at": _now(),
        "wallet_boundaries": {},
        "events": [],
        "threshold_records": [],
        "errors": [],
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "truth_contract": config.get("truth_contract") or {},
    }


def _mark_threshold_records(records: list[dict[str, Any]], markets: dict[str, dict[str, Any]]) -> None:
    now = _now()
    for rec in records:
        market = markets.get(str(rec.get("mint") or ""))
        if not market or not market.get("exact_mint_verified"):
            continue
        price = float(market.get("price_usd") or 0)
        entry = float(rec.get("entry_price_usd") or 0)
        ret = (price / entry - 1) * 100 if price > 0 and entry > 0 else None
        rec["last_mark_at"] = now
        rec["current_price_usd"] = price
        rec["current_liquidity_usd"] = market.get("liquidity_usd")
        rec["current_return_pct"] = round(ret, 6) if ret is not None else None
        if ret is not None:
            rec["peak_return_pct"] = round(max(float(rec.get("peak_return_pct") if rec.get("peak_return_pct") is not None else ret), ret), 6)
            rec["max_drawdown_pct"] = round(min(float(rec.get("max_drawdown_pct") if rec.get("max_drawdown_pct") is not None else ret), ret), 6)
            rec["ever_2x"] = bool(rec.get("ever_2x")) or ret >= 100
            rec["ever_3x"] = bool(rec.get("ever_3x")) or ret >= 200


def _threshold_stats(records: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
    rows = [x for x in records if int(x.get("threshold") or 0) == threshold]
    rets = [float(x["current_return_pct"]) for x in rows if x.get("current_return_pct") is not None]
    return {
        "records": len(rows),
        "measured": len(rets),
        "median_current_return_pct": round(statistics.median(rets), 6) if rets else None,
        "positive_rate_pct": round(100 * sum(1 for x in rets if x > 0) / len(rets), 3) if rets else None,
        "ever_2x_rate_pct": round(100 * sum(1 for x in rows if x.get("ever_2x")) / len(rows), 3) if rows else None,
    }


def run_once(*, market_resolver: Callable[[str, dict[str, Any]], dict[str, Any]] = resolve_market) -> dict[str, Any]:
    DATA.mkdir(parents=True, exist_ok=True)
    config = _load(CONFIG_PATH, {})
    state = _load(LEDGER_PATH, {})
    if not isinstance(state, dict) or not state:
        state = _new_state(config)
    state["truth_contract"] = config.get("truth_contract") or {}
    state["production_portfolio_impact"] = "NONE"
    state["automatic_buy"] = False
    errors: list[dict[str, Any]] = []
    rpc_url = os.getenv("SOLANA_RPC_URL", "").strip() or DEFAULT_RPC
    signature_batch = int(config.get("signature_batch") or 35)
    events = state.setdefault("events", [])
    seen = {str(x.get("event_id") or "") for x in events if isinstance(x, dict)}
    boundaries = state.setdefault("wallet_boundaries", {})

    for wallet in config.get("wallets") or []:
        wid = str(wallet.get("id") or "")
        address = str(wallet.get("address") or "")
        if not wid or not address:
            continue
        try:
            signatures = _recent_signatures(rpc_url, address, signature_batch)
        except Exception as exc:
            errors.append({"wallet_id": wid, "stage": "SIGNATURES", "error": f"{type(exc).__name__}: {exc}"[:400]})
            continue
        boundary = str(boundaries.get(wid) or "")
        # Hard prospective boundary: the first successful observation never books history.
        if not boundary:
            if signatures:
                boundaries[wid] = str(signatures[0].get("signature") or "")
            continue
        new_rows = []
        for row in signatures:
            sig = str(row.get("signature") or "")
            if sig == boundary:
                break
            new_rows.append(row)
        for row in reversed(new_rows):
            sig = str(row.get("signature") or "")
            if not sig:
                continue
            try:
                tx = _tx_for_signature(rpc_url, sig)
                evidence = verified_swap_evidence(tx or {})
                if not evidence:
                    continue
                parsed = parse_wallet_swap(tx or {}, address)
                if not parsed or parsed.get("side") != "BUY":
                    continue
                mint = str(parsed.get("output_mint") or "")
                eid = f"{wid}:{sig}:BUY:{mint}"
                if not mint or eid in seen:
                    continue
                event = {
                    "event_id": eid,
                    "wallet_id": wid,
                    "wallet_name": wallet.get("name"),
                    "wallet_address": address,
                    "independence_group": wallet.get("independence_group") or wid,
                    "signature": sig,
                    "slot": row.get("slot"),
                    "block_time": (tx or {}).get("blockTime") or row.get("blockTime"),
                    "observed_at": _now(),
                    "side": "BUY",
                    "mint": mint,
                    "quote_mint": parsed.get("input_mint"),
                    "quote_amount_raw": parsed.get("input_amount_raw"),
                    "quote_decimals": parsed.get("input_decimals"),
                    "token_amount_raw": parsed.get("output_amount_raw"),
                    "token_decimals": parsed.get("output_decimals"),
                    "swap_evidence": evidence,
                    "native_notional_is_estimate": parsed.get("native_notional_is_estimate"),
                }
                event.update(_relative_size(event, events))
                events.append(event)
                seen.add(eid)
            except Exception as exc:
                errors.append({"wallet_id": wid, "signature": sig, "stage": "PARSE_SWAP", "error": f"{type(exc).__name__}: {exc}"[:400]})
        if signatures:
            boundaries[wid] = str(signatures[0].get("signature") or boundary)

    if len(events) > 20000:
        del events[:-20000]

    active_minutes = int(config.get("active_window_minutes") or 45)
    now_dt = _now_dt()
    relevant_mints = set()
    for e in events:
        dt = _event_dt(e)
        if dt and 0 <= (now_dt - dt).total_seconds() <= active_minutes * 60:
            relevant_mints.add(str(e.get("mint") or ""))
    for rec in state.get("threshold_records") or []:
        if rec.get("mint"):
            relevant_mints.add(str(rec["mint"]))

    markets: dict[str, dict[str, Any]] = {}
    for mint in sorted(x for x in relevant_mints if x):
        try:
            markets[mint] = market_resolver(mint, config)
        except Exception as exc:
            markets[mint] = {"exact_mint_verified": False, "market_age_verified": False, "liquidity_pass": False, "reason": "MARKET_RESOLUTION_ERROR"}
            errors.append({"mint": mint, "stage": "MARKET", "error": f"{type(exc).__name__}: {exc}"[:400]})

    active = []
    for mint in sorted(relevant_mints):
        conv = convergence_for_mint(events, mint, config, markets.get(mint, {}), now=now_dt)
        if conv and conv.get("last_buy_age_seconds", 10**12) <= active_minutes * 60:
            active.append(conv)
    active.sort(key=lambda x: (int(x.get("threshold_level") or 0), int(x.get("repeat_accumulator_count") or 0), -float(x.get("last_buy_age_seconds") or 0)), reverse=True)

    records = state.setdefault("threshold_records", [])
    record_keys = {str(x.get("record_key") or "") for x in records}
    for conv in active:
        mint = str(conv["mint"])
        market = markets.get(mint, {})
        if not market.get("market_age_verified"):
            continue
        for threshold in sorted(int(x) for x in (config.get("thresholds") or [2, 3, 4, 5])):
            if int(conv.get("independent_wallet_groups") or 0) < threshold:
                continue
            sig = _threshold_cross_signature(events, mint, config, threshold)
            if not sig:
                continue
            key = f"{mint}:{threshold}:{sig}"
            if key in record_keys:
                continue
            records.append({
                "record_key": key,
                "mint": mint,
                "threshold": threshold,
                "threshold_cross_signature": sig,
                "first_observed_at": _now(),
                "entry_pair_address": market.get("pair_address"),
                "entry_price_usd": market.get("price_usd"),
                "entry_liquidity_usd": market.get("liquidity_usd"),
                "market_age_min_days": market.get("market_age_min_days"),
                "market_age_verified": True,
                "liquidity_pass_at_entry": bool(market.get("liquidity_pass")),
                "production_portfolio_impact": "NONE",
                "automatic_buy": False,
                "current_return_pct": 0.0 if float(market.get("price_usd") or 0) > 0 else None,
                "peak_return_pct": 0.0 if float(market.get("price_usd") or 0) > 0 else None,
                "max_drawdown_pct": 0.0 if float(market.get("price_usd") or 0) > 0 else None,
                "ever_2x": False,
                "ever_3x": False,
            })
            record_keys.add(key)

    _mark_threshold_records(records, markets)
    state["updated_at"] = _now()
    state.setdefault("errors", []).extend(errors)
    state["errors"] = state["errors"][-100:]
    summary = {
        "version": "KOL_REVIVAL_CONVERGENCE_V1",
        "mode": "FORWARD_ONLY_WALLET_FIRST_RESEARCH",
        "updated_at": state["updated_at"],
        "wallets_configured": len(config.get("wallets") or []),
        "forward_buy_events": len(events),
        "active_convergences": len(active),
        "active_eligible_research_watch": sum(1 for x in active if x.get("eligible_research_watch")),
        "strong_or_higher_now": sum(1 for x in active if int(x.get("threshold_level") or 0) >= 3 and x.get("eligible_research_watch")),
        "active": active[:30],
        "threshold_performance": {str(t): _threshold_stats(records, int(t)) for t in (config.get("thresholds") or [2, 3, 4, 5])},
        "truth_contract": config.get("truth_contract") or {},
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "status": "ACTIVE_FORWARD" if boundaries else "WAITING_FORWARD_BOUNDARY",
        "errors": errors[-20:],
    }
    _write(LEDGER_PATH, state)
    _write(SUMMARY_PATH, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run_once(), ensure_ascii=False, indent=2))
