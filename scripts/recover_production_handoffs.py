"""Dispatch existing production consumers when their handoff is missing.

This orchestrates existing workflows only; it never scans, publishes data or sends
Telegram. API errors fail visibly rather than being interpreted as an idle queue.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ACTIVE = {"queued", "in_progress", "pending", "waiting", "requested"}
LANES = (
    ("verified-publisher.yml", "publish-evidence.json", 30 * 60),
    ("unified-watch-engine.yml", "unified-watch-intelligence-report.json", 20 * 60),
)


def stale(path: Path, max_age: int, now: datetime) -> bool:
    try:
        doc = json.loads(path.read_text())
        stamp = doc.get("updated_at") or doc.get("created_at") or doc.get("generated_at")
        observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return True
        age = (now - observed).total_seconds()
        return age < -300 or age > max_age
    except (OSError, ValueError, TypeError, AttributeError):
        return True


def api(repository: str, endpoint: str, body: dict | None = None) -> dict:
    args = ["gh", "api", "--method", "POST" if body is not None else "GET",
            f"repos/{repository}/{endpoint}"]
    if body is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def recover(repository: str, *, data_dir: Path = Path("data"), source_run_id: str | None = None,
            now: datetime | None = None, request=api) -> list[dict]:
    if source_run_id is not None and (not str(source_run_id).isascii() or not str(source_run_id).isdigit()):
        raise ValueError("INVALID_SOURCE_RUN_ID")
    now = now or datetime.now(timezone.utc)
    results = []
    for workflow, filename, max_age in LANES:
        # Every validated scan needs its exact artifact published. The watch lane
        # is dispatched only when stale so a code change cannot replace fresh work.
        required = (workflow == "verified-publisher.yml" and source_run_id is not None) or stale(data_dir / filename, max_age, now)
        if not required:
            results.append({"workflow": workflow, "status": "CURRENT"})
            continue
        runs = request(repository, f"actions/workflows/{workflow}/runs?per_page=30")
        if not isinstance(runs.get("workflow_runs"), list):
            raise RuntimeError("HANDOFF_RUN_INVENTORY_INVALID")
        if any(r.get("status") in ACTIVE for r in runs["workflow_runs"]):
            results.append({"workflow": workflow, "status": "ACTIVE_NO_DUPLICATE"})
            continue
        body = {"ref": "main"}
        if workflow == "verified-publisher.yml" and source_run_id is not None:
            body["inputs"] = {"source_run_id": str(source_run_id)}
        request(repository, f"actions/workflows/{workflow}/dispatches", body)
        results.append({"workflow": workflow, "status": "DISPATCHED"})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-id")
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    print(json.dumps(recover(repo, source_run_id=args.source_run_id)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
