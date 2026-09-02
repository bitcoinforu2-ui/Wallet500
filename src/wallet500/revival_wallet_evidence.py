from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import cyberleek_wallet_flow as base
from . import revival_forensics_v2 as forensic

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
FORENSICS_STATE = DATA / "revival-forensics-state.json"
STATE = DATA / "revival-wallet-evidence-state.json"
LATEST = DATA / "revival-wallet-evidence.json"

VERSION = "REVIVAL_WALLET_EVIDENCE_V1"
MODE = "RESEARCH_ONLY_EXACT_PAIR_WALLET_EVIDENCE"
NETWORK = "solana"
MAX_SIGNATURES_PER_TOKEN_PER_RUN = int(
    os.environ.get("REVIVAL_WALLET_MAX_SIGNATURES", "180")
)
MIN_RESOLUTION_PCT = float(
    os.environ.get("REVIVAL_WALLET_MIN_RESOLUTION_PCT", "80")
)
KEEP_SECONDS = 25 * 60 * 60
WINDOWS = {
    "m5": 5 * 60,
    "m15": 15 * 60,
    "h1": 60 * 60,
    "h4": 4 * 60 * 60,
    "h12": 12 * 60 * 60,
    "h24": 24 * 60 * 60,
}
EPSILON = 1e-12


def _epoch_now() -> int:
    return int(time.time())


def _iso(epoch: int | float | None = None) -> str:
    if epoch is None:
        epoch = _epoch_now()
    return datetime.fromtimestamp(
        float(epoch), tz=timezone.utc
    ).isoformat().replace("+00:00", "Z")


def _load(path: Path, default: Any) -> Any:
    try:
        return (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else default
        )
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _targets() -> list[dict]:
    """Current WAKING plus not-yet-completed forensic follow-up events."""
    revival = _load(REVIVAL, {})
    if (
        revival.get("network") != NETWORK
        or revival.get("no_hindsight") is not True
        or revival.get("production_portfolio_impact") != "NONE"
    ):
        raise RuntimeError("REVIVAL_WALLET_SOURCE_TRUTH_CONTRACT_INVALID")

    by_mint: dict[str, dict] = {}
    for coin in revival.get("coins") or []:
        if coin.get("watch_status") != forensic.WAKING_STATUS:
            continue
        mint = forensic.token_key(coin)
        pair = forensic.exact_pair(coin)
        if not mint or not pair:
            continue
        by_mint[mint] = {
            "token_address": mint,
            "symbol": coin.get("symbol"),
            "pair_address": pair,
            "reason": "CURRENT_WAKING",
        }

    fs = _load(FORENSICS_STATE, {})
    for event in (fs.get("events") or {}).values():
        if not isinstance(event, dict) or event.get("completed"):
            continue
        t0 = event.get("t0") or {}
        mint = str(event.get("token_address") or "").strip()
        pair = str(t0.get("pair_address") or "").strip()
        if not mint or not pair:
            continue
        by_mint[mint] = {
            "token_address": mint,
            "symbol": event.get("symbol"),
            "pair_address": pair,
            "forensics_event_id": event.get("event_id"),
            "forensics_t0": t0.get("waking_t0"),
            "reason": "FORENSICS_24H_FOLLOWUP",
        }

    return list(by_mint.values())


def _fetch_new_signatures(pair: str, cursor: str) -> tuple[list[dict], bool]:
    rows_all: list[dict] = []
    before = None
    overflow = False
    while len(rows_all) < MAX_SIGNATURES_PER_TOKEN_PER_RUN:
        limit = min(1000, MAX_SIGNATURES_PER_TOKEN_PER_RUN - len(rows_all))
        opts: dict[str, Any] = {
            "limit": limit,
            "commitment": "confirmed",
            "until": cursor,
        }
        if before:
            opts["before"] = before
        rows = base._rpc("getSignaturesForAddress", [pair, opts]) or []
        if not rows:
            break
        rows_all.extend(rows)
        if len(rows) < limit:
            break
        before = rows[-1].get("signature")
        if not before:
            break
    if len(rows_all) >= MAX_SIGNATURES_PER_TOKEN_PER_RUN:
        overflow = True
    return rows_all, overflow


def _extract_trade(
    tx: dict | None,
    signature: str,
    mint: str,
    block_time: int | None = None,
) -> dict | None:
    """Resolve only signed owners with a real target-mint balance delta."""
    if not isinstance(tx, dict) or (tx.get("meta") or {}).get("err") is not None:
        return None
    signers = base._signers(tx)
    if not signers:
        return None
    deltas = base._mint_owner_deltas(tx, mint)
    candidates = [
        (wallet, delta)
        for wallet, delta in deltas.items()
        if wallet in signers and abs(delta) > EPSILON
    ]
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


def _fetch_transactions(rows: list[dict], mint: str) -> tuple[list[dict], int]:
    events: list[dict] = []
    unresolved = 0
    valid = [
        row
        for row in rows
        if row.get("err") is None and row.get("signature")
    ]
    failures = 0
    for index, row in enumerate(valid):
        try:
            tx = base._rpc(
                "getTransaction",
                [
                    row["signature"],
                    {
                        "encoding": "jsonParsed",
                        "commitment": "confirmed",
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            )
        except Exception:
            tx = None
            failures += 1
        event = _extract_trade(
            tx,
            str(row["signature"]),
            mint,
            row.get("blockTime"),
        )
        if event:
            events.append(event)
        else:
            unresolved += 1
        if index + 1 < len(valid):
            time.sleep(0.035)
    if valid and failures == len(valid):
        raise RuntimeError("RPC_GETTRANSACTION_ALL_READS_FAILED")
    return events, unresolved


def _window(events: list[dict], wallet_first: dict[str, dict], cutoff: int) -> dict:
    rows = [event for event in events if int(event.get("t") or 0) >= cutoff]
    buys = [event for event in rows if event.get("side") == "BUY"]
    sells = [event for event in rows if event.get("side") == "SELL"]
    buy_wallets = {str(event["w"]) for event in buys}
    sell_wallets = {str(event["w"]) for event in sells}
    traders = buy_wallets | sell_wallets
    first_seen_buyers = {
        wallet
        for wallet in buy_wallets
        if (wallet_first.get(wallet) or {}).get("side") == "BUY"
        and int((wallet_first.get(wallet) or {}).get("t") or 0) >= cutoff
    }
    net: dict[str, float] = defaultdict(float)
    tx_counts: Counter[str] = Counter()
    for event in rows:
        wallet = str(event["w"])
        net[wallet] += float(event.get("token_delta") or 0)
        tx_counts[wallet] += 1
    top10_tx = sum(count for _, count in tx_counts.most_common(10))
    return {
        "resolved_swaps": len(rows),
        "unique_traders": len(traders),
        "unique_buyers": len(buy_wallets),
        "unique_sellers": len(sell_wallets),
        "first_seen_buyers_since_monitor_t0": len(first_seen_buyers),
        "net_accumulating_wallets": sum(1 for value in net.values() if value > EPSILON),
        "net_distributing_wallets": sum(1 for value in net.values() if value < -EPSILON),
        "top10_wallet_tx_share_pct": (
            round(top10_tx / len(rows) * 100.0, 2) if rows else None
        ),
        "wallet_buy_sell_ratio": (
            round(len(buy_wallets) / len(sell_wallets), 4)
            if sell_wallets
            else None
        ),
    }


def _top_wallets(events: list[dict], limit: int = 20) -> list[dict]:
    stats: dict[str, dict] = {}
    for event in events:
        wallet = str(event.get("w") or "")
        if not wallet:
            continue
        row = stats.setdefault(
            wallet,
            {
                "wallet": wallet,
                "buys": 0,
                "sells": 0,
                "net_token_delta": 0.0,
                "first_seen_at": int(event.get("t") or 0),
                "last_seen_at": int(event.get("t") or 0),
            },
        )
        side = str(event.get("side") or "")
        if side == "BUY":
            row["buys"] += 1
        elif side == "SELL":
            row["sells"] += 1
        row["net_token_delta"] += float(event.get("token_delta") or 0)
        t = int(event.get("t") or 0)
        row["first_seen_at"] = min(row["first_seen_at"], t)
        row["last_seen_at"] = max(row["last_seen_at"], t)
    ranked = sorted(
        stats.values(),
        key=lambda row: (
            row["buys"] + row["sells"],
            abs(row["net_token_delta"]),
        ),
        reverse=True,
    )[:limit]
    for row in ranked:
        row["net_token_delta"] = round(row["net_token_delta"], 9)
        row["first_seen_at"] = _iso(row["first_seen_at"])
        row["last_seen_at"] = _iso(row["last_seen_at"])
        row["tier"] = "UNSCORED_RAW_VERIFIED"
    return ranked


def _init_target(target: dict, now: int) -> tuple[dict, dict]:
    pair = target["pair_address"]
    latest = base._rpc(
        "getSignaturesForAddress",
        [pair, {"limit": 1, "commitment": "confirmed"}],
    ) or []
    state = {
        "pair_address": pair,
        "symbol": target.get("symbol"),
        "monitor_started_at": now,
        "cursor": latest[0].get("signature") if latest else None,
        "wallet_first": {},
        "events": [],
        "last_run": {
            "at": now,
            "status": "WARMING_UP_FORWARD_ONLY",
            "signatures": 0,
            "resolved": 0,
            "unresolved": 0,
            "coverage_gap": False,
        },
    }
    return state, _summary_for(target, state, now)


def _summary_for(target: dict, state: dict, now: int) -> dict:
    events = list(state.get("events") or [])
    wallet_first = state.get("wallet_first") or {}
    last = state.get("last_run") or {}
    resolved = int(last.get("resolved") or 0)
    unresolved = int(last.get("unresolved") or 0)
    denom = resolved + unresolved
    resolution_pct = (
        round(resolved / denom * 100.0, 2) if denom else None
    )
    gap = bool(last.get("coverage_gap")) or (
        resolution_pct is not None and resolution_pct < MIN_RESOLUTION_PCT
    )
    forensic_t0 = forensic.parse_dt(target.get("forensics_t0"))
    monitor_started = datetime.fromtimestamp(
        int(state.get("monitor_started_at") or now), tz=timezone.utc
    )
    t0_eligible = bool(forensic_t0 and monitor_started <= forensic_t0)
    return {
        "token_address": target["token_address"],
        "symbol": target.get("symbol"),
        "exact_pair": target["pair_address"],
        "forensics_event_id": target.get("forensics_event_id"),
        "forensics_t0": target.get("forensics_t0"),
        "monitor_started_at": _iso(state.get("monitor_started_at") or now),
        "status": last.get("status") or "LIVE_FORWARD_ONLY",
        "truth_contract": {
            "pair_identity_locked": True,
            "wallet_identity_requires_signed_token_owner_delta": True,
            "unresolved_transactions_are_not_guessed": True,
            "monitor_is_forward_only": True,
            "wallet_t0_claim_requires_monitor_started_before_or_at_forensics_t0": True,
            "production_portfolio_impact": "NONE",
        },
        "coverage": {
            "tracked_wallets_since_monitor_t0": len(wallet_first),
            "tracked_events_24h": len(events),
            "last_run_signatures": int(last.get("signatures") or 0),
            "last_run_resolved_swaps": resolved,
            "last_run_unresolved": unresolved,
            "last_run_resolution_pct": resolution_pct,
            "minimum_resolution_pct": MIN_RESOLUTION_PCT,
            "coverage_gap": gap,
            "coverage_quality": "PARTIAL" if gap else "ACCEPTABLE",
            "eligible_as_forensics_t0_wallet_evidence": t0_eligible,
        },
        "windows": {
            key: _window(events, wallet_first, now - seconds)
            for key, seconds in WINDOWS.items()
        },
        "top_wallets_raw_verified": _top_wallets(events),
        "smart_money_tiers": {
            "status": "NOT_SCORED_NO_CROSS_TOKEN_HISTORY_YET",
            "elite": 0,
            "strong": 0,
            "watch": 0,
        },
    }


def run() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    now = _epoch_now()
    targets = _targets()
    target_by = {row["token_address"]: row for row in targets}
    state = _load(
        STATE,
        {
            "version": VERSION,
            "mode": MODE,
            "network": NETWORK,
            "tokens": {},
        },
    )
    token_states = state.setdefault("tokens", {})
    summaries: list[dict] = []

    for mint, target in target_by.items():
        token_state = token_states.get(mint)
        if (
            not isinstance(token_state, dict)
            or token_state.get("pair_address") != target["pair_address"]
        ):
            try:
                token_state, summary = _init_target(target, now)
                token_states[mint] = token_state
                summaries.append(summary)
            except Exception as exc:
                summaries.append(
                    {
                        "token_address": mint,
                        "symbol": target.get("symbol"),
                        "exact_pair": target["pair_address"],
                        "status": "RPC_ERROR_FAIL_CLOSED",
                        "error": str(exc),
                        "coverage": {
                            "coverage_gap": True,
                            "coverage_quality": "PARTIAL",
                            "eligible_as_forensics_t0_wallet_evidence": False,
                        },
                        "smart_money_tiers": {
                            "status": "NOT_SCORED_NO_VERIFIED_WALLET_DATA",
                            "elite": 0,
                            "strong": 0,
                            "watch": 0,
                        },
                    }
                )
            continue

        cursor = str(token_state.get("cursor") or "")
        if not cursor:
            try:
                fresh_state, summary = _init_target(target, now)
                token_states[mint] = fresh_state
                summaries.append(summary)
            except Exception as exc:
                token_state["last_run"] = {
                    "at": now,
                    "status": "RPC_ERROR_FAIL_CLOSED",
                    "signatures": 0,
                    "resolved": 0,
                    "unresolved": 0,
                    "coverage_gap": True,
                    "error": str(exc),
                }
                summaries.append(_summary_for(target, token_state, now))
            continue

        try:
            signature_rows, overflow = _fetch_new_signatures(
                target["pair_address"], cursor
            )
            events_new, unresolved = _fetch_transactions(signature_rows, mint)
            events_new.sort(key=lambda row: (int(row["t"]), str(row["sig"])))
            wallet_first = token_state.setdefault("wallet_first", {})
            for event in events_new:
                wallet = str(event["w"])
                if wallet not in wallet_first:
                    wallet_first[wallet] = {
                        "t": int(event["t"]),
                        "side": str(event["side"]),
                    }
            events = list(token_state.get("events") or []) + events_new
            events = [
                event
                for event in events
                if int(event.get("t") or 0) >= now - KEEP_SECONDS
            ]
            token_state["events"] = events
            if signature_rows and signature_rows[0].get("signature"):
                token_state["cursor"] = signature_rows[0]["signature"]
            token_state["last_run"] = {
                "at": now,
                "status": "LIVE_FORWARD_ONLY",
                "signatures": len(signature_rows),
                "resolved": len(events_new),
                "unresolved": unresolved,
                "coverage_gap": overflow,
            }
        except Exception as exc:
            token_state["last_run"] = {
                "at": now,
                "status": "RPC_ERROR_FAIL_CLOSED",
                "signatures": 0,
                "resolved": 0,
                "unresolved": 0,
                "coverage_gap": True,
                "error": str(exc),
            }
        summaries.append(_summary_for(target, token_state, now))

    state.update(
        {
            "version": VERSION,
            "mode": MODE,
            "network": NETWORK,
            "updated_at": _iso(now),
            "truth_contract": {
                "exact_pair_only": True,
                "signed_token_owner_delta_only": True,
                "unresolved_not_guessed": True,
                "forward_only": True,
                "production_portfolio_impact": "NONE",
            },
            "tokens": token_states,
        }
    )
    _write(STATE, state)

    payload = {
        "version": VERSION,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": _iso(now),
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "truth_contract": state["truth_contract"],
        "targets": len(targets),
        "tokens": summaries,
        "smart_money_bridge": {
            "raw_verified_wallet_evidence_connected": True,
            "wallet500_tiers_connected": False,
            "reason": "NO_VERIFIED_CROSS_TOKEN_WALLET_HISTORY_REGISTRY_AVAILABLE_YET",
        },
    }
    _write(LATEST, payload)
    return payload


def main() -> None:
    payload = run()
    print(
        json.dumps(
            {
                "version": payload["version"],
                "targets": payload["targets"],
                "bridge": payload["smart_money_bridge"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
