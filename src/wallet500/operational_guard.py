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
    "CEX_SPOT_IDENTITY_STALE_OR_FAILED",
    "DECISION_GENERATION_STALE_OR_INVALID",
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

    # The action lane must not silently disappear when scheduled producer runs
    # are skipped under GitHub Actions queue pressure. Never use stale identity.
    cex_identity = _load(DATA / "cex-spot-identity-radar.json", {})
    cex_generated = _parse(cex_identity.get("generated_at") if isinstance(cex_identity, dict) else None)
    cex_age = (now - cex_generated).total_seconds() if cex_generated is not None else None
    cex_runs = _workflow_runs(token, "cex-spot-revival-fast.yml", 5)
    latest_cex = cex_runs[0] if cex_runs else {}
    cex_last_run_at = _parse(latest_cex.get("updated_at") or latest_cex.get("created_at"))
    cex_failed_newer = bool(
        latest_cex.get("status") == "completed"
        and latest_cex.get("conclusion") == "failure"
        and cex_last_run_at is not None
        and (cex_generated is None or cex_last_run_at > cex_generated)
    )
    cex_stale = cex_age is None or cex_age < -120 or cex_age > 45 * 60
    if cex_stale or cex_failed_newer:
        incidents.append(_incident(
            "CEX_SPOT_IDENTITY_STALE_OR_FAILED",
            "HIGH",
            "CEX fast promotion lacks fresh exact-identity source; remain fail closed",
            age_seconds=round(cex_age, 1) if cex_age is not None else None,
            max_age_seconds=45 * 60,
            latest_producer_run_id=latest_cex.get("id"),
            latest_producer_conclusion=latest_cex.get("conclusion"),
            latest_producer_at=latest_cex.get("updated_at"),
            last_published_at=cex_identity.get("generated_at") if isinstance(cex_identity, dict) else None,
        ))

    # Health reporting must never depend on the decision generation being
    # healthy: a stale decision producer is precisely when the watchdog matters.
    generation = _load(DATA / "decision-generation.json", {})
    generation_time = _parse(generation.get("created_at") if isinstance(generation, dict) else None)
    generation_age = (now - generation_time).total_seconds() if generation_time else None
    generation_ok = bool(
        isinstance(generation, dict)
        and generation.get("status") == "COHERENT_READY"
        and generation_age is not None
        and -120 <= generation_age <= 45 * 60
    )
    if not generation_ok:
        incidents.append(_incident(
            "DECISION_GENERATION_STALE_OR_INVALID", "HIGH",
            "No current coherent decision generation; BUY/publishing gates remain fail closed",
            age_seconds=round(generation_age, 1) if generation_age is not None else None,
            reported_status=generation.get("status") if isinstance(generation, dict) else None,
            max_age_seconds=45 * 60,
        ))

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
    checks["cex_spot_identity_freshness"] = {
        "ok": not (cex_stale or cex_failed_newer),
        "age_seconds": round(cex_age, 1) if cex_age is not None else None,
        "max_age_seconds": 45 * 60,
        "latest_producer_run_id": latest_cex.get("id"),
        "latest_producer_conclusion": latest_cex.get("conclusion"),
        "source_generated_at": cex_identity.get("generated_at") if isinstance(cex_identity, dict) else None,
        "fail_closed_when_stale": True,
    }
    checks["decision_generation_freshness"] = {
        "ok": generation_ok,
        "age_seconds": round(generation_age, 1) if generation_age is not None else None,
        "max_age_seconds": 45 * 60,
        "status": generation.get("status") if isinstance(generation, dict) else None,
        "stale_never_authorizes_buy": True,
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
        "STALE_CEX_SPOT_IDENTITY_OR_FAILED_PRODUCER_IS_OPERATIONAL_INCIDENT",
        "STALE_DECISION_GENERATION_DOES_NOT_DISABLE_INDEPENDENT_WATCHDOG",
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
