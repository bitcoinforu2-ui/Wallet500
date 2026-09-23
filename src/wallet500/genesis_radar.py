from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

PAPER_ENTRY_USD = 5.0

ALERT_STAGE_WATCH = "WATCH"
ALERT_STAGE_HOT_WATCH = "HOT_WATCH"
ALERT_STAGE_REAL_ALERT = "REAL_ALERT"
ACTIONABLE_STATUSES = {"PAPER_BUY_CANDIDATE", "STRONG_GENESIS", "EXCEPTIONAL_GENESIS"}
ACTIVE_AGE_BANDS = {"EARLY_WATCH", "PRIME_GENESIS_WINDOW", "LATE_GENESIS_WINDOW"}


@dataclass(frozen=True)
class GenesisThresholds:
    min_liquidity_usd: float = 50_000.0
    preferred_liquidity_usd: float = 100_000.0
    min_holders: int = 250
    preferred_holders: int = 500
    top10_preferred_pct: float = 35.0
    top10_hard_max_pct: float = 50.0
    largest_wallet_preferred_pct: float = 8.0
    largest_wallet_hard_max_pct: float = 12.0
    min_buy_sell_ratio: float = 1.20
    min_quality_wallets: int = 2
    late_no_chase_pct: float = 5000.0


THRESHOLDS = GenesisThresholds()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _maybe_num(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> Optional[bool]:
    if value is True:
        return True
    if value is False:
        return False
    return None


def _score_band(score: float) -> str:
    if score >= 93:
        return "EXCEPTIONAL_GENESIS"
    if score >= 85:
        return "STRONG_GENESIS"
    if score >= 75:
        return "PAPER_BUY_CANDIDATE"
    if score >= 65:
        return "EVIDENCE_READY"
    if score >= 50:
        return "WATCH"
    return "IGNORE"


def extension_band(gain_pct: float) -> str:
    if gain_pct > 5000:
        return "LATE_NO_CHASE"
    if gain_pct > 1000:
        return "VERY_EXTENDED"
    if gain_pct > 300:
        return "EXTENDED"
    if gain_pct > 100:
        return "ELEVATED"
    return "NORMAL"


def age_band(age_minutes: float) -> str:
    if age_minutes < 15:
        return "DISCOVERY_ONLY"
    if age_minutes < 60:
        return "EARLY_WATCH"
    if age_minutes < 360:
        return "PRIME_GENESIS_WINDOW"
    if age_minutes < 1440:
        return "LATE_GENESIS_WINDOW"
    if age_minutes <= 10080:
        return "POST_GENESIS_SURVIVAL"
    return "OUTSIDE_GENESIS"


def source_catalyst(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Score trusted discovery-source evidence without bypassing safety gates.

    Moonshot direct views are intentionally weighted by timing: a new/finalized
    appearance is more useful than retrospective trending/top placement.
    """
    raw_sources = candidate.get("sources") or [candidate.get("source")]
    sources = [str(x or "").strip().lower() for x in raw_sources if str(x or "").strip()]
    confirmations = max(
        int(_num(candidate.get("source_confirmations"), len(sources) or 1)),
        len(set(sources)) or 1,
    )

    moonshot_views = sorted({
        source.split("moonshot:", 1)[1]
        for source in sources
        if source.startswith("moonshot:") and ":" in source
    })

    reasons: List[str] = []
    base = 0.0
    if "finalized" in moonshot_views:
        base = 10.0
        reasons.append("MOONSHOT_FINALIZED")
    elif "new" in moonshot_views:
        base = 8.0
        reasons.append("MOONSHOT_NEW")
    elif "rising" in moonshot_views:
        base = 7.0
        reasons.append("MOONSHOT_RISING")
    elif any(view in {"trending", "top"} for view in moonshot_views):
        base = 4.0
        reasons.append("MOONSHOT_MOMENTUM_VIEW")

    if any(source == "birdeye:new_listing" for source in sources):
        base = max(base, 3.0)
        reasons.append("BIRDEYE_NEW_LISTING")
    if any("token-boosts" in source for source in sources):
        base = max(base, 2.0)
        reasons.append("DEXSCREENER_BOOST")

    cross_source_bonus = min(4.0, max(0, confirmations - 1) * 2.0)
    if cross_source_bonus:
        reasons.append("CROSS_SOURCE_CONFIRMATION")

    score = min(10.0, base + cross_source_bonus)
    return {
        "score": round(score, 1),
        "moonshot_confirmed": bool(moonshot_views),
        "moonshot_views": moonshot_views,
        "source_confirmations": confirmations,
        "reasons": reasons,
    }


def safety_gate(candidate: Dict[str, Any], t: GenesisThresholds = THRESHOLDS) -> Dict[str, Any]:
    hard_blocks: List[str] = []
    research_only: List[str] = []

    liquidity = _maybe_num(candidate.get("liquidity_usd"))
    holders = _maybe_num(candidate.get("holders"))
    top10 = _maybe_num(candidate.get("top10_ex_system_pct"))
    largest = _maybe_num(candidate.get("largest_non_system_wallet_pct"))

    if liquidity is None:
        research_only.append("UNKNOWN_LIQUIDITY")
    elif liquidity < t.min_liquidity_usd:
        hard_blocks.append("BLOCKED_LOW_LIQUIDITY")

    if holders is None:
        research_only.append("UNKNOWN_HOLDERS")
    elif holders < t.min_holders:
        hard_blocks.append("BLOCKED_LOW_HOLDERS")

    if top10 is None:
        research_only.append("UNKNOWN_CONCENTRATION_TOP10")
    elif top10 > t.top10_hard_max_pct:
        hard_blocks.append("BLOCKED_CONCENTRATION_TOP10")

    if largest is None:
        research_only.append("UNKNOWN_CONCENTRATION_WALLET")
    elif largest > t.largest_wallet_hard_max_pct:
        hard_blocks.append("BLOCKED_CONCENTRATION_WALLET")

    for key, state in (
        ("MINT_AUTHORITY", _bool(candidate.get("mint_authority_safe"))),
        ("FREEZE_AUTHORITY", _bool(candidate.get("freeze_authority_safe"))),
        ("TRANSFER_RESTRICTIONS", _bool(candidate.get("transfer_restrictions_safe"))),
        ("LP_INTEGRITY", _bool(candidate.get("lp_integrity_safe"))),
    ):
        if state is False:
            hard_blocks.append(f"BLOCKED_{key}")
        elif state is None:
            research_only.append(f"UNKNOWN_{key}")

    return {
        "passed": not hard_blocks and not research_only,
        "hard_blocks": hard_blocks,
        "research_only_reasons": research_only,
    }


def acceleration_signals(candidate: Dict[str, Any], t: GenesisThresholds = THRESHOLDS) -> Dict[str, Any]:
    signals: List[str] = []
    primary = 0

    vol15 = _num(candidate.get("volume_15m_usd"))
    prev15 = _num(candidate.get("prev_volume_15m_usd"))
    vol30 = _num(candidate.get("volume_30m_usd"))
    baseline30 = _num(candidate.get("baseline_volume_30m_usd"))
    if (prev15 > 0 and vol15 / prev15 >= 2.0) or (baseline30 > 0 and vol30 / baseline30 >= 2.5):
        signals.append("VOLUME_ACCELERATION")
        primary += 1

    buyers15 = _num(candidate.get("unique_buyers_15m"))
    prev_buyers15 = _num(candidate.get("prev_unique_buyers_15m"))
    buys = _num(candidate.get("buys_15m"))
    sells = _num(candidate.get("sells_15m"))
    ratio = buys / max(sells, 1.0)
    if prev_buyers15 > 0 and buyers15 / prev_buyers15 >= 1.5 and ratio >= t.min_buy_sell_ratio:
        signals.append("BUYER_ACCELERATION")
        primary += 1

    holder_growth_30m = _maybe_num(candidate.get("holder_growth_30m_pct"))
    holder_growth_2h = _maybe_num(candidate.get("holder_growth_2h_pct"))
    concentration_delta = _maybe_num(candidate.get("top10_concentration_delta_pct"))
    holder_growth_hit = (
        holder_growth_30m is not None and holder_growth_30m >= 10.0
    ) or (
        holder_growth_2h is not None and holder_growth_2h >= 20.0
    )
    if holder_growth_hit and concentration_delta is not None and concentration_delta <= 0:
        signals.append("HOLDER_ACCELERATION")
        primary += 1

    liq_growth_30m = _maybe_num(candidate.get("liquidity_growth_30m_pct"))
    liq_growth_2h = _maybe_num(candidate.get("liquidity_growth_2h_pct"))
    liq_dd = _maybe_num(candidate.get("liquidity_drawdown_from_peak_pct"))
    liq_growth_hit = (
        liq_growth_30m is not None and liq_growth_30m >= 10.0
    ) or (
        liq_growth_2h is not None and liq_growth_2h >= 20.0
    )
    if liq_growth_hit and liq_dd is not None and liq_dd <= 15.0:
        signals.append("LIQUIDITY_GROWTH")

    quality_wallets = int(_num(candidate.get("quality_wallet_buyers")))
    high_conf_wallets = int(_num(candidate.get("high_confidence_wallet_buyers")))
    organic = _bool(candidate.get("organic_acceleration_confirmed")) is True
    if quality_wallets >= t.min_quality_wallets or (high_conf_wallets >= 1 and organic):
        signals.append("SMART_WALLET_EVIDENCE")

    return {
        "signals": signals,
        "count": len(signals),
        "primary_count": primary,
        "passed": len(signals) >= 3 and primary >= 1,
        "buy_sell_ratio_15m": round(ratio, 3),
    }


def _alert_stage(
    status: str,
    score: float,
    safety: Dict[str, Any],
    accel: Dict[str, Any],
    catalyst: Dict[str, Any],
    age: str,
    ext: str,
) -> str:
    if safety.get("passed") is True and accel.get("passed") is True and status in ACTIONABLE_STATUSES:
        return ALERT_STAGE_REAL_ALERT

    if safety.get("hard_blocks"):
        return ALERT_STAGE_WATCH

    hot_evidence = (
        score >= 65.0
        or int(_num(accel.get("count"))) >= 2
        or _num(catalyst.get("score")) >= 6.0
    )
    if age in ACTIVE_AGE_BANDS and ext not in {"VERY_EXTENDED", "LATE_NO_CHASE"} and hot_evidence:
        return ALERT_STAGE_HOT_WATCH
    return ALERT_STAGE_WATCH


def genesis_score(candidate: Dict[str, Any], t: GenesisThresholds = THRESHOLDS) -> Dict[str, Any]:
    safety = safety_gate(candidate, t)
    accel = acceleration_signals(candidate, t)
    catalyst = source_catalyst(candidate)

    liquidity = _maybe_num(candidate.get("liquidity_usd"))
    holders = _maybe_num(candidate.get("holders"))
    top10 = _maybe_num(candidate.get("top10_ex_system_pct"))
    largest = _maybe_num(candidate.get("largest_non_system_wallet_pct"))
    liq_dd = _maybe_num(candidate.get("liquidity_drawdown_from_peak_pct"))
    quality_wallets = int(_num(candidate.get("quality_wallet_buyers")))
    high_conf_wallets = int(_num(candidate.get("high_confidence_wallet_buyers")))
    social = _bool(candidate.get("organic_social_confirmed")) is True

    safety_points = 0.0
    if safety["passed"]:
        safety_points += 18.0
    if liquidity is not None and liquidity >= t.preferred_liquidity_usd:
        safety_points += 6.0
    elif liquidity is not None and liquidity >= t.min_liquidity_usd:
        safety_points += 3.0
    if holders is not None and holders >= t.preferred_holders:
        safety_points += 3.0
    elif holders is not None and holders >= t.min_holders:
        safety_points += 1.5
    if top10 is not None and largest is not None and top10 <= t.top10_preferred_pct and largest <= t.largest_wallet_preferred_pct:
        safety_points += 3.0
    safety_points = min(30.0, safety_points)

    acceleration_points = min(25.0, accel["count"] * 5.0 + accel["primary_count"] * 2.5)

    holder_points = 0.0
    if holders is not None and holders >= t.preferred_holders:
        holder_points += 5.0
    elif holders is not None and holders >= t.min_holders:
        holder_points += 3.0
    if top10 is not None:
        if top10 <= t.top10_preferred_pct:
            holder_points += 5.0
        elif top10 <= t.top10_hard_max_pct:
            holder_points += 2.0
    if largest is not None:
        if largest <= t.largest_wallet_preferred_pct:
            holder_points += 5.0
        elif largest <= t.largest_wallet_hard_max_pct:
            holder_points += 2.0
    holder_points = min(15.0, holder_points)

    liquidity_points = 0.0
    if liquidity is not None and liquidity >= 250_000:
        liquidity_points += 8.0
    elif liquidity is not None and liquidity >= t.preferred_liquidity_usd:
        liquidity_points += 6.0
    elif liquidity is not None and liquidity >= t.min_liquidity_usd:
        liquidity_points += 4.0
    if liq_dd is not None:
        if liq_dd <= 5:
            liquidity_points += 7.0
        elif liq_dd <= 10:
            liquidity_points += 5.0
        elif liq_dd <= 15:
            liquidity_points += 3.0
    liquidity_points = min(15.0, liquidity_points)

    wallet_points = 0.0
    if high_conf_wallets >= 2:
        wallet_points = 10.0
    elif quality_wallets >= 3:
        wallet_points = 8.0
    elif quality_wallets >= 2:
        wallet_points = 6.0
    elif high_conf_wallets >= 1:
        wallet_points = 5.0

    social_points = 5.0 if social else 0.0
    catalyst_points = _num(catalyst.get("score"))
    score = round(min(
        100.0,
        safety_points
        + acceleration_points
        + holder_points
        + liquidity_points
        + wallet_points
        + social_points
        + catalyst_points,
    ), 1)

    ext = extension_band(_num(candidate.get("gain_from_baseline_pct")))
    age = age_band(_num(candidate.get("pair_age_minutes")))
    status = _score_band(score)

    if not safety["passed"]:
        status = "RESEARCH_ONLY" if not safety["hard_blocks"] else "BLOCKED"
    elif age == "DISCOVERY_ONLY":
        status = "DISCOVERY_ONLY"
    elif age == "OUTSIDE_GENESIS":
        status = "OUTSIDE_GENESIS"
    elif not accel["passed"] and status in {"EVIDENCE_READY", "PAPER_BUY_CANDIDATE", "STRONG_GENESIS", "EXCEPTIONAL_GENESIS"}:
        status = "WATCH"
    elif ext == "LATE_NO_CHASE":
        status = "LATE_NO_CHASE"
    elif ext == "VERY_EXTENDED" and status in {"PAPER_BUY_CANDIDATE", "STRONG_GENESIS", "EXCEPTIONAL_GENESIS"}:
        status = "VERY_EXTENDED_WATCH"
    elif ext == "EXTENDED" and score < 85 and status in {"PAPER_BUY_CANDIDATE", "STRONG_GENESIS", "EXCEPTIONAL_GENESIS"}:
        status = "EXTENDED_WATCH"

    decision_signals = list(accel["signals"])
    if social:
        decision_signals.append("SOCIAL_NARRATIVE")
    if catalyst_points > 0:
        decision_signals.append("SOURCE_CATALYST")
    stage = _alert_stage(status, score, safety, accel, catalyst, age, ext)

    return {
        "genesis_score": score,
        "status": status,
        "alert_stage": stage,
        "age_band": age,
        "extension_band": ext,
        "safety": safety,
        "acceleration": accel,
        "source_catalyst": catalyst,
        "signal_summary": {
            "signals": decision_signals,
            "passed": len(decision_signals),
            "total": 7,
        },
        "subscores": {
            "safety_tradability": round(safety_points, 1),
            "organic_acceleration": round(acceleration_points, 1),
            "holder_distribution": round(holder_points, 1),
            "liquidity_survival": round(liquidity_points, 1),
            "smart_wallet": round(wallet_points, 1),
            "social_narrative": round(social_points, 1),
            "source_catalyst": round(catalyst_points, 1),
        },
        "paper_entry_usd": PAPER_ENTRY_USD,
        "thresholds": asdict(t),
    }


def rank_candidates(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        row.update(genesis_score(candidate))
        ranked.append(row)
    stage_priority = {
        ALERT_STAGE_REAL_ALERT: 2,
        ALERT_STAGE_HOT_WATCH: 1,
        ALERT_STAGE_WATCH: 0,
    }
    return sorted(
        ranked,
        key=lambda x: (
            stage_priority.get(str(x.get("alert_stage")), 0),
            _num(x.get("genesis_score")),
        ),
        reverse=True,
    )
