"""Create one auditable generation manifest for canonical decision outputs.

Research/advisory surfaces such as cross-signal fusion may refresh independently,
but they never authorize production and are intentionally excluded from the
canonical decision generation boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .safe_json import load_json_state
from .truth_contract import policy_snapshot, POLICY_ID

CANONICAL_FILES = (
    "data/revival-1000-latest.json",
    "data/cex-revival-radar.json",
    "data/active-qualified-candidates.json",
    "data/active-qualified-age-gate.json",
    "data/candidate-evidence-envelope.json",
    "data/real-alerts.json",
    "data/revival-funnel-diagnostics.json",
    "data/system-health.json",
    "data/strict-validation.json",
    "data/production-status.json",
    "data/decision-snapshot-integrity.json",
)
ADVISORY_FILES = (
    "data/cross-signal-fusion-v2.json",
    "data/research-decision-engine.json",
    "data/liquidity-recovery-shadow.json",
)
OUT = Path("data/decision-generation.json")
MAX_SOURCE_AGE_SECONDS = 2 * 3600
MAX_SOURCE_FUTURE_SKEW_SECONDS = 5 * 60


def _source_freshness(stamp: object, now: datetime) -> tuple[str, float | None]:
    try:
        observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return "SOURCE_TIMESTAMP_INVALID", None
        age = (now - observed.astimezone(timezone.utc)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return "SOURCE_TIMESTAMP_INVALID", None
    if age < -MAX_SOURCE_FUTURE_SKEW_SECONDS:
        return "SOURCE_TIMESTAMP_IN_FUTURE", age
    if age > MAX_SOURCE_AGE_SECONDS:
        return "SOURCE_STALE", age
    return "CURRENT", age


def build(*, source_sha: str | None = None, run_id: str | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("DECISION_GENERATION_NOW_MUST_BE_TIMEZONE_AWARE")
    now = now.astimezone(timezone.utc)
    source_sha = str(source_sha or os.getenv("SOURCE_SHA") or os.getenv("GITHUB_SHA") or "LOCAL").strip()
    run_id = str(run_id or os.getenv("GITHUB_RUN_ID") or "LOCAL").strip()
    states = {}
    hashes = {}
    generated = {}
    freshness = {}
    unhealthy = []
    for name in CANONICAL_FILES:
        r = load_json_state(name)
        states[name] = r.state
        if not r.valid:
            unhealthy.append({"path": name, "state": r.state, "error": r.error})
            continue
        raw = Path(name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        if isinstance(r.value, dict):
            generated[name] = r.value.get("generated_at") or r.value.get("updated_at") or r.value.get("created_at")
            status, age = _source_freshness(generated[name], now)
            freshness[name] = {"status": status, "age_seconds": age}
            if status != "CURRENT":
                unhealthy.append({"path": name, "state": status, "age_seconds": age})
        elif name != "data/active-qualified-candidates.json" or not isinstance(r.value, list):
            unhealthy.append({"path": name, "state": "SOURCE_SHAPE_INVALID"})

    advisory_states = {}
    for name in ADVISORY_FILES:
        r = load_json_state(name)
        advisory_states[name] = r.state

    generation_id = f"wallet500:{run_id}:{source_sha}"
    payload = {
        "version": 3,
        "generation_id": generation_id,
        "source_sha": source_sha,
        "workflow_run_id": run_id,
        "created_at": now.isoformat(),
        "policy_id": POLICY_ID,
        "policy": policy_snapshot(),
        "status": "COHERENT_READY" if not unhealthy else "INCOMPLETE_FAIL_CLOSED",
        "canonical_files": list(CANONICAL_FILES),
        "advisory_files": list(ADVISORY_FILES),
        "source_states": states,
        "advisory_states": advisory_states,
        "source_timestamps": generated,
        "source_freshness": freshness,
        "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
        "max_source_future_skew_seconds": MAX_SOURCE_FUTURE_SKEW_SECONDS,
        "hashes": hashes,
        "unhealthy_sources": unhealthy,
        "dashboard_rule": "DASHBOARD_MUST_NOT_MIX_CANONICAL_DECISION_FILES_FROM_DIFFERENT_GENERATIONS",
        "advisory_rule": "ADVISORY_FILES_MAY_REFRESH_INDEPENDENTLY_AND_NEVER_AUTHORIZE_PRODUCTION",
        "automatic_buy": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if unhealthy:
        raise RuntimeError("DECISION_GENERATION_INCOMPLETE_FAIL_CLOSED")
    return payload


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
