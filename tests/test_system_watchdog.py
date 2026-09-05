import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500.system_watchdog import build_report


def write(root: Path, name: str, value):
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def seed(root: Path, now: datetime):
    ts = now.isoformat()
    write(root, "real-alerts.json", {"generated_at": ts, "counts": {"real_alerts": 1}, "alerts": [{"symbol": "OLD", "chain": "solana", "token_address": "mint-old", "pair_address": "pair-old", "status": "REAL_ALERT"}]})
    write(root, "system-health.json", {"updated_at": ts, "failure_summary": {"system_production_blockers": 0}, "failures": []})
    write(root, "scheduler-health.json", {"updated_at": ts})
    write(root, "telegram-alert-report.json", {"updated_at": ts, "configured": True, "error_count": 0, "delivered": []})
    write(root, "telegram-alert-state.json", {"updated_at": ts, "sent": {}})
    write(root, "real-alert-10usd-summary.json", {"updated_at": ts, "positions": []})


def codes(report):
    return {x["code"] for x in report["incidents"]}


def test_first_run_baselines_existing_real_alerts_without_fake_gap(tmp_path):
    now = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)
    seed(tmp_path, now)
    report, state = build_report(tmp_path, now=now, state={})
    assert "NEW_REAL_ALERT_TELEGRAM_GAP" not in codes(report)
    assert state["baseline_initialized"] is True
    assert state["active_real_keys"] == ["solana:mint-old:pair-old"]


def test_new_real_alert_transition_without_telegram_is_critical(tmp_path):
    now = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)
    seed(tmp_path, now)
    _, baseline = build_report(tmp_path, now=now, state={})
    real = json.loads((tmp_path / "real-alerts.json").read_text())
    real["alerts"].append({"symbol": "NEW", "chain": "solana", "token_address": "mint-new", "pair_address": "pair-new", "status": "REAL_ALERT"})
    write(tmp_path, "real-alerts.json", real)
    report, _ = build_report(tmp_path, now=now, state=baseline)
    assert "NEW_REAL_ALERT_TELEGRAM_GAP" in codes(report)
    assert report["overall"] == "CRITICAL"


def test_delivered_alert_missing_from_10usd_tracker_is_critical(tmp_path):
    now = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)
    seed(tmp_path, now)
    write(tmp_path, "telegram-alert-report.json", {
        "updated_at": now.isoformat(),
        "configured": True,
        "error_count": 0,
        "delivered": [{"key": "solana:mint-new:pair-new", "sent_at": now.isoformat()}],
    })
    report, _ = build_report(tmp_path, now=now, state={})
    assert "TELEGRAM_DELIVERY_PAPER_TRACKER_GAP" in codes(report)


def test_stale_system_health_is_detected_even_when_other_feeds_are_fresh(tmp_path):
    now = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)
    seed(tmp_path, now)
    write(tmp_path, "system-health.json", {
        "updated_at": "2026-09-05T14:00:00+00:00",
        "failure_summary": {"system_production_blockers": 0},
        "failures": [],
    })
    report, _ = build_report(tmp_path, now=now, state={})
    assert "SYSTEM_HEALTH_STALE" in codes(report)
    assert report["overall"] == "DEGRADED"


def test_healthy_fresh_snapshot_has_no_incidents(tmp_path):
    now = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)
    seed(tmp_path, now)
    report, _ = build_report(tmp_path, now=now, state={})
    assert report["overall"] == "HEALTHY"
    assert report["incident_count"] == 0
    assert report["new_notifications"] == []
