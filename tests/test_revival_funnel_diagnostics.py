from __future__ import annotations

import json
from pathlib import Path

from wallet500 import revival_funnel_diagnostics as rfd


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_diagnostics_separates_parallel_lanes_and_identifies_upstream_blocker(tmp_path: Path) -> None:
    _write(tmp_path / "revival-1000-latest.json", {
        "generated_at": "2026-09-04T10:00:00Z",
        "age_gate": {"status": "ENFORCED_FAIL_CLOSED", "minimum_market_age_days": 180},
        "counts": {"universe": 120, "age_verified_180d_plus": 120, "core_drawdown_watch": 30, "pre_alpha": 0},
        "coins": [
            {"pre_alpha_eligible": False, "pre_alpha_blocker": "PENDING"},
            {"pre_alpha_eligible": False, "pre_alpha_blocker": "PENDING"},
        ],
    })
    _write(tmp_path / "revival-precursor-latest.json", {
        "counts": {"targets": 12, "PRE_BREAKOUT_CANDIDATE": 2, "INSUFFICIENT_PRECURSOR_EVIDENCE": 8},
    })
    _write(tmp_path / "revival-prewaking-wallet-evidence.json", {
        "targets": 2,
        "tokens": [
            {"coverage": {"coverage_quality": "PARTIAL", "coverage_gap": True, "eligible_as_forensics_t0_wallet_evidence": False}},
            {"coverage": {"coverage_quality": "COMPLETE", "coverage_gap": False, "eligible_as_forensics_t0_wallet_evidence": True}},
        ],
    })
    _write(tmp_path / "reawakening-shadow.json", {
        "counts": {
            "eligible_liquidity_only_rejects": 388,
            "outcome_tracker_matches": 365,
            "forward_tracker_rows_after_v2_start": 0,
            "shadow_triggers_v2": 0,
        }
    })
    _write(tmp_path / "alpha-proof-report.json", {
        "primary_proof_status": "COLLECTING_FORWARD_SAMPLE",
        "formal_signal_count": 1,
        "formal_control_count": 0,
    })
    _write(tmp_path / "active-qualified-candidates.json", [])
    _write(tmp_path / "active-qualified-age-gate.json", {
        "raw_active_before_age_governance": 0,
        "accepted": 0,
        "status": "QUARANTINED_FAIL_CLOSED_UNAPPROVED_POLICY",
    })

    out = rfd.build(tmp_path)
    codes = {x["code"] for x in out["blockers"]}

    assert out["production_change"] is False
    assert "parallel research lanes" in out["cohort_warning"].lower()
    assert out["lanes"]["solana_veteran_revival"]["minimum_market_age_days"] == 180
    assert out["lanes"]["reawakening_recovery"]["eligible_liquidity_only_rejects"] == 388
    assert "REVIVAL_RESEARCH_EVIDENCE_PENDING_NOT_FAILED" in codes
    assert "REAWAKENING_FORWARD_TRACKER_EMPTY_AFTER_ACTIVATION" in codes
    assert "NO_ACTIVE_QUALIFIED_BEFORE_AGE_GOVERNANCE" in codes
