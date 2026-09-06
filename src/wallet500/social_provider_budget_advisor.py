from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
HISTORY = DATA / "social-source-health-history.json"
OUTPUT = DATA / "social-provider-budget-advisor.json"
MODE = "SOCIAL_PROVIDER_BUDGET_ADVISOR_OBSERVABILITY_ONLY_V1"
MIN_RUNS_FOR_POLICY_ADVICE = 6
MIN_RUNS_FOR_DECREASE_ADVICE = 12

REQUIRED_TRUTH = {
    "recommendations_never_modify_api_budgets",
    "recommendations_never_modify_token_scores",
    "recommendations_never_modify_alert_gate",
    "single_run_never_produces_budget_change_advice",
    "unknown_is_not_zero",
    "not_configured_is_not_bad_evidence",
    "indexed_context_never_counts_as_direct_efficiency",
    "no_direct_calls_means_no_efficiency_score",
    "budget_advice_uses_only_positive_call_exposure_runs",
    "zero_direct_yield_means_zero_efficiency_score",
    "public_index_never_gets_direct_budget_advice",
}

CHANGE_RECOMMENDATIONS = {
    "CANDIDATE_INCREASE_AFTER_HUMAN_REVIEW",
    "CANDIDATE_DECREASE_AFTER_HUMAN_REVIEW",
}


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _confidence(measured_runs: int) -> str:
    if measured_runs >= 16:
        return "HIGH"
    if measured_runs >= MIN_RUNS_FOR_POLICY_ADVICE:
        return "MEDIUM"
    return "LOW"


def _efficiency_score(provider: str, row: dict) -> float | None:
    state = str(row.get("latest_state") or "UNKNOWN")
    calls_used = row.get("calls_used_total")
    measured_runs = _int(row.get("call_exposure_runs"))
    if provider == "social_mesh_public_index" or state in {"NOT_CONFIGURED", "INDEX_CONTEXT_ONLY"}:
        return None
    if row.get("latest_call_budget") is None or calls_used is None or _int(calls_used) <= 0 or measured_runs <= 0:
        return None
    exact_ratio = min(1.0, max(0.0, _num(row.get("call_exposure_exact_evidence_run_ratio"))))
    reliability = 1.0 - min(1.0, max(0.0, _num(row.get("call_exposure_degraded_run_ratio"))))
    exact_per_call = min(1.0, max(0.0, _num(row.get("exact_events_per_call"))))
    tokens_per_call = min(1.0, max(0.0, _num(row.get("direct_tokens_with_exact_evidence_per_call", row.get("tokens_with_exact_evidence_per_call"))) / 0.25))
    yield_score = 55.0 * exact_ratio + 30.0 * exact_per_call + 15.0 * tokens_per_call
    return round(yield_score * reliability, 2)


def _recommend(provider: str, row: dict) -> tuple[str, list[str]]:
    measured_runs = _int(row.get("call_exposure_runs"))
    state = str(row.get("latest_state") or "UNKNOWN")
    degraded = _num(row.get("call_exposure_degraded_run_ratio"))
    exact_ratio = _num(row.get("call_exposure_exact_evidence_run_ratio"))
    exact_per_call = row.get("exact_events_per_call")
    tokens_per_call = row.get("direct_tokens_with_exact_evidence_per_call", row.get("tokens_with_exact_evidence_per_call"))
    latest_budget = row.get("latest_call_budget")
    exact_total = _int(row.get("call_metric_exact_events_total"))

    if state == "NOT_CONFIGURED":
        return "CONNECT_PROVIDER_FIRST", ["provider_not_configured", "budget_cannot_be_evaluated_without_direct_calls"]
    if provider == "social_mesh_public_index":
        return "OBSERVE_CONTEXT_ONLY_SOURCE", ["context_only_source", "never_grade_as_direct_evidence_efficiency"]
    if latest_budget is None:
        return "OBSERVE_NON_BUDGETED_SOURCE", ["no_explicit_call_budget", "keep_as_observability_source"]
    if measured_runs < MIN_RUNS_FOR_POLICY_ADVICE:
        return "COLLECT_MORE_MEASURED_HISTORY", [f"call_exposure_runs={measured_runs}", f"minimum_required={MIN_RUNS_FOR_POLICY_ADVICE}"]
    if degraded >= 0.5:
        return "FIX_RELIABILITY_BEFORE_SPEND", [f"measured_degraded_run_ratio={round(degraded,4)}", "do_not_reward_unreliable_provider"]

    exact_per_call_n = _num(exact_per_call)
    tokens_per_call_n = _num(tokens_per_call)
    if exact_ratio >= 0.5 and exact_per_call_n >= 0.25 and tokens_per_call_n >= 0.05:
        return "CANDIDATE_INCREASE_AFTER_HUMAN_REVIEW", [
            f"measured_exact_evidence_run_ratio={round(exact_ratio,4)}",
            f"exact_events_per_call={round(exact_per_call_n,4)}",
            f"direct_tokens_with_exact_evidence_per_call={round(tokens_per_call_n,4)}",
        ]
    if measured_runs >= MIN_RUNS_FOR_DECREASE_ADVICE and exact_ratio <= 0.1 and exact_total == 0:
        return "CANDIDATE_DECREASE_AFTER_HUMAN_REVIEW", [
            f"call_exposure_runs={measured_runs}",
            f"measured_exact_evidence_run_ratio={round(exact_ratio,4)}",
            "zero_exact_direct_events_across_measured_window",
        ]
    return "HOLD_CURRENT_BUDGET", [
        f"measured_exact_evidence_run_ratio={round(exact_ratio,4)}",
        f"measured_degraded_run_ratio={round(degraded,4)}",
        "measured_evidence_not_strong_enough_for_budget_change",
    ]


def build(history: dict) -> dict:
    rollup = history.get("provider_rollup") if isinstance(history.get("provider_rollup"), dict) else {}
    rows = []
    for provider, raw in sorted(rollup.items()):
        if not isinstance(raw, dict):
            continue
        recommendation, reasons = _recommend(str(provider), raw)
        history_runs = _int(raw.get("runs_observed"))
        measured_runs = _int(raw.get("call_exposure_runs"))
        direct_tokens_per_call = raw.get("direct_tokens_with_exact_evidence_per_call", raw.get("tokens_with_exact_evidence_per_call"))
        rows.append({
            "provider": str(provider),
            "recommendation": recommendation,
            "confidence": _confidence(measured_runs),
            "runs_observed": history_runs,
            "measured_runs_for_policy": measured_runs,
            "latest_state": raw.get("latest_state") or "UNKNOWN",
            "latest_call_budget": raw.get("latest_call_budget"),
            "calls_used_total": raw.get("calls_used_total"),
            "historical_exact_evidence_run_ratio": raw.get("exact_evidence_run_ratio"),
            "measured_exact_evidence_run_ratio": raw.get("call_exposure_exact_evidence_run_ratio"),
            "measured_degraded_run_ratio": raw.get("call_exposure_degraded_run_ratio"),
            "exact_events_per_call": raw.get("exact_events_per_call"),
            "tokens_with_exact_evidence_per_call": direct_tokens_per_call,
            "direct_tokens_with_exact_evidence_per_call": direct_tokens_per_call,
            "evidence_efficiency_score": _efficiency_score(str(provider), raw),
            "reasons": reasons,
            "suggested_budget_delta": None,
            "automatic_change": False,
            "score_effect": "NONE_PROVIDER_POLICY_ADVICE_ONLY",
            "alert_gate_effect": "NONE",
        })

    priority = {
        "FIX_RELIABILITY_BEFORE_SPEND": 0,
        "CONNECT_PROVIDER_FIRST": 1,
        "CANDIDATE_INCREASE_AFTER_HUMAN_REVIEW": 2,
        "CANDIDATE_DECREASE_AFTER_HUMAN_REVIEW": 3,
        "HOLD_CURRENT_BUDGET": 4,
        "COLLECT_MORE_MEASURED_HISTORY": 5,
        "OBSERVE_CONTEXT_ONLY_SOURCE": 6,
        "OBSERVE_NON_BUDGETED_SOURCE": 7,
    }
    rows.sort(key=lambda r: (priority.get(str(r.get("recommendation")), 99), -(r.get("evidence_efficiency_score") or 0), r.get("provider") or ""))

    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("recommendation") or "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1

    return {
        "version": 1,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "history_mode": history.get("mode"),
        "history_runs_count": _int(history.get("runs_count")),
        "minimum_measured_runs_for_policy_advice": MIN_RUNS_FOR_POLICY_ADVICE,
        "minimum_measured_runs_for_decrease_advice": MIN_RUNS_FOR_DECREASE_ADVICE,
        "observability_only": True,
        "production_effect": False,
        "automatic_budget_changes": False,
        "automatic_buy": False,
        "truth_contract": {
            "recommendations_never_modify_api_budgets": True,
            "recommendations_never_modify_token_scores": True,
            "recommendations_never_modify_alert_gate": True,
            "single_run_never_produces_budget_change_advice": True,
            "unknown_is_not_zero": True,
            "not_configured_is_not_bad_evidence": True,
            "indexed_context_never_counts_as_direct_efficiency": True,
            "no_direct_calls_means_no_efficiency_score": True,
            "budget_advice_uses_only_positive_call_exposure_runs": True,
            "zero_direct_yield_means_zero_efficiency_score": True,
            "public_index_never_gets_direct_budget_advice": True,
        },
        "counts": counts,
        "providers": rows,
    }


def validate(payload: dict) -> None:
    if payload.get("mode") != MODE:
        raise ValueError("SOCIAL_BUDGET_ADVISOR_MODE_INVALID")
    if payload.get("observability_only") is not True or payload.get("production_effect") is not False or payload.get("automatic_budget_changes") is not False or payload.get("automatic_buy") is not False:
        raise ValueError("SOCIAL_BUDGET_ADVISOR_PRODUCTION_LEAK")
    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    for key in REQUIRED_TRUTH:
        if truth.get(key) is not True:
            raise ValueError(f"SOCIAL_BUDGET_ADVISOR_TRUTH_MISSING:{key}")

    minimum = _int(payload.get("minimum_measured_runs_for_policy_advice")) or MIN_RUNS_FOR_POLICY_ADVICE
    decrease_minimum = _int(payload.get("minimum_measured_runs_for_decrease_advice")) or MIN_RUNS_FOR_DECREASE_ADVICE
    for row in payload.get("providers") or []:
        if not isinstance(row, dict):
            raise ValueError("SOCIAL_BUDGET_ADVISOR_ROW_INVALID")
        provider = str(row.get("provider") or "UNKNOWN")
        recommendation = str(row.get("recommendation") or "")
        measured = _int(row.get("measured_runs_for_policy"))
        calls = row.get("calls_used_total")
        score = row.get("evidence_efficiency_score")

        if row.get("automatic_change") is not False or row.get("suggested_budget_delta") is not None:
            raise ValueError(f"SOCIAL_BUDGET_ADVISOR_AUTO_CHANGE_LEAK:{provider}")
        if row.get("score_effect") != "NONE_PROVIDER_POLICY_ADVICE_ONLY" or row.get("alert_gate_effect") != "NONE":
            raise ValueError(f"SOCIAL_BUDGET_ADVISOR_PRODUCTION_EFFECT_LEAK:{provider}")
        if measured < minimum and recommendation in CHANGE_RECOMMENDATIONS:
            raise ValueError(f"SOCIAL_BUDGET_ADVISOR_EARLY_POLICY_ADVICE:{provider}")
        if recommendation == "CANDIDATE_DECREASE_AFTER_HUMAN_REVIEW" and measured < decrease_minimum:
            raise ValueError(f"SOCIAL_BUDGET_ADVISOR_EARLY_DECREASE_ADVICE:{provider}")

        if provider == "social_mesh_public_index":
            if recommendation != "OBSERVE_CONTEXT_ONLY_SOURCE" or score is not None:
                raise ValueError("SOCIAL_BUDGET_ADVISOR_PUBLIC_INDEX_POLICY_LEAK")
        if row.get("latest_state") == "NOT_CONFIGURED":
            if recommendation != "CONNECT_PROVIDER_FIRST" or score is not None:
                raise ValueError(f"SOCIAL_BUDGET_ADVISOR_NOT_CONFIGURED_GRADED:{provider}")
        if measured == 0 or calls is None or _int(calls) == 0:
            if score is not None:
                raise ValueError(f"SOCIAL_BUDGET_ADVISOR_SCORE_WITHOUT_CALL_EXPOSURE:{provider}")

        direct_tokens_rate = row.get("direct_tokens_with_exact_evidence_per_call")
        if row.get("tokens_with_exact_evidence_per_call") != direct_tokens_rate:
            raise ValueError(f"SOCIAL_BUDGET_ADVISOR_DIRECT_TOKEN_ALIAS_SKEW:{provider}")
        exact_ratio = _num(row.get("measured_exact_evidence_run_ratio"))
        exact_per_call = _num(row.get("exact_events_per_call"))
        direct_rate = _num(direct_tokens_rate)
        if measured > 0 and provider != "social_mesh_public_index" and row.get("latest_state") not in {"NOT_CONFIGURED", "INDEX_CONTEXT_ONLY"}:
            if exact_ratio == 0.0 and exact_per_call == 0.0 and direct_rate == 0.0 and score not in (0, 0.0):
                raise ValueError(f"SOCIAL_BUDGET_ADVISOR_ZERO_YIELD_SCORE_INFLATION:{provider}")


def run(data_dir: str | Path = DATA) -> dict:
    data = Path(data_dir)
    history = _load(data / HISTORY.name, {})
    payload = build(history)
    validate(payload)
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "history_runs": payload.get("history_runs_count"),
        "counts": payload.get("counts"),
        "top": [
            {"provider": x.get("provider"), "recommendation": x.get("recommendation"), "measured_runs": x.get("measured_runs_for_policy"), "score": x.get("evidence_efficiency_score")}
            for x in (payload.get("providers") or [])[:5]
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
