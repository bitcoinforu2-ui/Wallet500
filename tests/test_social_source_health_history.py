import wallet500.social_source_health_history as hist


def _scan(ts, x_state="ACTIVE_EXACT_EVIDENCE", x_exact=2, bluesky_state="DEGRADED_UNKNOWN"):
    return {
        "version": 8,
        "generated_at": ts,
        "targets_scanned": 24,
        "source_health": {
            "providers": {
                "x": {
                    "state": x_state,
                    "configured": True,
                    "exact_direct_events": x_exact,
                    "official_context_events": 0,
                    "indexed_exact_context_events": 0,
                    "tokens_with_exact_evidence": 1 if x_exact else 0,
                    "credential_requirements": ["SHOULD_NOT_BE_STORED"],
                },
                "bluesky": {
                    "state": bluesky_state,
                    "configured": True,
                    "exact_direct_events": 0,
                    "official_context_events": 0,
                    "indexed_exact_context_events": 0,
                    "tokens_with_exact_evidence": 0,
                },
            }
        },
    }


def test_history_deduplicates_same_scan_and_never_stores_secret_metadata():
    first = hist.build(_scan("2026-09-06T05:00:00+00:00"), {})
    second = hist.build(_scan("2026-09-06T05:00:00+00:00"), first)
    assert first["runs_count"] == 1
    assert second["runs_count"] == 1
    assert second["new_run_appended"] is False
    assert "credential_requirements" not in str(second["runs"])
    assert second["truth_contract"]["secret_values_never_stored"] is True
    assert second["truth_contract"]["provider_health_never_auto_changes_api_budgets"] is True


def test_history_rollup_measures_multi_run_yield_without_policy_effect():
    first = hist.build(_scan("2026-09-06T05:00:00+00:00"), {})
    second = hist.build(
        _scan("2026-09-06T05:30:00+00:00", x_state="ACTIVE_NO_EXACT_EVIDENCE", x_exact=0),
        first,
    )
    x = second["provider_rollup"]["x"]
    assert second["runs_count"] == 2
    assert x["runs_observed"] == 2
    assert x["exact_evidence_run_ratio"] == 0.5
    assert x["exact_direct_events_total"] == 2
    assert x["budget_recommendation_effect"] == "NONE_OBSERVE_ONLY"
    assert second["production_effect"] is False
    assert second["automatic_buy"] is False


def test_history_tracks_degraded_ratio_as_observability_only():
    first = hist.build(_scan("2026-09-06T05:00:00+00:00"), {})
    second = hist.build(_scan("2026-09-06T05:30:00+00:00", bluesky_state="ACTIVE_EXACT_EVIDENCE"), first)
    bsky = second["provider_rollup"]["bluesky"]
    assert bsky["degraded_run_ratio"] == 0.5
    assert bsky["exact_evidence_run_ratio"] == 0.0
    assert second["truth_contract"]["single_run_never_changes_provider_policy"] is True
