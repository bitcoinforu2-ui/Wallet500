import wallet500.social_provider_budget_advisor as adv


def _history(runs=1, state="ACTIVE_EXACT_EVIDENCE", exact_ratio=1.0, degraded=0.0, exact_total=8, exact_per_call=1.0, tokens_per_call=0.25, budget=4):
    return {
        "mode": "SOCIAL_SOURCE_HEALTH_HISTORY_OBSERVABILITY_ONLY_V2",
        "runs_count": runs,
        "provider_rollup": {
            "demo": {
                "runs_observed": runs,
                "latest_state": state,
                "latest_call_budget": budget,
                "calls_used_total": runs * 2,
                "exact_evidence_run_ratio": exact_ratio,
                "degraded_run_ratio": degraded,
                "exact_direct_events_total": exact_total,
                "exact_events_per_call": exact_per_call,
                "tokens_with_exact_evidence_per_call": tokens_per_call,
            }
        },
    }


def test_single_run_never_produces_budget_change_advice():
    payload = adv.build(_history(runs=1))
    row = payload["providers"][0]
    assert row["recommendation"] == "COLLECT_MORE_HISTORY"
    assert row["suggested_budget_delta"] is None
    assert row["automatic_change"] is False
    assert payload["automatic_budget_changes"] is False
    assert payload["production_effect"] is False
    assert payload["truth_contract"]["single_run_never_produces_budget_change_advice"] is True


def test_good_multi_run_direct_yield_can_only_be_human_review_candidate():
    payload = adv.build(_history(runs=6, exact_ratio=0.83, exact_total=18, exact_per_call=0.75, tokens_per_call=0.2))
    row = payload["providers"][0]
    assert row["recommendation"] == "CANDIDATE_INCREASE_AFTER_HUMAN_REVIEW"
    assert row["confidence"] == "MEDIUM"
    assert row["evidence_efficiency_score"] is not None
    assert row["automatic_change"] is False
    assert row["score_effect"] == "NONE_PROVIDER_POLICY_ADVICE_ONLY"
    assert row["alert_gate_effect"] == "NONE"


def test_degraded_provider_is_fixed_before_more_spend():
    payload = adv.build(_history(runs=8, exact_ratio=0.75, degraded=0.625, exact_total=20, exact_per_call=1.0, tokens_per_call=0.4))
    row = payload["providers"][0]
    assert row["recommendation"] == "FIX_RELIABILITY_BEFORE_SPEND"
    assert row["automatic_change"] is False


def test_zero_yield_needs_longer_window_before_decrease_candidate():
    early = adv.build(_history(runs=8, state="ACTIVE_NO_EXACT_EVIDENCE", exact_ratio=0.0, exact_total=0, exact_per_call=0.0, tokens_per_call=0.0))
    late = adv.build(_history(runs=12, state="ACTIVE_NO_EXACT_EVIDENCE", exact_ratio=0.0, exact_total=0, exact_per_call=0.0, tokens_per_call=0.0))
    assert early["providers"][0]["recommendation"] == "HOLD_CURRENT_BUDGET"
    assert late["providers"][0]["recommendation"] == "CANDIDATE_DECREASE_AFTER_HUMAN_REVIEW"


def test_not_configured_is_connection_gap_not_bad_evidence():
    payload = adv.build(_history(runs=20, state="NOT_CONFIGURED", exact_ratio=0.0, exact_total=0, exact_per_call=0.0, tokens_per_call=0.0, budget=6))
    row = payload["providers"][0]
    assert row["recommendation"] == "CONNECT_PROVIDER_FIRST"
    assert payload["truth_contract"]["not_configured_is_not_bad_evidence"] is True


def test_non_budgeted_official_source_remains_observability_only():
    payload = adv.build(_history(runs=20, state="ACTIVE_OFFICIAL_CONTEXT", exact_ratio=0.5, exact_total=10, exact_per_call=0.0, tokens_per_call=0.0, budget=None))
    row = payload["providers"][0]
    assert row["recommendation"] == "OBSERVE_NON_BUDGETED_SOURCE"
    assert row["evidence_efficiency_score"] is None
