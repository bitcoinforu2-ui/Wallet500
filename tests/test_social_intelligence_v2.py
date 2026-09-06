from datetime import datetime, timezone

from wallet500.social_intelligence_v2 import _freshness_score, score_token


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


def test_rfc2822_freshness_is_parsed():
    now = datetime(2026, 9, 6, 3, 0, tzinfo=timezone.utc)
    assert _freshness_score("Sat, 05 Sep 2026 23:30:00 GMT", now) == 85.0


def test_indexed_exact_context_never_becomes_kol_or_organic():
    now = datetime.now(timezone.utc)
    scan = {
        "symbol": "TEST",
        "events": [
            {
                "source": "x_index",
                "author": "x.com",
                "attribution": "EXACT_CONTRACT",
                "text": "exact indexed mention",
                "published_at": now.isoformat(),
            }
        ],
        "provider_status": [{"provider": "x", "status": "FALLBACK_INDEX_OK_CONTEXT_ONLY"}],
    }
    row = score_token("mint", scan, None, {}, {}, now)
    assert row["coverage"]["indexed_exact_context_events"] == 1
    assert row["coverage"]["exact_social_events"] == 0
    assert row["scores"]["kol_quality"] == 0
    assert row["coverage"]["indexed_exact_context_is_organic"] is False
