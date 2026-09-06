from __future__ import annotations

import json
from pathlib import Path

from wallet500 import revival_funnel_diagnostics as rfd


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_diagnostics_separates_hard_blockers_from_pending_confirmations(tmp_path: Path) -> None:
    _write(tmp_path / "revival-1000-latest.json", {
        "generated_at": "2026-09-04T10:00:00Z",
        "age_gate": {"status": "ENFORCED_FAIL_CLOSED", "minimum_market_age_days": 180},
        "counts": {"universe": 120, "age_verified_180d_plus": 120, "core_drawdown_watch": 30, "waking_market_only": 4, "pre_alpha": 0},
        "coins": [
            {"pre_alpha_eligible": False, "pre_alpha_blocker": "PENDING"},
            {"pre_alpha_eligible": False, "pre_alpha_blocker": "PENDING"},
        ],
    })
    _write(tmp_path / "candidate-evidence-envelope.json", {
        "generated_at": "2026-09-04T10:05:00Z",
        "counts": {
            "universe_with_exact_pair": 100,
            "evidence_ready": 2,
            "verified_watch": 15,
            "deep_watch": 70,
            "blocked_truth": 13,
            "pre_waking_evidence_ready": 4,
            "anomaly_watch": 6,
            "waking_market_watch": 5,
            "baseline_deep_watch": 70,
            "market_confirmation_pending": 80,
            "independent_evidence_pending": 60,
            "adaptive_anomaly_positive": 10,
            "adaptive_velocity_positive": 8,
            "adaptive_persistence_positive": 30,
            "rescue_shadow_eligible": 12,
            "with_verified_holder_growth_lane": 10,
            "with_positive_holder_growth": 3,
            "with_verified_wallet_lane": 8,
            "with_positive_wallet_accumulation": 2,
            "with_positive_smart_money": 0,
            "with_positive_cex": 1,
        },
        "candidates": [
            {
                "status": "VERIFIED_WATCH",
                "discovery_tier": "ANOMALY_WATCH",
                "blockers": [],
                "pending_confirmations": ["MARKET_CONFIRMATION_PENDING", "INDEPENDENT_EVIDENCE_PENDING"],
                "rescue_shadow": {"eligible": False},
            },
            {
                "status": "BLOCKED_TRUTH",
                "discovery_tier": "HARD_TRUTH_BLOCKED",
                "blockers": ["EXECUTION_LIQUIDITY_LT_50K"],
                "pending_confirmations": [],
                "rescue_shadow": {"eligible": True},
            },
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
        "status": "ENFORCED_FAIL_CLOSED",
    })

    out = rfd.build(tmp_path)
    hard_codes = {x["code"] for x in out["blockers"]}
    pending_codes = {x["code"] for x in out["pending_confirmations"]}

    assert out["version"] == 3
    assert out["production_change"] is False
    assert out["lanes"]["solana_veteran_revival"]["minimum_market_age_days"] == 180
    assert out["lanes"]["evidence_promotion"]["evidence_ready"] == 2
    assert out["lanes"]["evidence_promotion"]["pre_waking_evidence_ready"] == 4
    assert out["lanes"]["evidence_promotion"]["anomaly_watch"] == 6
    assert out["lanes"]["evidence_promotion"]["positive_holder_growth"] == 3
    assert out["lanes"]["adaptive_discovery"]["market_waking_is_early_gate"] is False
    assert out["lanes"]["reawakening_recovery"]["eligible_liquidity_only_rejects"] == 388
    assert "MARKET_CONFIRMATION_PENDING" not in hard_codes
    assert "INDEPENDENT_EVIDENCE_PENDING" not in hard_codes
    assert "MARKET_CONFIRMATION_PENDING" in pending_codes
    assert "INDEPENDENT_EVIDENCE_PENDING" in pending_codes
    assert "EXECUTION_LIQUIDITY_LT_50K" in hard_codes
    assert "REAWAKENING_FORWARD_TRACKER_EMPTY_AFTER_ACTIVATION" in hard_codes
    assert "NO_ACTIVE_QUALIFIED_BEFORE_AGE_GOVERNANCE" not in hard_codes
    assert "active_qualification" not in out["lanes"]
    assert "MARKET_WAKING_IS_LATE_CONFIRMATION_NOT_EARLY_DISCOVERY_GATE" in out["truth_rules"]
