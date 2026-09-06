from wallet500.narrative_decision import classify


def row(**scores):
    return {
        "token_address": "mint",
        "pair_address": "pair",
        "scores": {"narrative": 75, "social_momentum": 80, "confidence": 80, "hype_manipulation_risk": 10, **scores},
        "coverage": {"independent_sources": 3, "independent_authors": 3, "news_events": 2, "freshness_score": 90},
        "catalysts": {"positive": ["listing"], "negative": []},
    }


def test_green_requires_cross_source_confirmation():
    out = classify(row())
    assert out["traffic_light"] == "GREEN"
    assert out["production_effect"] is False
    assert out["automatic_buy"] is False


def test_high_hype_is_red():
    out = classify(row(hype_manipulation_risk=70))
    assert out["traffic_light"] == "RED"


def test_missing_cross_source_stays_orange():
    x = row(); x["coverage"]["independent_sources"] = 1
    assert classify(x)["traffic_light"] == "ORANGE"


def test_pair_identity_is_never_rewritten():
    x = row(); x["pair_address"] = "locked-exact-pair"
    assert classify(x)["pair_address"] == "locked-exact-pair"
