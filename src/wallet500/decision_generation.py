"""Create one auditable generation manifest for all canonical decision outputs."""
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
    "data/cross-signal-fusion-v2.json",
    "data/system-health.json",
    "data/strict-validation.json",
    "data/production-status.json",
    "data/decision-snapshot-integrity.json",
)
OUT = Path("data/decision-generation.json")


def build(*, source_sha: str | None = None, run_id: str | None = None) -> dict:
    source_sha = str(source_sha or os.getenv("SOURCE_SHA") or os.getenv("GITHUB_SHA") or "LOCAL").strip()
    run_id = str(run_id or os.getenv("GITHUB_RUN_ID") or "LOCAL").strip()
    states = {}
    hashes = {}
    generated = {}
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
    generation_id = f"wallet500:{run_id}:{source_sha}"
    payload = {
        "version": 1,
        "generation_id": generation_id,
        "source_sha": source_sha,
        "workflow_run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_id": POLICY_ID,
        "policy": policy_snapshot(),
        "status": "COHERENT_READY" if not unhealthy else "INCOMPLETE_FAIL_CLOSED",
        "canonical_files": list(CANONICAL_FILES),
        "source_states": states,
        "source_timestamps": generated,
        "hashes": hashes,
        "unhealthy_sources": unhealthy,
        "dashboard_rule": "DASHBOARD_MUST_NOT_MIX_CANONICAL_FILES_FROM_DIFFERENT_GENERATION_MANIFESTS",
        "automatic_buy": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if unhealthy:
        raise RuntimeError("DECISION_GENERATION_INCOMPLETE_FAIL_CLOSED")
    return payload


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
