from wallet500.composite_strong_shadow import evaluate_candidate


def test_promotes_only_missing_strong_decision():
    obs = {
        "symbol": "RAY", "token_address": "ray", "pair_address": "pair",
        "exact_identity_verified": True, "exact_pair_verified": True,
        "market_age_verified": True, "market_activity_verified": True,
        "execution_pool_liquidity_usd": 1_000_000,
        "signal_score": 65, "source_lane_count": 2,
        "evidence_positive_lanes": ["HOLDER_GROWTH"],
        "missing_gates": ["STRONG_DECISION_LANE"],
        "blockers": ["NO_STRONG_DECISION_LANE"],
    }
    real = {"source_lane_count": 2, "source_lanes": ["CEX_REVIVAL", "REVIVAL_MARKET_STRUCTURE"]}
    assert evaluate_candidate(obs, real)["shadow_composite_pass"] is True


def test_does_not_bypass_independent_confirmation_or_risk():
    obs = {
        "symbol": "X", "token_address": "x", "pair_address": "pair",
        "exact_identity_verified": True, "exact_pair_verified": True,
        "market_age_verified": True, "market_activity_verified": True,
        "execution_pool_liquidity_usd": 1_000_000,
        "signal_score": 90, "source_lane_count": 3,
        "evidence_positive_lanes": ["HOLDER_GROWTH"],
        "missing_gates": ["STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION"],
        "blockers": ["NO_STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION_LT_2"],
    }
    real = {"source_lane_count": 3, "source_lanes": ["CEX_REVIVAL", "REVIVAL_MARKET_STRUCTURE", "WAKING_CONFIRMATION"]}
    assert evaluate_candidate(obs, real)["shadow_composite_pass"] is False
