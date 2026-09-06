from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
SCAN = DATA / "social-source-scan.json"
OUTPUT = DATA / "social-source-health-history.json"
MODE = "SOCIAL_SOURCE_HEALTH_HISTORY_OBSERVABILITY_ONLY_V1"
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
        rows[str(provider)] = {
            "state": state,
            "configured": raw.get("configured") is True,
            "exact_direct_events": _int(raw.get("exact_direct_events")),
            "official_context_events": _int(raw.get("official_context_events")),
            "indexed_exact_context_events": _int(raw.get("indexed_exact_context_events")),
            "tokens_with_exact_evidence": _int(raw.get("tokens_with_exact_evidence")),
        }
    return {
        "generated_at": scan.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "scan_version": scan.get("version"),
        "targets_scanned": _int(scan.get("targets_scanned")),
        "providers": rows,
    }


def _fingerprint(snapshot: dict) -> str:
    # generated_at is the canonical run identity. Re-running the publisher against
    # the same scan must never duplicate a historical observation.
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
            exact_events += direct
            official_events += official
            indexed_events += indexed
            tokens_exact_total += _int(row.get("tokens_with_exact_evidence"))
            if direct > 0:
                exact_runs += 1
            if official > 0:
                official_runs += 1
            if indexed > 0:
                index_runs += 1
            if state == "DEGRADED_UNKNOWN":
                degraded_runs += 1
            latest_state = state
            latest_at = run.get("generated_at")

        denom = max(1, observations)
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
        "version": 1,
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
