from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .mature_age_gate import MIN_MARKET_AGE_DAYS, enforce_active_candidates, validate_active_file

DATA = Path("data")
# Last evidence-approved production baseline. The 180d mature-pool study remains
# RESEARCH_ONLY / NOT_A_STRATEGY_BACKTEST, so it must not silently become a
# production threshold. Keep this aligned only after explicit evidence approval.
APPROVED_PRODUCTION_MIN_AGE_DAYS = 7


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

    # Never adopt a research-only threshold into Production by implication.
    # On mismatch quarantine this lane, rather than loosening/strengthening the
    # production rule without quantitative approval or aborting unrelated lanes.
    if MIN_MARKET_AGE_DAYS != APPROVED_PRODUCTION_MIN_AGE_DAYS:
        rejected = []
        for row in raw[:500]:
            if not isinstance(row, dict):
                continue
            rejected.append({
                "chain": row.get("chain"),
                "token": row.get("token") or row.get("mint") or row.get("token_address"),
                "pair_address": row.get("pair_address"),
                "reason": "UNAPPROVED_RESEARCH_AGE_POLICY_QUARANTINED",
            })
        active_path.write_text("[]", encoding="utf-8")
        report = {
            "version": 2,
            "generated_at": _now(),
            "status": "QUARANTINED_FAIL_CLOSED_UNAPPROVED_POLICY",
            "research_minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "approved_production_minimum_market_age_days": APPROVED_PRODUCTION_MIN_AGE_DAYS,
            "production_change_allowed": False,
            "raw_active_before_age_governance": len(raw),
            "accepted": 0,
            "quarantined": len(raw),
            "identity_rule": "EXACT_CHAIN_TOKEN_AND_LOCKED_PAIR_REQUIRED; SYMBOL_NOT_USED",
            "governance_rule": "RESEARCH_ONLY_THRESHOLD_MUST_NOT_BECOME_PRODUCTION_POLICY_WITHOUT_NUMERICAL_APPROVAL",
            "rejections": rejected,
        }
        audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    report = enforce_active_candidates(active_path, audit_path)
    validate_active_file(active_path)
    return report


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
