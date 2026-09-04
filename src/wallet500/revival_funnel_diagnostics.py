from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "revival-funnel-diagnostics.json"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
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
    reawakening = _load(data_dir / "reawakening-shadow.json", {})
    alpha = _load(data_dir / "alpha-proof-report.json", {})
    active = _load(data_dir / "active-qualified-candidates.json", [])
    active_age = _load(data_dir / "active-qualified-age-gate.json", {})

    revival_counts = _dict(revival.get("counts"))
    precursor_counts = _dict(precursor.get("counts"))
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
    research_pending = sum(
        1
        for row in revival_coins
        if isinstance(row, dict)
        and row.get("pre_alpha_eligible") is not True
        and bool(row.get("pre_alpha_blocker"))
    )

    blockers: list[dict[str, Any]] = []
    if research_pending:
        blockers.append({
            "code": "REVIVAL_RESEARCH_EVIDENCE_PENDING_NOT_FAILED",
            "count": research_pending,
            "classification": "MISSING_EVIDENCE",
            "detail": "Research rows remain non-actionable while holder/cluster/smart-money/fundamental evidence is unverified.",
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
            "detail": "Eligible historical rejects exist, but no post-activation forward tracker observations are available to create V2 triggers.",
        })

    raw_active = _num(active_age_counts.get("raw_active_before_age_governance"))
    if raw_active == 0:
        blockers.append({
            "code": "NO_ACTIVE_QUALIFIED_BEFORE_AGE_GOVERNANCE",
            "count": 0,
            "classification": "UPSTREAM_QUALIFICATION_EMPTY",
            "detail": "The active-qualified lane is empty before its age gate, so age governance is not the current blocker.",
        })

    active_count = len(active) if isinstance(active, list) else 0
    return {
        "version": 1,
        "mode": "REVIVAL_FUNNEL_DIAGNOSTICS_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_change": False,
        "production_portfolio_impact": "NONE",
        "cohort_warning": (
            "Solana Revival/Precursor and Reawakening recovery are parallel research lanes. "
            "Counts must not be interpreted as one continuous conversion funnel unless exact identities are linked."
        ),
        "lanes": {
            "solana_veteran_revival": {
                "source_generated_at": revival.get("generated_at") if isinstance(revival, dict) else None,
                "minimum_market_age_days": _num(age_gate.get("minimum_market_age_days")),
                "age_gate_status": age_gate.get("status"),
                "universe": _num(revival_counts.get("universe")),
                "age_verified_180d_plus": _num(revival_counts.get("age_verified_180d_plus")),
                "core_drawdown_watch": _num(revival_counts.get("core_drawdown_watch")),
                "waking_market_only": _num(revival_counts.get("waking_market_only")),
                "absorption_proxy_watch": _num(revival_counts.get("absorption_proxy_watch")),
                "absorption_candidate_proxy_watch": _num(revival_counts.get("absorption_candidate_proxy_watch")),
                "research_pre_alpha_eligible": _num(revival_counts.get("pre_alpha")),
                "research_evidence_pending": research_pending,
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
            "PARALLEL_LANES_ARE_NOT_FAKE_CONVERSION_STAGES",
            "AGE_GATE_IS_NOT_BLAMED_WHEN_RAW_ACTIVE_IS_ZERO",
            "NO_PRODUCTION_THRESHOLD_IS_CHANGED_BY_THIS_REPORT",
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
