from wallet500.holder_truth_guard import quarantine_revival_row, quarantine_waking_holder


def test_rugcheck_revival_holder_is_quarantined():
    row = {
        "source": "RUGCHECK_EXACT_MINT_PUBLIC_REPORT",
        "holder_count": 41556,
        "holder_growth_count": 20000,
        "holder_growth_pct": 93.0,
        "holder_growth_24h_ready": True,
        "holder_growth_24h_count": 20000,
        "holder_growth_24h_pct": 93.0,
        "holder_growth_7d_ready": True,
    }
    assert quarantine_revival_row(row) is True
    assert row["raw_provider_holder_count"] == 41556
    assert row["holder_count"] is None
    assert row["growth_eligible"] is False
    assert row["holder_growth_24h_ready"] is False
    assert row["holder_growth_7d_ready"] is False
    assert row["holder_growth_count"] is None
    assert row["holder_truth_status"] == "QUARANTINED_PROVIDER_SEMANTICS"


def test_rugcheck_waking_holder_cannot_score_growth():
    holder = {
        "source": "RUGCHECK_EXACT_MINT_PUBLIC_REPORT",
        "verified": True,
        "score": 80.0,
        "signals": ["HOLDER_GROWTH_STRONG"],
        "metrics": {
            "holder_count": 41556,
            "previous_holder_count": 21267,
            "holder_change_pct": 95.4,
        },
    }
    assert quarantine_waking_holder(holder) is True
    assert holder["verified"] is False
    assert holder["score"] == 0.0
    assert holder["growth_eligible"] is False
    assert holder["metrics"]["raw_provider_holder_count"] == 41556
    assert holder["metrics"]["holder_count"] is None
    assert holder["metrics"]["previous_holder_count"] is None
    assert holder["metrics"]["holder_change_pct"] is None


def test_trusted_non_rugcheck_source_is_untouched():
    row = {"source": "TRUSTED_UNIQUE_OWNER_SOURCE", "holder_count": 100}
    assert quarantine_revival_row(row) is False
    assert row == {"source": "TRUSTED_UNIQUE_OWNER_SOURCE", "holder_count": 100}
