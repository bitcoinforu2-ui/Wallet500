from wallet500.cex_market_timing_shadow import classify, _update_state


def candidate(**overrides):
    row = {
        "symbol": "TESTUSDT",
        "observed_at": "2026-09-14T12:00:00+00:00",
        "shadow_features": [
            "CROSS_VENUE_PRICE_DISPERSION_SHADOW",
            "TURNOVER_STEP_EXPANSION_SHADOW",
            "MARKET_FRAGMENTATION_COMPOSITE_SHADOW",
        ],
        "price_dispersion_ratio": 1.20,
        "regional_lead_gap_pct": 12.0,
        "volume_step_multiple": 1.8,
        "usd_like_venues": 3,
    }
    row.update(overrides)
    return row


def verified_identity(liquidity=80_000.0):
    return {
        "symbol": "TEST",
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "selected_pair_liquidity_usd": liquidity,
    }


def test_early_signals_remain_research_only_without_identity():
    out = classify(candidate(), {}, None)
    assert out["stage"] == "PRE_BUY"
    assert out["actionable"] is False
    assert out["automatic_buy"] is False
    assert "EXACT_PAIR_IDENTITY_NOT_VERIFIED" in out["blockers"]


def test_entry_zone_requires_exact_pair_and_50k_liquidity():
    good = classify(candidate(), verified_identity(), None)
    assert good["stage"] == "ENTRY_ZONE"

    low = classify(candidate(), verified_identity(49_999), None)
    assert low["stage"] == "PRE_BUY"
    assert "VERIFIED_EXECUTION_LIQUIDITY_BELOW_50K" in low["blockers"]

    missing = classify(candidate(), {"identity_status": "DEX_VERIFIED", "identity_verified": True}, None)
    assert missing["stage"] == "PRE_BUY"
    assert "VERIFIED_EXECUTION_LIQUIDITY_MISSING" in missing["blockers"]


def test_post_entry_hard_gate_invalidation_is_shadow_risk_off():
    out = classify(candidate(), verified_identity(40_000), "ENTRY_ZONE")
    assert out["stage"] == "EXIT_RISK_OFF"
    assert out["automatic_sell"] is False
    assert out["actionable"] is False


def test_post_entry_dangerous_dispersion_is_take_profit_warning_only():
    out = classify(candidate(price_dispersion_ratio=1.9), verified_identity(), "HOLD_ADD")
    assert out["stage"] == "TAKE_PROFIT_WARNING"
    assert out["automatic_sell"] is False


def test_first_stage_timestamp_is_immutable_across_later_runs():
    first_row = {
        "symbol": "TESTUSDT",
        "stage": "EARLY_WATCH",
        "observed_at": "2026-09-14T12:00:00+00:00",
        "evidence": {"volume_step_multiple": 1.6},
    }
    state1 = _update_state({}, [first_row], "2026-09-14T12:00:01+00:00")
    later_row = {
        **first_row,
        "observed_at": "2026-09-14T13:00:00+00:00",
        "evidence": {"volume_step_multiple": 3.0},
    }
    state2 = _update_state(state1, [later_row], "2026-09-14T13:00:01+00:00")
    first = state2["first_stage_observed"]["TESTUSDT"]["EARLY_WATCH"]
    assert first["observed_at"] == "2026-09-14T12:00:00+00:00"
    assert first["evidence_at_first_observation"]["volume_step_multiple"] == 1.6
