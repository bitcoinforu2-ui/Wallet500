from wallet500.veteran_dna_forward_lab import summarize, MAX_24H_LABEL_LAG_HOURS


def test_late_24h_is_counted_but_not_assumed_a_winner():
    records = {
        "solana:token:pair": {
            "t0_features": {"volume_h1_usd": 10},
            "checkpoints": {"24h": {"observed_age_hours": 33.0, "label_eligible": False, "return_pct": 200}},
            "label_24h": None,
            "label_status": "INSUFFICIENT_TIMESTAMP_COVERAGE",
        }
    }
    result = summarize(records)
    assert result["counts"]["late_24h_excluded_from_labels"] == 1
    assert result["counts"]["winners"] == 0
    assert result["counts"]["open"] == 1
    assert result["counts"]["research_ready"] is False


def test_24h_label_window_is_bounded():
    assert MAX_24H_LABEL_LAG_HOURS == 2.0
