from __future__ import annotations

import json
import math
import os
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PAIR = "G8kgi7aUpeX8EVR8VMkrth9SKEv5BietWC33UjAiiMGh"
MINT = "ApZuxdpzMrbEYTGEzeY9afh5pj9d6qPRJCTgQYiipbKg"
RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DATA = Path("data")
STATE_PATH = DATA / "cyberleek-wallet-flow-state.json"
SUMMARY_PATH = DATA / "cyberleek-wallet-flow.json"
WINDOWS = {"m5": 5 * 60, "h1": 60 * 60, "h6": 6 * 60 * 60, "h24": 24 * 60 * 60}
MAX_SIGNATURES_PER_RUN = 3000
BATCH_SIZE = 20
EPSILON = 1e-12


def _now_epoch() -> int:
    return int(time.time())


def _iso(epoch: int | float | None = None) -> str:
    if epoch is None:
        epoch = _now_epoch()
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rpc_post(payload, timeout: int = 30):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RPC_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Wallet500-CYBERLEEK-WalletFlow/1.0"},
        method="POST",
    )
    last_exc = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_exc))


def _rpc(method: str, params):
    response = _rpc_post({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if isinstance(response, dict) and response.get("error"):
        raise RuntimeError(f"RPC {method} error: {response['error']}")
    return response.get("result") if isinstance(response, dict) else None


def _rpc_batch(method: str, params_list: list[list]) -> list:
    if not params_list:
        return []
    payload = [
        {"jsonrpc": "2.0", "id": i + 1, "method": method, "params": params}
        for i, params in enumerate(params_list)
    ]
    response = _rpc_post(payload, timeout=45)
    if not isinstance(response, list):
        return [None] * len(params_list)
    by_id = {int(row.get("id")): row for row in response if isinstance(row, dict) and row.get("id") is not None}
    out = []
    for i in range(1, len(params_list) + 1):
        row = by_id.get(i) or {}
        out.append(None if row.get("error") else row.get("result"))
    return out


def _amount(balance: dict) -> float:
    ui = (balance or {}).get("uiTokenAmount") or {}
    raw = ui.get("amount")
    decimals = int(ui.get("decimals") or 0)
    try:
        return int(raw) / (10 ** decimals)
    except Exception:
        try:
            return float(ui.get("uiAmountString") or ui.get("uiAmount") or 0)
        except Exception:
            return 0.0


def _signers(tx: dict) -> set[str]:
    try:
        keys = tx["transaction"]["message"]["accountKeys"]
    except Exception:
        return set()
    out: set[str] = set()
    for key in keys or []:
        if isinstance(key, dict) and key.get("signer") and key.get("pubkey"):
            out.add(str(key["pubkey"]))
    return out


def _mint_owner_deltas(tx: dict, mint: str = MINT) -> dict[str, float]:
    meta = tx.get("meta") or {}
    pre = defaultdict(float)
    post = defaultdict(float)
    for row in meta.get("preTokenBalances") or []:
        if row.get("mint") == mint and row.get("owner"):
            pre[str(row["owner"])] += _amount(row)
    for row in meta.get("postTokenBalances") or []:
        if row.get("mint") == mint and row.get("owner"):
            post[str(row["owner"])] += _amount(row)
    owners = set(pre) | set(post)
    return {owner: post.get(owner, 0.0) - pre.get(owner, 0.0) for owner in owners}


def _extract_trade(tx: dict | None, signature: str, block_time: int | None = None) -> dict | None:
    """Resolve a real trader only when a signed wallet has a CYBERLEEK balance delta.

    This intentionally fails closed for aggregator/program-only transactions where the
    end-user owner cannot be tied to a signer from parsed transaction data.
    """
    if not isinstance(tx, dict) or (tx.get("meta") or {}).get("err") is not None:
        return None
    signers = _signers(tx)
    if not signers:
        return None
    deltas = _mint_owner_deltas(tx)
    candidates = [(wallet, delta) for wallet, delta in deltas.items() if wallet in signers and abs(delta) > EPSILON]
    if not candidates:
        return None
    wallet, delta = max(candidates, key=lambda item: abs(item[1]))
    t = int(block_time or tx.get("blockTime") or 0)
    if t <= 0:
        return None
    return {
        "t": t,
        "sig": signature,
        "w": wallet,
        "side": "BUY" if delta > 0 else "SELL",
        "token_delta": round(float(delta), 9),
        "resolution": "SIGNED_TOKEN_OWNER_DELTA",
    }


def _fetch_new_signatures(cursor: str) -> tuple[list[dict], bool]:
    rows_all: list[dict] = []
    before = None
    overflow = False
    while len(rows_all) < MAX_SIGNATURES_PER_RUN:
        limit = min(1000, MAX_SIGNATURES_PER_RUN - len(rows_all))
        opts = {"limit": limit, "commitment": "confirmed", "until": cursor}
        if before:
            opts["before"] = before
        rows = _rpc("getSignaturesForAddress", [PAIR, opts]) or []
        if not rows:
            break
        rows_all.extend(rows)
        if len(rows) < limit:
            break
        before = rows[-1].get("signature")
        if not before:
            break
    if len(rows_all) >= MAX_SIGNATURES_PER_RUN:
        overflow = True
    return rows_all, overflow


def _fetch_transactions(rows: list[dict]) -> tuple[list[dict], int]:
    params = []
    valid_rows = []
    for row in rows:
        if row.get("err") is not None or not row.get("signature"):
            continue
        valid_rows.append(row)
        params.append([
            row["signature"],
            {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0},
        ])
    events: list[dict] = []
    null_or_unresolved = 0
    for start in range(0, len(params), BATCH_SIZE):
        chunk_params = params[start : start + BATCH_SIZE]
        chunk_rows = valid_rows[start : start + BATCH_SIZE]
        results = _rpc_batch("getTransaction", chunk_params)
        for row, tx in zip(chunk_rows, results):
            event = _extract_trade(tx, str(row["signature"]), row.get("blockTime"))
            if event:
                events.append(event)
            else:
                null_or_unresolved += 1
        if start + BATCH_SIZE < len(params):
            time.sleep(0.15)
    return events, null_or_unresolved


def _summarize_window(events: list[dict], wallet_first: dict[str, dict], cutoff: int) -> dict:
    rows = [e for e in events if int(e.get("t") or 0) >= cutoff]
    buys = [e for e in rows if e.get("side") == "BUY"]
    sells = [e for e in rows if e.get("side") == "SELL"]
    buy_wallets = {str(e["w"]) for e in buys}
    sell_wallets = {str(e["w"]) for e in sells}
    traders = buy_wallets | sell_wallets
    first_seen_buyers = {
        w
        for w in buy_wallets
        if (wallet_first.get(w) or {}).get("side") == "BUY" and int((wallet_first.get(w) or {}).get("t") or 0) >= cutoff
    }
    repeat_buyers = buy_wallets - first_seen_buyers
    buy_token = sum(max(0.0, float(e.get("token_delta") or 0)) for e in buys)
    sell_token = sum(abs(min(0.0, float(e.get("token_delta") or 0))) for e in sells)
    per_wallet = Counter(str(e["w"]) for e in rows)
    top10 = sum(v for _, v in per_wallet.most_common(10))
    net = defaultdict(float)
    for event in rows:
        net[str(event["w"])] += float(event.get("token_delta") or 0)
    accumulators = sum(1 for value in net.values() if value > EPSILON)
    distributors = sum(1 for value in net.values() if value < -EPSILON)
    resolved = len(rows)
    unique_traders = len(traders)
    return {
        "resolved_swaps": resolved,
        "buy_swaps": len(buys),
        "sell_swaps": len(sells),
        "unique_traders": unique_traders,
        "unique_buyers": len(buy_wallets),
        "unique_sellers": len(sell_wallets),
        "first_seen_buyers_since_t0": len(first_seen_buyers),
        "repeat_buyers": len(repeat_buyers),
        "wallet_buy_sell_ratio": round(len(buy_wallets) / len(sell_wallets), 4) if sell_wallets else None,
        "buy_token_flow": round(buy_token, 6),
        "sell_token_flow": round(sell_token, 6),
        "token_flow_ratio": round(buy_token / sell_token, 4) if sell_token > 0 else None,
        "median_buy_tokens": round(statistics.median([abs(float(e["token_delta"])) for e in buys]), 6) if buys else None,
        "median_sell_tokens": round(statistics.median([abs(float(e["token_delta"])) for e in sells]), 6) if sells else None,
        "tx_per_unique_trader": round(resolved / unique_traders, 4) if unique_traders else None,
        "repeat_tx_excess_share_pct": round(max(0, resolved - unique_traders) / resolved * 100.0, 2) if resolved else None,
        "top10_wallet_tx_share_pct": round(top10 / resolved * 100.0, 2) if resolved else None,
        "net_accumulating_wallets": accumulators,
        "net_distributing_wallets": distributors,
        "first_seen_buyer_share_pct": round(len(first_seen_buyers) / len(buy_wallets) * 100.0, 2) if buy_wallets else None,
    }


def _empty_summary(status: str, generated_at: int, started_at: int | None = None, error: str | None = None) -> dict:
    return {
        "version": "CYBERLEEK_WALLET_FLOW_V1",
        "generated_at": _iso(generated_at),
        "status": status,
        "chain": "solana",
        "mint": MINT,
        "exact_pair": PAIR,
        "monitor_started_at": _iso(started_at) if started_at else None,
        "source": "Solana JSON-RPC getSignaturesForAddress + getTransaction(jsonParsed)",
        "truth_contract": {
            "dex_txn_counts_are_not_wallet_counts": True,
            "unique_wallet_metric_requires_signed_token_owner_delta": True,
            "unresolved_transactions_are_not_guessed": True,
            "first_seen_buyers_are_since_monitor_t0_not_lifetime_new_holders": True,
            "pair_identity_locked": True,
            "production_portfolio_impact": "NONE",
        },
        "coverage": {
            "tracked_wallets_since_t0": 0,
            "tracked_events_24h": 0,
            "last_run_signatures": 0,
            "last_run_resolved_swaps": 0,
            "last_run_unresolved": 0,
            "last_run_resolution_pct": None,
            "coverage_gap": False,
        },
        "windows": {key: _summarize_window([], {}, generated_at - seconds) for key, seconds in WINDOWS.items()},
        "error": error,
    }


def run() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    now = _now_epoch()
    state = _load(STATE_PATH, {})
    started_at = int(state.get("started_at") or 0) or None
    try:
        if not state.get("cursor"):
            latest = _rpc("getSignaturesForAddress", [PAIR, {"limit": 1, "commitment": "confirmed"}]) or []
            if not latest or not latest[0].get("signature"):
                summary = _empty_summary("WAITING_FOR_EXACT_PAIR_ACTIVITY", now, started_at)
                _write(SUMMARY_PATH, summary)
                return summary
            started_at = now
            state = {
                "version": "CYBERLEEK_WALLET_FLOW_STATE_V1",
                "started_at": started_at,
                "cursor": latest[0]["signature"],
                "wallet_first": {},
                "events": [],
                "last_run": {},
            }
            _write(STATE_PATH, state)
            summary = _empty_summary("WARMING_UP_FORWARD_ONLY", now, started_at)
            summary["coverage"]["cursor_established"] = True
            _write(SUMMARY_PATH, summary)
            return summary

        cursor = str(state["cursor"])
        signature_rows, overflow = _fetch_new_signatures(cursor)
        events_new, unresolved = _fetch_transactions(signature_rows)
        events_new.sort(key=lambda e: (int(e["t"]), str(e["sig"])))
        wallet_first = state.get("wallet_first") or {}
        for event in events_new:
            wallet = str(event["w"])
            if wallet not in wallet_first:
                wallet_first[wallet] = {"t": int(event["t"]), "side": str(event["side"])}

        events = list(state.get("events") or []) + events_new
        keep_after = now - WINDOWS["h24"] - 15 * 60
        events = [e for e in events if int(e.get("t") or 0) >= keep_after]
        if signature_rows and signature_rows[0].get("signature"):
            state["cursor"] = signature_rows[0]["signature"]
        state["wallet_first"] = wallet_first
        state["events"] = events
        state["last_run"] = {
            "at": now,
            "signatures": len(signature_rows),
            "resolved": len(events_new),
            "unresolved": unresolved,
            "coverage_gap": overflow,
        }
        _write(STATE_PATH, state)

        denom = len(events_new) + unresolved
        summary = {
            "version": "CYBERLEEK_WALLET_FLOW_V1",
            "generated_at": _iso(now),
            "status": "LIVE_ONCHAIN" if now - int(started_at or now) >= 300 else "WARMING_UP_FORWARD_ONLY",
            "chain": "solana",
            "mint": MINT,
            "exact_pair": PAIR,
            "monitor_started_at": _iso(started_at),
            "source": "Solana JSON-RPC getSignaturesForAddress + getTransaction(jsonParsed)",
            "truth_contract": {
                "dex_txn_counts_are_not_wallet_counts": True,
                "unique_wallet_metric_requires_signed_token_owner_delta": True,
                "unresolved_transactions_are_not_guessed": True,
                "first_seen_buyers_are_since_monitor_t0_not_lifetime_new_holders": True,
                "pair_identity_locked": True,
                "production_portfolio_impact": "NONE",
            },
            "coverage": {
                "tracked_wallets_since_t0": len(wallet_first),
                "tracked_events_24h": len([e for e in events if int(e.get("t") or 0) >= now - WINDOWS["h24"]]),
                "last_run_signatures": len(signature_rows),
                "last_run_resolved_swaps": len(events_new),
                "last_run_unresolved": unresolved,
                "last_run_resolution_pct": round(len(events_new) / denom * 100.0, 2) if denom else 100.0,
                "coverage_gap": overflow,
            },
            "windows": {key: _summarize_window(events, wallet_first, now - seconds) for key, seconds in WINDOWS.items()},
            "error": None,
        }
        _write(SUMMARY_PATH, summary)
        return summary
    except Exception as exc:
        summary = _empty_summary("RPC_ERROR_FAIL_CLOSED", now, started_at, f"{type(exc).__name__}: {exc}"[:500])
        if state:
            wallet_first = state.get("wallet_first") or {}
            events = state.get("events") or []
            summary["coverage"]["tracked_wallets_since_t0"] = len(wallet_first)
            summary["coverage"]["tracked_events_24h"] = len(events)
            summary["windows"] = {key: _summarize_window(events, wallet_first, now - seconds) for key, seconds in WINDOWS.items()}
        _write(SUMMARY_PATH, summary)
        return summary


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result.get("status"), "coverage": result.get("coverage")}, ensure_ascii=False))
