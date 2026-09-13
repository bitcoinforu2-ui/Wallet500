import json
from datetime import datetime, timedelta, timezone

from wallet500.decision_replay_lab import build


def _source(price=1.0, event_at="2026-09-13T00:00:00+00:00", *, token="TOKEN", pair="PAIR", actionable=None, liquidity=None, checkpoints=None):
    entry = {
        "observed_at": event_at,
        "radar_tier": "NEAR_ALERT",
        "entry_price_usd": price,
        "readiness_passed": 6,
        "readiness_total": 7,
        "verified_execution_liquidity_usd": liquidity,
    }
    if actionable is not None:
        entry["actionable"] = actionable
    return {
        "updated_at": event_at,
        "records": {
            "SHADOW|solana|TOKEN|PAIR": {
                "sample_id": "ignored-sample-id",
                "lane": "NEAR_ALERT_SHADOW",
                "chain": "solana",
                "token_address": token,
                "pair_address": pair,
                "event_at": event_at,
                "entry_price_usd": price,
                "decision_snapshot": {
                    "identity": {"chain": "solana", "token": token, "pair_address": pair},
                    "entry": entry,
                },
                "checkpoints": checkpoints or {},
            }
        },
    }


def _single_record(source):
    return next(iter(source["records"].values()))


def _add_history(source, history):
    _single_record(source)["checkpoint_history"] = history
    return source


def _at(base, **delta):
    return (datetime.fromisoformat(base) + timedelta(**delta)).isoformat()


def test_key_includes_first_decision_timestamp_and_ignores_sample_id():
    source = _source()
    _single_record(source)["sample_id"] = "one"
    ledger1, report = build(source, {})
    source2 = _source()
    _single_record(source2)["sample_id"] = "completely-different"
    ledger2, _ = build(source2, {})
    expected = "solana|TOKEN|PAIR|2026-09-13T00:00:00+00:00"
    assert expected in ledger1["records"]
    assert set(ledger1["records"]) == set(ledger2["records"])
    assert report["source_integrity"]["replay_key_includes_first_decision_timestamp"] is True
    assert report["guardrails"]["symbol_only_identity_forbidden"] is True


def test_existing_t0_is_never_overwritten_on_source_drift():
    ledger1, _ = build(_source(price=1.0), {})
    ledger2, report2 = build(_source(price=2.0), ledger1)
    rec = ledger2["records"]["solana|TOKEN|PAIR|2026-09-13T00:00:00+00:00"]
    assert rec["t0"]["price_usd"] == 1.0
    assert any(x["type"] == "IMMUTABLE_T0_MISMATCH_PRESERVED_OLD_VALUE" for x in report2["source_integrity"]["integrity_events"])


def test_t0_null_stays_null_when_later_source_backfills_value():
    ledger1, _ = build(_source(liquidity=None), {})
    ledger2, report2 = build(_source(liquidity=123456.0), ledger1)
    rec = next(iter(ledger2["records"].values()))
    assert rec["t0"]["exact_pair_liquidity_usd"] is None
    assert any(e["type"] == "IMMUTABLE_T0_MISMATCH_PRESERVED_OLD_VALUE" for e in report2["source_integrity"]["integrity_events"])


def test_same_pair_different_first_decision_times_are_distinct_records():
    first, _ = build(_source(event_at="2026-09-13T00:00:00+00:00"), {})
    second, _ = build(_source(event_at="2026-09-13T01:00:00+00:00"), first)
    assert len(second["records"]) == 2


def test_missing_exact_identity_is_rejected():
    bad = {"records": {"x": {"chain": "solana", "token_address": "TOKEN", "event_at": "2026-09-13T00:00:00+00:00"}}}
    ledger, report = build(bad, {})
    assert not ledger["records"]
    assert report["source_integrity"]["integrity_events"][0]["type"] == "REJECTED_INCOMPLETE_EXACT_IDENTITY"


def test_conflicting_snapshot_pair_is_rejected():
    source = _source()
    _single_record(source)["decision_snapshot"]["identity"]["pair_address"] = "OTHER_PAIR"
    ledger, report = build(source, {})
    assert not ledger["records"]
    assert report["source_integrity"]["integrity_events"][0]["type"] == "REJECTED_IDENTITY_CONFLICT"


def test_first_reliable_observation_at_or_after_horizon_is_selected_not_best_or_latest():
    base = "2026-09-13T00:00:00+00:00"
    source = _add_history(_source(event_at=base), [
        {"captured_at": _at(base, minutes=59), "price_usd": 0.50, "pair_address": "PAIR", "source": "exact"},
        {"captured_at": _at(base, minutes=61), "price_usd": 1.10, "pair_address": "PAIR", "source": "exact"},
        {"captured_at": _at(base, minutes=70), "price_usd": 9.00, "pair_address": "PAIR", "source": "exact"},
    ])
    ledger, _ = build(source, {})
    one_h = next(iter(ledger["records"].values()))["outcomes"]["1h"]
    assert one_h["observed_at"] == _at(base, minutes=61)
    assert one_h["price_usd"] == 1.10
    assert one_h["lag_seconds"] == 60.0


def test_wrong_pair_checkpoint_is_rejected_and_never_selected():
    base = "2026-09-13T00:00:00+00:00"
    source = _add_history(_source(event_at=base), [
        {"captured_at": _at(base, minutes=60), "price_usd": 99.0, "pair_address": "WRONG", "source": "bad"},
        {"captured_at": _at(base, minutes=65), "price_usd": 1.05, "pair_address": "PAIR", "source": "good"},
    ])
    ledger, report = build(source, {})
    one_h = next(iter(ledger["records"].values()))["outcomes"]["1h"]
    assert one_h["price_usd"] == 1.05
    assert one_h["provenance"]["pair_address"] == "PAIR"
    assert one_h["provenance"]["exact_pair_identity_preserved"] is True
    assert any(e["type"] == "REJECTED_CHECKPOINT_IDENTITY_CONFLICT" for e in report["source_integrity"]["integrity_events"])


def test_checkpoint_before_horizon_does_not_mature_that_horizon():
    base = "2026-09-13T00:00:00+00:00"
    source = _add_history(_source(event_at=base), [
        {"captured_at": _at(base, minutes=59, seconds=59), "price_usd": 1.01, "pair_address": "PAIR", "source": "exact"},
    ])
    ledger, _ = build(source, {})
    one_h = next(iter(ledger["records"].values()))["outcomes"]["1h"]
    assert one_h["status"] == "NOT_MATURED_OR_INSUFFICIENT_COVERAGE"


def _matured_source(count, spacing_days, *, dense_hours=False):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = {}
    for i in range(count):
        decision = start + (timedelta(hours=i) if dense_hours else timedelta(days=i * spacing_days))
        terminal = decision + timedelta(days=7, minutes=1)
        event_at = decision.isoformat()
        token = f"TOKEN{i}"
        pair = f"PAIR{i}"
        ret_price = 1.30 if i % 2 == 0 else 0.95
        records[f"sample-{i}"] = {
            "lane": "TEST",
            "chain": "solana",
            "token_address": token,
            "pair_address": pair,
            "event_at": event_at,
            "decision_snapshot": {
                "identity": {"chain": "solana", "token": token, "pair_address": pair},
                "entry": {
                    "observed_at": event_at,
                    "entry_price_usd": 1.0,
                    "actionable": i % 3 == 0,
                    "verified_execution_liquidity_usd": 100000.0,
                    "verified_execution_tradable": True,
                    "turnover": 0.8,
                    "readiness_passed": 6,
                    "readiness_total": 7,
                    "source_lane_count": 2,
                    "evidence_positive_count": 2,
                    "buy_flow_usd": 200.0,
                    "sell_flow_usd": 100.0,
                    "signal_score": 80.0,
                },
            },
            "checkpoint_history": [
                {"captured_at": terminal.isoformat(), "price_usd": ret_price, "pair_address": pair, "verified_execution_liquidity_usd": 110000.0, "source": "EXACT"}
            ],
        }
    return {"updated_at": (start + timedelta(days=400)).isoformat(), "records": records}


def test_29_matured_decisions_can_never_be_ready_for_review():
    _, report = build(_matured_source(29, 8), {})
    assert report["walk_forward"]["matured_decisions"] == 29
    assert report["promotion_gate"]["hard_prerequisites"]["matured_decisions_gte_30"] is False
    assert report["promotion_gate"]["status"] == "NOT_READY_FOR_REVIEW"


def test_30_matured_but_without_two_valid_windows_can_never_be_ready():
    _, report = build(_matured_source(30, 0, dense_hours=True), {})
    assert report["walk_forward"]["matured_decisions"] == 30
    assert report["walk_forward"]["valid_validation_windows"] < 2
    assert report["promotion_gate"]["hard_prerequisites"]["valid_non_overlapping_validation_windows_gte_2"] is False
    assert report["promotion_gate"]["status"] == "NOT_READY_FOR_REVIEW"


def test_walk_forward_has_two_non_overlapping_leakage_free_windows_when_history_allows():
    _, report = build(_matured_source(30, 8), {})
    wf = report["walk_forward"]
    valid = [w for w in wf["non_overlapping_validation_windows"] if w["status"] == "VALID"]
    assert wf["matured_decisions"] == 30
    assert len(valid) == 2
    assert set(valid[0]["validation_keys"]).isdisjoint(valid[1]["validation_keys"])
    for window in valid:
        assert window["leakage_free"] is True
        assert datetime.fromisoformat(window["reference_label_max_at"]) < datetime.fromisoformat(window["validation_started_at"])


def test_policy_a_is_exactly_frozen_t0_actionable_and_shadow_policies_do_not_mutate_it():
    ledger, report = build(_matured_source(30, 8), {})
    for rec in ledger["records"].values():
        assert rec["shadow_decisions"]["A_CURRENT_PRODUCTION"] is rec["t0"]["actionable"]
    assert report["promotion_gate"]["hard_prerequisites"]["baseline_policy_a_unchanged"] is True


def test_build_is_byte_stable_for_unchanged_input_and_previous_ledger():
    source = _matured_source(3, 8)
    ledger1, report1 = build(source, {})
    ledger2, report2 = build(source, ledger1)
    assert json.dumps(ledger1, sort_keys=True, separators=(",", ":")) == json.dumps(ledger2, sort_keys=True, separators=(",", ":"))
    assert json.dumps(report1, sort_keys=True, separators=(",", ":")) == json.dumps(report2, sort_keys=True, separators=(",", ":"))
