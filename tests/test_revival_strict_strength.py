from wallet500.revival_strict_strength import apply_strict_strength, grade_strict_flow


def flow(**overrides):
    row = {
        "signal": True,
        "sell_buy_count_ratio_h24": 1.20,
        "liquidity_usd": 300_000,
        "volume_to_liquidity": 0.60,
        "buys_h24": 300,
        "sells_h24": 360,
        "price_change_h24_pct": 12.0,
        "price_change_h6_pct": 3.0,
        "price_change_h1_pct": 0.5,
    }
    row.update(overrides)
    return row


def coin(f):
    return {
        "source": "revival_discovery_state+dexscreener_absorption_expansion",
        "absorption_candidate_proxy": True,
        "order_flow_absorption": f,
        "pre_alpha_eligible": False,
        "revival_score_verified": 41.0,
    }


def test_strict_3_requires_strong_structure():
    result = grade_strict_flow(flow(
        liquidity_usd=1_500_000,
        volume_to_liquidity=1.2,
        buys_h24=1200,
        sells_h24=1500,
        price_change_h24_pct=25.0,
        price_change_h6_pct=5.0,
        price_change_h1_pct=1.0,
    ))
    assert result["strict_grade"] == "STRICT-3"
    assert result["strict_level"] == 3
    assert result["strict_strength_score"] >= 80


def test_strict_2_is_middle_strength_band():
    result = grade_strict_flow(flow())
    assert result["strict_grade"] == "STRICT-2"
    assert 60 <= result["strict_strength_score"] < 80


def test_strict_1_can_pass_strict_but_have_weaker_structure():
    result = grade_strict_flow(flow(
        sell_buy_count_ratio_h24=1.90,
        liquidity_usd=55_000,
        volume_to_liquidity=0.06,
        buys_h24=25,
        sells_h24=50,
        price_change_h24_pct=0.5,
        price_change_h6_pct=-5.0,
        price_change_h1_pct=-4.0,
    ))
    assert result["strict_grade"] == "STRICT-1"
    assert result["strict_strength_score"] < 60


def test_non_strict_never_receives_a_grade():
    result = grade_strict_flow(flow(signal=False))
    assert result["eligible"] is False
    assert result["strict_level"] is None
    assert result["strict_grade"] is None


def test_layer_grades_only_green_expansion_and_never_changes_production_fields():
    strict = coin(flow())
    pre_move = coin(flow(signal=False))
    pre_move["order_flow_absorption"]["strict_level"] = 3
    pre_move["order_flow_absorption"]["strict_grade"] = "STRICT-3"
    base = {
        "source": "coingecko",
        "absorption_candidate_proxy": False,
        "order_flow_absorption": flow(),
        "pre_alpha_eligible": False,
        "revival_score_verified": 70.0,
    }
    payload = {
        "counts": {},
        "coins": [strict, pre_move, base],
    }
    out = apply_strict_strength(payload)
    assert out["counts"]["strict_strength_graded"] == 1
    assert strict["strict_strength"]["strict_level"] == 2
    assert strict["pre_alpha_eligible"] is False
    assert strict["revival_score_verified"] == 41.0
    assert "strict_strength" not in pre_move
    assert "strict_level" not in pre_move["order_flow_absorption"]
    assert "strict_strength" not in base
    assert out["strict_strength_contract"]["pre_alpha_promotion"] == "FORBIDDEN"
