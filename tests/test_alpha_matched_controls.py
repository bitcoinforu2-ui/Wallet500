from datetime import datetime, timezone
import json

from wallet500.alpha_matched_controls import MODE, run


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def base_record(lane, chain, token, pair, event_at, enrolled_at, liquidity, ret24=None):
    checkpoints = {}
    if ret24 is not None:
        checkpoints["24h"] = {
            "gross_return_pct": ret24,
            "friction_adjusted_return_pct": ret24 - 2.0,
        }
    return {
        "lane": lane,
        "chain": chain,
        "token": token,
        "pair_address": pair,
        "event_at": event_at,
        "enrolled_at": enrolled_at,
        "entry_liquidity_usd": liquidity,
        "checkpoints": checkpoints,
    }


def test_matched_controls_never_drop_unmatched_signal(tmp_path):
    signal = base_record(
        "PRECURSOR_REAWAKENING", "solana", "SIG", "PAIR-S",
        "2026-09-03T12:10:00+00:00", "2026-09-03T12:11:00+00:00", 100000, 30.0,
    )
    write(tmp_path / "alpha-proof-ledger.json", {
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "signals": {"signal-1": signal},
        "controls": {},
    })
    report = run(tmp_path, now=datetime(2026, 9, 3, 12, 12, tzinfo=timezone.utc))
    assert report["mode"] == MODE
    assert report["formal_signal_count_unchanged"] == 1
    assert report["matched_signal_count"] == 0
    assert report["unmatched_signal_count"] == 1
    assert report["safety_contract"]["can_block_or_drop_signal"] is False
    assert report["safety_contract"]["changes_production_gate"] is False


def test_same_chain_preexisting_similar_liquidity_control_matches(tmp_path):
    signal = base_record(
        "PRECURSOR_REAWAKENING", "solana", "SIG", "PAIR-S",
        "2026-09-03T12:10:00+00:00", "2026-09-03T12:11:00+00:00", 100000, 30.0,
    )
    good = base_record(
        "REJECTED_TRADABLE_CONTROL", "solana", "CTL", "PAIR-C",
        "2026-09-03T11:55:00+00:00", "2026-09-03T12:11:00+00:00", 80000, 10.0,
    )
    wrong_chain = base_record(
        "REJECTED_TRADABLE_CONTROL", "bsc", "CTL2", "PAIR-C2",
        "2026-09-03T12:00:00+00:00", "2026-09-03T12:11:00+00:00", 99000, 50.0,
    )
    write(tmp_path / "alpha-proof-ledger.json", {
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "signals": {"signal-1": signal},
        "controls": {"control-good": good, "control-wrong": wrong_chain},
    })
    report = run(tmp_path, now=datetime(2026, 9, 3, 12, 12, tzinfo=timezone.utc))
    assert report["matched_signal_count"] == 1
    row = report["rows"][0]
    assert row["control_record_id"] == "control-good"
    assert row["horizons"]["24h"]["matched_alpha_gross_pct"] == 20.0


def test_control_discovered_after_signal_enrollment_is_not_backfilled(tmp_path):
    signal = base_record(
        "PRECURSOR_REAWAKENING", "solana", "SIG", "PAIR-S",
        "2026-09-03T12:10:00+00:00", "2026-09-03T12:11:00+00:00", 100000,
    )
    late_control = base_record(
        "REJECTED_TRADABLE_CONTROL", "solana", "CTL", "PAIR-C",
        "2026-09-03T12:00:00+00:00", "2026-09-03T12:20:00+00:00", 95000,
    )
    write(tmp_path / "alpha-proof-ledger.json", {
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "signals": {"signal-1": signal},
        "controls": {"control-late": late_control},
    })
    first = run(tmp_path, now=datetime(2026, 9, 3, 12, 21, tzinfo=timezone.utc))
    assert first["matched_signal_count"] == 0
    state_before = json.loads((tmp_path / "alpha-matched-control-state.json").read_text())
    assert state_before["matches"]["signal-1"]["status"] == "NO_MATCH_AT_FIRST_EVALUATION"

    # Even if a seemingly better control appears later, the old signal is not hindsight-rematched.
    earlier_control = base_record(
        "REJECTED_TRADABLE_CONTROL", "solana", "CTL2", "PAIR-C2",
        "2026-09-03T11:58:00+00:00", "2026-09-03T12:10:00+00:00", 100000,
    )
    write(tmp_path / "alpha-proof-ledger.json", {
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "signals": {"signal-1": signal},
        "controls": {"control-late": late_control, "control-earlier": earlier_control},
    })
    second = run(tmp_path, now=datetime(2026, 9, 3, 12, 30, tzinfo=timezone.utc))
    assert second["matched_signal_count"] == 0
