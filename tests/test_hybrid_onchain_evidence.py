from wallet500.hybrid_onchain_evidence import concentration_score


def test_holder_distribution_score_rewards_lower_concentration():
    clean_score, clean_risk, clean_signals = concentration_score(4.0, 28.0)
    concentrated_score, concentrated_risk, concentrated_signals = concentration_score(24.0, 66.0)
    assert clean_score == 100.0
    assert clean_risk == 0.0
    assert "TOP1_OWNER_LT_10PCT" in clean_signals
    assert "TOP10_OWNERS_LT_40PCT" in clean_signals
    assert concentrated_score == 35.0
    assert concentrated_risk == 65.0
    assert "TOP1_OWNER_GE_20PCT" in concentrated_signals
    assert "TOP10_OWNERS_GE_60PCT" in concentrated_signals


def test_holder_score_is_bounded():
    score, risk, _ = concentration_score(100.0, 100.0)
    assert 0.0 <= score <= 100.0
    assert 0.0 <= risk <= 100.0
    assert score + risk == 100.0
