import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wallet500 import system_watchdog as watchdog
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


def test_single_cancelled_live_scan_is_transient_when_success_is_fresh(tmp_path):
    now = datetime(2026, 9, 11, 6, 15, tzinfo=timezone.utc)
    seed(tmp_path, now)
    gh = {
        "latest_status": "completed",
        "latest_conclusion": "cancelled",
        "latest_run_id": 200,
        "last_success_at": (now - timedelta(minutes=15)).isoformat(),
        "last_success_run_id": 199,
        "cancellations_since_success": 1,
        "latest_cancelled_run_id": 200,
        "latest_hard_failure_conclusion": None,
        "latest_hard_failure_run_id": None,
        "active_run_count": 0,
    }
    report, _ = build_report(tmp_path, now=now, state={}, gh=gh)
    assert "LIVE_SCAN_EXECUTION_FAILED" not in codes(report)
    assert "LIVE_SCAN_REPEATED_CANCELLATIONS" not in codes(report)
    assert "LIVE_SCAN_LAST_SUCCESS_STALE" not in codes(report)
    assert report["overall"] == "HEALTHY"


def test_repeated_live_scan_cancellations_degrade_before_success_goes_stale(tmp_path):
    now = datetime(2026, 9, 11, 6, 15, tzinfo=timezone.utc)
    seed(tmp_path, now)
    gh = {
        "latest_status": "completed",
        "latest_conclusion": "cancelled",
        "latest_run_id": 201,
        "last_success_at": (now - timedelta(minutes=20)).isoformat(),
        "last_success_run_id": 199,
        "cancellations_since_success": 2,
        "latest_cancelled_run_id": 201,
        "latest_hard_failure_conclusion": None,
        "latest_hard_failure_run_id": None,
        "active_run_count": 0,
    }
    report, _ = build_report(tmp_path, now=now, state={}, gh=gh)
    assert "LIVE_SCAN_REPEATED_CANCELLATIONS" in codes(report)
    assert report["overall"] == "DEGRADED"


def test_real_live_scan_execution_failure_is_reported_with_fresh_prior_success(tmp_path):
    now = datetime(2026, 9, 11, 6, 15, tzinfo=timezone.utc)
    seed(tmp_path, now)
    gh = {
        "latest_status": "completed",
        "latest_conclusion": "failure",
        "latest_run_id": 202,
        "last_success_at": (now - timedelta(minutes=10)).isoformat(),
        "last_success_run_id": 199,
        "cancellations_since_success": 0,
        "latest_cancelled_run_id": None,
        "latest_hard_failure_conclusion": "failure",
        "latest_hard_failure_run_id": 202,
        "active_run_count": 0,
    }
    report, _ = build_report(tmp_path, now=now, state={}, gh=gh)
    assert "LIVE_SCAN_EXECUTION_FAILED" in codes(report)
    assert report["overall"] == "DEGRADED"


def test_stale_last_success_is_critical_even_if_latest_run_was_only_cancelled(tmp_path):
    now = datetime(2026, 9, 11, 6, 15, tzinfo=timezone.utc)
    seed(tmp_path, now)
    gh = {
        "latest_status": "completed",
        "latest_conclusion": "cancelled",
        "latest_run_id": 203,
        "last_success_at": (now - timedelta(minutes=46)).isoformat(),
        "last_success_run_id": 190,
        "cancellations_since_success": 1,
        "latest_cancelled_run_id": 203,
        "latest_hard_failure_conclusion": None,
        "latest_hard_failure_run_id": None,
        "active_run_count": 0,
    }
    report, _ = build_report(tmp_path, now=now, state={}, gh=gh)
    assert "LIVE_SCAN_LAST_SUCCESS_STALE" in codes(report)
    assert "LIVE_SCAN_REPEATED_CANCELLATIONS" not in codes(report)
    assert report["overall"] == "CRITICAL"


def test_github_live_status_uses_operational_runs_and_ignores_push_ci(monkeypatch):
    payload = {
        "workflow_runs": [
            {"id": 305, "event": "push", "status": "completed", "conclusion": "cancelled", "created_at": "2026-09-11T06:15:00Z", "updated_at": "2026-09-11T06:15:10Z"},
            {"id": 304, "event": "push", "status": "completed", "conclusion": "failure", "created_at": "2026-09-11T06:14:00Z", "updated_at": "2026-09-11T06:14:30Z"},
            {"id": 303, "event": "workflow_dispatch", "status": "in_progress", "conclusion": None, "created_at": "2026-09-11T06:13:00Z", "updated_at": "2026-09-11T06:13:30Z"},
            {"id": 302, "event": "workflow_dispatch", "status": "completed", "conclusion": "cancelled", "created_at": "2026-09-11T06:00:00Z", "updated_at": "2026-09-11T06:08:00Z"},
            {"id": 301, "event": "schedule", "status": "completed", "conclusion": "success", "created_at": "2026-09-11T05:45:00Z", "updated_at": "2026-09-11T05:55:00Z"},
            {"id": 300, "event": "schedule", "status": "completed", "conclusion": "failure", "created_at": "2026-09-11T05:30:00Z", "updated_at": "2026-09-11T05:40:00Z"},
        ]
    }
    monkeypatch.setattr(watchdog, "_http_json", lambda *args, **kwargs: payload)
    status = watchdog.github_live_status()
    assert status["latest_run_id"] == 303
    assert status["latest_event"] == "workflow_dispatch"
    assert status["last_success_run_id"] == 301
    assert status["cancellations_since_success"] == 1
    assert status["latest_hard_failure_conclusion"] is None
    assert status["active_run_count"] == 1
    assert status["ignored_non_operational_run_count"] == 2
