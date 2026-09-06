import copy

import pytest

import wallet500.social_provider_budget_advisor as adv


def _history(
    measured_runs=1,
    history_runs=None,
    state="ACTIVE_EXACT_EVIDENCE",
    measured_exact_ratio=1.0,
    measured_degraded=0.0,
    measured_exact_total=8,
    exact_per_call=1.0,
    tokens_per_call=0.25,
    budget=4,
    calls_used=None,
    provider="demo",
):
    if history_runs is None:
        history_runs = measured_runs
    if calls_used is None:
        calls_used = measured_runs * 2
    return {
        "mode": "SOCIAL_SOURCE_HEALTH_HISTORY_OBSERVABILITY_ONLY_V2",
        "runs_count": history_runs,
        "provider_rollup": {
            provider: {
                "runs_observed": history_runs,
                "call_exposure_runs": measured_runs,
                "latest_state": state,
                "latest_call_budget": budget,
                "calls_used_total": calls_used,
                "exact_evidence_run_ratio": measured_exact_ratio,
                "call_exposure_exact_evidence_run_ratio": measured_exact_ratio if measured_runs else None,
                "call_exposure_degraded_run_ratio": measured_degraded if measured_runs else None,
                "call_metric_exact_events_total": measured_exact_total,
                "exact_events_per_call": exact_per_call,
                "tokens_with_exact_evidence_per_call": tokens_per_call,
                "direct_tokens_with_exact_evidence_per_call": tokens_per_call,
            }
        },
    }


def test_single_measured_run_never_produces_budget_change_advice():
    payload = adv.build(_history(measured_runs=1, history_runs=20))
    row = payload["providers"][0]
    assert row["recommendation"] == "COLLECT_MORE_MEASURED_HISTORY"
    assert row["measured_runs_for_policy"] == 1
    assert row["runs_observed"] == 20
    assert row["suggested_budget_delta"] is None
    assert row["automatic_change"] is False
    assert payload["automatic_budget_changes"] is False
    assert payload["production_effect"] is False
    assert payload["truth_contract"]["single_run_never_produces_budget_change_advice"] is True
    assert payload["truth_contract"]["budget_advice_uses_only_positive_call_exposure_runs"] is True
    adv.validate(payload)


def test_good_measured_direct_yield_can_only_be_human_review_candidate():
    payload = adv.build(_history(measured_runs=6, measured_exact_ratio=0.83, measured_exact_total=18, exact_per_call=0.75, tokens_per_call=0.2))
    row = payload["providers"][0]
    assert row["recommendation"] == "CANDIDATE_INCREASE_AFTER_HUMAN_REVIEW"
    assert row["confidence"] == "MEDIUM"
    assert row["evidence_efficiency_score"] is not None
    assert row["evidence_efficiency_score"] > 0
    assert row["automatic_change"] is False
    assert row["score_effect"] == "NONE_PROVIDER_POLICY_ADVICE_ONLY"
    assert row["alert_gate_effect"] == "NONE"
    adv.validate(payload)


def test_degraded_measured_provider_is_fixed_before_more_spend():
    payload = adv.build(_history(measured_runs=8, measured_exact_ratio=0.75, measured_degraded=0.625, measured_exact_total=20, exact_per_call=1.0, tokens_per_call=0.4))
    row = payload["providers"][0]
    assert row["recommendation"] == "FIX_RELIABILITY_BEFORE_SPEND"
    assert row["automatic_change"] is False
    adv.validate(payload)


def test_zero_yield_needs_longer_measured_window_before_decrease_candidate_and_scores_zero():
    early = adv.build(_history(measured_runs=8, state="ACTIVE_NO_EXACT_EVIDENCE", measured_exact_ratio=0.0, measured_exact_total=0, exact_per_call=0.0, tokens_per_call=0.0))
    late = adv.build(_history(measured_runs=12, state="ACTIVE_NO_EXACT_EVIDENCE", measured_exact_ratio=0.0, measured_exact_total=0, exact_per_call=0.0, tokens_per_call=0.0))
    assert early["providers"][0]["recommendation"] == "HOLD_CURRENT_BUDGET"
    assert early["providers"][0]["evidence_efficiency_score"] == 0.0
    assert late["providers"][0]["recommendation"] == "CANDIDATE_DECREASE_AFTER_HUMAN_REVIEW"
    assert late["providers"][0]["evidence_efficiency_score"] == 0.0
    assert late["truth_contract"]["zero_direct_yield_means_zero_efficiency_score"] is True
    adv.validate(early)
    adv.validate(late)


def test_not_configured_is_connection_gap_not_bad_evidence_and_has_no_efficiency_score():
    payload = adv.build(_history(measured_runs=0, history_runs=20, state="NOT_CONFIGURED", measured_exact_ratio=0.0, measured_exact_total=0, exact_per_call=0.0, tokens_per_call=0.0, budget=6, calls_used=0))
    row = payload["providers"][0]
    assert row["recommendation"] == "CONNECT_PROVIDER_FIRST"
    assert row["evidence_efficiency_score"] is None
    assert row["measured_runs_for_policy"] == 0
    assert payload["truth_contract"]["not_configured_is_not_bad_evidence"] is True
    assert payload["truth_contract"]["no_direct_calls_means_no_efficiency_score"] is True
    adv.validate(payload)


def test_nonbudgeted_official_source_remains_observability_only():
    payload = adv.build(_history(measured_runs=0, history_runs=20, state="ACTIVE_OFFICIAL_CONTEXT", measured_exact_ratio=0.5, measured_exact_total=10, exact_per_call=0.0, tokens_per_call=0.0, budget=None, calls_used=0))
    row = payload["providers"][0]
    assert row["recommendation"] == "OBSERVE_NON_BUDGETED_SOURCE"
    assert row["evidence_efficiency_score"] is None
    adv.validate(payload)


def test_public_index_never_gets_direct_budget_advice():
    payload = adv.build(_history(measured_runs=30, history_runs=30, state="ACTIVE_NO_EXACT_EVIDENCE", measured_exact_ratio=0.0, measured_exact_total=0, exact_per_call=0.0, tokens_per_call=0.0, budget=8, calls_used=240, provider="social_mesh_public_index"))
    row = payload["providers"][0]
    assert row["recommendation"] == "OBSERVE_CONTEXT_ONLY_SOURCE"
    assert row["evidence_efficiency_score"] is None
    assert row["suggested_budget_delta"] is None
    assert payload["truth_contract"]["public_index_never_gets_direct_budget_advice"] is True
    adv.validate(payload)


def test_validate_rejects_early_increase_advice():
    payload = adv.build(_history(measured_runs=1, history_runs=20))
    bad = copy.deepcopy(payload)
    bad["providers"][0]["recommendation"] = "CANDIDATE_INCREASE_AFTER_HUMAN_REVIEW"
    with pytest.raises(ValueError, match="EARLY_POLICY_ADVICE"):
        adv.validate(bad)


def test_validate_rejects_public_index_policy_drift():
    payload = adv.build(_history(measured_runs=30, history_runs=30, state="ACTIVE_NO_EXACT_EVIDENCE", measured_exact_ratio=0.0, measured_exact_total=0, exact_per_call=0.0, tokens_per_call=0.0, budget=8, calls_used=240, provider="social_mesh_public_index"))
    bad = copy.deepcopy(payload)
    bad["providers"][0]["recommendation"] = "HOLD_CURRENT_BUDGET"
    with pytest.raises(ValueError, match="PUBLIC_INDEX_POLICY_LEAK"):
        adv.validate(bad)


def test_validate_rejects_any_automatic_change():
    payload = adv.build(_history(measured_runs=6, measured_exact_ratio=0.8, exact_per_call=0.8, tokens_per_call=0.2))
    bad = copy.deepcopy(payload)
    bad["providers"][0]["automatic_change"] = True
    with pytest.raises(ValueError, match="AUTO_CHANGE_LEAK"):
        adv.validate(bad)


def test_validate_rejects_efficiency_score_without_calls():
    payload = adv.build(_history(measured_runs=0, history_runs=10, state="ACTIVE_NO_EXACT_EVIDENCE", measured_exact_ratio=0.0, measured_exact_total=0, exact_per_call=0.0, tokens_per_call=0.0, budget=4, calls_used=0))
    bad = copy.deepcopy(payload)
    bad["providers"][0]["evidence_efficiency_score"] = 25.0
    with pytest.raises(ValueError, match="SCORE_WITHOUT_CALL_EXPOSURE"):
        adv.validate(bad)
