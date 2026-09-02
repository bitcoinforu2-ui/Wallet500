from wallet500.research_decision_engine import build, _recommend


def test_case_study_never_auto_promotes():
    case = {
        "asset": {"symbol": "DOGE-1"},
        "lookahead_policy": "NO_HINDSIGHT_FORWARD_ONLY",
        "entity_flow_features": ["CEX_NET_OUTFLOW"],
    }
    out = build({}, {}, [case])
    p = out["proposals"][0]
    assert p["recommendation"] == "MORE_DATA"
    assert p["hard_rule_change_allowed"] is False
    assert out["production_change_allowed"] is False


def test_measured_recommendation_thresholds():
    assert _recommend(50, 30, 40, True) == "MORE_DATA"
    assert _recommend(150, 15, 10, True) == "SHADOW_TEST"
    assert _recommend(350, 25, 35, True) == "APPROVED_CANDIDATE"
    assert _recommend(350, 25, 35, False) == "REJECT"
    assert _recommend(350, -1, 35, True) == "REJECT"
