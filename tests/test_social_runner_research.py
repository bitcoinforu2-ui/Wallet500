from wallet500.social_runner_research import (
    build_features,
    classify_features,
    coverage_adjusted_rate,
    label_outcome,
)


def _snapshot(**overrides):
    base = {
        "observed_at": "2026-09-18T00:00:00Z",
        "chain": "ethereum",
        "contract": "0xabc",
        "symbol": "TEST",
        "windows": {
            "3h": {"mentions": 45, "indexed_communities": 80000},
            "24h": {"mentions": 160, "indexed_communities": 80000},
            "3d": {"mentions": 300, "indexed_communities": 80000},
            "7d": {"mentions": 420, "indexed_communities": 80000},
            "21d": {"mentions": 500, "indexed_communities": 80000},
        },
        "organic_share": 0.9,
        "unique_communities": 12,
        "first_time_communities": 5,
        "platform_mentions": {"telegram": 20, "x": 10, "reddit": 2},
        "coordination_ratio": 0.05,
        "market": {"pre_24h_return_pct": 4, "pre_72h_return_pct": 8},
        "onchain": {},
    }
    base.update(overrides)
    return base


def test_coverage_normalization_is_invariant_when_mentions_and_coverage_scale_together():
    a = coverage_adjusted_rate(100, 20000, 24)
    b = coverage_adjusted_rate(400, 80000, 24)
    assert a["mentions_per_10k_communities_per_hour"] == b["mentions_per_10k_communities_per_hour"]


def test_missing_coverage_is_not_faked_as_adjusted():
    row = coverage_adjusted_rate(100, None, 24)
    assert row["coverage_adjusted"] is False
    assert row["mentions_per_10k_communities_per_hour"] is None


def test_clean_early_attention_is_early_runner_but_never_actionable():
    result = classify_features(build_features(_snapshot()))
    assert result["state"] == "EARLY_RUNNER"
    assert result["actionable"] is False
    assert result["automatic_buy"] is False
    assert result["production_effect"] is False


def test_late_price_move_overrides_clean_social():
    snap = _snapshot(market={"pre_24h_return_pct": 45, "pre_72h_return_pct": 80})
    result = classify_features(build_features(snap))
    assert result["state"] == "LATE_ATTENTION"
    assert result["late_attention_penalty"] is True


def test_low_organic_coordinated_social_is_false_social():
    snap = _snapshot(organic_share=0.1, coordination_ratio=0.85)
    result = classify_features(build_features(snap))
    assert result["state"] == "DISTRIBUTION_FALSE_SOCIAL"
    assert result["false_social_risk"] is True


def test_market_and_onchain_confirmation_yields_confirmed_runner():
    snap = _snapshot(
        market={
            "pre_24h_return_pct": 5,
            "pre_72h_return_pct": 8,
            "volume_ratio": 2.2,
            "buy_sell_imbalance": 0.31,
            "liquidity_change_pct": 8,
        },
        onchain={"new_holder_change_pct": 7, "smart_wallet_accumulation_score": 78},
    )
    result = classify_features(build_features(snap))
    assert result["state"] == "CONFIRMED_RUNNER"
    assert result["market_confirmations"] >= 2
    assert result["onchain_confirmations"] >= 1


def test_distribution_flow_overrides_attention():
    snap = _snapshot(
        market={
            "pre_24h_return_pct": 2,
            "pre_72h_return_pct": 3,
            "volume_ratio": 3,
            "buy_sell_imbalance": -0.4,
            "liquidity_change_pct": -8,
        },
        onchain={"exchange_inflow_score": 90},
    )
    result = classify_features(build_features(snap))
    assert result["state"] == "DISTRIBUTION_FALSE_SOCIAL"
    assert result["distribution_risk"] is True


def test_runner_outcomes_require_target_before_excess_drawdown():
    outcome = label_outcome(
        1.0,
        [
            {"hours_from_t0": 1, "price": 0.95},
            {"hours_from_t0": 4, "price": 1.10},
            {"hours_from_t0": 20, "price": 1.26},
            {"hours_from_t0": 70, "price": 1.45},
            {"hours_from_t0": 160, "price": 2.10},
        ],
    )
    assert outcome["runner_24h"] is True
    assert outcome["runner_72h"] is True
    assert outcome["moonshot_7d"] is True
    assert outcome["targets"]["RUNNER_24H"]["time_to_hit_hours"] == 20


def test_runner_24h_is_rejected_when_drawdown_precedes_hit():
    outcome = label_outcome(
        1.0,
        [
            {"hours_from_t0": 2, "price": 0.80},
            {"hours_from_t0": 20, "price": 1.30},
        ],
    )
    assert outcome["runner_24h"] is False
    assert outcome["targets"]["RUNNER_24H"]["hit_target_but_drawdown_failed"] is True
