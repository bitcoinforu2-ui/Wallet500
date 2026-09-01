from wallet500.decision_engine_v1 import evaluate, score_execution, score_exit_risk


def base_row():
    return {
        "chain": "bsc",
        "token": "0x1",
        "pair_address": "0xabc",
        "locked_pair_address": "0xabc",
        "pair_identity_locked": True,
        "live_survival_gate": "ACTIVE",
        "production_live_liquidity_usd": 300000,
        "liquidity_usd": 300000,
        "tradable_liquidity_usd": 280000,
        "tradable_liquidity_share_pct": 93,
        "dex_liquidity_to_market_cap_pct": 12,
        "top_pool_share_pct": 70,
        "tradable_pool_count": 3,
        "execution_depth_status": "VERIFIED_ROUTER_DEPTH",
        "anomaly_score": 85,
        "volume_velocity": 8,
        "buy_sell_ratio": 1.5,
        "turnover_h1": 1.2,
        "live_activity_h1": 600,
        "price_change_m5": 8,
        "price_change_h1": 60,
        "liquidity_reality_score": 80,
        "production_liquidity_retention_from_peak": .97,
        "production_risk_gate": "PASS",
        "pump_dump_risk_level": "LOW",
        "pump_dump_blocked": False,
        "production_risk_blocked": False,
        "lp_removal_protection_verified": True,
        "liquidity_drain_holder_cluster_verified": True,
        "pre_rug_danger_score": 0,
        "pre_rug_exit_warning": False,
        "pre_rug_sell_buy_ratio_h1": .7,
        "peak_drawdown_pct": -5,
    }


def test_strong_complete_evidence_can_reach_shadow_buy():
    d = evaluate(base_row(), in_position=False)
    assert d["model_signal"] == "STRONG_BUY"
    assert d["recommended_action"] == "BUY"
    assert d["state"] == "BUY_ZONE"
    assert d["hard_safety_failures"] == []
    assert d["evidence_gaps"] == []


def test_missing_exit_depth_is_fail_closed_for_buy():
    row = base_row()
    row["execution_depth_status"] = "ROUTER_QUOTES_REQUIRED"
    d = evaluate(row, in_position=False)
    assert d["recommended_action"] == "RESEARCH"
    assert "EXECUTABLE_EXIT_DEPTH" in d["evidence_gaps"]
    assert d["scores"]["confidence"] <= 69


def test_holder_and_lp_evidence_are_fail_closed_for_buy():
    row = base_row()
    row["lp_removal_protection_verified"] = False
    row["liquidity_drain_holder_cluster_verified"] = False
    d = evaluate(row, in_position=False)
    assert d["recommended_action"] == "RESEARCH"
    assert "LP_REMOVAL_PROTECTION" in d["evidence_gaps"]
    assert "HOLDER_CLUSTER" in d["evidence_gaps"]


def test_hard_gate_failure_rejects_even_with_momentum():
    row = base_row()
    row["production_live_liquidity_usd"] = 20_000
    row["pump_dump_blocked"] = True
    row["live_survival_gate"] = "FAILED"
    d = evaluate(row, in_position=False)
    assert d["recommended_action"] == "REJECT"
    assert "LIQUIDITY_BELOW_50K" in d["hard_safety_failures"]
    assert "PUMP_DUMP_BLOCK" in d["hard_safety_failures"]
    assert "LIVE_SURVIVAL_INACTIVE" in d["hard_safety_failures"]


def test_exit_warning_promotes_open_position_to_sell():
    row = base_row()
    row["pre_rug_exit_warning"] = True
    row["pre_rug_danger_score"] = 3
    row["pre_rug_sell_buy_ratio_h1"] = 1.5
    d = evaluate(row, in_position=True)
    assert d["scores"]["exit_risk"] >= 75
    assert d["recommended_action"] == "SELL"


def test_router_quote_gap_is_reported_by_execution_score():
    row = base_row()
    row["execution_depth_status"] = "ROUTER_QUOTES_REQUIRED"
    _, _, missing = score_execution(row)
    assert missing == ["EXECUTABLE_EXIT_DEPTH"]


def test_exit_risk_stays_low_for_healthy_row():
    risk, reasons = score_exit_risk(base_row())
    assert risk < 25
    assert "PRE_RUG_EXIT_WARNING" not in reasons
