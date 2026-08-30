from __future__ import annotations


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def evaluate_entry_quality(record: dict, live: dict) -> dict:
    """Prospective quality filter layered on top of the hard market gate.

    This never rewrites historical entries. It only decides whether a newly
    market-eligible candidate should enter the forward $1 research cohort now.
    """
    liq = _f(live.get("liquidity_usd"))
    vol = _f(live.get("volume_h1"))
    turnover = (vol / liq) if liq > 0 else None

    discovery = _f(record.get("entry_price_usd"))
    current = _f(live.get("price_usd"))
    same_pair = str(record.get("entry_pair_address") or "").lower() == str(live.get("pair_address") or record.get("entry_pair_address") or "").lower()
    pre_runup = None
    if same_pair and discovery > 0 and current > 0:
        pre_runup = ((current / discovery) - 1.0) * 100.0

    reasons = []
    status = "QUALITY_PASS"

    # Data-integrity guard: huge ratios are more likely denominator/quote errors
    # than useful alpha. Quarantine them instead of teaching the engine from them.
    if pre_runup is not None and pre_runup > 100000:
        status = "DATA_INTEGRITY_REVIEW"
        reasons.append("EXTREME_DISCOVERY_TO_ENTRY_RATIO")

    # Anti-chase rule discovered by the current forward cohort research.
    elif pre_runup is not None and pre_runup > 25.0:
        status = "HOT_WATCH_DELAY"
        reasons.append("PRE_ENTRY_RUNUP_GT_25PCT")

    # Near-floor liquidity + overheated turnover was the clearest severe-loss pattern.
    elif liq < 100000.0 and turnover is not None and turnover > 2.0:
        status = "HOT_WATCH_DELAY"
        reasons.append("LOW_LIQ_HIGH_TURNOVER")

    return {
        "status": status,
        "pass": status == "QUALITY_PASS",
        "reasons": reasons,
        "pre_entry_runup_pct": round(pre_runup, 6) if pre_runup is not None else None,
        "turnover_h1": round(turnover, 6) if turnover is not None else None,
        "policy": "ANTI_CHASE_V1: delay new entry when same-pair pre-entry run-up >25%; delay when liquidity <100K and H1 turnover >2x; quarantine extreme discovery/entry ratios. Hard liquidity floor remains 50K.",
    }
