"""CEX source operational freshness is observable, never inferred from old rows."""
import json
from datetime import datetime, timedelta, timezone

from wallet500 import operational_guard as guard

NOW = datetime(2026, 10, 3, 13, 0, tzinfo=timezone.utc)


def _setup(tmp_path, monkeypatch, generated_at, producer=None):
    monkeypatch.setattr(guard, "DATA", tmp_path)
    monkeypatch.setattr(guard, "REPORT", tmp_path / "system-watchdog.json")
    monkeypatch.setattr(guard, "STATE", tmp_path / "system-watchdog-state.json")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    (tmp_path / "system-watchdog.json").write_text(json.dumps({
        "incidents": [], "checks": {}, "truth_contract": []
    }))
    (tmp_path / "system-watchdog-state.json").write_text("{}")
    (tmp_path / "run-summary.json").write_text(json.dumps({"active_qualified": 0}))
    (tmp_path / "system-health.json").write_text("{}")
    (tmp_path / "revival-1000-latest.json").write_text(json.dumps({"generated_at": NOW.isoformat()}))
    (tmp_path / "cex-spot-identity-radar.json").write_text(json.dumps({"generated_at": generated_at}))
    monkeypatch.setattr(guard, "_count", lambda *_a, **_kw: 0)
    def runs(_token, workflow, _limit=5):
        if workflow == "revival-1000.yml":
            return []
        assert workflow == "cex-spot-revival-fast.yml"
        return [producer or {
            "status": "completed", "conclusion": "success",
            "updated_at": NOW.isoformat(), "id": 456,
        }]
    monkeypatch.setattr(guard, "_workflow_runs", runs)


def _codes(report):
    return {item["code"] for item in report["incidents"]}


def test_stale_cex_producer_is_high_severity_operational_incident(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, (NOW - timedelta(hours=2)).isoformat())
    report = guard.run(NOW)
    assert "CEX_SPOT_IDENTITY_STALE_OR_FAILED" in _codes(report)
    assert report["checks"]["cex_spot_identity_freshness"]["ok"] is False
    assert report["checks"]["cex_spot_identity_freshness"]["age_seconds"] == 7200.0
    assert report["overall"] == "DEGRADED"


def test_fresh_cex_producer_removes_managed_stale_incident(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, (NOW - timedelta(minutes=5)).isoformat())
    # Recovered incident from a previous failed workflow must not linger.
    (tmp_path / "system-watchdog.json").write_text(json.dumps({
        "incidents": [{"code": "CEX_SPOT_IDENTITY_STALE_OR_FAILED", "severity": "HIGH"}],
        "checks": {}, "truth_contract": []
    }))
    report = guard.run(NOW)
    assert "CEX_SPOT_IDENTITY_STALE_OR_FAILED" not in _codes(report)
    assert report["checks"]["cex_spot_identity_freshness"]["ok"] is True


def test_newer_failed_producer_cannot_be_hidden_by_fresh_older_snapshot(tmp_path, monkeypatch):
    _setup(
        tmp_path, monkeypatch,
        (NOW - timedelta(minutes=5)).isoformat(),
        producer={"status": "completed", "conclusion": "failure",
                  "updated_at": NOW.isoformat(), "id": 789},
    )
    report = guard.run(NOW)
    assert "CEX_SPOT_IDENTITY_STALE_OR_FAILED" in _codes(report)
    assert report["checks"]["cex_spot_identity_freshness"]["ok"] is False
    assert report["checks"]["cex_spot_identity_freshness"]["latest_producer_run_id"] == 789


def test_stale_decision_generation_is_reported_without_blocking_watchdog(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, (NOW - timedelta(minutes=2)).isoformat())
    (tmp_path / "decision-generation.json").write_text(json.dumps({
        "status": "COHERENT_READY",
        "created_at": (NOW - timedelta(hours=2)).isoformat(),
    }))
    report = guard.run(NOW)
    assert "DECISION_GENERATION_STALE_OR_INVALID" in _codes(report)
    assert report["checks"]["decision_generation_freshness"]["ok"] is False
    assert report["checks"]["cex_spot_identity_freshness"]["ok"] is True


def test_fresh_coherent_decision_generation_recovers_observability(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, (NOW - timedelta(minutes=2)).isoformat())
    (tmp_path / "decision-generation.json").write_text(json.dumps({
        "status": "COHERENT_READY",
        "created_at": (NOW - timedelta(minutes=3)).isoformat(),
    }))
    report = guard.run(NOW)
    assert "DECISION_GENERATION_STALE_OR_INVALID" not in _codes(report)
    assert report["checks"]["decision_generation_freshness"]["ok"] is True
