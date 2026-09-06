import wallet500.social_source_health_history as hist


def _scan(ts, x_state="ACTIVE_EXACT_EVIDENCE", x_exact=2, bluesky_state="DEGRADED_UNKNOWN"):
    return {
        "version": 8,
        "generated_at": ts,
        "targets_scanned": 24,
        "direct_provider_budget": {"x": 1, "youtube": 1, "reddit": 6},
        "direct_provider_calls_used": {"x": 1, "youtube": 1, "reddit": 3},
        "mesh_provider_budget": {"telegram_mtproto": 4, "farcaster": 6, "discord": 6, "threads": 6, "bluesky": 12},
        "mesh_provider_calls_used": {"telegram_mtproto": 0, "farcaster": 0, "discord": 0, "threads": 0, "bluesky": 2},
        "mesh_public_index": {"budget": 8, "calls_used": 8},
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
                "social_mesh_public_index": {
                    "state": "ACTIVE_NO_EXACT_EVIDENCE",
                    "configured": True,
                    "exact_direct_events": 0,
                    "official_context_events": 0,
                    "indexed_exact_context_events": 0,
                    "tokens_with_exact_evidence": 0,
                },
                "telegram_official": {
                    "state": "ACTIVE_OFFICIAL_CONTEXT",
                    "configured": True,
                    "exact_direct_events": 0,
                    "official_context_events": 5,
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
    assert second["truth_contract"]["call_efficiency_is_observability_only"] is True
    assert second["truth_contract"]["call_efficiency_uses_only_same_run_measured_events"] is True


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
    assert x["calls_used_total"] == 2
    assert x["call_budget_total"] == 2
    assert x["call_metric_exact_events_total"] == 2
    assert x["call_metric_tokens_with_exact_evidence_total"] == 1
    assert x["call_utilization_ratio"] == 1.0
    assert x["exact_events_per_call"] == 1.0
    assert x["tokens_with_exact_evidence_per_call"] == 0.5
    assert x["budget_recommendation_effect"] == "NONE_OBSERVE_ONLY"
    assert second["production_effect"] is False
    assert second["automatic_buy"] is False


def test_history_tracks_degraded_ratio_as_observability_only():
    first = hist.build(_scan("2026-09-06T05:00:00+00:00"), {})
    second = hist.build(_scan("2026-09-06T05:30:00+00:00", bluesky_state="ACTIVE_EXACT_EVIDENCE"), first)
    bsky = second["provider_rollup"]["bluesky"]
    assert bsky["degraded_run_ratio"] == 0.5
    assert bsky["exact_evidence_run_ratio"] == 0.0
    assert bsky["calls_used_total"] == 4
    assert bsky["call_budget_total"] == 24
    assert bsky["call_metric_exact_events_total"] == 0
    assert bsky["call_utilization_ratio"] == 0.1667
    assert second["truth_contract"]["single_run_never_changes_provider_policy"] is True


def test_legacy_events_without_call_metrics_never_inflate_efficiency():
    first = hist.build(_scan("2026-09-06T05:00:00+00:00"), {})
    legacy = first["runs"][0]["providers"]["bluesky"]
    legacy["exact_direct_events"] = 27
    legacy["tokens_with_exact_evidence"] = 4
    legacy.pop("call_budget", None)
    legacy.pop("calls_used", None)

    second = hist.build(_scan("2026-09-06T05:30:00+00:00", bluesky_state="DEGRADED_UNKNOWN"), first)
    bsky = second["provider_rollup"]["bluesky"]
    assert bsky["exact_direct_events_total"] == 27
    assert bsky["tokens_with_exact_evidence_total"] == 4
    assert bsky["call_metric_runs"] == 1
    assert bsky["calls_used_total"] == 2
    assert bsky["call_metric_exact_events_total"] == 0
    assert bsky["call_metric_tokens_with_exact_evidence_total"] == 0
    assert bsky["exact_events_per_call"] == 0.0
    assert bsky["tokens_with_exact_evidence_per_call"] == 0.0


def test_history_keeps_unknown_call_metrics_null_for_non_budgeted_sources():
    payload = hist.build(_scan("2026-09-06T05:00:00+00:00"), {})
    telegram = payload["provider_rollup"]["telegram_official"]
    assert telegram["calls_used_total"] is None
    assert telegram["call_budget_total"] is None
    assert telegram["exact_events_per_call"] is None
    assert telegram["call_utilization_ratio"] is None
