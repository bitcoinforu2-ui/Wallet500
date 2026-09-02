from __future__ import annotations

import json

from wallet500.production_status import build


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_ready_no_signal_is_distinct_from_validation_failure(tmp_path):
    _write(tmp_path / "run-summary.json", {"updated_at": "2026-09-02T12:00:00+00:00"})
    _write(tmp_path / "cex-revival-radar.json", {
        "healthy_sources": 7,
        "requested_sources": ["a", "b"],
        "contracts_seen": 5000,
        "symbols_seen": 1900,
        "alerts_count": 50,
        "identity_counts": {"dex_verified": 4, "pair_pending": 2, "identity_pending": 44},
        "platform_catalog": {"status": "OK", "requested_coin_ids": 50, "resolved_coin_ids": 48, "error": None},
    })
    _write(tmp_path / "real-alerts.json", {
        "counts": {"real_alerts": 0, "verified_watch_not_real": 4, "identity_pending_not_actionable": 44},
        "alerts": [],
    })
    _write(tmp_path / "active-qualified-candidates.json", [])
    _write(tmp_path / "strict-validation.json", {"passed": True, "failure_count": 0})
    _write(tmp_path / "system-health.json", {"overall": "DEGRADED", "failure_summary": {"system_production_blockers": 0, "codes": ["PREVIOUS_PUBLISH_EVIDENCE_STALE_OR_MISSING"]}})
    _write(tmp_path / "holder-cluster-production-report.json", {"promoted_count": 0})
    out = build(str(tmp_path))
    assert out["operator_status"] == "READY_NO_ACTIONABLE_SIGNAL"
    assert out["observability_status"] == "DEGRADED_NON_BLOCKING"
    assert out["policy"]["minimum_verified_market_age_days"] == 180
    assert out["policy"]["new_token_production_attention_pct"] == 0
    assert out["cex_revival"]["dex_verified"] == 4
    assert out["real_alert_feed"]["identity_pending_not_actionable"] == 44


def test_real_alert_presence_changes_operator_status_but_not_execution_mode(tmp_path):
    _write(tmp_path / "real-alerts.json", {"counts": {"real_alerts": 1}, "alerts": [{"symbol": "ABC"}]})
    _write(tmp_path / "strict-validation.json", {"passed": True, "failure_count": 0})
    _write(tmp_path / "system-health.json", {"overall": "HEALTHY", "failure_summary": {"system_production_blockers": 0}})
    _write(tmp_path / "active-qualified-candidates.json", [])
    out = build(str(tmp_path))
    assert out["operator_status"] == "ACTIONABLE_RESEARCH_ALERTS_PRESENT"
    assert out["policy"]["real_money_execution"] is False
    assert out["production_funnel"]["paper_only"] is True


def test_validation_failure_blocks_status_fail_closed(tmp_path):
    _write(tmp_path / "strict-validation.json", {"passed": False, "failure_count": 1})
    _write(tmp_path / "system-health.json", {"overall": "FAILED", "failure_summary": {"system_production_blockers": 1}})
    _write(tmp_path / "real-alerts.json", {"counts": {"real_alerts": 3}})
    _write(tmp_path / "active-qualified-candidates.json", [])
    out = build(str(tmp_path))
    assert out["operator_status"] == "VALIDATION_BLOCKED"
