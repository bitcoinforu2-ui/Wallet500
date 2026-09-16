from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = "bitcoinforu2-ui/Wallet500"
DATA = Path("data")
REPORT = DATA / "system-watchdog.json"
STATE = DATA / "system-watchdog-state.json"

QUEUE_HIGH = 8
RUNNING_HIGH = 12
RUNS_PER_DAY_HIGH = 1500
FAILURES_PER_DAY_HIGH = 20
STARVATION_WARN_SECONDS = 90 * 60
MANAGED_CODES = {
    "GITHUB_ACTIONS_CAPACITY_PRESSURE",
    "GITHUB_ACTIONS_FAILURE_PRESSURE",
    "REVIVAL_NEWER_RUN_FAILED_TO_PUBLISH",
    "CANDIDATE_STARVATION_SUSTAINED",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _api(path: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Wallet500-Operational-Guard/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        value = json.loads(response.read().decode("utf-8"))
    return value if isinstance(value, dict) else {}


def _count(token: str, **params: object) -> int:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    payload = _api(f"/actions/runs?{query}", token)
    return int(payload.get("total_count") or 0)


def _workflow_runs(token: str, workflow: str, limit: int = 5) -> list[dict[str, Any]]:
    payload = _api(f"/actions/workflows/{workflow}/runs?per_page={limit}", token)
    rows = payload.get("workflow_runs") or []
    return [x for x in rows if isinstance(x, dict)]


def _incident(code: str, severity: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "detail": detail, **extra}


def _starvation_state(now: datetime, report_state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    summary = _load(DATA / "run-summary.json", {})
    health = _load(DATA / "system-health.json", {})
    active = int(summary.get("active_qualified") or 0) if isinstance(summary, dict) else 0
    lane = health.get("lane_metrics") or {} if isinstance(health, dict) else {}
    general = lane.get("legacy_general_scan") or {} if isinstance(lane, dict) else {}
    scanned = int(general.get("market_scan") or 0)
    qualified = int(general.get("qualified") or 0)

    previous = report_state.get("operational_guard") or {}
    started = _parse(previous.get("zero_active_started_at"))
    if active == 0 and scanned >= 100 and qualified > 0:
        started = started or now
        age = max(0.0, (now - started).total_seconds())
        state = {
            "zero_active_started_at": started.isoformat(),
            "zero_active_age_seconds": round(age, 1),
            "active_qualified": active,
            "market_scan": scanned,
            "legacy_qualified": qualified,
        }
        if age >= STARVATION_WARN_SECONDS:
            return state, _incident(
                "CANDIDATE_STARVATION_SUSTAINED",
                "MEDIUM",
                f"active_qualified=0 for {age/60:.0f}m while scanner sees {qualified} qualified of {scanned}",
                **state,
            )
        return state, None

    return {
        "zero_active_started_at": None,
        "zero_active_age_seconds": 0,
        "active_qualified": active,
        "market_scan": scanned,
        "legacy_qualified": qualified,
    }, None


def run(now: datetime | None = None) -> dict[str, Any]:
    now = (now or _now()).astimezone(timezone.utc)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("OPERATIONAL_GUARD_GITHUB_TOKEN_MISSING")

    report = _load(REPORT, {})
    state = _load(STATE, {})
    if not isinstance(report, dict) or not isinstance(state, dict):
        raise SystemExit("OPERATIONAL_GUARD_WATCHDOG_INPUT_INVALID")

    start_day = now.strftime("%Y-%m-%dT00:00:00Z")
    queued = _count(token, status="queued", per_page=1)
    running = _count(token, status="in_progress", per_page=1)
    today = _count(token, created=f">={start_day}", per_page=1)
    failures = _count(token, status="failure", created=f">={start_day}", per_page=1)

    incidents: list[dict[str, Any]] = []
    if queued >= QUEUE_HIGH or running >= RUNNING_HIGH or today >= RUNS_PER_DAY_HIGH:
        incidents.append(
            _incident(
                "GITHUB_ACTIONS_CAPACITY_PRESSURE",
                "HIGH",
                f"queued={queued}, in_progress={running}, runs_today={today}",
                queued=queued,
                in_progress=running,
                runs_today=today,
                thresholds={
                    "queued": QUEUE_HIGH,
                    "in_progress": RUNNING_HIGH,
                    "runs_today": RUNS_PER_DAY_HIGH,
                },
            )
        )
    if failures >= FAILURES_PER_DAY_HIGH:
        incidents.append(
            _incident(
                "GITHUB_ACTIONS_FAILURE_PRESSURE",
                "HIGH",
                f"workflow failures today={failures}",
                failures_today=failures,
                threshold=FAILURES_PER_DAY_HIGH,
            )
        )

    revival_runs = _workflow_runs(token, "revival-1000.yml", 5)
    latest_revival = revival_runs[0] if revival_runs else {}
    revival_data = _load(DATA / "revival-1000-latest.json", {})
    generated = _parse(revival_data.get("generated_at") if isinstance(revival_data, dict) else None)
    latest_run_time = _parse(latest_revival.get("updated_at") or latest_revival.get("created_at"))
    if (
        latest_revival.get("status") == "completed"
        and latest_revival.get("conclusion") == "failure"
        and latest_run_time is not None
        and (generated is None or latest_run_time > generated)
    ):
        incidents.append(
            _incident(
                "REVIVAL_NEWER_RUN_FAILED_TO_PUBLISH",
                "HIGH",
                "latest Revival run failed after the currently published snapshot was generated",
                run_id=latest_revival.get("id"),
                run_updated_at=latest_revival.get("updated_at"),
                published_generated_at=revival_data.get("generated_at") if isinstance(revival_data, dict) else None,
            )
        )

    starvation_state, starvation = _starvation_state(now, state)
    if starvation:
        incidents.append(starvation)

    checks = report.setdefault("checks", {})
    checks["github_actions_capacity"] = {
        "queued": queued,
        "in_progress": running,
        "runs_today": today,
        "failures_today": failures,
        "ok": not any(i["code"].startswith("GITHUB_ACTIONS_") for i in incidents),
    }
    checks["revival_publish_freshness"] = {
        "latest_run_id": latest_revival.get("id"),
        "latest_status": latest_revival.get("status"),
        "latest_conclusion": latest_revival.get("conclusion"),
        "latest_updated_at": latest_revival.get("updated_at"),
        "published_generated_at": revival_data.get("generated_at") if isinstance(revival_data, dict) else None,
        "ok": not any(i["code"] == "REVIVAL_NEWER_RUN_FAILED_TO_PUBLISH" for i in incidents),
    }
    checks["candidate_starvation"] = {
        **starvation_state,
        "warn_after_seconds": STARVATION_WARN_SECONDS,
        "ok": starvation is None,
    }

    # Operational incidents are edge-triggered facts, not permanent history.
    # Drop managed codes that have recovered; keep incidents owned by the base watchdog.
    existing = [
        x
        for x in report.get("incidents") or []
        if isinstance(x, dict) and str(x.get("code") or "") not in MANAGED_CODES
    ]
    by_code = {str(x.get("code") or ""): x for x in existing if x.get("code")}
    for item in incidents:
        by_code[str(item["code"])] = item
    merged = list(by_code.values())
    order = {"INFO": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    merged.sort(key=lambda x: (-order.get(str(x.get("severity")), 0), str(x.get("code"))))
    report["incidents"] = merged
    report["incident_count"] = len(merged)
    report["critical_count"] = sum(1 for x in merged if x.get("severity") == "CRITICAL")
    report["high_count"] = sum(1 for x in merged if x.get("severity") == "HIGH")
    report["overall"] = (
        "CRITICAL"
        if report["critical_count"]
        else "DEGRADED"
        if merged
        else "HEALTHY"
    )
    report["operational_guard_updated_at"] = now.isoformat()
    contract = list(report.get("truth_contract") or [])
    for rule in (
        "GLOBAL_ACTIONS_QUEUE_AND_RUN_PRESSURE_IS_MEASURED",
        "NEWER_FAILED_REVIVAL_PUBLICATION_IS_NOT_HEALTHY",
        "SUSTAINED_ZERO_ACTIVE_WITH_QUALIFIED_SCAN_INPUT_IS_STARVATION",
        "OPERATIONAL_GUARD_NEVER_CHANGES_TRADING_POLICY",
    ):
        if rule not in contract:
            contract.append(rule)
    report["truth_contract"] = contract

    state["operational_guard"] = starvation_state
    state["updated_at"] = now.isoformat()
    _write(REPORT, report)
    _write(STATE, state)
    print(json.dumps({"overall": report["overall"], "operational_incidents": incidents, "checks": checks}, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
