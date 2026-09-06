from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "revival-funnel-diagnostics.json"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _num(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build(data_dir: Path = DATA) -> dict[str, Any]:
    revival = _load(data_dir / "revival-1000-latest.json", {})
    precursor = _load(data_dir / "revival-precursor-latest.json", {})
    wallets = _load(data_dir / "revival-prewaking-wallet-evidence.json", {})
    envelope = _load(data_dir / "candidate-evidence-envelope.json", {})
    reawakening = _load(data_dir / "reawakening-shadow.json", {})
    alpha = _load(data_dir / "alpha-proof-report.json", {})

    revival_counts = _dict(revival.get("counts"))
    precursor_counts = _dict(precursor.get("counts"))
    envelope_counts = _dict(envelope.get("counts"))
    reawakening_counts = _dict(reawakening.get("counts"))
    age_gate = _dict(revival.get("age_gate"))

    wallet_rows = wallets.get("tokens") if isinstance(wallets, dict) else []
    wallet_rows = wallet_rows if isinstance(wallet_rows, list) else []
    wallet_partial = 0
    wallet_complete = 0
    wallet_forensics_eligible = 0
    for row in wallet_rows:
        if not isinstance(row, dict):
            continue
        coverage = _dict(row.get("coverage"))
        if coverage.get("coverage_quality") == "PARTIAL" or coverage.get("coverage_gap") is True:
            wallet_partial += 1
        else:
            wallet_complete += 1
        if coverage.get("eligible_as_forensics_t0_wallet_evidence") is True:
            wallet_forensics_eligible += 1

    envelope_rows = envelope.get("candidates") if isinstance(envelope, dict) else []
    envelope_rows = envelope_rows if isinstance(envelope_rows, list) else []

    # V3 separates hard truth blockers from "not confirmed yet".
    blocker_counts = Counter()
    pending_counts = Counter()
    discovery_tier_counts = Counter()
    rescue_eligible = 0
    for row in envelope_rows:
        if not isinstance(row, dict):
            continue
        for code in row.get("blockers") or []:
            blocker_counts[str(code)] += 1
        for code in row.get("pending_confirmations") or []:
            pending_counts[str(code)] += 1
        tier = str(row.get("discovery_tier") or "")
        if tier:
            discovery_tier_counts[tier] += 1
        if (_dict(row.get("rescue_shadow"))).get("eligible") is True:
            rescue_eligible += 1

    blockers: list[dict[str, Any]] = []
    for code, count in blocker_counts.most_common(8):
        blockers.append({
            "code": code,
            "count": count,
            "classification": "HARD_TRUTH_OR_RISK_BLOCKER",
            "detail": "Counted from canonical Candidate Evidence Envelope hard blockers only.",
        })

    pending_confirmations: list[dict[str, Any]] = []
    for code, count in pending_counts.most_common(10):
        pending_confirmations.append({
            "code": code,
            "count": count,
            "classification": "PENDING_CONFIRMATION_NOT_HARD_FAILURE",
            "detail": "Kept in forward watch; missing/not-yet-positive evidence is not converted into a failure.",
        })

    insufficient = _num(precursor_counts.get("INSUFFICIENT_PRECURSOR_EVIDENCE"))
    if insufficient:
        pending_confirmations.append({
            "code": "PRECURSOR_EVIDENCE_INSUFFICIENT",
            "count": insufficient,
            "classification": "PENDING_CONFIRMATION_NOT_HARD_FAILURE",
        })

    if wallet_partial:
        pending_confirmations.append({
            "code": "PREWAKING_WALLET_COVERAGE_PARTIAL",
            "count": wallet_partial,
            "classification": "COVERAGE_GAP_NOT_HARD_FAILURE",
        })

    eligible_reawakening = _num(reawakening_counts.get("eligible_liquidity_only_rejects"))
    forward_rows = _num(reawakening_counts.get("forward_tracker_rows_after_v2_start"))
    if eligible_reawakening > 0 and forward_rows == 0:
        blockers.append({
            "code": "REAWAKENING_FORWARD_TRACKER_EMPTY_AFTER_ACTIVATION",
            "count": eligible_reawakening,
            "classification": "DATA_FLOW_BLOCKER",
        })

    return {
        "version": 3,
        "mode": "REVIVAL_FUNNEL_DIAGNOSTICS_V3_ADAPTIVE_DISCOVERY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_change": False,
        "production_portfolio_impact": "NONE",
        "cohort_warning": (
            "Revival, adaptive discovery, Precursor, Evidence Envelope and Reawakening are distinct lanes. "
            "Only exact token/pair identity links may be compared."
        ),
        "lanes": {
            "solana_veteran_revival": {
                "source_generated_at": revival.get("generated_at") if isinstance(revival, dict) else None,
                "minimum_market_age_days": _num(age_gate.get("minimum_market_age_days")) or 180,
                "age_gate_status": age_gate.get("status"),
                "universe": _num(revival_counts.get("universe")),
                "age_verified_180d_plus": _num(revival_counts.get("age_verified_180d_plus")),
                "core_drawdown_watch": _num(revival_counts.get("core_drawdown_watch")),
                "waking_market_only": _num(revival_counts.get("waking_market_only")),
                "absorption_proxy_watch": _num(revival_counts.get("absorption_proxy_watch")),
                "absorption_candidate_proxy_watch": _num(revival_counts.get("absorption_candidate_proxy_watch")),
            },
            "evidence_promotion": {
                "source_generated_at": envelope.get("generated_at") if isinstance(envelope, dict) else None,
                "universe_with_exact_pair": _num(envelope_counts.get("universe_with_exact_pair")),
                "evidence_ready": _num(envelope_counts.get("evidence_ready")),
                "verified_watch": _num(envelope_counts.get("verified_watch")),
                "deep_watch": _num(envelope_counts.get("deep_watch")),
                "blocked_truth": _num(envelope_counts.get("blocked_truth")),
                "pre_waking_evidence_ready": _num(envelope_counts.get("pre_waking_evidence_ready")),
                "anomaly_watch": _num(envelope_counts.get("anomaly_watch")),
                "waking_market_watch": _num(envelope_counts.get("waking_market_watch")),
                "baseline_deep_watch": _num(envelope_counts.get("baseline_deep_watch")),
                "market_confirmation_pending": _num(envelope_counts.get("market_confirmation_pending")),
                "independent_evidence_pending": _num(envelope_counts.get("independent_evidence_pending")),
                "adaptive_anomaly_positive": _num(envelope_counts.get("adaptive_anomaly_positive")),
                "adaptive_velocity_positive": _num(envelope_counts.get("adaptive_velocity_positive")),
                "adaptive_persistence_positive": _num(envelope_counts.get("adaptive_persistence_positive")),
                "rescue_shadow_eligible": _num(envelope_counts.get("rescue_shadow_eligible")) or rescue_eligible,
                "verified_holder_lane": _num(envelope_counts.get("with_verified_holder_growth_lane")),
                "positive_holder_growth": _num(envelope_counts.get("with_positive_holder_growth")),
                "verified_wallet_lane": _num(envelope_counts.get("with_verified_wallet_lane")),
                "positive_wallet_accumulation": _num(envelope_counts.get("with_positive_wallet_accumulation")),
                "positive_smart_money": _num(envelope_counts.get("with_positive_smart_money")),
                "positive_cex": _num(envelope_counts.get("with_positive_cex")),
                "production_effect": False,
            },
            "adaptive_discovery": {
                "pre_waking_evidence_ready": discovery_tier_counts.get("PRE_WAKING_EVIDENCE_READY", 0),
                "anomaly_watch": discovery_tier_counts.get("ANOMALY_WATCH", 0),
                "waking_evidence_ready": discovery_tier_counts.get("WAKING_EVIDENCE_READY", 0),
                "waking_market_watch": discovery_tier_counts.get("WAKING_MARKET_WATCH", 0),
                "baseline_deep_watch": discovery_tier_counts.get("BASELINE_DEEP_WATCH", 0),
                "rescue_shadow_eligible": rescue_eligible,
                "market_waking_is_early_gate": False,
                "real_alert_gate_changed": False,
            },
            "precursor": {
                "source_generated_at": precursor.get("generated_at") if isinstance(precursor, dict) else None,
                "targets": _num(precursor_counts.get("targets")),
                "high_conviction": _num(precursor_counts.get("HIGH_CONVICTION_PRECURSOR")),
                "pre_breakout": _num(precursor_counts.get("PRE_BREAKOUT_CANDIDATE")),
                "early_watch": _num(precursor_counts.get("EARLY_REVIVAL_WATCH")),
                "late_do_not_chase": _num(precursor_counts.get("LATE_MOVE_DO_NOT_CHASE")),
                "insufficient_evidence": insufficient,
            },
            "prewaking_wallet_evidence": {
                "source_generated_at": wallets.get("generated_at") if isinstance(wallets, dict) else None,
                "targets": _num(wallets.get("targets")) if isinstance(wallets, dict) else 0,
                "coverage_complete": wallet_complete,
                "coverage_partial": wallet_partial,
                "forensics_t0_eligible": wallet_forensics_eligible,
            },
            "reawakening_recovery": {
                "source_generated_at": reawakening.get("generated_at") if isinstance(reawakening, dict) else None,
                "rejected_ledger_records": _num(reawakening_counts.get("rejected_ledger_records")),
                "eligible_liquidity_only_rejects": eligible_reawakening,
                "outcome_tracker_matches": _num(reawakening_counts.get("outcome_tracker_matches")),
                "forward_tracker_rows_after_activation": forward_rows,
                "shadow_triggers_v2": _num(reawakening_counts.get("shadow_triggers_v2")),
                "legacy_v1_triggers_preserved": _num(reawakening_counts.get("legacy_v1_triggers_preserved")),
            },
            "formal_alpha_proof": {
                "source_updated_at": alpha.get("updated_at") if isinstance(alpha, dict) else None,
                "status": alpha.get("primary_proof_status") if isinstance(alpha, dict) else None,
                "formal_signals": _num(alpha.get("formal_signal_count")) if isinstance(alpha, dict) else 0,
                "formal_controls": _num(alpha.get("formal_control_count")) if isinstance(alpha, dict) else 0,
            },
        },
        "blockers": blockers,
        "pending_confirmations": pending_confirmations,
        "truth_rules": [
            "MISSING_EVIDENCE_IS_NOT_FAILURE",
            "EVIDENCE_READY_IS_RESEARCH_PROMOTION_NOT_BUY_SIGNAL",
            "CONCENTRATION_IS_RISK_CONTEXT_ONLY",
            "STALE_EVIDENCE_NEVER_COUNTS_POSITIVE",
            "MARKET_WAKING_IS_LATE_CONFIRMATION_NOT_EARLY_DISCOVERY_GATE",
            "HARD_TRUTH_BLOCKERS_ARE_SEPARATE_FROM_PENDING_CONFIRMATIONS",
            "ADAPTIVE_DISCOVERY_IS_WATCH_ONLY_AND_NEVER_AUTO_BUY",
            "REAL_ALERT_STRICT_GATE_IS_UNCHANGED",
            "RESCUE_SHADOW_RECHECKS_EARLY_FALSE_NEGATIVES_FORWARD_ONLY",
            "PARALLEL_LANES_ARE_NOT_FAKE_CONVERSION_STAGES",
            "VETERAN_180D_IS_PROJECT_SCOPE_NOT_ALPHA_THRESHOLD",
        ],
    }


def run(data_dir: Path = DATA) -> dict[str, Any]:
    payload = build(data_dir)
    out = data_dir / OUTPUT.name
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
