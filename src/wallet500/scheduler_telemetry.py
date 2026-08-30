from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _age_seconds(ts: object, now: datetime):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def run(output_dir: str = "data"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    summary = _load(out / "run-summary.json", {})
    previous = _load(out / "scheduler-health.json", {})
    history = previous.get("history", []) if isinstance(previous, dict) else []
    if not isinstance(history, list):
        history = []

    updated_at = summary.get("updated_at") if isinstance(summary, dict) else None
    age = _age_seconds(updated_at, now)
    sample = {
        "observed_at": now.isoformat(),
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "run_number": os.getenv("GITHUB_RUN_NUMBER"),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "event": os.getenv("GITHUB_EVENT_NAME"),
        "sha": os.getenv("GITHUB_SHA"),
        "summary_updated_at": updated_at,
        "summary_age_seconds": round(age, 1) if age is not None else None,
        "active_qualified": int(summary.get("active_qualified", 0) or 0) if isinstance(summary, dict) else 0,
        "system_health": ((summary.get("system_health") or {}).get("overall")) if isinstance(summary, dict) else None,
    }
    history.append(sample)
    payload = {
        "version": 1,
        "updated_at": now.isoformat(),
        "mode": "OBSERVABILITY_ONLY_NO_POLICY_EFFECT",
        "current": sample,
        "history": history[-192:],
        "policy": "Telemetry never changes qualification, liquidity, exact-pair, holder/cluster, track-record, or experiment rules.",
    }
    (out / "scheduler-health.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(sample, indent=2))
    return payload


if __name__ == "__main__":
    run()
