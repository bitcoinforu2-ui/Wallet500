from wallet500.forensics import wallet_forensics


def test_high_activity_reliable():
    result = wallet_forensics({"transactions_seen": 100, "success_rate": 0.99})
    assert result["forensics_tier"] == "HIGH_ACTIVITY_RELIABLE"
    assert result["confidence"] == 99.0
