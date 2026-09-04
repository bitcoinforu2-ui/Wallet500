from __future__ import annotations

import json
import os
from pathlib import Path

from . import revival_forensics_v2 as forensic
from . import revival_wallet_evidence as collector

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-prewaking-wallet-evidence-state.json"
LATEST = DATA / "revival-prewaking-wallet-evidence.json"

VERSION = "REVIVAL_PREWAKING_WALLET_EVIDENCE_V1"
MODE = "RESEARCH_ONLY_PREWAKING_EXACT_PAIR_WALLET_EVIDENCE"
MAX_TARGETS = int(os.environ.get("REVIVAL_PREWAKING_MAX_TARGETS", "8"))
MAX_SIGNATURES = int(os.environ.get("REVIVAL_PREWAKING_MAX_SIGNATURES", "45"))
PRIORITY_SLOTS = int(os.environ.get("REVIVAL_PREWAKING_PRIORITY_SLOTS", "4"))
KEEP_SECONDS = int(os.environ.get("REVIVAL_PREWAKING_KEEP_SECONDS", str(7 * 24 * 60 * 60)))
ACTIVE_LIQUIDITY_USD = float(os.environ.get("REVIVAL_PREWAKING_ACTIVE_LIQUIDITY_USD", "50000"))
ACTIVE_VOLUME_24H_USD = float(os.environ.get("REVIVAL_PREWAKING_ACTIVE_VOLUME_24H_USD", "25000"))
WARM_LIQUIDITY_USD = float(os.environ.get("REVIVAL_PREWAKING_WARM_LIQUIDITY_USD", "10000"))
WARM_VOLUME_24H_USD = float(os.environ.get("REVIVAL_PREWAKING_WARM_VOLUME_24H_USD", "5000"))


def _n(value: object, default: float = 0.0) -> float:
    try:
        x = float(value)
        if x != x:
            return default
        return x
    except (TypeError, ValueError):
        return default


def _validate_revival(revival: dict) -> None:
    if (
        revival.get("network") != "solana"
        or revival.get("no_hindsight") is not True
        or revival.get("production_portfolio_impact") != "NONE"
    ):
        raise RuntimeError("PREWAKING_WALLET_SOURCE_TRUTH_CONTRACT_INVALID")


def _activity_tier(coin: dict) -> tuple[int, str, float, float]:
    """Research scheduling tier only; never changes Revival/Production status.

    Exact-pair liquidity and exact-pair 24h volume are used to keep scarce RPC slots
    focused on markets that are actually alive. COLD rows remain in the rotating
    coverage universe, so historical misses are never erased by this prioritization.
    """
    liq = _n(coin.get("dex_pair_liquidity_usd"))
    vol = _n(coin.get("dex_pair_volume_24h_usd") or coin.get("volume_24h_usd"))
    if liq >= ACTIVE_LIQUIDITY_USD or vol >= ACTIVE_VOLUME_24H_USD:
        return 2, "ACTIVE_DEEP_WATCH", liq, vol
    if liq >= WARM_LIQUIDITY_USD or vol >= WARM_VOLUME_24H_USD:
        return 1, "WARM_DEEP_WATCH", liq, vol
    return 0, "COLD_DEEP_WATCH", liq, vol


def _ranked_candidates(revival: dict) -> list[dict]:
    _validate_revival(revival)
    rows: list[tuple[tuple[float, float, float, float, str], dict]] = []
    for coin in revival.get("coins") or []:
        if coin.get("watch_status") != "DEEP_WATCH":
            continue
        if coin.get("market_age_verified") is not True:
            continue
        if int(_n(coin.get("market_age_min_days"), 0)) < forensic.MIN_AGE_DAYS:
            continue
        mint = forensic.token_key(coin)
        pair = forensic.exact_pair(coin)
        if not mint or not pair:
            continue
        activity_rank, activity_tier, liq, vol = _activity_tier(coin)
        revival_score = _n(coin.get("revival_score_verified"))
        rank = (activity_rank, revival_score, vol, liq, mint)
        rows.append((rank, {
            "token_address": mint,
            "symbol": coin.get("symbol"),
            "pair_address": pair,
            "reason": "PRE_WAKING_DEEP_WATCH",
            "activity_tier": activity_tier,
            "activity_rank": activity_rank,
            "exact_pair_liquidity_usd": liq,
            "exact_pair_volume_24h_usd": vol,
            "prewaking_rank_score": round(revival_score, 6),
            "source_revival_generated_at": revival.get("generated_at"),
        }))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows]


def select_targets(revival: dict, previous: dict | None = None, *, max_targets: int | None = None,
                   priority_slots: int | None = None) -> list[dict]:
    """Keep active high-priority candidates persistent while rotating all remaining rows.

    Rotation is based only on the previously published PRE-WAKING target set. It never
    uses future outcomes and it preserves exact token/pair identity. ACTIVE/WARM rows
    are ranked ahead of COLD rows, while spare rotation slots still cover the complete
    DEEP_WATCH universe so cold research cases cannot disappear from learning.
    """
    ranked = _ranked_candidates(revival)
    cap = max(0, int(MAX_TARGETS if max_targets is None else max_targets))
    pslots = max(0, int(PRIORITY_SLOTS if priority_slots is None else priority_slots))
    pslots = min(pslots, cap, len(ranked))
    if cap <= 0 or not ranked:
        return []

    priority = [dict(row, selection_lane="PRIORITY_PERSISTENT") for row in ranked[:pslots]]
    remainder = ranked[pslots:]
    rotation_slots = min(cap - len(priority), len(remainder))
    if rotation_slots <= 0:
        return priority

    high_tokens = {row["token_address"] for row in priority}
    previous_rotation = [
        str(row.get("token_address") or "")
        for row in ((previous or {}).get("tokens") or [])
        if isinstance(row, dict) and str(row.get("token_address") or "") not in high_tokens
    ]
    index_by_token = {row["token_address"]: i for i, row in enumerate(remainder)}
    previous_indices = [index_by_token[t] for t in previous_rotation if t in index_by_token]
    start = (max(previous_indices) + 1) % len(remainder) if previous_indices else 0

    rotation = []
    for offset in range(len(remainder)):
        if len(rotation) >= rotation_slots:
            break
        row = remainder[(start + offset) % len(remainder)]
        rotation.append(dict(row, selection_lane="ROTATION_COVERAGE"))
    return priority + rotation


def _targets() -> list[dict]:
    revival = collector._load(REVIVAL, {})
    previous = collector._load(LATEST, {})
    return select_targets(revival, previous)


def run() -> dict:
    # Freeze the selected set before collector.run(). The collector overwrites LATEST;
    # recomputing after that would advance the rotation twice in one run.
    revival = collector._load(REVIVAL, {})
    previous = collector._load(LATEST, {})
    ranked = _ranked_candidates(revival)
    selected = select_targets(revival, previous)
    candidate_count = len(ranked)

    # Reuse the signed-token-owner-delta collector in an isolated PRE-WAKING state lane.
    collector.STATE = STATE
    collector.LATEST = LATEST
    collector.MAX_SIGNATURES_PER_TOKEN_PER_RUN = MAX_SIGNATURES
    collector.KEEP_SECONDS = KEEP_SECONDS
    collector._targets = lambda: selected

    payload = collector.run()
    target_map = {row["token_address"]: row for row in selected}
    effective_priority = min(PRIORITY_SLOTS, MAX_TARGETS, candidate_count)
    activity_counts = {
        "active": sum(1 for r in ranked if r.get("activity_tier") == "ACTIVE_DEEP_WATCH"),
        "warm": sum(1 for r in ranked if r.get("activity_tier") == "WARM_DEEP_WATCH"),
        "cold": sum(1 for r in ranked if r.get("activity_tier") == "COLD_DEEP_WATCH"),
    }
    payload["version"] = VERSION
    payload["mode"] = MODE
    payload["lane"] = "PRE_WAKING_DEEP_WATCH"
    payload["selection_policy"] = {
        "status_required": "DEEP_WATCH",
        "market_age_verified_min_days": forensic.MIN_AGE_DAYS,
        "exact_pair_required": True,
        "max_targets": MAX_TARGETS,
        "priority_slots": effective_priority,
        "rotation_slots": max(0, min(MAX_TARGETS - effective_priority, candidate_count - effective_priority)),
        "coverage_rotation": True,
        "rotation_state_source": "PREVIOUS_PUBLISHED_TARGET_SET_ONLY",
        "candidate_universe": candidate_count,
        "activity_counts": activity_counts,
        "activity_thresholds": {
            "active_pair_liquidity_usd": ACTIVE_LIQUIDITY_USD,
            "active_pair_volume_24h_usd": ACTIVE_VOLUME_24H_USD,
            "warm_pair_liquidity_usd": WARM_LIQUIDITY_USD,
            "warm_pair_volume_24h_usd": WARM_VOLUME_24H_USD,
        },
        "rank_order": [
            "activity_tier_desc",
            "revival_score_verified_desc",
            "exact_pair_volume_24h_desc",
            "exact_pair_liquidity_desc",
            "token_address_desc_tiebreak",
        ],
        "cold_rows_removed_from_research": False,
        "future_data_used": False,
        "production_effect": False,
    }
    payload["collector_limits"] = {
        "max_signatures_per_token_per_run": MAX_SIGNATURES,
        "keep_seconds": KEEP_SECONDS,
        "max_signature_budget_per_run": MAX_TARGETS * MAX_SIGNATURES,
    }
    payload["smart_money_bridge"] = {
        "raw_verified_wallet_evidence_connected": True,
        "wallet500_tiers_connected": False,
        "reason": "HISTORICAL_REGISTRY_SCORES_ONLY_AFTER_COMPLETED_OUTCOMES",
    }
    for row in payload.get("tokens") or []:
        target = target_map.get(str(row.get("token_address") or "")) or {}
        row["target_reason"] = target.get("reason")
        row["selection_lane"] = target.get("selection_lane")
        row["activity_tier"] = target.get("activity_tier")
        row["activity_rank"] = target.get("activity_rank")
        row["prewaking_rank_score"] = target.get("prewaking_rank_score")
        row["source_revival_generated_at"] = target.get("source_revival_generated_at")
        (row.setdefault("coverage", {}))["eligible_as_forensics_t0_wallet_evidence"] = False
        row["future_t0_eligibility"] = "POTENTIAL_IF_WAKING_OCCURS_AFTER_MONITOR_START"
    collector._write(LATEST, payload)

    state = collector._load(STATE, {})
    state["version"] = VERSION
    state["mode"] = MODE
    state["lane"] = "PRE_WAKING_DEEP_WATCH"
    state["selection_policy"] = payload["selection_policy"]
    collector._write(STATE, state)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "version": payload.get("version"),
        "targets": payload.get("targets"),
        "selection_policy": payload.get("selection_policy"),
        "collector_limits": payload.get("collector_limits"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
