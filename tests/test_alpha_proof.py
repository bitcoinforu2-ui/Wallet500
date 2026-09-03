from datetime import datetime, timezone
import json

from wallet500.alpha_proof import MODE, run


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_forward_only_activation_and_immutable_checkpoints(tmp_path):
    t0 = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    write(tmp_path / "reawakening-shadow.json", {
        "targets": [{
            "chain": "solana", "token": "OLD", "pair_address": "PAIR1",
            "triggered_at": "2026-09-03T11:00:00+00:00", "price_usd": 1.0,
            "current_price_usd": 2.0, "current_return_pct": 100.0, "peak_return_pct": 120.0,
            "updated_at": "2026-09-03T12:00:00+00:00", "metrics": {"liquidity_usd": 60000},
        }]
    })
    write(tmp_path / "discovery-evidence-ledger.json", {"records": {}})
    write(tmp_path / "outcome-tracker.json", {"tokens": {}})
    write(tmp_path / "rejected-candidate-ledger.json", {"records": {}})

    first = run(tmp_path, now=t0)
    assert first["mode"] == MODE
    assert first["formal_signal_count"] == 0
    assert first["supporting_pre_activation"]["count"] == 1

    write(tmp_path / "reawakening-shadow.json", {
        "targets": [{
            "chain": "solana", "token": "NEW", "pair_address": "PAIR2",
            "triggered_at": "2026-09-03T12:01:00+00:00", "price_usd": 1.0,
            "current_price_usd": 1.10, "current_return_pct": 10.0, "peak_return_pct": 10.0,
            "updated_at": "2026-09-03T12:20:00+00:00", "metrics": {"liquidity_usd": 70000},
        }]
    })
    second = run(tmp_path, now=datetime(2026, 9, 3, 12, 20, tzinfo=timezone.utc))
    assert second["formal_signal_count"] == 1
    lane = second["lanes"]["PRECURSOR_REAWAKENING"]
    assert lane["horizons"]["5m"]["signal"]["n"] == 1
    assert lane["horizons"]["15m"]["signal"]["n"] == 1
    assert lane["horizons"]["1h"]["signal"]["n"] == 0
    assert lane["horizons"]["15m"]["signal"]["mean_friction_adjusted_return_pct"] == 8.0

    ledger_before = json.loads((tmp_path / "alpha-proof-ledger.json").read_text())
    cp_before = next(iter(ledger_before["signals"].values()))["checkpoints"]["15m"]
    write(tmp_path / "reawakening-shadow.json", {
        "targets": [{
            "chain": "solana", "token": "NEW", "pair_address": "PAIR2",
            "triggered_at": "2026-09-03T12:01:00+00:00", "price_usd": 1.0,
            "current_price_usd": 0.5, "updated_at": "2026-09-03T13:10:00+00:00",
            "metrics": {"liquidity_usd": 65000},
        }]
    })
    run(tmp_path, now=datetime(2026, 9, 3, 13, 10, tzinfo=timezone.utc))
    ledger_after = json.loads((tmp_path / "alpha-proof-ledger.json").read_text())
    rec = next(iter(ledger_after["signals"].values()))
    assert rec["checkpoints"]["15m"] == cp_before
    assert rec["checkpoints"]["1h"]["gross_return_pct"] == -50.0


def test_tradable_reject_becomes_control(tmp_path):
    activation = "2026-09-03T12:00:00+00:00"
    write(tmp_path / "alpha-proof-ledger.json", {
        "version": 1, "mode": MODE, "activation_at": activation,
        "created_at": activation, "updated_at": activation, "signals": {}, "controls": {}, "policy": {},
    })
    write(tmp_path / "reawakening-shadow.json", {"targets": []})
    write(tmp_path / "discovery-evidence-ledger.json", {"records": {}})
    write(tmp_path / "outcome-tracker.json", {"tokens": {}})
    snap = {"observed_at": "2026-09-03T12:02:00+00:00", "chain": "bsc", "token": "0x1", "pair_address": "0x2", "price_usd": 1.0, "liquidity_usd": 60000}
    write(tmp_path / "rejected-candidate-ledger.json", {"records": {"k": {
        "identity": {"chain": "bsc", "token": "0x1", "pair_address": "0x2"},
        "first_rejected_at": "2026-09-03T12:02:00+00:00", "first_reject_source": "PRODUCTION_RISK_BLOCK",
        "first_decision_class": "REJECT", "first_reject_snapshot": snap,
        "latest_observation": {**snap, "observed_at": "2026-09-03T12:20:00+00:00", "price_usd": 1.2},
    }}})
    report = run(tmp_path, now=datetime(2026, 9, 3, 12, 20, tzinfo=timezone.utc))
    assert report["formal_control_count"] == 1
