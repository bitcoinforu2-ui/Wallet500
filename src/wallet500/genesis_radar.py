from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional


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


def safety_gate(candidate: Dict[str, Any], t: GenesisThresholds = THRESHOLDS) -> Dict[str, Any]:
    reasons: List[str] = []
    research_only: List[str] = []

    liquidity = _num(candidate.get("liquidity_usd"))
    holders = int(_num(candidate.get("holders")))
    top10 = _num(candidate.get("top10_ex_system_pct"), 100.0)
    largest = _num(candidate.get("largest_non_system_wallet_pct"), 100.0)

    if liquidity < t.min_liquidity_usd:
        reasons.append("BLOCKED_LOW_LIQUIDITY")
    if holders < t.min_holders:
        reasons.append("BLOCKED_LOW_HOLDERS")
    if top10 > t.top10_hard_max_pct:
        reasons.append("BLOCKED_CONCENTRATION_TOP10")
    if largest > t.largest_wallet_hard_max_pct:
        reasons.append("BLOCKED_CONCENTRATION_WALLET")

    mint_safe = _bool(candidate.get("mint_authority_safe"))
    freeze_safe = _bool(candidate.get("freeze_authority_safe"))
    transfer_safe = _bool(candidate.get("transfer_restrictions_safe"))
    lp_safe = _bool(candidate.get("lp_integrity_safe"))

    for key, state in (
        ("MINT_AUTHORITY", mint_safe),
        ("FREEZE_AUTHORITY", freeze_safe),
        ("TRANSFER_RESTRICTIONS", transfer_safe),
        ("LP_INTEGRITY", lp_safe),
    ):
        if state is False:
            reasons.append(f"BLOCKED_{key}")
        elif state is None:
            research_only.append(f"UNKNOWN_{key}")

    passed = not reasons and not research_only
    return {
        "passed": passed,
        "hard_blocks": reasons,
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

    holder_growth_30m = _num(candidate.get("holder_growth_30m_pct"))
    holder_growth_2h = _num(candidate.get("holder_growth_2h_pct"))
    concentration_delta = _num(candidate.get("top10_concentration_delta_pct"))
    if (holder_growth_30m >= 10.0 or holder_growth_2h >= 20.0) and concentration_delta <= 0:
        signals.append("HOLDER_ACCELERATION")
        primary += 1

    liq_growth_30m = _num(candidate.get("liquidity_growth_30m_pct"))
    liq_growth_2h = _num(candidate.get("liquidity_growth_2h_pct"))
    liq_dd = _num(candidate.get("liquidity_drawdown_from_peak_pct"))
    if (liq_growth_30m >= 10.0 or liq_growth_2h >= 20.0) and liq_dd <= 15.0:
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


def genesis_score(candidate: Dict[str, Any], t: GenesisThresholds = THRESHOLDS) -> Dict[str, Any]:
    safety = safety_gate(candidate, t)
    accel = acceleration_signals(candidate, t)

    liquidity = _num(candidate.get("liquidity_usd"))
    holders = int(_num(candidate.get("holders")))
    top10 = _num(candidate.get("top10_ex_system_pct"), 100.0)
    largest = _num(candidate.get("largest_non_system_wallet_pct"), 100.0)
    liq_dd = _num(candidate.get("liquidity_drawdown_from_peak_pct"))
    quality_wallets = int(_num(candidate.get("quality_wallet_buyers")))
    high_conf_wallets = int(_num(candidate.get("high_confidence_wallet_buyers")))
    social = _bool(candidate.get("organic_social_confirmed")) is True

    # Safety / tradability: 30
    safety_points = 0.0
    if safety["passed"]:
        safety_points += 18.0
    if liquidity >= t.preferred_liquidity_usd:
        safety_points += 6.0
    elif liquidity >= t.min_liquidity_usd:
        safety_points += 3.0
    if holders >= t.preferred_holders:
        safety_points += 3.0
    elif holders >= t.min_holders:
        safety_points += 1.5
    if top10 <= t.top10_preferred_pct and largest <= t.largest_wallet_preferred_pct:
        safety_points += 3.0
    safety_points = min(30.0, safety_points)

    # Organic acceleration: 25
    acceleration_points = min(25.0, accel["count"] * 5.0 + accel["primary_count"] * 2.5)

    # Holder quality & distribution: 15
    holder_points = 0.0
    if holders >= t.preferred_holders:
        holder_points += 5.0
    elif holders >= t.min_holders:
        holder_points += 3.0
    if top10 <= t.top10_preferred_pct:
        holder_points += 5.0
    elif top10 <= t.top10_hard_max_pct:
        holder_points += 2.0
    if largest <= t.largest_wallet_preferred_pct:
        holder_points += 5.0
    elif largest <= t.largest_wallet_hard_max_pct:
        holder_points += 2.0
    holder_points = min(15.0, holder_points)

    # Liquidity strength & survival: 15
    liquidity_points = 0.0
    if liquidity >= 250_000:
        liquidity_points += 8.0
    elif liquidity >= t.preferred_liquidity_usd:
        liquidity_points += 6.0
    elif liquidity >= t.min_liquidity_usd:
        liquidity_points += 4.0
    if liq_dd <= 5:
        liquidity_points += 7.0
    elif liq_dd <= 10:
        liquidity_points += 5.0
    elif liq_dd <= 15:
        liquidity_points += 3.0
    liquidity_points = min(15.0, liquidity_points)

    # Smart-wallet evidence: 10
    wallet_points = 0.0
    if high_conf_wallets >= 2:
        wallet_points = 10.0
    elif quality_wallets >= 3:
        wallet_points = 8.0
    elif quality_wallets >= 2:
        wallet_points = 6.0
    elif high_conf_wallets >= 1:
        wallet_points = 5.0

    # Social / narrative confirmation: 5
    social_points = 5.0 if social else 0.0

    score = round(
        safety_points + acceleration_points + holder_points + liquidity_points + wallet_points + social_points,
        1,
    )

    gain_pct = _num(candidate.get("gain_from_baseline_pct"))
    ext = extension_band(gain_pct)
    age_minutes = _num(candidate.get("pair_age_minutes"))
    age = age_band(age_minutes)
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

    return {
        "genesis_score": score,
        "status": status,
        "age_band": age,
        "extension_band": ext,
        "safety": safety,
        "acceleration": accel,
        "subscores": {
            "safety_tradability": round(safety_points, 1),
            "organic_acceleration": round(acceleration_points, 1),
            "holder_distribution": round(holder_points, 1),
            "liquidity_survival": round(liquidity_points, 1),
            "smart_wallet": round(wallet_points, 1),
            "social_narrative": round(social_points, 1),
        },
        "thresholds": asdict(t),
    }


def rank_candidates(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        row.update(genesis_score(candidate))
        ranked.append(row)
    return sorted(ranked, key=lambda x: _num(x.get("genesis_score")), reverse=True)
