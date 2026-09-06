from datetime import datetime, timezone

from wallet500.pending_confirmation_truth_normalizer import normalize


NOW = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)


def candidate(*, market_observed=True, verified_independent=1):
    return {
        "token_address": "MintA",
        "pair_address": "PairA",
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


def probe(*, verified=True, promotion=False, positive=False, pair="PairA", unresolved=False):
    return {
        "version": "REVIVAL_WALLET_COVERAGE_PROBE_V1",
        "mode": "RESEARCH_ONLY_EXACT_PAIR_WALLET_COVERAGE_PROBE",
        "generated_at": "2026-09-06T09:59:00Z",
        "truth_contract": {
            "probe_is_coverage_only_not_accumulation_alpha": True,
            "probe_never_changes_candidate_promotion": True,
            "probe_never_changes_real_alert_gate": True,
            "unresolved_target_mint_touch_fails_closed": True,
        },
        "tokens": [{
            "token_address": "MintA",
            "pair_address": pair,
            "coverage_verified": verified,
            "promotion_eligible": promotion,
            "positive": positive,
            "target_mint_touched": unresolved,
            "unresolved_target_touch": unresolved,
            "resolved_signed_owner": verified and not unresolved,
            "status": "PARTIAL_TARGET_TOUCH_OWNER_UNRESOLVED" if unresolved else "VERIFIED_SIGNED_OWNER_TARGET_TOUCH",
        }],
    }


def test_verified_but_not_positive_is_not_pending():
    row = candidate()
    payload = normalize({"counts": {}, "truth_contract": {}, "candidates": [row]}, now=NOW)
    assert "MARKET_CONFIRMATION_PENDING" not in row["pending_confirmations"]
    assert "INDEPENDENT_EVIDENCE_PENDING" not in row["pending_confirmations"]
    assert "WALLET_COVERAGE_PENDING" in row["pending_confirmations"]
    assert "MARKET_EVIDENCE_VERIFIED_NOT_POSITIVE" in row["verification_outcomes"]
    assert "INDEPENDENT_EVIDENCE_VERIFIED_NOT_POSITIVE" in row["verification_outcomes"]
    assert row["status"] == "DEEP_WATCH"
    assert row["coverage"]["evidence_ready"] is False
    assert payload["truth_contract"]["normalizer_changes_real_alert_gate"] is False


def test_non_promoting_wallet_probe_closes_only_wallet_pending():
    row = candidate()
    payload = normalize({"counts": {}, "truth_contract": {}, "candidates": [row]}, probe(), now=NOW)
    assert "WALLET_COVERAGE_PENDING" not in row["pending_confirmations"]
    assert "WALLET_COVERAGE_VERIFIED_NON_PROMOTING_PROBE" in row["verification_outcomes"]
    assert row["coverage"]["wallet_coverage_observed"] is True
    assert row["coverage"]["verified_independent_count"] == 1
    assert row["coverage"]["positive_independent_count"] == 0
    assert row["coverage"]["evidence_ready"] is False
    assert row["status"] == "DEEP_WATCH"
    assert payload["counts"]["wallet_coverage_pending"] == 0
    assert payload["truth_contract"]["broad_wallet_probe_is_non_promoting_coverage_only"] is True
    assert payload["truth_contract"]["normalizer_changes_candidate_promotion"] is False
    assert payload["truth_contract"]["normalizer_changes_real_alert_gate"] is False


def test_verified_attribution_gap_is_fail_closed_not_pending():
    row = candidate()
    payload = normalize(
        {"counts": {}, "truth_contract": {}, "candidates": [row]},
        probe(verified=False, unresolved=True),
        now=NOW,
    )
    assert "WALLET_COVERAGE_PENDING" not in row["pending_confirmations"]
    assert "WALLET_ATTRIBUTION_GAP_VERIFIED_FAIL_CLOSED" in row["verification_outcomes"]
    assert row["coverage"]["wallet_coverage_observed"] is True
    assert row["coverage"]["wallet_attribution_resolved"] is False
    assert row["coverage"]["wallet_attribution_gap_fail_closed"] is True
    assert row["coverage"]["positive_independent_count"] == 0
    assert row["coverage"]["evidence_ready"] is False
    assert row["status"] == "DEEP_WATCH"
    assert payload["counts"]["wallet_attribution_gap_verified_fail_closed"] == 1
    assert payload["truth_contract"]["verified_wallet_attribution_gap_is_not_pending_and_never_positive"] is True
    assert payload["truth_contract"]["normalizer_changes_candidate_promotion"] is False
    assert payload["truth_contract"]["normalizer_changes_real_alert_gate"] is False


def test_probe_with_wrong_pair_or_alpha_flags_cannot_close_pending():
    for bad in (
        probe(pair="WrongPair"),
        probe(promotion=True),
        probe(positive=True),
    ):
        row = candidate()
        normalize({"counts": {}, "truth_contract": {}, "candidates": [row]}, bad, now=NOW)
        assert "WALLET_COVERAGE_PENDING" in row["pending_confirmations"]


def test_unverified_without_proven_attribution_gap_stays_pending():
    row = candidate()
    normalize({"counts": {}, "truth_contract": {}, "candidates": [row]}, probe(verified=False), now=NOW)
    assert "WALLET_COVERAGE_PENDING" in row["pending_confirmations"]


def test_missing_evidence_stays_pending():
    row = candidate(market_observed=False, verified_independent=0)
    normalize({"counts": {}, "truth_contract": {}, "candidates": [row]}, now=NOW)
    assert "MARKET_CONFIRMATION_PENDING" in row["pending_confirmations"]
    assert "INDEPENDENT_EVIDENCE_PENDING" in row["pending_confirmations"]
    assert "WALLET_COVERAGE_PENDING" in row["pending_confirmations"]
