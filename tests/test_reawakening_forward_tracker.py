import json

import wallet500.reawakening_forward_tracker as forward

PAIR = "0x9793a9cbb04f781433254e4530398107e6a8dcee"


def reject_record(extra_reasons=None):
    reasons = [
        "CURRENT_LIQUIDITY_BELOW_50K",
        "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION",
    ]
    if extra_reasons:
        reasons.extend(extra_reasons)
    return {
        "first_reject_source": "LIVE_SURVIVAL_FAILED",
        "first_rejected_at": "2026-09-01T10:00:00+00:00",
        "identity": {
            "chain": "bsc",
            "token": "0xabc",
            "pair_address": PAIR,
        },
        "first_reject_snapshot": {
            "observed_at": "2026-09-01T10:00:00+00:00",
            "chain": "bsc",
            "token": "0xabc",
            "pair_address": PAIR,
            "price_usd": 0.001,
            "liquidity_usd": 42_000,
            "live_survival_reasons": reasons,
        },
    }


def live(price=0.00110, liquidity=70_000):
    return {
        "chain": "bsc",
        "token": "0xabc",
        "pair_address": PAIR,
        "token_identity_verified": True,
        "target_token_side": "BASE",
        "price_usd": price,
        "liquidity_usd": liquidity,
        "volume_h1": 50_000,
        "buys_h1": 220,
        "sells_h1": 160,
    }


def seed(tmp_path, records=None):
    records = records or {f"bsc|0xabc|{PAIR}": reject_record()}
    (tmp_path / "rejected-candidate-ledger.json").write_text(
        json.dumps({"records": records})
    )
    (tmp_path / "outcome-tracker.json").write_text(
        json.dumps({"tokens": {}})
    )
    (tmp_path / "reawakening-shadow-state.json").write_text(
        json.dumps(
            {
                "version": 2,
                "mode": "RESEARCH_ONLY_SURVIVOR_REAWAKENING_V2",
                "updated_at": "2026-09-01T10:01:00+00:00",
                "v2_started_at": "2026-09-01T10:01:00+00:00",
                "legacy_v1_triggers": {},
                "v2_candidates": {},
                "v2_triggers": {},
            }
        )
    )


def test_two_dedicated_exact_pair_forward_rows_can_trigger_without_live_files(
    tmp_path, monkeypatch
):
    seed(tmp_path)
    current = {"snapshot": live(0.00110, 70_000)}
    monkeypatch.setattr(
        forward,
        "exact_pair_snapshot",
        lambda chain, token, pair: dict(current["snapshot"]),
    )

    first = forward.run(
        str(tmp_path),
        now_override="2026-09-01T10:05:00+00:00",
        pause_seconds=0,
    )
    assert first["counts"]["shadow_triggers_v2"] == 0
    assert first["counts"]["dedicated_forward_observations_added_this_run"] == 1

    current["snapshot"] = live(0.00115, 72_000)
    second = forward.run(
        str(tmp_path),
        now_override="2026-09-01T10:20:00+00:00",
        pause_seconds=0,
    )
    assert second["counts"]["shadow_triggers_v2"] == 1
    assert second["counts"]["dedicated_forward_triggers_v2"] == 1
    assert "reawakening-forward-state.json" in second["primary_recheck_source"]
    target = second["targets"][0]
    assert target["first_confirmation_at"] == "2026-09-01T10:05:00+00:00"
    assert target["triggered_at"] == "2026-09-01T10:20:00+00:00"
    assert target["evidence_source"] == "DEDICATED_EXACT_PAIR_FORWARD_TRACKER"
    assert target["production_portfolio_impact"] == "NONE"
    assert second["production_gate_changed"] is False
    assert second["automatic_buy"] is False


def test_transient_exact_pair_miss_never_erases_forward_history(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.setattr(
        forward,
        "exact_pair_snapshot",
        lambda chain, token, pair: live(),
    )
    forward.run(
        str(tmp_path),
        now_override="2026-09-01T10:05:00+00:00",
        pause_seconds=0,
    )

    monkeypatch.setattr(
        forward,
        "exact_pair_snapshot",
        lambda chain, token, pair: None,
    )
    payload = forward.run(
        str(tmp_path),
        now_override="2026-09-01T10:20:00+00:00",
        pause_seconds=0,
    )
    state = json.loads(
        (tmp_path / "reawakening-forward-state.json").read_text()
    )
    candidate = next(iter(state["candidates"].values()))
    assert candidate["observations_total"] == 1
    assert len(candidate["hot_observations"]) == 1
    assert payload["counts"]["dedicated_forward_exact_pair_misses_this_run"] == 1
    assert payload["counts"]["shadow_triggers_v2"] == 0


def test_identity_mismatch_is_fail_closed_and_hard_excluded_rejects_are_not_queried(
    tmp_path, monkeypatch
):
    good_key = f"bsc|0xabc|{PAIR}"
    bad_key = f"bsc|0xdef|{PAIR}"
    records = {
        good_key: reject_record(),
        bad_key: {
            **reject_record(extra_reasons=["PUMP_THEN_FAST_REVERSAL"]),
            "identity": {
                "chain": "bsc",
                "token": "0xdef",
                "pair_address": PAIR,
            },
        },
    }
    seed(tmp_path, records)
    calls = []

    def mismatched(chain, token, pair):
        calls.append((chain, token, pair))
        row = live()
        row["pair_address"] = "0xdeadbeef"
        return row

    monkeypatch.setattr(forward, "exact_pair_snapshot", mismatched)
    report = forward.collect(
        str(tmp_path),
        now_override="2026-09-01T10:05:00+00:00",
        pause_seconds=0,
    )
    assert report["eligible_rejects"] == 1
    assert report["exact_pair_attempted"] == 1
    assert len(calls) == 1
    assert report["identity_invalid_or_missing"] == 1
    state = json.loads(
        (tmp_path / "reawakening-forward-state.json").read_text()
    )
    candidate = state["candidates"][good_key]
    assert candidate.get("hot_observations") in (None, [])
    assert candidate["last_measurement_status"] == "EXACT_PAIR_IDENTITY_VALIDATION_FAILED"
