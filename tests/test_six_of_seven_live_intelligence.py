from wallet500.six_of_seven_live_intelligence import select_six_of_seven


def _row(**overrides):
    row = {
        "chain": "solana",
        "symbol": "RAY",
        "token_address": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "pair_address": "6UmmUiYoBjSrhakAobJw8BvkmJtDVxaeBtbt7rxWo1mg",
        "readiness_passed": 6,
        "readiness_total": 7,
        "missing_gates": ["STRONG_DECISION_LANE"],
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "market_age_verified": True,
        "radar_tier": "NEAR_ALERT",
        "risk_reasons": [],
        "signal_score": 70.0,
        "execution_pool_liquidity_usd": 5_000_000,
    }
    row.update(overrides)
    return row


def test_exact_veteran_six_of_seven_triggers_deep_live_scan():
    out = select_six_of_seven({"verified_watch": [_row()]})
    assert len(out) == 1
    assert out[0]["deep_live_trigger"] == "READINESS_6_OF_7"
    assert out[0]["deep_live_missing_gate"] == "STRONG_DECISION_LANE"


def test_five_of_seven_does_not_trigger():
    assert select_six_of_seven({"verified_watch": [_row(readiness_passed=5)]}) == []


def test_risk_blocked_six_of_seven_does_not_trigger():
    assert select_six_of_seven({"verified_watch": [_row(risk_reasons=["PUMP_DUMP_RISK"])]}) == []


def test_unverified_identity_or_pair_does_not_trigger():
    assert select_six_of_seven({"verified_watch": [_row(exact_pair_verified=False)]}) == []
    assert select_six_of_seven({"verified_watch": [_row(exact_identity_verified=False)]}) == []


def test_any_single_missing_gate_is_eligible_for_deep_intelligence():
    out = select_six_of_seven({"verified_watch": [_row(missing_gates=["INDEPENDENT_CONFIRMATION"]) ]})
    assert len(out) == 1
    assert out[0]["deep_live_missing_gate"] == "INDEPENDENT_CONFIRMATION"
