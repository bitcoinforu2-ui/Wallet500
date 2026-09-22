from wallet500.genesis_radar import PAPER_ENTRY_USD, age_band, extension_band, genesis_score, prebreakout_signals, safety_gate


def base_candidate():
    return {
        "liquidity_usd": 150_000,
        "holders": 700,
        "top10_ex_system_pct": 28,
        "largest_non_system_wallet_pct": 5,
        "mint_authority_safe": True,
        "freeze_authority_safe": True,
        "transfer_restrictions_safe": True,
        "lp_integrity_safe": True,
        "volume_15m_usd": 120_000,
        "prev_volume_15m_usd": 40_000,
        "volume_30m_usd": 180_000,
        "baseline_volume_30m_usd": 60_000,
        "unique_buyers_15m": 180,
        "prev_unique_buyers_15m": 80,
        "buys_15m": 220,
        "sells_15m": 120,
        "holder_growth_30m_pct": 14,
        "holder_growth_2h_pct": 25,
        "top10_concentration_delta_pct": -1.0,
        "liquidity_growth_30m_pct": 18,
        "liquidity_growth_2h_pct": 30,
        "liquidity_drawdown_from_peak_pct": 4,
        "quality_wallet_buyers": 3,
        "high_confidence_wallet_buyers": 1,
        "organic_acceleration_confirmed": True,
        "organic_social_confirmed": True,
        "gain_from_baseline_pct": 180,
        "pair_age_minutes": 120,
    }


def test_paper_size_is_five_dollars():
    assert PAPER_ENTRY_USD == 5.0


def test_age_bands():
    assert age_band(5) == "DISCOVERY_ONLY"
    assert age_band(30) == "EARLY_WATCH"
    assert age_band(120) == "PRIME_GENESIS_WINDOW"
    assert age_band(700) == "LATE_GENESIS_WINDOW"
    assert age_band(2000) == "POST_GENESIS_SURVIVAL"
    assert age_band(10081) == "OUTSIDE_GENESIS"


def test_no_chase_band():
    assert extension_band(5001) == "LATE_NO_CHASE"
    assert extension_band(2000) == "VERY_EXTENDED"
    assert extension_band(500) == "EXTENDED"


def test_low_liquidity_is_hard_block():
    c = base_candidate()
    c["liquidity_usd"] = 49_999
    result = safety_gate(c)
    assert result["passed"] is False
    assert "BLOCKED_LOW_LIQUIDITY" in result["hard_blocks"]


def test_unknown_concentration_is_research_not_fake_failure():
    c = base_candidate()
    c["top10_ex_system_pct"] = None
    result = safety_gate(c)
    assert result["passed"] is False
    assert "UNKNOWN_CONCENTRATION_TOP10" in result["research_only_reasons"]
    assert "BLOCKED_CONCENTRATION_TOP10" not in result["hard_blocks"]


def test_unknown_critical_control_is_research_only():
    c = base_candidate()
    c["lp_integrity_safe"] = None
    result = genesis_score(c)
    assert result["status"] == "RESEARCH_ONLY"


def test_exploded_coin_cannot_be_fresh_buy():
    c = base_candidate()
    c["gain_from_baseline_pct"] = 17243.22
    result = genesis_score(c)
    assert result["status"] == "LATE_NO_CHASE"


def test_healthy_accelerating_candidate_reaches_actionable_band():
    result = genesis_score(base_candidate())
    assert result["safety"]["passed"] is True
    assert result["acceleration"]["passed"] is True
    assert result["genesis_score"] >= 75
    assert result["status"] in {"PAPER_BUY_CANDIDATE", "STRONG_GENESIS", "EXCEPTIONAL_GENESIS"}


def test_prebreakout_detects_pressure_before_price_extension():
    c = base_candidate()
    c["gain_from_baseline_pct"] = 42
    c["price_change_h1"] = 11
    result = prebreakout_signals(c)
    assert "PRESSURE_BEFORE_PRICE_EXTENSION" in result["signals"]
    assert "LIQUIDITY_COMMITMENT" in result["signals"]
    assert "BREADTH_WITHOUT_CONCENTRATION" in result["signals"]
    assert result["priority_ready"] is True


def test_prebreakout_launchpad_lifecycle_is_optional_positive_evidence():
    c = base_candidate()
    c["gain_from_baseline_pct"] = 35
    c["price_change_h1"] = 8
    c["launchpad_curve_progress_pct"] = 88
    result = prebreakout_signals(c)
    assert "BONDING_CURVE_NEAR_GRADUATION" in result["signals"]
    assert result["coverage_pct"] > 50


def test_prebreakout_bundle_dominance_never_gets_priority():
    c = base_candidate()
    c["gain_from_baseline_pct"] = 25
    c["price_change_h1"] = 5
    c["sniper_bundle_share_pct"] = 82
    result = prebreakout_signals(c)
    assert "BUNDLE_DOMINATED_LAUNCH" in result["risks"]
    assert result["priority_ready"] is False
