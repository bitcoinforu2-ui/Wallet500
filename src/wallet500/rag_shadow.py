from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .rag_intelligence import Wallet500RAG

DATA = Path("data")
OUTPUT = DATA / "rag-intelligence-shadow.json"
VERSION = "RAG_INTELLIGENCE_SHADOW_V1"


def _load(path: Path, default: Any) -> Any:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _shadow_label(composite: float) -> str:
    if composite >= 70.0:
        return "BUY_ZONE_COUNTERFACTUAL"
    if composite >= 58.0:
        return "WATCH_COUNTERFACTUAL"
    return "RESEARCH_COUNTERFACTUAL"


def run(output_dir: str = "data") -> dict:
    global DATA, OUTPUT
    DATA = Path(output_dir)
    OUTPUT = DATA / "rag-intelligence-shadow.json"
    DATA.mkdir(parents=True, exist_ok=True)

    decision_payload = _load(DATA / "decision-engine-v1.json", {})
    decisions = decision_payload.get("decisions") if isinstance(decision_payload, dict) else []
    if not isinstance(decisions, list):
        decisions = []

    source_generated_at = str(decision_payload.get("generated_at") or "") if isinstance(decision_payload, dict) else ""
    as_of = source_generated_at or datetime.now(timezone.utc).isoformat()
    rag = Wallet500RAG(DATA)
    rows: list[dict] = []

    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        scores = decision.get("scores") if isinstance(decision.get("scores"), dict) else {}
        base_composite = _num(scores.get("composite"))
        context = rag.retrieve(decision, scores, as_of=as_of)
        delta = _num(context.get("score_delta"))
        shadow_composite = max(0.0, min(100.0, base_composite + delta))
        base_action = str(decision.get("recommended_action") or "")
        rows.append(
            {
                "key": decision.get("key"),
                "chain": decision.get("chain"),
                "token": decision.get("token"),
                "symbol": decision.get("symbol"),
                "pair_address": decision.get("pair_address"),
                "production_action_unchanged": base_action,
                "base_composite": round(base_composite, 4),
                "rag_score_delta": round(delta, 4),
                "rag_shadow_composite": round(shadow_composite, 4),
                "rag_shadow_label": _shadow_label(shadow_composite),
                "rag": context,
            }
        )

    ready = [x for x in rows if (x.get("rag") or {}).get("status") == "READY"]
    enough = [
        x for x in ready
        if int((x.get("rag") or {}).get("sample_count") or 0) >= 5
        and float((x.get("rag") or {}).get("retrieval_confidence") or 0.0) >= 0.55
    ]
    changed_counterfactual = [
        x for x in rows
        if x.get("rag_shadow_label") not in {
            "BUY_ZONE_COUNTERFACTUAL" if x.get("production_action_unchanged") == "BUY" else "__NO_MATCH__"
        }
        and abs(float(x.get("rag_score_delta") or 0.0)) > 0.0
    ]

    payload = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_decision_generated_at": source_generated_at or None,
        "mode": "SHADOW_ONLY_NO_PRODUCTION_ACTION_CHANGE",
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {
            "strict_prior_only": True,
            "exact_chain_token_pair_identity": True,
            "same_candidate_history_excluded": True,
            "hard_gates_never_weakened": True,
            "production_action_never_changed": True,
            "fail_open_for_scanner": True,
            "score_delta_bound": 5.0,
        },
        "promotion_contract": {
            "status": "NOT_ELIGIBLE_YET",
            "requires_prospective_holdout_validation": True,
            "requires_measured_incremental_uplift": True,
            "requires_no_material_risk_regression": True,
            "requires_explicit_production_promotion": True,
        },
        "summary": {
            "decisions_evaluated": len(rows),
            "rag_ready": len(ready),
            "rag_minimum_evidence_ready": len(enough),
            "nonzero_shadow_deltas": sum(1 for x in rows if abs(float(x.get("rag_score_delta") or 0.0)) > 0.0),
            "counterfactual_rows_with_nonzero_delta": len(changed_counterfactual),
        },
        "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return payload


def main() -> None:
    run()


if __name__ == "__main__":
    main()
