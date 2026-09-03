from datetime import datetime, timezone
import json

from wallet500.alpha_robustness import MODE, run


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def rec(lane, event_at, ret24=None, ret7=None):
    checkpoints = {}
    if ret24 is not None:
        checkpoints["24h"] = {"friction_adjusted_return_pct": ret24}
    if ret7 is not None:
        checkpoints["7d"] = {"friction_adjusted_return_pct": ret7}
    return {"lane": lane, "event_at": event_at, "checkpoints": checkpoints}


def test_audit_isolated_and_collecting(tmp_path):
    write(tmp_path / "alpha-proof-ledger.json", {
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "signals": {"s1": rec("PRECURSOR_REAWAKENING", "2026-09-01T00:00:00+00:00", 10)},
        "controls": {"c1": rec("REJECTED_TRADABLE_CONTROL", "2026-09-01T00:00:00+00:00", 1)},
    })
    write(tmp_path / "alpha-matched-controls.json", {"mode": "ALPHA_MATCHED_CONTROLS_DIAGNOSTIC_V1", "lanes": {}})
    report = run(tmp_path, now=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc))
    assert report["mode"] == MODE
    assert report["primary_robustness_status"] == "COLLECTING_FORWARD_SAMPLE"
    safety = report["safety_contract"]
    assert safety["changes_discovery_funnel"] is False
    assert safety["changes_candidate_qualification"] is False
    assert safety["changes_production_gate"] is False
    assert safety["can_block_or_drop_candidate"] is False
    assert safety["can_block_or_drop_signal"] is False


def test_robust_24h_waits_for_7d(tmp_path):
    signals = {}
    controls = {}
    for i in range(20):
        signals[f"s{i}"] = rec("PRECURSOR_REAWAKENING", "2026-09-01T00:00:00+00:00", 15 + i * 0.1)
        controls[f"c{i}"] = rec("REJECTED_TRADABLE_CONTROL", "2026-09-01T00:00:00+00:00", 1 + i * 0.05)
    write(tmp_path / "alpha-proof-ledger.json", {"mode": "FORWARD_ONLY_ALPHA_PROOF_V1", "signals": signals, "controls": controls})
    write(tmp_path / "alpha-matched-controls.json", {"mode": "ALPHA_MATCHED_CONTROLS_DIAGNOSTIC_V1", "lanes": {}})
    report = run(tmp_path, now=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc))
    assert report["primary_robustness_status"] == "ROBUST_24H_AWAITING_7D"
    h24 = report["lanes"]["PRECURSOR_REAWAKENING"]["horizons"]["24h"]
    assert h24["signal"]["coverage_pct"] == 100.0
    assert h24["control"]["coverage_pct"] == 100.0
    assert h24["mean_alpha_pct"] > 0
    assert h24["median_alpha_pct"] > 0
    assert h24["leave_one_out"]["all_single_deletions_positive"] is True


def test_best_signal_dependency_is_flagged(tmp_path):
    signals = {}
    controls = {}
    for i in range(20):
        ret = 300.0 if i == 0 else 0.0
        signals[f"s{i}"] = rec("PRECURSOR_REAWAKENING", "2026-09-01T00:00:00+00:00", ret)
        controls[f"c{i}"] = rec("REJECTED_TRADABLE_CONTROL", "2026-09-01T00:00:00+00:00", 5.0)
    write(tmp_path / "alpha-proof-ledger.json", {"mode": "FORWARD_ONLY_ALPHA_PROOF_V1", "signals": signals, "controls": controls})
    write(tmp_path / "alpha-matched-controls.json", {"mode": "ALPHA_MATCHED_CONTROLS_DIAGNOSTIC_V1", "lanes": {}})
    report = run(tmp_path, now=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc))
    lane = report["lanes"]["PRECURSOR_REAWAKENING"]
    assert lane["robustness_status"] == "FRAGILE_FORWARD_ALPHA"
    assert "BEST_SIGNAL_DOMINATES_ALPHA" in lane["robustness_reasons"]
