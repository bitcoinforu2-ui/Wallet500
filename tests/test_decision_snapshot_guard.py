import json
from pathlib import Path

from wallet500.decision_snapshot_guard import build


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _ready_rows(count: int, surface: str = "verified_watch") -> dict:
    rows = []
    for i in range(count):
        rows.append({
            "chain": "testchain",
            "token_address": f"TOKEN{i}",
            "pair_address": f"PAIR{i}",
            "evidence_ready": True,
            "evidence_envelope_status": "EVIDENCE_READY",
            "status": "EVIDENCE_READY_NOT_REAL_ALERT" if surface == "verified_watch" else "DORMANT_NO_ACTIVITY_NOT_VERIFIED_WATCH",
        })
    return {surface: rows}


def seed(root: Path, ready=2, real_ready=2, funnel_ready=2, visible_ready=None, dormant_ready=0, age_status="ENFORCED_FAIL_CLOSED"):
    visible_ready = real_ready if visible_ready is None else visible_ready
    write(root, "candidate-evidence-envelope.json", {
        "mode": "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1",
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {"minimum_market_age_days": 180, "exact_pair_required": True},
        "counts": {"evidence_ready": ready},
        "candidates": [],
    })
    watch_n = max(0, visible_ready - dormant_ready)
    real_payload = {
        "counts": {
            "evidence_ready_research": real_ready,
            "real_alerts": 0,
            "verified_watch_not_real": watch_n,
            "dormant_no_activity": dormant_ready,
            "identity_pending_not_actionable": 3,
        },
        "alerts": [],
        "verified_watch": _ready_rows(watch_n)["verified_watch"],
        "dormant_no_activity": _ready_rows(dormant_ready, "dormant_no_activity")["dormant_no_activity"],
    }
    # Avoid duplicate synthetic keys when evidence is split across surfaces.
    for i, row in enumerate(real_payload["dormant_no_activity"], start=watch_n):
        row["token_address"] = f"TOKEN{i}"
        row["pair_address"] = f"PAIR{i}"
    write(root, "real-alerts.json", real_payload)
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
    assert result["counts"]["evidence_ready_visible"] == 2


def test_guard_accepts_dormant_evidence_ready_as_visible_research(tmp_path):
    seed(tmp_path, ready=2, real_ready=2, funnel_ready=2, visible_ready=2, dormant_ready=1)
    result = build(tmp_path)
    assert result["passed"] is True
    assert result["counts"]["dormant_no_activity"] == 1
    assert result["evidence_ready_coherence"]["visible_across_watch_evidence_dormant"] == 2


def test_guard_detects_derived_count_skew(tmp_path):
    seed(tmp_path, ready=2, real_ready=0, funnel_ready=2, visible_ready=2)
    result = build(tmp_path)
    assert result["passed"] is False
    assert "EVIDENCE_READY_COUNT_SKEW" in {x["code"] for x in result["failures"]}


def test_guard_detects_visibility_skew_even_when_counts_match(tmp_path):
    seed(tmp_path, ready=2, real_ready=2, funnel_ready=2, visible_ready=1)
    result = build(tmp_path)
    assert result["passed"] is False
    assert "EVIDENCE_READY_VISIBILITY_SKEW" in {x["code"] for x in result["failures"]}


def test_guard_detects_legacy_age_quarantine(tmp_path):
    seed(tmp_path, age_status="QUARANTINED_FAIL_CLOSED_UNAPPROVED_POLICY")
    result = build(tmp_path)
    assert result["passed"] is False
    assert "STALE_7D_AGE_GOVERNOR" in {x["code"] for x in result["failures"]}
