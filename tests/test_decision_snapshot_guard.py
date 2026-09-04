import json
from pathlib import Path

from wallet500.decision_snapshot_guard import build


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def seed(root: Path, ready=2, real_ready=2, funnel_ready=2, age_status="ENFORCED_FAIL_CLOSED"):
    write(root, "candidate-evidence-envelope.json", {
        "mode": "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1",
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {"minimum_market_age_days": 180, "exact_pair_required": True},
        "counts": {"evidence_ready": ready},
        "candidates": [],
    })
    write(root, "real-alerts.json", {
        "counts": {"evidence_ready_research": real_ready, "real_alerts": 0, "verified_watch_not_real": 4, "identity_pending_not_actionable": 3},
        "alerts": [],
    })
    write(root, "revival-funnel-diagnostics.json", {
        "lanes": {"evidence_promotion": {"evidence_ready": funnel_ready}},
    })
    write(root, "active-qualified-age-gate.json", {
        "status": age_status,
        "minimum_market_age_days": 180,
        "project_scope_minimum_market_age_days": 180,
    })
    write(root, "production-status.json", {
        "policy": {"minimum_verified_market_age_days": 180},
    })


def test_guard_passes_coherent_snapshot(tmp_path):
    seed(tmp_path)
    result = build(tmp_path)
    assert result["passed"] is True
    assert result["failure_count"] == 0
    assert result["counts"]["evidence_ready"] == 2


def test_guard_detects_derived_count_skew(tmp_path):
    seed(tmp_path, ready=2, real_ready=0, funnel_ready=2)
    result = build(tmp_path)
    assert result["passed"] is False
    assert "EVIDENCE_READY_COUNT_SKEW" in {x["code"] for x in result["failures"]}


def test_guard_detects_legacy_age_quarantine(tmp_path):
    seed(tmp_path, age_status="QUARANTINED_FAIL_CLOSED_UNAPPROVED_POLICY")
    result = build(tmp_path)
    assert result["passed"] is False
    assert "STALE_7D_AGE_GOVERNOR" in {x["code"] for x in result["failures"]}
