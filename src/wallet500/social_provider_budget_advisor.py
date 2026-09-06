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


def _confidence(runs: int) -> str:
    if runs >= 16:
        return "HIGH"
    if runs >= MIN_RUNS_FOR_POLICY_ADVICE:
        return "MEDIUM"
    return "LOW"


def _efficiency_score(row: dict) -> float | None:
    state = str(row.get("latest_state") or "UNKNOWN")
    calls_used = row.get("calls_used_total")
    if state in {"NOT_CONFIGURED", "INDEX_CONTEXT_ONLY"}:
        return None
    if row.get("latest_call_budget") is None or calls_used is None or _int(calls_used) <= 0:
        return None
    exact_ratio = min(1.0, max(0.0, _num(row.get("exact_evidence_run_ratio"))))
    reliability = 1.0 - min(1.0, max(0.0, _num(row.get("degraded_run_ratio"))))
    exact_per_call = min(1.0, max(0.0, _num(row.get("exact_events_per_call"))))
    tokens_per_call = min(1.0, max(0.0, _num(row.get("tokens_with_exact_evidence_per_call")) / 0.25))
    return round(45.0 * exact_ratio + 25.0 * reliability + 20.0 * exact_per_call + 10.0 * tokens_per_call, 2)


def _recommend(provider: str, row: dict) -> tuple[str, list[str]]:
    runs = _int(row.get("runs_observed"))
    state = str(row.get("latest_state") or "UNKNOWN")
    degraded = _num(row.get("degraded_run_ratio"))
    exact_ratio = _num(row.get("exact_evidence_run_ratio"))
    exact_per_call = row.get("exact_events_per_call")
    tokens_per_call = row.get("tokens_with_exact_evidence_per_call")
    latest_budget = row.get("latest_call_budget")
    exact_total = _int(row.get("exact_direct_events_total"))

    if state == "NOT_CONFIGURED":
        return "CONNECT_PROVIDER_FIRST", ["provider_not_configured", "budget_cannot_be_evaluated_without_direct_runs"]
    if latest_budget is None:
        return "OBSERVE_NON_BUDGETED_SOURCE", ["no_explicit_call_budget", "keep_as_observability_source"]
    if runs < MIN_RUNS_FOR_POLICY_ADVICE:
        return "COLLECT_MORE_HISTORY", [f"runs_observed={runs}", f"minimum_required={MIN_RUNS_FOR_POLICY_ADVICE}"]
    if degraded >= 0.5:
        return "FIX_RELIABILITY_BEFORE_SPEND", [f"degraded_run_ratio={round(degraded,4)}", "do_not_reward_unreliable_provider"]

    exact_per_call_n = _num(exact_per_call)
    tokens_per_call_n = _num(tokens_per_call)
    if exact_ratio >= 0.5 and exact_per_call_n >= 0.25 and tokens_per_call_n >= 0.05:
        return "CANDIDATE_INCREASE_AFTER_HUMAN_REVIEW", [
            f"exact_evidence_run_ratio={round(exact_ratio,4)}",
            f"exact_events_per_call={round(exact_per_call_n,4)}",
            f"tokens_with_exact_evidence_per_call={round(tokens_per_call_n,4)}",
        ]
    if runs >= MIN_RUNS_FOR_DECREASE_ADVICE and exact_ratio <= 0.1 and exact_total == 0:
        return "CANDIDATE_DECREASE_AFTER_HUMAN_REVIEW", [
            f"runs_observed={runs}",
            f"exact_evidence_run_ratio={round(exact_ratio,4)}",
            "zero_exact_direct_events_across_observed_window",
        ]
    return "HOLD_CURRENT_BUDGET", [
        f"exact_evidence_run_ratio={round(exact_ratio,4)}",
        f"degraded_run_ratio={round(degraded,4)}",
        "evidence_not_strong_enough_for_budget_change",
    ]


def build(history: dict) -> dict:
    rollup = history.get("provider_rollup") if isinstance(history.get("provider_rollup"), dict) else {}
    rows = []
    for provider, raw in sorted(rollup.items()):
        if not isinstance(raw, dict):
            continue
        recommendation, reasons = _recommend(str(provider), raw)
        runs = _int(raw.get("runs_observed"))
        rows.append({
            "provider": str(provider),
            "recommendation": recommendation,
            "confidence": _confidence(runs),
            "runs_observed": runs,
            "latest_state": raw.get("latest_state") or "UNKNOWN",
            "latest_call_budget": raw.get("latest_call_budget"),
            "calls_used_total": raw.get("calls_used_total"),
            "exact_evidence_run_ratio": raw.get("exact_evidence_run_ratio"),
            "degraded_run_ratio": raw.get("degraded_run_ratio"),
            "exact_events_per_call": raw.get("exact_events_per_call"),
            "tokens_with_exact_evidence_per_call": raw.get("tokens_with_exact_evidence_per_call"),
            "evidence_efficiency_score": _efficiency_score(raw),
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
        "COLLECT_MORE_HISTORY": 5,
        "OBSERVE_NON_BUDGETED_SOURCE": 6,
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
        "minimum_runs_for_policy_advice": MIN_RUNS_FOR_POLICY_ADVICE,
        "minimum_runs_for_decrease_advice": MIN_RUNS_FOR_DECREASE_ADVICE,
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
        },
        "counts": counts,
        "providers": rows,
    }


def run(data_dir: str | Path = DATA) -> dict:
    data = Path(data_dir)
    history = _load(data / HISTORY.name, {})
    payload = build(history)
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "history_runs": payload.get("history_runs_count"),
        "counts": payload.get("counts"),
        "top": [
            {"provider": x.get("provider"), "recommendation": x.get("recommendation"), "score": x.get("evidence_efficiency_score")}
            for x in (payload.get("providers") or [])[:5]
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
