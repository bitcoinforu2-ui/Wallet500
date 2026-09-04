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
    active = _load(data_dir / "active-qualified-candidates.json", [])
    active_age = _load(data_dir / "active-qualified-age-gate.json", {})

    revival_counts = _dict(revival.get("counts"))
    precursor_counts = _dict(precursor.get("counts"))
    envelope_counts = _dict(envelope.get("counts"))
    reawakening_counts = _dict(reawakening.get("counts"))
    age_gate = _dict(revival.get("age_gate"))
    active_age_counts = _dict(active_age)

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

    revival_coins = revival.get("coins") if isinstance(revival, dict) else []
    revival_coins = revival_coins if isinstance(revival_coins, list) else []
    legacy_research_pending = sum(
        1
        for row in revival_coins
        if isinstance(row, dict)
        and row.get("pre_alpha_eligible") is not True
        and bool(row.get("pre_alpha_blocker"))
    )

    envelope_rows = envelope.get("candidates") if isinstance(envelope, dict) else []
    envelope_rows = envelope_rows if isinstance(envelope_rows, list) else []
    blocker_counts = Counter()
    for row in envelope_rows:
        if not isinstance(row, dict):
            continue
        for code in row.get("blockers") or []:
            blocker_counts[str(code)] += 1

    blockers: list[dict[str, Any]] = []
    for code, count in blocker_counts.most_common(8):
        blockers.append({
            "code": code,
            "count": count,
            "classification": "EVIDENCE_OR_TRUTH_BLOCKER",
            "detail": "Counted from the canonical Candidate Evidence Envelope; missing evidence is not treated as failure.",
        })

    insufficient = _num(precursor_counts.get("INSUFFICIENT_PRECURSOR_EVIDENCE"))
    if insufficient:
        blockers.append({
            "code": "PRECURSOR_EVIDENCE_INSUFFICIENT",
            "count": insufficient,
            "classification": "INSUFFICIENT_EVIDENCE",
        })

    if wallet_partial:
        blockers.append({
            "code": "PREWAKING_WALLET_COVERAGE_PARTIAL",
            "count": wallet_partial,
            "classification": "COVERAGE_GAP",
        })

    eligible_reawakening = _num(reawakening_counts.get("eligible_liquidity_only_rejects"))
    forward_rows = _num(reawakening_counts.get("forward_tracker_rows_after_v2_start"))
    if eligible_reawakening > 0 and forward_rows == 0:
        blockers.append({
            "code": "REAWAKENING_FORWARD_TRACKER_EMPTY_AFTER_ACTIVATION",
            "count": eligible_reawakening,
            "classification": "DATA_FLOW_BLOCKER",
        })

    raw_active = _num(active_age_counts.get("raw_active_before_age_governance"))
    if raw_active == 0:
        blockers.append({
            "code": "NO_ACTIVE_QUALIFIED_BEFORE_AGE_GOVERNANCE",
            "count": 0,
            "classification": "UPSTREAM_QUALIFICATION_EMPTY",
            "detail": "Legacy active-qualified is empty; Evidence Envelope is reported separately and does not silently become production authority.",
        })

    active_count = len(active) if isinstance(active, list) else 0
    return {
        "version": 2,
        "mode": "REVIVAL_FUNNEL_DIAGNOSTICS_V2_EVIDENCE_PROMOTION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_change": False,
        "production_portfolio_impact": "NONE",
        "cohort_warning": (
            "Revival, Precursor, Evidence Envelope, Reawakening and legacy Active Qualification are distinct lanes. "
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
                "legacy_pre_alpha_eligible": _num(revival_counts.get("pre_alpha")),
                "legacy_research_pending": legacy_research_pending,
            },
            "evidence_promotion": {
                "source_generated_at": envelope.get("generated_at") if isinstance(envelope, dict) else None,
                "universe_with_exact_pair": _num(envelope_counts.get("universe_with_exact_pair")),
                "evidence_ready": _num(envelope_counts.get("evidence_ready")),
                "verified_watch": _num(envelope_counts.get("verified_watch")),
                "deep_watch": _num(envelope_counts.get("deep_watch")),
                "blocked_truth": _num(envelope_counts.get("blocked_truth")),
                "verified_holder_lane": _num(envelope_counts.get("with_verified_holder_growth_lane")),
                "positive_holder_growth": _num(envelope_counts.get("with_positive_holder_growth")),
                "verified_wallet_lane": _num(envelope_counts.get("with_verified_wallet_lane")),
                "positive_wallet_accumulation": _num(envelope_counts.get("with_positive_wallet_accumulation")),
                "positive_smart_money": _num(envelope_counts.get("with_positive_smart_money")),
                "positive_cex": _num(envelope_counts.get("with_positive_cex")),
                "production_effect": False,
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
            "active_qualification": {
                "active_candidates": active_count,
                "raw_before_age_governance": raw_active,
                "accepted_after_age_governance": _num(active_age_counts.get("accepted")),
                "age_gate_status": active_age_counts.get("status"),
            },
        },
        "blockers": blockers,
        "truth_rules": [
            "MISSING_EVIDENCE_IS_NOT_FAILURE",
            "EVIDENCE_READY_IS_RESEARCH_PROMOTION_NOT_BUY_SIGNAL",
            "CONCENTRATION_IS_RISK_CONTEXT_ONLY",
            "STALE_EVIDENCE_NEVER_COUNTS_POSITIVE",
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
