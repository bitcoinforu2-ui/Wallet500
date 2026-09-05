from wallet500.social_coverage_hardening import harden


def test_missing_social_and_kol_are_null_not_fake_zero():
    payload = {
        "truth_contract": {},
        "counts": {},
        "tokens": [{
            "coverage": {
                "organic_social_available": False,
                "exact_social_events": 0,
                "news_events": 3,
            },
            "scores": {
                "social_momentum": 0.0,
                "kol_quality": 0.0,
                "news_catalyst": 87.0,
                "hype_manipulation_risk": 0.0,
                "narrative": 87.0,
                "confidence": 21.6,
            },
        }],
    }
    out = harden(payload)
    row = out["tokens"][0]
    assert row["scores"]["social_momentum"] is None
    assert row["scores"]["kol_quality"] is None
    assert row["scores"]["hype_manipulation_risk"] is None
    assert row["scores"]["news_catalyst"] == 87.0
    assert row["availability"]["news_catalyst"] is True
    assert out["truth_contract"]["missing_channel_is_unknown_not_zero"] is True


def test_observed_zero_remains_zero_when_channel_is_really_observed():
    payload = {
        "truth_contract": {},
        "counts": {},
        "tokens": [{
            "coverage": {
                "organic_social_available": True,
                "exact_social_events": 1,
                "news_events": 0,
            },
            "scores": {
                "social_momentum": 0.0,
                "kol_quality": 0.0,
                "news_catalyst": 0.0,
                "hype_manipulation_risk": 0.0,
            },
        }],
    }
    row = harden(payload)["tokens"][0]
    assert row["scores"]["social_momentum"] == 0.0
    assert row["scores"]["kol_quality"] == 0.0
    assert row["scores"]["hype_manipulation_risk"] == 0.0
    assert row["scores"]["news_catalyst"] is None
