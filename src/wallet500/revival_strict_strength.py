from __future__ import annotations

import json
from pathlib import Path

from .solana_mintability_gate import enforce_revival

DATA = Path("data")
LATEST = DATA / "revival-1000-latest.json"
MODE = "STRICT_STRENGTH_LEVELS_V1"
EXPANSION_SOURCE = "revival_discovery_state+dexscreener_absorption_expansion"


def n(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def gradeable_green_strict(coin: dict) -> bool:
    flow = coin.get("order_flow_absorption") or {}
    return all([
        coin.get("source") == EXPANSION_SOURCE,
        coin.get("absorption_candidate_proxy") is True,
        flow.get("signal") is True,
    ])


def grade_strict_flow(flow: dict) -> dict:
    """Grade an already-STRICT absorption proxy without changing STRICT eligibility.

    STRICT-1/2/3 is a research-only strength rank. It never turns a non-STRICT
    row into STRICT and never changes PRE-ALPHA or portfolio behavior.
    """
    if flow.get("signal") is not True:
        return {
            "eligible": False,
            "strict_level": None,
            "strict_grade": None,
            "strict_strength_score": None,
            "components": {},
        }

    ratio = n(flow.get("sell_buy_count_ratio_h24"), 0.0)
    liquidity = max(n(flow.get("liquidity_usd")), 0.0)
    turnover = max(n(flow.get("volume_to_liquidity")), 0.0)
    txns = int(n(flow.get("buys_h24"))) + int(n(flow.get("sells_h24")))
    h24 = n(flow.get("price_change_h24_pct"))
    h6 = n(flow.get("price_change_h6_pct"))
    h1 = n(flow.get("price_change_h1_pct"))

    if 1.10 <= ratio <= 1.50:
        imbalance = 20
    elif 1.0 < ratio < 1.10 or 1.50 < ratio <= 1.75:
        imbalance = 14
    elif 1.75 < ratio <= 2.0:
        imbalance = 8
    else:
        imbalance = 0

    if liquidity >= 1_000_000:
        liquidity_points = 20
    elif liquidity >= 250_000:
        liquidity_points = 16
    elif liquidity >= 100_000:
        liquidity_points = 12
    elif liquidity >= 50_000:
        liquidity_points = 8
    else:
        liquidity_points = 0

    if turnover >= 1.0:
        turnover_points = 20
    elif turnover >= 0.50:
        turnover_points = 16
    elif turnover >= 0.25:
        turnover_points = 12
    elif turnover >= 0.10:
        turnover_points = 8
    elif turnover >= 0.05:
        turnover_points = 5
    else:
        turnover_points = 0

    if txns >= 2_000:
        activity = 20
    elif txns >= 500:
        activity = 16
    elif txns >= 150:
        activity = 12
    elif txns >= 40:
        activity = 8
    else:
        activity = 0

    momentum = 0
    if h24 >= 20:
        momentum += 10
    elif h24 >= 5:
        momentum += 8
    elif h24 > 0:
        momentum += 5
    if h6 > 0:
        momentum += 6
    elif h6 >= -2:
        momentum += 3
    if h1 >= 0:
        momentum += 4
    elif h1 >= -2:
        momentum += 2

    components = {
        "sell_imbalance_quality": imbalance,
        "liquidity_depth": liquidity_points,
        "turnover": turnover_points,
        "transaction_activity": activity,
        "momentum_persistence": momentum,
    }
    score = min(100, sum(components.values()))
    if score >= 90:
        level, grade = 3, "STRICT-3"
    elif score >= 65:
        level, grade = 2, "STRICT-2"
    else:
        level, grade = 1, "STRICT-1"

    return {
        "eligible": True,
        "strict_level": level,
        "strict_grade": grade,
        "strict_strength_score": score,
        "components": components,
        "research_only": True,
        "no_hindsight": True,
    }


def apply_strict_strength(payload: dict) -> dict:
    counts = {1: 0, 2: 0, 3: 0}
    graded = 0

    for coin in payload.get("coins") or []:
        flow = coin.get("order_flow_absorption") or {}
        if not gradeable_green_strict(coin):
            coin.pop("strict_strength", None)
            flow.pop("strict_level", None)
            flow.pop("strict_grade", None)
            flow.pop("strict_strength_score", None)
            continue

        grade = grade_strict_flow(flow)
        level = int(grade["strict_level"])
        counts[level] += 1
        graded += 1
        coin["strict_strength"] = grade
        flow["strict_level"] = level
        flow["strict_grade"] = grade["strict_grade"]
        flow["strict_strength_score"] = grade["strict_strength_score"]

    c = payload.setdefault("counts", {})
    c["strict_strength_graded"] = graded
    c["strict_level_1"] = counts[1]
    c["strict_level_2"] = counts[2]
    c["strict_level_3"] = counts[3]
    payload["strict_strength_contract"] = {
        "version": MODE,
        "research_only": True,
        "production_portfolio_impact": "NONE",
        "scope": "GREEN_STRICT_DISCOVERY_EXPANSION_ONLY",
        "eligibility_rule": "MUST_ALREADY_PASS_ALL_STRICT_ABSORPTION_CONDITIONS",
        "levels": {
            "STRICT-1": "strength_score_below_65",
            "STRICT-2": "strength_score_65_to_89",
            "STRICT-3": "strength_score_90_to_100",
        },
        "score_components": "SELL_IMBALANCE_QUALITY_20 + LIQUIDITY_DEPTH_20 + TURNOVER_20 + TX_ACTIVITY_20 + MOMENTUM_PERSISTENCE_20",
        "pre_alpha_promotion": "FORBIDDEN",
        "revival_score_mutation": "NONE",
        "no_hindsight": True,
    }
    return payload


def main() -> None:
    if not LATEST.exists():
        raise SystemExit("REVIVAL_STRICT_STRENGTH_LATEST_MISSING")
    # Hard product rule: no Solana token reaches grading or the public Revival
    # universe unless its on-chain mint authority is verified revoked/null.
    enforce_revival(DATA)
    payload = json.loads(LATEST.read_text())
    if payload.get("network") != "solana" or payload.get("production_portfolio_impact") != "NONE":
        raise SystemExit("REVIVAL_STRICT_STRENGTH_UNSAFE_INPUT")
    payload = apply_strict_strength(payload)
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    c = payload.get("counts") or {}
    print(json.dumps({
        "graded": c.get("strict_strength_graded", 0),
        "strict_1": c.get("strict_level_1", 0),
        "strict_2": c.get("strict_level_2", 0),
        "strict_3": c.get("strict_level_3", 0),
    }))


if __name__ == "__main__":
    main()
