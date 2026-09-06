from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
SCAN = DATA / "social-source-scan.json"
OUTPUT = DATA / "social-source-health-history.json"
MODE = "SOCIAL_SOURCE_HEALTH_HISTORY_OBSERVABILITY_ONLY_V2"
MAX_RUNS = 192

VALID_STATES = {
    "ACTIVE_EXACT_EVIDENCE",
    "ACTIVE_OFFICIAL_CONTEXT",
    "INDEX_CONTEXT_ONLY",
    "DEGRADED_UNKNOWN",
    "NOT_CONFIGURED",
    "ACTIVE_NO_EXACT_EVIDENCE",
    "UNKNOWN",
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


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0, int(value))
    except Exception:
        return None


def _provider_call_metrics(scan: dict, provider: str) -> tuple[int | None, int | None]:
    direct_budget = scan.get("direct_provider_budget") if isinstance(scan.get("direct_provider_budget"), dict) else {}
    direct_calls = scan.get("direct_provider_calls_used") if isinstance(scan.get("direct_provider_calls_used"), dict) else {}
    mesh_budget = scan.get("mesh_provider_budget") if isinstance(scan.get("mesh_provider_budget"), dict) else {}
    mesh_calls = scan.get("mesh_provider_calls_used") if isinstance(scan.get("mesh_provider_calls_used"), dict) else {}

    direct_key = {"x": "x", "youtube": "youtube", "reddit": "reddit"}.get(provider)
    mesh_key = {
        "telegram_mtproto": "telegram_mtproto",
        "farcaster": "farcaster",
        "discord": "discord",
        "threads": "threads",
        "bluesky": "bluesky",
    }.get(provider)

    if direct_key:
        return _optional_int(direct_budget.get(direct_key)), _optional_int(direct_calls.get(direct_key))
    if mesh_key:
        return _optional_int(mesh_budget.get(mesh_key)), _optional_int(mesh_calls.get(mesh_key))
    if provider == "social_mesh_public_index":
        meta = scan.get("mesh_public_index") if isinstance(scan.get("mesh_public_index"), dict) else {}
        return _optional_int(meta.get("budget")), _optional_int(meta.get("calls_used"))
    return None, None


def _snapshot(scan: dict) -> dict:
    health = scan.get("source_health") if isinstance(scan.get("source_health"), dict) else {}
    providers = health.get("providers") if isinstance(health.get("providers"), dict) else {}
    rows = {}
    for provider, raw in sorted(providers.items()):
        if not isinstance(raw, dict):
            continue
        state = str(raw.get("state") or "UNKNOWN")
        if state not in VALID_STATES:
            state = "UNKNOWN"
        budget, calls_used = _provider_call_metrics(scan, str(provider))
        rows[str(provider)] = {
            "state": state,
            "configured": raw.get("configured") is True,
            "exact_direct_events": _int(raw.get("exact_direct_events")),
            "official_context_events": _int(raw.get("official_context_events")),
            "indexed_exact_context_events": _int(raw.get("indexed_exact_context_events")),
            "tokens_with_exact_evidence": _int(raw.get("tokens_with_exact_evidence")),
            "call_budget": budget,
            "calls_used": calls_used,
        }
    return {
        "generated_at": scan.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "scan_version": scan.get("version"),
        "targets_scanned": _int(scan.get("targets_scanned")),
        "providers": rows,
    }


def _fingerprint(snapshot: dict) -> str:
    return str(snapshot.get("generated_at") or "")


def _aggregate(runs: list[dict]) -> dict:
    providers: dict[str, dict] = {}
    names = sorted({
        str(name)
        for run in runs if isinstance(run, dict)
        for name in ((run.get("providers") or {}).keys() if isinstance(run.get("providers"), dict) else [])
    })
    for provider in names:
        state_counts = Counter()
        configured_runs = 0
        exact_runs = 0
        official_runs = 0
        index_runs = 0
        degraded_runs = 0
        exact_events = 0
        official_events = 0
        indexed_events = 0
        tokens_exact_total = 0
        observations = 0
        metric_runs = 0
        calls_total = 0
        budget_total = 0
        metric_exact_events = 0
        metric_tokens_exact = 0
        latest_budget = None
        latest_calls_used = None
        latest_state = "UNKNOWN"
        latest_at = None

        for run in runs:
            row = (run.get("providers") or {}).get(provider) if isinstance(run, dict) else None
            if not isinstance(row, dict):
                continue
            observations += 1
            state = str(row.get("state") or "UNKNOWN")
            state_counts[state] += 1
            if row.get("configured") is True:
                configured_runs += 1
            direct = _int(row.get("exact_direct_events"))
            official = _int(row.get("official_context_events"))
            indexed = _int(row.get("indexed_exact_context_events"))
            tokens_exact = _int(row.get("tokens_with_exact_evidence"))
            exact_events += direct
            official_events += official
            indexed_events += indexed
            tokens_exact_total += tokens_exact
            if direct > 0:
                exact_runs += 1
            if official > 0:
                official_runs += 1
            if indexed > 0:
                index_runs += 1
            if state == "DEGRADED_UNKNOWN":
                degraded_runs += 1

            budget = _optional_int(row.get("call_budget"))
            calls = _optional_int(row.get("calls_used"))
            if budget is not None and calls is not None:
                metric_runs += 1
                budget_total += budget
                calls_total += calls
                metric_exact_events += direct
                metric_tokens_exact += tokens_exact
            latest_budget = budget
            latest_calls_used = calls
            latest_state = state
            latest_at = run.get("generated_at")

        denom = max(1, observations)
        exact_per_call = round(metric_exact_events / calls_total, 4) if calls_total > 0 else None
        tokens_per_call = round(metric_tokens_exact / calls_total, 4) if calls_total > 0 else None
        utilization = round(calls_total / budget_total, 4) if budget_total > 0 else None
        providers[provider] = {
            "runs_observed": observations,
            "latest_state": latest_state,
            "latest_at": latest_at,
            "state_counts": dict(state_counts),
            "configured_run_ratio": round(configured_runs / denom, 4),
            "exact_evidence_run_ratio": round(exact_runs / denom, 4),
            "official_context_run_ratio": round(official_runs / denom, 4),
            "indexed_context_run_ratio": round(index_runs / denom, 4),
            "degraded_run_ratio": round(degraded_runs / denom, 4),
            "exact_direct_events_total": exact_events,
            "official_context_events_total": official_events,
            "indexed_exact_context_events_total": indexed_events,
            "tokens_with_exact_evidence_total": tokens_exact_total,
            "call_metric_runs": metric_runs,
            "calls_used_total": calls_total if metric_runs else None,
            "call_budget_total": budget_total if metric_runs else None,
            "call_metric_exact_events_total": metric_exact_events if metric_runs else None,
            "call_metric_tokens_with_exact_evidence_total": metric_tokens_exact if metric_runs else None,
            "latest_call_budget": latest_budget,
            "latest_calls_used": latest_calls_used,
            "call_utilization_ratio": utilization,
            "exact_events_per_call": exact_per_call,
            "tokens_with_exact_evidence_per_call": tokens_per_call,
            "budget_recommendation_effect": "NONE_OBSERVE_ONLY",
        }
    return providers


def build(scan: dict, previous: dict | None = None) -> dict:
    previous = previous if isinstance(previous, dict) else {}
    old_runs = previous.get("runs") if isinstance(previous.get("runs"), list) else []
    runs = [x for x in old_runs if isinstance(x, dict)]
    current = _snapshot(scan)
    fp = _fingerprint(current)
    known = {_fingerprint(x) for x in runs}
    appended = bool(fp and fp not in known)
    if appended:
        runs.append(current)
    runs = runs[-MAX_RUNS:]

    return {
        "version": 2,
        "mode": MODE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "observability_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "history_limit_runs": MAX_RUNS,
        "runs_count": len(runs),
        "new_run_appended": appended,
        "latest_scan_generated_at": current.get("generated_at"),
        "truth_contract": {
            "provider_health_never_modifies_token_scores": True,
            "provider_health_never_modifies_alert_gate": True,
            "provider_health_never_auto_changes_api_budgets": True,
            "single_run_never_changes_provider_policy": True,
            "secret_values_never_stored": True,
            "unknown_is_not_zero": True,
            "configuration_is_not_evidence": True,
            "call_efficiency_is_observability_only": True,
            "call_efficiency_uses_only_same_run_measured_events": True,
        },
        "provider_rollup": _aggregate(runs),
        "runs": runs,
    }


def run(data_dir: str | Path = DATA) -> dict:
    data = Path(data_dir)
    scan = _load(data / SCAN.name, {})
    previous = _load(data / OUTPUT.name, {})
    payload = build(scan, previous)
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    compact = {
        name: {
            "latest": row.get("latest_state"),
            "exact_ratio": row.get("exact_evidence_run_ratio"),
            "degraded_ratio": row.get("degraded_run_ratio"),
            "exact_per_call": row.get("exact_events_per_call"),
        }
        for name, row in (payload.get("provider_rollup") or {}).items()
    }
    print(json.dumps({
        "runs": payload.get("runs_count"),
        "appended": payload.get("new_run_appended"),
        "providers": compact,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
