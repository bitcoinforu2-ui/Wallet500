from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .mature_age_gate import MIN_MARKET_AGE_DAYS, enforce_active_candidates, validate_active_file

DATA = Path("data")

# Veteran-only is a project scope invariant, not a learned alpha threshold.
# Signal thresholds still require prospective evidence; the universe boundary does not.
PROJECT_SCOPE_MIN_AGE_DAYS = 180
APPROVED_PRODUCTION_MIN_AGE_DAYS = PROJECT_SCOPE_MIN_AGE_DAYS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(
    active_path: Path = DATA / "active-qualified-candidates.json",
    audit_path: Path = DATA / "active-qualified-age-gate.json",
) -> dict:
    if not active_path.exists():
        raise SystemExit("ACTIVE_QUALIFIED_CANDIDATES_MISSING")
    raw = json.loads(active_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("ACTIVE_QUALIFIED_CANDIDATES_NOT_LIST")

    # Any drift between the canonical mature gate and the explicit veteran-only
    # product scope is a configuration error and remains fail-closed.
    if MIN_MARKET_AGE_DAYS != PROJECT_SCOPE_MIN_AGE_DAYS or MIN_MARKET_AGE_DAYS != APPROVED_PRODUCTION_MIN_AGE_DAYS:
        rejected = []
        for row in raw[:500]:
            if not isinstance(row, dict):
                continue
            rejected.append({
                "chain": row.get("chain"),
                "token": row.get("token") or row.get("mint") or row.get("token_address"),
                "pair_address": row.get("pair_address"),
                "reason": "VETERAN_SCOPE_POLICY_DRIFT_QUARANTINED",
            })
        active_path.write_text("[]", encoding="utf-8")
        report = {
            "version": 3,
            "generated_at": _now(),
            "status": "QUARANTINED_FAIL_CLOSED_SCOPE_POLICY_DRIFT",
            "project_scope_minimum_market_age_days": PROJECT_SCOPE_MIN_AGE_DAYS,
            "gate_minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "approved_production_minimum_market_age_days": APPROVED_PRODUCTION_MIN_AGE_DAYS,
            "production_change_allowed": False,
            "raw_active_before_age_governance": len(raw),
            "accepted": 0,
            "quarantined": len(raw),
            "identity_rule": "EXACT_CHAIN_TOKEN_AND_LOCKED_PAIR_REQUIRED; SYMBOL_NOT_USED",
            "governance_rule": "VETERAN_ONLY_SCOPE_MUST_BE_180D_EVERYWHERE; SIGNAL_THRESHOLDS_REMAIN_SEPARATELY_GOVERNED",
            "rejections": rejected,
        }
        audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    report = enforce_active_candidates(active_path, audit_path)
    report["project_scope_minimum_market_age_days"] = PROJECT_SCOPE_MIN_AGE_DAYS
    report["scope_policy"] = "VETERAN_ONLY_PRODUCT_SCOPE_NOT_ALPHA_THRESHOLD"
    audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    validate_active_file(active_path)
    return report


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
