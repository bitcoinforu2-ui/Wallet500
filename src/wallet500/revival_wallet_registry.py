from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import revival_forensics_v2 as forensic

DATA = Path("data")
PRE_STATE = DATA / "revival-prewaking-wallet-evidence-state.json"
WAKING_STATE = DATA / "revival-wallet-evidence-state.json"
FORENSICS_STATE = DATA / "revival-forensics-state.json"
STATE = DATA / "revival-wallet-registry-state.json"
LATEST = DATA / "revival-wallet-registry.json"

VERSION = "REVIVAL_WALLET_REGISTRY_V1"
MODE = "RESEARCH_ONLY_TIME_SAFE_SMART_MONEY_REGISTRY"
POLICY = "REVIVAL_SMART_MONEY_POLICY_V1"
NETWORK = "solana"

MIN_TIER_EXPOSURES = 5
MIN_TIER_TOKENS = 3
ELITE_MIN_EXPOSURES = 8
ELITE_MIN_TOKENS = 5
ELITE_MIN_X2_HIT_RATE = 0.625
ELITE_MAX_LIQ_FAIL_RATE = 0.125
STRONG_MIN_X2_HIT_RATE = 0.50
STRONG_MAX_LIQ_FAIL_RATE = 0.20

WIN_OUTCOMES = {"REVIVAL_X2", "REVIVAL_X4", "REVIVAL_X10"}
FAIL_LIQ_OUTCOME = "FAILED_LIQUIDITY_SURVIVAL"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def epoch(value: object) -> int | None:
    dt = forensic.parse_dt(value)
    return int(dt.timestamp()) if dt else None


def _event_epoch(row: dict) -> int | None:
    try:
        x = int(row.get("t") or 0)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def tier_from_exposures(exposures: list[dict], as_of: object | None = None) -> dict:
    """Score only outcomes that were already completed by the requested time."""
    as_of_epoch = epoch(as_of) if as_of is not None else None
    eligible = []
    for exposure in exposures:
        completed = epoch(exposure.get("completed_at"))
        if not completed:
            continue
        if as_of_epoch is not None and completed > as_of_epoch:
            continue
        eligible.append(exposure)

    tokens = {str(row.get("token_address") or "") for row in eligible if row.get("token_address")}
    wins = sum(1 for row in eligible if row.get("outcome_class") in WIN_OUTCOMES)
    liq_fails = sum(1 for row in eligible if row.get("outcome_class") == FAIL_LIQ_OUTCOME)
    total = len(eligible)
    hit_rate = round(wins / total, 6) if total else None
    liq_fail_rate = round(liq_fails / total, 6) if total else None

    tier = "PENDING_HISTORY"
    reason = "MINIMUM_COMPLETED_PREWAKING_BUY_HISTORY_NOT_MET"
    if total >= MIN_TIER_EXPOSURES and len(tokens) >= MIN_TIER_TOKENS:
        tier = "WATCH"
        reason = "MINIMUM_HISTORY_MET_BELOW_STRONG_THRESHOLDS"
        if (
            hit_rate is not None
            and hit_rate >= STRONG_MIN_X2_HIT_RATE
            and liq_fail_rate is not None
            and liq_fail_rate <= STRONG_MAX_LIQ_FAIL_RATE
        ):
            tier = "STRONG"
            reason = "STRONG_POLICY_MET"
        if (
            total >= ELITE_MIN_EXPOSURES
            and len(tokens) >= ELITE_MIN_TOKENS
            and hit_rate is not None
            and hit_rate >= ELITE_MIN_X2_HIT_RATE
            and liq_fail_rate is not None
            and liq_fail_rate <= ELITE_MAX_LIQ_FAIL_RATE
        ):
            tier = "ELITE"
            reason = "ELITE_POLICY_MET"

    quality_index = None
    if total and hit_rate is not None and liq_fail_rate is not None:
        quality_index = round((0.75 * hit_rate + 0.25 * (1.0 - liq_fail_rate)) * 100.0, 2)

    return {
        "tier": tier,
        "reason": reason,
        "policy": POLICY,
        "completed_pre_waking_buy_exposures": total,
        "distinct_completed_tokens": len(tokens),
        "x2_plus_wins": wins,
        "x2_plus_hit_rate": hit_rate,
        "liquidity_failures": liq_fails,
        "liquidity_fail_rate": liq_fail_rate,
        "quality_index_research_only": quality_index,
        "as_of": str(as_of) if as_of is not None else None,
    }


def _source_tokens(payload: dict, lane: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for mint, state in (payload.get("tokens") or {}).items():
        if not isinstance(state, dict):
            continue
        pair = str(state.get("pair_address") or "").strip()
        if not mint or not pair:
            continue
        out[str(mint)] = {
            "lane": lane,
            "pair_address": pair,
            "monitor_started_at": int(state.get("monitor_started_at") or 0),
            "symbol": state.get("symbol"),
            "events": list(state.get("events") or []),
        }
    return out


def merged_evidence_by_token(pre: dict, waking: dict) -> dict[str, list[dict]]:
    merged: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for lane, payload in (("PRE_WAKING_DEEP_WATCH", pre), ("WAKING_AND_FOLLOWUP", waking)):
        for mint, source in _source_tokens(payload, lane).items():
            pair = source["pair_address"]
            for row in source["events"]:
                wallet = str(row.get("w") or "").strip()
                sig = str(row.get("sig") or "").strip()
                t = _event_epoch(row)
                if not wallet or not sig or not t:
                    continue
                key = (mint, sig, wallet)
                if key in seen:
                    continue
                seen.add(key)
                merged[mint].append(
                    {
                        **row,
                        "token_address": mint,
                        "pair_address": pair,
                        "lane": lane,
                        "monitor_started_at": source["monitor_started_at"],
                    }
                )
    for rows in merged.values():
        rows.sort(key=lambda row: (_event_epoch(row) or 0, str(row.get("sig") or "")))
    return dict(merged)


def build_completed_exposures(forensics_state: dict, merged: dict[str, list[dict]]) -> list[dict]:
    """A historical smart-money exposure exists only for a verified BUY at/before WAKING T0.

    The outcome itself is attachable only after the Forensics event completed. This makes
    exposure records safe to use in later events, never in the event that generated them.
    """
    out: list[dict] = []
    for event in (forensics_state.get("events") or {}).values():
        if not isinstance(event, dict) or event.get("completed") is not True:
            continue
        completed_at = event.get("completed_at")
        completed_epoch = epoch(completed_at)
        t0 = event.get("t0") or {}
        t0_epoch = epoch(t0.get("waking_t0"))
        pair = str(t0.get("pair_address") or "")
        mint = str(event.get("token_address") or "")
        if not completed_epoch or not t0_epoch or not pair or not mint:
            continue
        if completed_epoch < t0_epoch:
            continue

        by_wallet: dict[str, list[dict]] = defaultdict(list)
        for row in merged.get(mint) or []:
            if str(row.get("pair_address") or "") != pair:
                continue
            t = _event_epoch(row)
            if not t or t > t0_epoch or row.get("side") != "BUY":
                continue
            by_wallet[str(row.get("w") or "")].append(row)

        for wallet, buys in by_wallet.items():
            if not wallet:
                continue
            first = min(buys, key=lambda row: _event_epoch(row) or 0)
            out.append(
                {
                    "exposure_id": f"{event.get('event_id')}:{wallet}",
                    "event_id": event.get("event_id"),
                    "wallet": wallet,
                    "token_address": mint,
                    "symbol": event.get("symbol"),
                    "pair_address": pair,
                    "signal_side": "BUY",
                    "signal_at": datetime.fromtimestamp(
                        _event_epoch(first) or 0, tz=timezone.utc
                    ).isoformat(),
                    "signal_lane": first.get("lane"),
                    "waking_t0": t0.get("waking_t0"),
                    "completed_at": completed_at,
                    "outcome_class": event.get("outcome_class"),
                    "eligible_for_future_tiers": True,
                }
            )
    return out


def _raw_wallet_stats(merged: dict[str, list[dict]]) -> dict[str, dict]:
    wallets: dict[str, dict] = {}
    for mint, rows in merged.items():
        for row in rows:
            wallet = str(row.get("w") or "")
            if not wallet:
                continue
            item = wallets.setdefault(
                wallet,
                {
                    "wallet": wallet,
                    "observed_tokens": {},
                    "verified_events": 0,
                    "verified_buys": 0,
                    "verified_sells": 0,
                    "first_seen_at": None,
                    "last_seen_at": None,
                },
            )
            t = _event_epoch(row)
            if not t:
                continue
            item["verified_events"] += 1
            if row.get("side") == "BUY":
                item["verified_buys"] += 1
            elif row.get("side") == "SELL":
                item["verified_sells"] += 1
            token = item["observed_tokens"].setdefault(
                mint,
                {
                    "token_address": mint,
                    "pair_address": row.get("pair_address"),
                    "first_seen_at": t,
                    "last_seen_at": t,
                    "lanes": [],
                },
            )
            token["first_seen_at"] = min(int(token["first_seen_at"]), t)
            token["last_seen_at"] = max(int(token["last_seen_at"]), t)
            lane = str(row.get("lane") or "")
            if lane and lane not in token["lanes"]:
                token["lanes"].append(lane)
            item["first_seen_at"] = t if item["first_seen_at"] is None else min(item["first_seen_at"], t)
            item["last_seen_at"] = t if item["last_seen_at"] is None else max(item["last_seen_at"], t)
    return wallets


def _serialize_wallet(wallet: dict, exposures: list[dict]) -> dict:
    tokens = []
    for row in wallet.get("observed_tokens", {}).values():
        tokens.append(
            {
                **row,
                "first_seen_at": datetime.fromtimestamp(row["first_seen_at"], tz=timezone.utc).isoformat(),
                "last_seen_at": datetime.fromtimestamp(row["last_seen_at"], tz=timezone.utc).isoformat(),
            }
        )
    tokens.sort(key=lambda row: row["last_seen_at"], reverse=True)
    return {
        "wallet": wallet["wallet"],
        "tier_current": tier_from_exposures(exposures),
        "observed_distinct_tokens": len(tokens),
        "verified_events": wallet["verified_events"],
        "verified_buys": wallet["verified_buys"],
        "verified_sells": wallet["verified_sells"],
        "first_seen_at": datetime.fromtimestamp(wallet["first_seen_at"], tz=timezone.utc).isoformat() if wallet.get("first_seen_at") else None,
        "last_seen_at": datetime.fromtimestamp(wallet["last_seen_at"], tz=timezone.utc).isoformat() if wallet.get("last_seen_at") else None,
        "observed_tokens": tokens,
        "completed_exposures": sorted(exposures, key=lambda row: str(row.get("completed_at") or "")),
    }


def _event_bridge(forensics_state: dict, merged: dict[str, list[dict]], exposure_by_wallet: dict[str, list[dict]]) -> list[dict]:
    bridges: list[dict] = []
    for event in (forensics_state.get("events") or {}).values():
        if not isinstance(event, dict):
            continue
        t0 = event.get("t0") or {}
        t0_value = t0.get("waking_t0")
        t0_epoch = epoch(t0_value)
        pair = str(t0.get("pair_address") or "")
        mint = str(event.get("token_address") or "")
        if not t0_epoch or not pair or not mint:
            continue
        wallet_rows: dict[str, list[dict]] = defaultdict(list)
        for row in merged.get(mint) or []:
            if str(row.get("pair_address") or "") != pair:
                continue
            wallet = str(row.get("w") or "")
            if wallet:
                wallet_rows[wallet].append(row)
        ranked = sorted(wallet_rows.items(), key=lambda item: len(item[1]), reverse=True)[:25]
        wallets = []
        influential = 0
        for wallet, rows in ranked:
            pre_buys = [
                row for row in rows
                if row.get("side") == "BUY" and (_event_epoch(row) or 10**20) <= t0_epoch
            ]
            first_seen = min((_event_epoch(row) or 10**20) for row in rows)
            score = tier_from_exposures(exposure_by_wallet.get(wallet, []), as_of=t0_value)
            eligible = bool(pre_buys and score["tier"] in {"ELITE", "STRONG"})
            if eligible:
                influential += 1
            wallets.append(
                {
                    "wallet": wallet,
                    "verified_events_on_token": len(rows),
                    "first_seen_at": datetime.fromtimestamp(first_seen, tz=timezone.utc).isoformat() if first_seen < 10**20 else None,
                    "pre_waking_verified_buy": bool(pre_buys),
                    "tier_as_of_event_t0": score,
                    "eligible_to_influence_event": eligible,
                }
            )
        bridges.append(
            {
                "event_id": event.get("event_id"),
                "token_address": mint,
                "symbol": event.get("symbol"),
                "waking_t0": t0_value,
                "pair_address": pair,
                "wallets": wallets,
                "verified_wallets_seen": len(wallet_rows),
                "historically_qualified_pre_waking_buyers": influential,
                "truth_rule": "TIER_AS_OF_T0_USES_ONLY_OUTCOMES_COMPLETED_BEFORE_THIS_T0",
            }
        )
    return bridges


def run() -> dict:
    pre = load(PRE_STATE, {})
    waking = load(WAKING_STATE, {})
    forensics_state = load(FORENSICS_STATE, {})
    if forensics_state.get("network") != NETWORK or forensics_state.get("no_hindsight") is not True:
        raise SystemExit("REVIVAL_WALLET_REGISTRY_FORENSICS_TRUTH_INVALID")

    merged = merged_evidence_by_token(pre, waking)
    raw_wallets = _raw_wallet_stats(merged)
    completed = build_completed_exposures(forensics_state, merged)

    state = load(
        STATE,
        {
            "version": VERSION,
            "mode": MODE,
            "network": NETWORK,
            "wallets": {},
            "completed_exposures": {},
        },
    )
    stored_exposures = state.setdefault("completed_exposures", {})
    for exposure in completed:
        stored_exposures[str(exposure["exposure_id"])] = exposure

    exposure_by_wallet: dict[str, list[dict]] = defaultdict(list)
    for exposure in stored_exposures.values():
        if isinstance(exposure, dict) and exposure.get("eligible_for_future_tiers") is True:
            exposure_by_wallet[str(exposure.get("wallet") or "")].append(exposure)

    # Persist raw cross-token observations as evidence of overlap, but never convert
    # overlap alone into Smart Money status.
    stored_wallets = state.setdefault("wallets", {})
    for wallet, raw in raw_wallets.items():
        previous = stored_wallets.setdefault(wallet, {"observed_tokens": {}})
        obs = previous.setdefault("observed_tokens", {})
        for mint, token in raw.get("observed_tokens", {}).items():
            old = obs.get(mint)
            if not old:
                obs[mint] = token
            else:
                old["first_seen_at"] = min(int(old.get("first_seen_at") or token["first_seen_at"]), int(token["first_seen_at"]))
                old["last_seen_at"] = max(int(old.get("last_seen_at") or token["last_seen_at"]), int(token["last_seen_at"]))
                for lane in token.get("lanes") or []:
                    if lane not in old.setdefault("lanes", []):
                        old["lanes"].append(lane)
        previous["wallet"] = wallet
        previous["verified_events"] = max(int(previous.get("verified_events") or 0), int(raw.get("verified_events") or 0))
        previous["verified_buys"] = max(int(previous.get("verified_buys") or 0), int(raw.get("verified_buys") or 0))
        previous["verified_sells"] = max(int(previous.get("verified_sells") or 0), int(raw.get("verified_sells") or 0))
        first = raw.get("first_seen_at")
        last = raw.get("last_seen_at")
        if first:
            previous["first_seen_at"] = first if previous.get("first_seen_at") is None else min(int(previous["first_seen_at"]), int(first))
        if last:
            previous["last_seen_at"] = last if previous.get("last_seen_at") is None else max(int(previous["last_seen_at"]), int(last))

    generated = now_iso()
    state.update(
        {
            "version": VERSION,
            "mode": MODE,
            "network": NETWORK,
            "updated_at": generated,
            "policy": POLICY,
            "production_portfolio_impact": "NONE",
            "automatic_buy": False,
            "truth_contract": {
                "wallet_identity": "SIGNED_TARGET_TOKEN_OWNER_DELTA_ONLY",
                "pair_identity": "EXACT_PAIR_ONLY",
                "tier_input": "COMPLETED_PRE_WAKING_VERIFIED_BUY_EXPOSURES_ONLY",
                "as_of_t0_guard": True,
                "raw_overlap_never_implies_smart_money": True,
                "production_portfolio_impact": "NONE",
            },
            "wallets": stored_wallets,
            "completed_exposures": stored_exposures,
        }
    )
    write(STATE, state)

    serialized = []
    for wallet, raw in stored_wallets.items():
        if not raw.get("wallet"):
            raw["wallet"] = wallet
        serialized.append(_serialize_wallet(raw, exposure_by_wallet.get(wallet, [])))
    serialized.sort(
        key=lambda row: (
            row["observed_distinct_tokens"],
            row["verified_events"],
            row["wallet"],
        ),
        reverse=True,
    )
    tier_counts: dict[str, int] = defaultdict(int)
    for row in serialized:
        tier_counts[str((row.get("tier_current") or {}).get("tier") or "UNKNOWN")] += 1

    bridges = _event_bridge(forensics_state, merged, exposure_by_wallet)
    payload = {
        "version": VERSION,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": generated,
        "policy": {
            "version": POLICY,
            "minimum_history": {
                "completed_pre_waking_buy_exposures": MIN_TIER_EXPOSURES,
                "distinct_tokens": MIN_TIER_TOKENS,
            },
            "strong": {
                "min_x2_hit_rate": STRONG_MIN_X2_HIT_RATE,
                "max_liquidity_fail_rate": STRONG_MAX_LIQ_FAIL_RATE,
            },
            "elite": {
                "min_completed_exposures": ELITE_MIN_EXPOSURES,
                "min_distinct_tokens": ELITE_MIN_TOKENS,
                "min_x2_hit_rate": ELITE_MIN_X2_HIT_RATE,
                "max_liquidity_fail_rate": ELITE_MAX_LIQ_FAIL_RATE,
            },
        },
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "truth_contract": state["truth_contract"],
        "counts": {
            "wallets_registry": len(serialized),
            "cross_token_wallets": sum(1 for row in serialized if row["observed_distinct_tokens"] >= 2),
            "completed_eligible_exposures": len(stored_exposures),
            "elite": tier_counts.get("ELITE", 0),
            "strong": tier_counts.get("STRONG", 0),
            "watch": tier_counts.get("WATCH", 0),
            "pending_history": tier_counts.get("PENDING_HISTORY", 0),
        },
        "top_cross_token_wallets": [row for row in serialized if row["observed_distinct_tokens"] >= 2][:50],
        "wallets": serialized[:500],
        "event_bridge": bridges,
    }
    write(LATEST, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({"version": payload["version"], "counts": payload["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
