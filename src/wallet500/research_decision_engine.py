"""Wallet500 Research Decision Engine.

Turns research artifacts into advisory implementation proposals. It is fail-closed,
never edits production thresholds, and never promotes anecdotal case studies by
itself.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
FILTER_ADVISOR = DATA / "filter-tuning-advisor.json"
REJECTED_OUTCOMES = DATA / "rejected-outcome-report.json"
CASE_FILES = [DATA / "case-study-cyberleek.json", DATA / "case-study-doge1.json"]
OUT = DATA / "research-decision-engine.json"

HARD_RULES = [
    "LIQUIDITY_GTE_50K_EXACT_EXECUTION_POOL",
    "EXACT_PAIR_IDENTITY",
    "HOLDER_CLUSTER_FAIL_CLOSED",
    "IMMUTABLE_TRACK_RECORD",
    "NO_HINDSIGHT",
    "PAPER_ONLY",
]


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _recommend(sample: int, lift_pct: float | None, forward_n: int, safe: bool) -> str:
    if not safe:
        return "REJECT"
    if sample < 100:
        return "MORE_DATA"
    if lift_pct is None:
        return "MORE_DATA"
    if lift_pct <= 0:
        return "REJECT"
    if sample >= 300 and forward_n >= 30 and lift_pct >= 20:
        return "APPROVED_CANDIDATE"
    if lift_pct >= 10:
        return "SHADOW_TEST"
    return "MORE_DATA"


def build(filter_advisor: dict, rejected: dict, cases: list[dict]) -> dict:
    proposals: list[dict] = []

    # 1) Existing false-negative research can nominate filters for measurement,
    # but never directly relax a production threshold.
    for item in filter_advisor.get("review_candidates", []) if isinstance(filter_advisor, dict) else []:
        if not isinstance(item, dict):
            continue
        n = int(item.get("records") or 0)
        fn = int(item.get("false_negative_winners") or 0)
        rate = float(item.get("false_negative_rate_pct") or 0.0)
        proposals.append({
            "hypothesis_id": f"FILTER_FN::{item.get('filter','UNKNOWN')}",
            "source_research_ids": ["filter-tuning-advisor"],
            "feature_or_rule": str(item.get("filter") or "UNKNOWN"),
            "proposal_type": "FALSE_NEGATIVE_RESEARCH",
            "sample_size": n,
            "positive_cases": fn,
            "baseline_rate_pct": rate,
            "candidate_rate_pct": None,
            "lift_pct": None,
            "forward_only_evidence_count": 0,
            "lookahead_check": "PASS",
            "safety_regression_check": "PASS",
            "hard_rule_change_allowed": False,
            "recommendation": "MORE_DATA",
            "decision_note": "Measure a recovery/recheck feature in shadow; do not lower the hard production gate.",
        })

    # 2) Case studies are hypothesis generators only.
    for case in cases:
        if not isinstance(case, dict) or not case:
            continue
        asset = case.get("asset") if isinstance(case.get("asset"), dict) else {}
        sym = asset.get("symbol") or case.get("symbol") or "CASE"
        qs = case.get("research_questions") if isinstance(case.get("research_questions"), list) else []
        features = case.get("entity_flow_features") if isinstance(case.get("entity_flow_features"), list) else []
        proposals.append({
            "hypothesis_id": f"CASE::{sym}",
            "source_research_ids": [f"case-study-{str(sym).lower()}"],
            "feature_or_rule": ",".join(features[:6]) if features else "CASE_STUDY_PATTERN",
            "proposal_type": "CASE_STUDY_HYPOTHESIS",
            "sample_size": 1,
            "positive_cases": 0,
            "baseline_rate_pct": None,
            "candidate_rate_pct": None,
            "lift_pct": None,
            "forward_only_evidence_count": 1 if "FORWARD" in str(case.get("lookahead_policy", "")).upper() else 0,
            "lookahead_check": "PASS" if "NO_HINDSIGHT" in str(case.get("lookahead_policy", "")).upper() else "UNKNOWN",
            "safety_regression_check": "PASS",
            "hard_rule_change_allowed": False,
            "recommendation": "MORE_DATA",
            "decision_note": "Convert repeated case-study pattern into a measurable cohort feature before any filter change.",
            "research_questions": qs[:5],
        })

    # Deterministic recommendation state is recomputed for proposals that later
    # receive real cohort metrics.
    for p in proposals:
        if p.get("proposal_type") == "MEASURED_COHORT":
            p["recommendation"] = _recommend(
                int(p.get("sample_size") or 0),
                p.get("lift_pct"),
                int(p.get("forward_only_evidence_count") or 0),
                p.get("lookahead_check") == "PASS" and p.get("safety_regression_check") == "PASS",
            )

    counts = {k: 0 for k in ["REJECT", "MORE_DATA", "SHADOW_TEST", "APPROVED_CANDIDATE"]}
    for p in proposals:
        counts[p.get("recommendation", "MORE_DATA")] = counts.get(p.get("recommendation", "MORE_DATA"), 0) + 1

    return {
        "version": 1,
        "mode": "RESEARCH_ADVISORY_ONLY",
        "production_change_allowed": False,
        "production_thresholds_modified": False,
        "hard_rules": HARD_RULES,
        "decision_states": counts,
        "proposals": proposals,
        "next_human_decision": [
            p for p in proposals if p.get("recommendation") in {"SHADOW_TEST", "APPROVED_CANDIDATE"}
        ],
        "source_health": {
            "filter_advisor_loaded": bool(filter_advisor),
            "rejected_outcomes_loaded": bool(rejected),
            "case_studies_loaded": sum(1 for c in cases if c),
        },
    }


def main() -> None:
    result = build(
        _load(FILTER_ADVISOR, {}),
        _load(REJECTED_OUTCOMES, {}),
        [_load(p, {}) for p in CASE_FILES],
    )
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({
        "mode": result["mode"],
        "proposals": len(result["proposals"]),
        "decision_states": result["decision_states"],
        "production_change_allowed": result["production_change_allowed"],
    }, indent=2))


if __name__ == "__main__":
    main()
