from datetime import datetime, timezone

from wallet500.social_intelligence_v2 import score_token


def test_unknown_influencer_is_capped_without_forward_history():
    now = datetime.now(timezone.utc)
    scan = {
        "symbol": "TEST",
        "events": [
            {"source": "x", "author": "a", "attribution": "EXACT_CONTRACT", "text": "mint"},
            {"source": "youtube", "author": "b", "attribution": "EXACT_CONTRACT", "text": "mint"},
            {"source": "reddit", "author": "c", "attribution": "EXACT_CONTRACT", "text": "mint"},
        ],
        "provider_status": [],
    }
    row = score_token("mint", scan, None, {}, {}, now)
    assert row["scores"]["kol_quality"] <= 45
    assert row["kol_confidence"] == "ATTENTION_ONLY_NO_FORWARD_REPUTATION"
    assert row["automatic_buy"] is False


def test_paid_contamination_penalizes_narrative():
    now = datetime.now(timezone.utc)
    organic = {
        "organic_acceleration_score": 80,
        "contamination_ratio_24h": 0.8,
        "latest_event_at": now.isoformat(),
        "last_24h": {"raw_mentions": 20, "independent_organic_mentions": 2},
        "status": "ORGANIC_ACCELERATION",
    }
    row = score_token("mint", {}, organic, {}, {}, now)
    assert row["scores"]["hype_manipulation_risk"] >= 50
    assert row["scores"]["narrative"] < 80
