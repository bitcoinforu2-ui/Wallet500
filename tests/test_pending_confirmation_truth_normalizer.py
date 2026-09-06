from wallet500.pending_confirmation_truth_normalizer import normalize


def candidate(*, market_observed=True, verified_independent=1):
    return {
        "truth": {
            "revival_source_fresh": True,
            "exact_pair_verified": True,
        },
        "market": {
            "price_usd": 1.0 if market_observed else None,
            "liquidity_usd": 75000.0 if market_observed else None,
            "market_positive": False,
        },
        "coverage": {
            "verified_independent_count": verified_independent,
            "positive_independent_count": 0,
            "evidence_ready": False,
        },
        "pending_confirmations": [
            "MARKET_CONFIRMATION_PENDING",
            "INDEPENDENT_EVIDENCE_PENDING",
            "WALLET_COVERAGE_PENDING",
        ],
        "verification_outcomes": [],
        "status": "DEEP_WATCH",
        "discovery_tier": "BASELINE_DEEP_WATCH",
    }


def test_verified_but_not_positive_is_not_pending():
    row = candidate()
    payload = normalize({"counts": {}, "truth_contract": {}, "candidates": [row]})
    assert "MARKET_CONFIRMATION_PENDING" not in row["pending_confirmations"]
    assert "INDEPENDENT_EVIDENCE_PENDING" not in row["pending_confirmations"]
    assert "WALLET_COVERAGE_PENDING" in row["pending_confirmations"]
    assert "MARKET_EVIDENCE_VERIFIED_NOT_POSITIVE" in row["verification_outcomes"]
    assert "INDEPENDENT_EVIDENCE_VERIFIED_NOT_POSITIVE" in row["verification_outcomes"]
    assert row["status"] == "DEEP_WATCH"
    assert row["coverage"]["evidence_ready"] is False
    assert payload["truth_contract"]["normalizer_changes_real_alert_gate"] is False


def test_missing_evidence_stays_pending():
    row = candidate(market_observed=False, verified_independent=0)
    normalize({"counts": {}, "truth_contract": {}, "candidates": [row]})
    assert "MARKET_CONFIRMATION_PENDING" in row["pending_confirmations"]
    assert "INDEPENDENT_EVIDENCE_PENDING" in row["pending_confirmations"]
