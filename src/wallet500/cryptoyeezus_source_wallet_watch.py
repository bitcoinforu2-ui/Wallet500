from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_WALLET = "JCxTzSXz1f8s3UEtYQzaDdBDWneaD6yo1cX38RBf6Rjd"
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD8sC4rVJ1tEP4MZfV2F6Ys"
COUNTERS = {WSOL: "SOL", USDC: "USDC", USDT: "USDT"}
DATA = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
STATE_PATH = DATA / "cryptoyeezus-source-wallet-state.json"
LATEST_PATH = DATA / "cryptoyeezus-source-wallet-latest.json"
EVENTS_PATH = DATA / "cryptoyeezus-source-wallet-events.json"
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://solana-rpc.publicnode.com")
MAX_SIGNATURES = int(os.getenv("YEEZUS_SOURCE_WALLET_MAX_SIGNATURES", "120"))
DEX_PROGRAM_HINTS = (
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzG2ZbLpD9dK",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rpc(method: str, params: list[Any], attempts: int = 4) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC_URL, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Wallet500-CryptoYeezus-SourceWallet/1.0"}, method="POST")
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode())
            if body.get("error"):
                raise RuntimeError(str(body["error"]))
            return body.get("result")
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"RPC_{method}_FAILED:{type(last).__name__}:{last}")


def _amount(row: dict) -> float:
    ui = (row or {}).get("uiTokenAmount") or {}
    try:
        return int(ui.get("amount") or 0) / (10 ** int(ui.get("decimals") or 0))
    except Exception:
        try:
            return float(ui.get("uiAmountString") or ui.get("uiAmount") or 0)
        except Exception:
            return 0.0


def _account_keys(tx: dict) -> list[str]:
    try:
        rows = tx["transaction"]["message"]["accountKeys"] or []
    except Exception:
        return []
    out = []
    for row in rows:
        if isinstance(row, dict):
            value = row.get("pubkey")
        else:
            value = row
        if value:
            out.append(str(value))
    return out


def _wallet_is_signer(tx: dict) -> bool:
    try:
        rows = tx["transaction"]["message"]["accountKeys"] or []
    except Exception:
        return False
    for row in rows:
        if isinstance(row, dict) and str(row.get("pubkey") or "") == SOURCE_WALLET and row.get("signer") is True:
            return True
    return False


def _token_deltas(tx: dict) -> dict[str, float]:
    meta = tx.get("meta") or {}
    pre: dict[str, float] = {}
    post: dict[str, float] = {}
    for row in meta.get("preTokenBalances") or []:
        if str(row.get("owner") or "") == SOURCE_WALLET and row.get("mint"):
            pre[str(row["mint"])] = pre.get(str(row["mint"]), 0.0) + _amount(row)
    for row in meta.get("postTokenBalances") or []:
        if str(row.get("owner") or "") == SOURCE_WALLET and row.get("mint"):
            post[str(row["mint"])] = post.get(str(row["mint"]), 0.0) + _amount(row)
    return {mint: post.get(mint, 0.0) - pre.get(mint, 0.0) for mint in set(pre) | set(post)}


def _native_sol_delta(tx: dict) -> float | None:
    keys = _account_keys(tx)
    try:
        idx = keys.index(SOURCE_WALLET)
        pre = int((tx.get("meta") or {}).get("preBalances")[idx])
        post = int((tx.get("meta") or {}).get("postBalances")[idx])
    except Exception:
        return None
    delta = (post - pre) / 1_000_000_000
    if idx == 0:
        try:
            delta += int((tx.get("meta") or {}).get("fee") or 0) / 1_000_000_000
        except Exception:
            pass
    return delta


def _has_swap_evidence(tx: dict) -> bool:
    logs = "\n".join(str(x) for x in ((tx.get("meta") or {}).get("logMessages") or []))
    if "swap" in logs.lower():
        return True
    accounts = set(_account_keys(tx))
    return any(program in accounts for program in DEX_PROGRAM_HINTS)


def classify_verified_swap(tx: dict, signature: str, block_time: int | None) -> dict | None:
    """Conservatively classify only signed, two-sided DEX swap balance changes."""
    if not isinstance(tx, dict) or (tx.get("meta") or {}).get("err") is not None:
        return None
    if not _wallet_is_signer(tx) or not _has_swap_evidence(tx):
        return None
    deltas = {k: v for k, v in _token_deltas(tx).items() if abs(v) > 1e-10}
    non_counter = [(mint, delta) for mint, delta in deltas.items() if mint not in COUNTERS]
    if len(non_counter) != 1:
        return None
    mint, target_delta = non_counter[0]

    counter_candidates: list[tuple[str, float]] = [(COUNTERS[m], d) for m, d in deltas.items() if m in COUNTERS and abs(d) > 1e-10]
    native = _native_sol_delta(tx)
    if native is not None and abs(native) > 1e-7:
        counter_candidates.append(("SOL", native))
    if not counter_candidates:
        return None
    counter_asset, counter_delta = max(counter_candidates, key=lambda x: abs(x[1]))

    if target_delta > 0 and counter_delta < 0:
        side = "BUY"
    elif target_delta < 0 and counter_delta > 0:
        side = "SELL"
    else:
        return None

    when = datetime.fromtimestamp(int(block_time), tz=timezone.utc).isoformat() if block_time else None
    notional_amount = abs(float(counter_delta))
    usd = notional_amount if counter_asset in {"USDC", "USDT"} else None
    return {
        "event_type": f"SOURCE_WALLET_{side}",
        "side": side,
        "wallet": SOURCE_WALLET,
        "signature": signature,
        "block_time": int(block_time or tx.get("blockTime") or 0) or None,
        "observed_chain_time": when,
        "token_mint": mint,
        "token_delta": round(float(target_delta), 12),
        "source_notional": {"asset": counter_asset, "amount": round(notional_amount, 9), "usd": usd},
        "copy_1pct_notional": {"asset": counter_asset, "amount": round(notional_amount * 0.01, 9), "usd": round(usd * 0.01, 6) if usd is not None else None},
        "verification": "SIGNED_WALLET_TWO_SIDED_BALANCE_DELTA_PLUS_DEX_SWAP_EVIDENCE",
        "simulation_only": True,
        "real_trade_claimed": False,
    }


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Wallet500-CryptoYeezus-SourceWallet/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.loads(r.read().decode())
    return body if isinstance(body, dict) else {}


def exact_pair_snapshot(mint: str, tx_accounts: list[str]) -> tuple[dict | None, list[str]]:
    flags: list[str] = []
    try:
        payload = _get_json("https://api.dexscreener.com/latest/dex/tokens/" + urllib.parse.quote(mint))
    except Exception as exc:
        return None, [f"DEXSCREENER_LOOKUP_FAILED:{type(exc).__name__}"]
    accounts = set(tx_accounts)
    matches = []
    for pair in payload.get("pairs") or []:
        if str((pair.get("baseToken") or {}).get("address") or "") != mint:
            continue
        pair_address = str(pair.get("pairAddress") or "")
        if pair_address and pair_address in accounts:
            liq = float((pair.get("liquidity") or {}).get("usd") or 0)
            matches.append((liq, pair))
    if not matches:
        return None, ["NO_DEXSCREENER_PAIR_INTERSECTS_TX_ACCOUNTS"]
    matches.sort(key=lambda x: x[0], reverse=True)
    if len(matches) > 1:
        flags.append("MULTIPLE_TX_PAIR_MATCHES_DEEPEST_SELECTED")
    pair = matches[0][1]
    snap = {
        "observed_at": _now_iso(),
        "chain": pair.get("chainId"),
        "pair_address": pair.get("pairAddress"),
        "pair_identity_locked": True,
        "pair_identity_evidence": "DEXSCREENER_PAIR_ADDRESS_PRESENT_IN_SOURCE_TX",
        "price_usd": pair.get("priceUsd"),
        "market_cap_usd": pair.get("marketCap"),
        "fdv_usd": pair.get("fdv"),
        "liquidity_usd": (pair.get("liquidity") or {}).get("usd"),
        "volume_h1_usd": (pair.get("volume") or {}).get("h1"),
        "volume_h24_usd": (pair.get("volume") or {}).get("h24"),
        "pair_created_at": pair.get("pairCreatedAt"),
        "dex_url": pair.get("url"),
    }
    try:
        liq = float(snap.get("liquidity_usd") or 0)
        if liq < 50_000:
            flags.append("EXACT_PAIR_LIQUIDITY_LT_50K")
    except Exception:
        flags.append("LIQUIDITY_UNVERIFIED")
    return snap, flags


def _walk_matches(value: Any, mint: str, out: list[str]) -> None:
    if isinstance(value, dict):
        if mint in json.dumps(value, ensure_ascii=False):
            for key in ("observed_at", "generated_at", "first_seen_at", "updated_at", "triggered_at"):
                if value.get(key):
                    out.append(str(value[key]))
            for child in value.values():
                _walk_matches(child, mint, out)
    elif isinstance(value, list):
        for child in value:
            _walk_matches(child, mint, out)


def wallet500_detection_relation(mint: str, event_time: str | None) -> dict:
    sources = [
        "candidate-evidence-envelope.json", "real-alerts.json", "revival-radar.json",
        "active-qualified-candidates.json", "waking-confirmation.json",
    ]
    timestamps: list[str] = []
    matched = []
    for name in sources:
        path = DATA / name
        try:
            raw = _load(path, {})
            if mint in path.read_text(encoding="utf-8"):
                matched.append(name)
                _walk_matches(raw, mint, timestamps)
        except Exception:
            continue
    if not matched:
        return {"relation": "NOT_DETECTED_IN_CURRENT_WALLET500_EVIDENCE", "sources": []}
    if not event_time or not timestamps:
        return {"relation": "DETECTED_TIMESTAMP_UNRESOLVED", "sources": matched}
    try:
        event_dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        parsed = [datetime.fromisoformat(x.replace("Z", "+00:00")) for x in timestamps]
        earliest = min(parsed)
        diff = (earliest - event_dt).total_seconds()
        relation = "BEFORE" if diff < -60 else "AFTER" if diff > 60 else "AT"
        return {"relation": relation, "earliest_detection_at": earliest.isoformat(), "sources": matched}
    except Exception:
        return {"relation": "DETECTED_TIMESTAMP_UNRESOLVED", "sources": matched}


def _telegram(text: str) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"configured": False, "sent": False}
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"configured": True, "sent": 200 <= int(r.status) < 300}
    except Exception as exc:
        return {"configured": True, "sent": False, "error": type(exc).__name__}


def _alert(event: dict) -> dict:
    snap = event.get("market_snapshot") or {}
    relation = (event.get("wallet500_detection") or {}).get("relation")
    n = event.get("source_notional") or {}
    c = event.get("copy_1pct_notional") or {}
    text = "\n".join([
        f"🔥🔥🔥 CryptoYeezus SOURCE WALLET {event.get('side')}",
        f"Mint: {event.get('token_mint')}",
        f"TX: {event.get('signature')}",
        f"Time: {event.get('observed_chain_time')}",
        f"Source: {n.get('amount')} {n.get('asset')}",
        f"1% cohort: {c.get('amount')} {c.get('asset')}",
        f"Exact pair: {snap.get('pair_address') or 'UNRESOLVED'}",
        f"Liquidity: {snap.get('liquidity_usd') if snap else 'UNRESOLVED'}",
        f"Wallet500 detection: {relation}",
        "SIMULATION ONLY — no real trade executed",
    ])
    return _telegram(text)


def _fetch_new_signatures(cursor: str) -> list[dict]:
    opts: dict[str, Any] = {"limit": MAX_SIGNATURES, "commitment": "confirmed"}
    if cursor:
        opts["until"] = cursor
    return _rpc("getSignaturesForAddress", [SOURCE_WALLET, opts]) or []


def _refresh_positions(state: dict) -> None:
    positions = state.setdefault("positions", {})
    for mint, pos in list(positions.items()):
        pair = pos.get("exact_pair")
        entry = float(pos.get("entry_price_usd") or 0)
        if not pair or entry <= 0:
            continue
        try:
            payload = _get_json(f"https://api.dexscreener.com/latest/dex/pairs/solana/{urllib.parse.quote(str(pair))}")
            pairs = payload.get("pairs") or []
            if not pairs:
                continue
            price = float(pairs[0].get("priceUsd") or 0)
        except Exception:
            continue
        if price <= 0:
            continue
        multiple = price / entry
        pos["last_price_usd"] = price
        pos["last_multiple"] = round(multiple, 4)
        pos["max_multiple"] = max(float(pos.get("max_multiple") or 0), multiple)
        pos["updated_at"] = _now_iso()
        for name, trigger in (("primary", 3.0), ("shadow", 4.0)):
            lane = pos.setdefault(name, {"status": "OPEN"})
            if lane.get("status") == "OPEN" and multiple >= trigger:
                lane.update({"status": "EXITED_TARGET", "exit_multiple": round(multiple, 4), "exit_price_usd": price, "exited_at": _now_iso()})
        if any((pos.get(x) or {}).get("status", "OPEN") != "OPEN" for x in ("primary", "shadow")):
            pos["post_exit_max_multiple"] = max(float(pos.get("post_exit_max_multiple") or 0), multiple)


def run() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    state = _load(STATE_PATH, {})
    events_file = _load(EVENTS_PATH, {"version": 1, "events": []})
    now = _now_iso()

    if not state.get("cursor"):
        latest = _rpc("getSignaturesForAddress", [SOURCE_WALLET, {"limit": 1, "commitment": "confirmed"}]) or []
        cursor = str((latest[0] if latest else {}).get("signature") or "")
        state = {"version": 1, "wallet": SOURCE_WALLET, "started_at": now, "cursor": cursor, "positions": {}, "processed": []}
        _write(STATE_PATH, state)
        latest_payload = {"version": 1, "observed_at": now, "status": "FORWARD_BASELINE_ESTABLISHED", "wallet": SOURCE_WALLET, "new_verified_swaps": 0, "simulation_only": True}
        _write(LATEST_PATH, latest_payload)
        _write(EVENTS_PATH, events_file)
        return latest_payload

    rows = _fetch_new_signatures(str(state.get("cursor") or ""))
    processed = set(state.get("processed") or [])
    new_events: list[dict] = []
    for row in reversed(rows):
        sig = str(row.get("signature") or "")
        if not sig or sig in processed or row.get("err") is not None:
            continue
        try:
            tx = _rpc("getTransaction", [sig, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
        except Exception:
            continue
        event = classify_verified_swap(tx or {}, sig, row.get("blockTime") or (tx or {}).get("blockTime"))
        processed.add(sig)
        if not event:
            continue
        snap, flags = exact_pair_snapshot(event["token_mint"], _account_keys(tx or {}))
        event["first_observed_at"] = now
        event["market_snapshot"] = snap
        event["risk_liquidity_flags"] = flags
        event["wallet500_detection"] = wallet500_detection_relation(event["token_mint"], event.get("observed_chain_time"))
        event["alert"] = _alert(event)
        new_events.append(event)
        events_file.setdefault("events", []).append(event)

        positions = state.setdefault("positions", {})
        mint = event["token_mint"]
        if event["side"] == "BUY" and snap and snap.get("price_usd"):
            price = float(snap["price_usd"])
            positions[mint] = {
                "mint": mint, "source_buy_signature": sig, "entry_observed_at": snap.get("observed_at"),
                "entry_price_usd": price, "exact_pair": snap.get("pair_address"), "max_multiple": 1.0,
                "primary": {"status": "OPEN", "rule": "SOURCE_SELL_OR_3X_FIRST"},
                "shadow": {"status": "OPEN", "rule": "SOURCE_SELL_OR_4X_FIRST"},
                "simulation_only": True,
            }
        elif event["side"] == "SELL" and mint in positions:
            pos = positions[mint]
            exit_price = float((snap or {}).get("price_usd") or pos.get("last_price_usd") or 0) or None
            for name in ("primary", "shadow"):
                lane = pos.setdefault(name, {"status": "OPEN"})
                if lane.get("status") == "OPEN":
                    lane.update({"status": "EXITED_SOURCE_SELL", "source_sell_signature": sig, "exit_price_usd": exit_price, "exited_at": now})

    if rows and rows[0].get("signature"):
        state["cursor"] = rows[0]["signature"]
    state["processed"] = list(processed)[-1000:]
    _refresh_positions(state)
    state["updated_at"] = now
    events_file["updated_at"] = now
    events_file["wallet"] = SOURCE_WALLET
    events_file["simulation_only"] = True
    events_file["events"] = events_file.get("events", [])[-1000:]
    _write(STATE_PATH, state)
    _write(EVENTS_PATH, events_file)
    latest_payload = {
        "version": 1, "observed_at": now, "status": "OK", "wallet": SOURCE_WALLET,
        "new_verified_swaps": len(new_events), "events": new_events,
        "open_positions": sum(1 for p in state.get("positions", {}).values() if (p.get("primary") or {}).get("status") == "OPEN" or (p.get("shadow") or {}).get("status") == "OPEN"),
        "simulation_only": True, "real_money_execution": False,
    }
    _write(LATEST_PATH, latest_payload)
    return latest_payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
