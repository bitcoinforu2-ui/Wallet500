from __future__ import annotations

import base64
import json
import math
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
USDT = "Es9vMFrzaCERmJfrF4H2FYDqkr8qmWAnctmU7k6uX5u"
QUOTE_MINTS = {WSOL, USDC, USDT}
DATA = Path("data")
CONFIG_PATH = Path("experiments/cryptoyeezus-copy-v1.json")
LEDGER_PATH = DATA / "cryptoyeezus-copy-ledger.json"
SUMMARY_PATH = DATA / "cryptoyeezus-copy-summary.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _http_json(url: str, *, method: str = "GET", payload: Any = None, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    h = {"User-Agent": "Wallet500-CryptoYeezusCopy/1.0", "Accept": "application/json"}
    if body is not None:
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _rpc(rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    out = _http_json(rpc_url, method="POST", payload=payload, timeout=25)
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(f"RPC {method}: {out['error']}")
    return out.get("result") if isinstance(out, dict) else None


def _pubkey(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get("pubkey") or "")
    return ""


def _is_signer(entry: Any) -> bool:
    return bool(entry.get("signer")) if isinstance(entry, dict) else False


def _raw_token_balances(rows: Any, wallet: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("owner") or "") != wallet:
            continue
        mint = str(row.get("mint") or "")
        ui = row.get("uiTokenAmount") if isinstance(row.get("uiTokenAmount"), dict) else {}
        if not mint or not ui:
            continue
        try:
            amount = int(str(ui.get("amount") or "0"))
            decimals = int(ui.get("decimals") or 0)
        except Exception:
            continue
        slot = result.setdefault(mint, {"raw": 0, "decimals": decimals})
        slot["raw"] += amount
        slot["decimals"] = decimals
    return result


def parse_wallet_swap(tx: dict[str, Any], wallet: str = SOURCE_WALLET) -> dict[str, Any] | None:
    """Parse a simple wallet-level swap and fail closed on ambiguous flows."""
    if not isinstance(tx, dict):
        return None
    meta = tx.get("meta") if isinstance(tx.get("meta"), dict) else {}
    if meta.get("err") is not None:
        return None
    transaction = tx.get("transaction") if isinstance(tx.get("transaction"), dict) else {}
    message = transaction.get("message") if isinstance(transaction.get("message"), dict) else {}
    keys = message.get("accountKeys") if isinstance(message.get("accountKeys"), list) else []
    wallet_index = None
    signer = False
    for i, key in enumerate(keys):
        if _pubkey(key) == wallet:
            wallet_index = i
            signer = _is_signer(key)
            break
    if wallet_index is None or not signer:
        return None

    pre = _raw_token_balances(meta.get("preTokenBalances"), wallet)
    post = _raw_token_balances(meta.get("postTokenBalances"), wallet)
    deltas: dict[str, dict[str, Any]] = {}
    for mint in set(pre) | set(post):
        p = pre.get(mint, {"raw": 0, "decimals": post.get(mint, {}).get("decimals", 0)})
        q = post.get(mint, {"raw": 0, "decimals": p.get("decimals", 0)})
        raw = int(q.get("raw", 0)) - int(p.get("raw", 0))
        if raw:
            deltas[mint] = {"mint": mint, "raw": raw, "decimals": int(q.get("decimals", p.get("decimals", 0)))}

    # Prefer an explicit WSOL token delta. Otherwise use the wallet lamport delta,
    # adding the transaction fee back. ATA rent can still contaminate this raw-RPC
    # estimate, so we preserve a flag instead of pretending the notional is exact.
    if WSOL not in deltas:
        pre_bal = meta.get("preBalances") if isinstance(meta.get("preBalances"), list) else []
        post_bal = meta.get("postBalances") if isinstance(meta.get("postBalances"), list) else []
        if wallet_index < len(pre_bal) and wallet_index < len(post_bal):
            try:
                fee = int(meta.get("fee") or 0)
                native_raw = int(post_bal[wallet_index]) - int(pre_bal[wallet_index]) + fee
                if native_raw:
                    deltas[WSOL] = {"mint": WSOL, "raw": native_raw, "decimals": 9, "native_estimate": True}
            except Exception:
                pass

    positives = [v for v in deltas.values() if int(v["raw"]) > 0]
    negatives = [v for v in deltas.values() if int(v["raw"]) < 0]
    if not positives or not negatives:
        return None

    buy_outputs = [v for v in positives if v["mint"] not in QUOTE_MINTS]
    buy_inputs = [v for v in negatives if v["mint"] in QUOTE_MINTS]
    sell_inputs = [v for v in negatives if v["mint"] not in QUOTE_MINTS]
    sell_outputs = [v for v in positives if v["mint"] in QUOTE_MINTS]

    if len(buy_outputs) == 1 and len(buy_inputs) == 1 and not sell_inputs:
        inp, out = buy_inputs[0], buy_outputs[0]
        return {
            "side": "BUY",
            "input_mint": inp["mint"],
            "input_amount_raw": abs(int(inp["raw"])),
            "input_decimals": int(inp["decimals"]),
            "output_mint": out["mint"],
            "output_amount_raw": int(out["raw"]),
            "output_decimals": int(out["decimals"]),
            "native_notional_is_estimate": bool(inp.get("native_estimate")),
        }
    if len(sell_inputs) == 1 and len(sell_outputs) == 1 and not buy_outputs:
        inp, out = sell_inputs[0], sell_outputs[0]
        return {
            "side": "SELL",
            "input_mint": inp["mint"],
            "input_amount_raw": abs(int(inp["raw"])),
            "input_decimals": int(inp["decimals"]),
            "output_mint": out["mint"],
            "output_amount_raw": int(out["raw"]),
            "output_decimals": int(out["decimals"]),
            "native_notional_is_estimate": bool(out.get("native_estimate")),
        }
    return None


def _jup_headers() -> dict[str, str]:
    key = os.getenv("JUPITER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("JUPITER_API_KEY is required for Jupiter Swap V2")
    return {"x-api-key": key}


def jupiter_order(input_mint: str, output_mint: str, amount_raw: int, *, taker: str | None = None) -> dict[str, Any]:
    params = {"inputMint": input_mint, "outputMint": output_mint, "amount": str(int(amount_raw))}
    if taker:
        params["taker"] = taker
    url = "https://api.jup.ag/swap/v2/order?" + urllib.parse.urlencode(params)
    out = _http_json(url, headers=_jup_headers(), timeout=25)
    if not isinstance(out, dict) or not out.get("outAmount"):
        raise RuntimeError(f"Jupiter order missing outAmount: {str(out)[:500]}")
    return out


def _sign_order_transaction(order: dict[str, Any], secret_b58: str, expected_pubkey: str) -> str:
    try:
        from solders.keypair import Keypair
        from solders.signature import Signature
        from solders.transaction import VersionedTransaction
    except ImportError as exc:
        raise RuntimeError("Install live dependency: pip install solders") from exc
    raw = base64.b64decode(str(order.get("transaction") or ""))
    tx = VersionedTransaction.from_bytes(raw)
    kp = Keypair.from_base58_string(secret_b58)
    if str(kp.pubkey()) != expected_pubkey:
        raise RuntimeError("COPY_WALLET_SECRET_B58 does not match COPY_WALLET_PUBKEY")
    required = int(tx.message.header.num_required_signatures)
    account_keys = list(tx.message.account_keys)
    signer_index = next((i for i, key in enumerate(account_keys[:required]) if str(key) == expected_pubkey), None)
    if signer_index is None:
        raise RuntimeError("Jupiter transaction does not require the configured wallet signature")
    signatures = list(tx.signatures)
    while len(signatures) < required:
        signatures.append(Signature.default())
    signatures[signer_index] = kp.sign_message(bytes(tx.message))
    signed = VersionedTransaction.populate(tx.message, signatures)
    return base64.b64encode(bytes(signed)).decode("ascii")


def execute_jupiter_swap(input_mint: str, output_mint: str, amount_raw: int, config: dict[str, Any]) -> dict[str, Any]:
    pubkey = os.getenv("COPY_WALLET_PUBKEY", "").strip()
    secret = os.getenv("COPY_WALLET_SECRET_B58", "").strip()
    if not pubkey or not secret:
        raise RuntimeError("COPY_WALLET_PUBKEY and COPY_WALLET_SECRET_B58 are required in live mode")
    order = jupiter_order(input_mint, output_mint, amount_raw, taker=pubkey)
    try:
        impact = float(order.get("priceImpactPct") or 0)
    except Exception:
        impact = 0.0
    cap = float(config.get("max_price_impact_pct") or 0.10)
    if impact > cap:
        raise RuntimeError(f"Price impact {impact:.4%} exceeds cap {cap:.4%}")
    signed = _sign_order_transaction(order, secret, pubkey)
    payload = {"signedTransaction": signed, "requestId": order.get("requestId")}
    if order.get("lastValidBlockHeight") is not None:
        payload["lastValidBlockHeight"] = str(order["lastValidBlockHeight"])
    result = _http_json("https://api.jup.ag/swap/v2/execute", method="POST", payload=payload, headers=_jup_headers(), timeout=40)
    if not isinstance(result, dict) or result.get("status") != "Success" or not result.get("signature"):
        raise RuntimeError(f"Jupiter execute failed: {str(result)[:700]}")
    result["_order"] = {k: order.get(k) for k in ("requestId", "outAmount", "inAmount", "priceImpactPct", "router", "mode", "platformFee")}
    return result


def _tx_for_signature(rpc_url: str, signature: str) -> dict[str, Any] | None:
    return _rpc(rpc_url, "getTransaction", [signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])


def _recent_signatures(rpc_url: str, wallet: str, limit: int = 30) -> list[dict[str, Any]]:
    rows = _rpc(rpc_url, "getSignaturesForAddress", [wallet, {"limit": limit, "commitment": "confirmed"}])
    return rows if isinstance(rows, list) else []


def _event_id(signature: str, side: str, mint: str) -> str:
    return f"{signature}:{side}:{mint}"


def _notify(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return
    payload = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def _format_amount(raw: int, decimals: int) -> float:
    return float(raw) / (10 ** int(decimals))


def _live_enabled(config: dict[str, Any]) -> bool:
    return os.getenv("COPY_LIVE_ENABLED", "").strip().lower() in {"1", "true", "yes"} and bool(config.get("allow_live_execution"))


def _new_state(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "CRYPTOYEEZUS_DIRECT_WALLET_COPY_V1",
        "created_at": _now(),
        "source_wallet": str(config.get("source_wallet") or SOURCE_WALLET),
        "copy_ratio": float(config.get("copy_ratio") or 0.01),
        "mode": "LIVE_ARMABLE_FAIL_CLOSED",
        "events": [],
        "positions": [],
        "last_source_signature": None,
    }


def _copy_amount(source_raw: int, ratio: float) -> int:
    return max(0, int(math.floor(int(source_raw) * float(ratio))))


def _open_shadow_position(event: dict[str, Any], quote: dict[str, Any] | None, copy_raw: int) -> dict[str, Any]:
    out_raw = int(quote.get("outAmount") or 0) if isinstance(quote, dict) else 0
    return {
        "position_id": event["event_id"],
        "source_signature": event["signature"],
        "token_mint": event["output_mint"],
        "entry_at": event["observed_at"],
        "entry_input_mint": event["input_mint"],
        "entry_input_amount_raw": copy_raw,
        "token_amount_raw": out_raw,
        "entry_execution": "SHADOW_QUOTE" if quote else "PENDING_QUOTE",
        "entry_tx": None,
        "status": "OPEN_SHADOW",
        "target_3x_input_raw": copy_raw * 3,
        "shadow_target_4x_input_raw": copy_raw * 4,
        "ever_3x": False,
        "ever_4x": False,
        "exit_reason": None,
        "exit_at": None,
        "exit_tx": None,
        "marks": [],
    }


def _handle_buy(state: dict[str, Any], event: dict[str, Any], config: dict[str, Any], live: bool) -> None:
    ratio = float(config.get("copy_ratio") or 0.01)
    copy_raw = _copy_amount(event["input_amount_raw"], ratio)
    event["copy_ratio"] = ratio
    event["copy_input_amount_raw"] = copy_raw
    event["copy_input_amount_ui"] = _format_amount(copy_raw, event["input_decimals"])
    if copy_raw <= 0:
        event["copy_status"] = "SKIPPED_TOO_SMALL"
        return
    quote = None
    try:
        quote = jupiter_order(event["input_mint"], event["output_mint"], copy_raw)
        event["shadow_quote_out_raw"] = int(quote.get("outAmount") or 0)
        event["shadow_price_impact_pct"] = quote.get("priceImpactPct")
    except Exception as exc:
        event["quote_error"] = f"{type(exc).__name__}: {exc}"[:500]
    position = _open_shadow_position(event, quote, copy_raw)
    if live:
        result = execute_jupiter_swap(event["input_mint"], event["output_mint"], copy_raw, config)
        actual_out = int(result.get("outputAmountResult") or result.get("totalOutputAmount") or 0)
        actual_in = int(result.get("inputAmountResult") or result.get("totalInputAmount") or copy_raw)
        if actual_out <= 0:
            raise RuntimeError("Live buy returned no output amount")
        position.update({
            "entry_input_amount_raw": actual_in,
            "token_amount_raw": actual_out,
            "entry_execution": "LIVE_JUPITER_SWAP_V2",
            "entry_tx": result["signature"],
            "status": "OPEN_LIVE",
            "target_3x_input_raw": actual_in * 3,
            "shadow_target_4x_input_raw": actual_in * 4,
        })
        event["copy_status"] = "LIVE_FILLED"
        event["copy_tx"] = result["signature"]
    else:
        event["copy_status"] = "SHADOW_ONLY"
    state["positions"].append(position)


def _close_position(position: dict[str, Any], reason: str, config: dict[str, Any], live: bool) -> None:
    if not str(position.get("status") or "").startswith("OPEN"):
        return
    token_raw = int(position.get("token_amount_raw") or 0)
    if token_raw <= 0:
        position.update(status="CLOSED_NO_EXECUTABLE_AMOUNT", exit_reason=reason, exit_at=_now())
        return
    if live and position.get("entry_execution") == "LIVE_JUPITER_SWAP_V2":
        result = execute_jupiter_swap(str(position["token_mint"]), str(position["entry_input_mint"]), token_raw, config)
        position.update({
            "status": "CLOSED_LIVE",
            "exit_reason": reason,
            "exit_at": _now(),
            "exit_tx": result["signature"],
            "exit_output_raw": int(result.get("outputAmountResult") or result.get("totalOutputAmount") or 0),
        })
    else:
        try:
            q = jupiter_order(str(position["token_mint"]), str(position["entry_input_mint"]), token_raw)
            out_raw = int(q.get("outAmount") or 0)
        except Exception:
            out_raw = 0
        position.update(status="CLOSED_SHADOW", exit_reason=reason, exit_at=_now(), exit_tx=None, exit_output_raw=out_raw)


def _handle_sell(state: dict[str, Any], event: dict[str, Any], config: dict[str, Any], live: bool) -> None:
    closed = 0
    token = str(event["input_mint"])
    for position in state.get("positions") or []:
        if str(position.get("token_mint")) == token and str(position.get("status", "")).startswith("OPEN"):
            _close_position(position, f"SOURCE_WALLET_SELL:{event['signature']}", config, live)
            closed += 1
    event["copy_status"] = f"SOURCE_SELL_CLOSED_{closed}"


def _mark_positions(state: dict[str, Any], config: dict[str, Any], live: bool) -> None:
    now = _now()
    take_profit = float(config.get("take_profit_multiple") or 3.0)
    shadow_compare = float(config.get("shadow_compare_multiple") or 4.0)
    for p in state.get("positions") or []:
        token_raw = int(p.get("token_amount_raw") or 0)
        if token_raw <= 0:
            continue
        try:
            q = jupiter_order(str(p["token_mint"]), str(p["entry_input_mint"]), token_raw)
            out_raw = int(q.get("outAmount") or 0)
        except Exception as exc:
            p["last_mark_error"] = f"{type(exc).__name__}: {exc}"[:300]
            p["last_mark_at"] = now
            continue
        cost = max(1, int(p.get("entry_input_amount_raw") or 1))
        multiple = out_raw / cost
        p["last_mark_at"] = now
        p["last_quote_output_raw"] = out_raw
        p["last_executable_multiple"] = round(multiple, 6)
        p["peak_executable_multiple"] = round(max(float(p.get("peak_executable_multiple") or multiple), multiple), 6)
        p["ever_3x"] = bool(p.get("ever_3x")) or multiple >= take_profit
        p["ever_4x"] = bool(p.get("ever_4x")) or multiple >= shadow_compare
        marks = p.setdefault("marks", [])
        marks.append({"at": now, "multiple": round(multiple, 6), "quote_output_raw": out_raw})
        max_marks = int(config.get("max_marks_per_position") or 500)
        if len(marks) > max_marks:
            del marks[:-max_marks]
        if str(p.get("status") or "").startswith("OPEN") and multiple >= take_profit:
            _close_position(p, f"TAKE_PROFIT_{take_profit:g}X_EXECUTABLE_QUOTE", config, live)
        elif not str(p.get("status") or "").startswith("OPEN"):
            p["post_exit_peak_multiple"] = round(max(float(p.get("post_exit_peak_multiple") or multiple), multiple), 6)


def _summary(state: dict[str, Any], config: dict[str, Any], live: bool, errors: list[dict[str, Any]]) -> dict[str, Any]:
    positions = state.get("positions") or []
    events = state.get("events") or []
    return {
        "version": "CRYPTOYEEZUS_DIRECT_WALLET_COPY_V1",
        "updated_at": _now(),
        "source_wallet": state.get("source_wallet"),
        "copy_ratio": state.get("copy_ratio"),
        "live_execution_armed": live,
        "real_money_claim_policy": "A trade is LIVE only when Jupiter execute returns Success plus a transaction signature.",
        "source_swap_events": len(events),
        "source_buys": sum(1 for x in events if x.get("side") == "BUY"),
        "source_sells": sum(1 for x in events if x.get("side") == "SELL"),
        "positions_total": len(positions),
        "open_positions": sum(1 for x in positions if str(x.get("status", "")).startswith("OPEN")),
        "live_entries": sum(1 for x in positions if x.get("entry_execution") == "LIVE_JUPITER_SWAP_V2"),
        "closed_source_sell": sum(1 for x in positions if str(x.get("exit_reason") or "").startswith("SOURCE_WALLET_SELL")),
        "closed_3x": sum(1 for x in positions if str(x.get("exit_reason") or "").startswith("TAKE_PROFIT_3X")),
        "ever_4x_shadow": sum(1 for x in positions if x.get("ever_4x")),
        "errors": errors[-20:],
        "requirements_for_live": {
            "persistent_process": True,
            "env": ["COPY_LIVE_ENABLED=true", "COPY_WALLET_PUBKEY", "COPY_WALLET_SECRET_B58", "JUPITER_API_KEY", "SOLANA_RPC_URL"],
            "python_package": "solders",
        },
        "rules": config,
    }


def run_once() -> dict[str, Any]:
    DATA.mkdir(parents=True, exist_ok=True)
    config = _load(CONFIG_PATH, {})
    state = _load(LEDGER_PATH, {})
    if not isinstance(state, dict) or not state:
        state = _new_state(config)
    errors: list[dict[str, Any]] = []
    live = _live_enabled(config)
    rpc_url = os.getenv("SOLANA_RPC_URL", "").strip() or str(config.get("rpc_url") or "https://api.mainnet-beta.solana.com")
    wallet = str(config.get("source_wallet") or state.get("source_wallet") or SOURCE_WALLET)
    state["source_wallet"] = wallet
    state["copy_ratio"] = float(config.get("copy_ratio") or 0.01)

    seen = {str(x.get("event_id")) for x in state.get("events") or [] if isinstance(x, dict)}
    try:
        signatures = _recent_signatures(rpc_url, wallet, int(config.get("signature_batch") or 30))
    except Exception as exc:
        signatures = []
        errors.append({"stage": "SIGNATURES", "error": f"{type(exc).__name__}: {exc}"[:500]})

    # First run establishes a hard forward boundary. No historical swap is booked.
    if not state.get("last_source_signature") and signatures:
        state["last_source_signature"] = str(signatures[0].get("signature") or "")
        state["forward_boundary_established_at"] = _now()
        state["forward_boundary_signature"] = state["last_source_signature"]
    else:
        boundary = str(state.get("last_source_signature") or "")
        new_rows = []
        for row in signatures:
            if str(row.get("signature") or "") == boundary:
                break
            new_rows.append(row)
        for row in reversed(new_rows):
            sig = str(row.get("signature") or "")
            if not sig:
                continue
            try:
                tx = _tx_for_signature(rpc_url, sig)
                parsed = parse_wallet_swap(tx or {}, wallet)
                if not parsed:
                    continue
                token = parsed["output_mint"] if parsed["side"] == "BUY" else parsed["input_mint"]
                eid = _event_id(sig, parsed["side"], token)
                if eid in seen:
                    continue
                event = {
                    "event_id": eid,
                    "signature": sig,
                    "slot": row.get("slot"),
                    "block_time": (tx or {}).get("blockTime"),
                    "observed_at": _now(),
                    **parsed,
                }
                state.setdefault("events", []).append(event)
                seen.add(eid)
                try:
                    if event["side"] == "BUY":
                        _handle_buy(state, event, config, live)
                    else:
                        _handle_sell(state, event, config, live)
                    _notify(
                        f"CryptoYeezus wallet {event['side']} detected\n"
                        f"Mint: {token}\nTx: {sig}\n"
                        f"Copy: {event.get('copy_status','TRACKED')}\n"
                        f"Mode: {'LIVE' if live else 'SHADOW'}"
                    )
                except Exception as exc:
                    event["copy_status"] = "FAILED_CLOSED"
                    event["copy_error"] = f"{type(exc).__name__}: {exc}"[:700]
                    errors.append({"stage": f"{event['side']}_COPY", "signature": sig, "error": event["copy_error"]})
            except Exception as exc:
                errors.append({"stage": "PARSE_TX", "signature": sig, "error": f"{type(exc).__name__}: {exc}"[:500]})
        if signatures:
            state["last_source_signature"] = str(signatures[0].get("signature") or state.get("last_source_signature") or "")

    try:
        _mark_positions(state, config, live)
    except Exception as exc:
        errors.append({"stage": "MARK_POSITIONS", "error": f"{type(exc).__name__}: {exc}"[:500]})

    state["updated_at"] = _now()
    state.setdefault("errors", []).extend(errors)
    if len(state["errors"]) > 100:
        state["errors"] = state["errors"][-100:]
    summary = _summary(state, config, live, errors)
    _write(LEDGER_PATH, state)
    _write(SUMMARY_PATH, summary)
    return summary


def serve() -> None:
    config = _load(CONFIG_PATH, {})
    poll = max(1.0, float(os.getenv("COPY_POLL_SECONDS", "") or config.get("poll_seconds") or 5.0))
    while True:
        try:
            print(json.dumps(run_once(), ensure_ascii=False))
        except Exception as exc:
            print(json.dumps({"updated_at": _now(), "fatal_iteration_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        time.sleep(poll)


if __name__ == "__main__":
    if os.getenv("COPY_DAEMON", "").strip().lower() in {"1", "true", "yes"}:
        serve()
    else:
        print(json.dumps(run_once(), indent=2, ensure_ascii=False))
