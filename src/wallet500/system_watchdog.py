from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DATA = Path("data")
REPORT = DATA / "system-watchdog.json"
STATE = DATA / "system-watchdog-state.json"
REPO = "bitcoinforu2-ui/Wallet500"
LIVE_WORKFLOW = "live-scan.yml"
PUBLIC_ROOT = "https://bitcoinforu2-ui.github.io/Wallet500/"
PUBLIC_REAL = PUBLIC_ROOT + "data/real-alerts.json"

FRESHNESS = {
    "real-alerts.json": ("generated_at", 45 * 60, "CRITICAL", "REAL_ALERT_FEED_STALE"),
    "system-health.json": ("updated_at", 45 * 60, "HIGH", "SYSTEM_HEALTH_STALE"),
    "scheduler-health.json": ("updated_at", 45 * 60, "HIGH", "SCHEDULER_TELEMETRY_STALE"),
    "telegram-alert-report.json": ("updated_at", 60 * 60, "HIGH", "TELEGRAM_REPORT_STALE"),
    "real-alert-10usd-summary.json": ("updated_at", 60 * 60, "HIGH", "PAPER_TRACKER_STALE"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_ts(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _age_seconds(value: object, now: datetime) -> float | None:
    dt = _parse_ts(value)
    if dt is None:
        return None
    return (now - dt).total_seconds()


def _key(row: dict[str, Any]) -> str:
    chain = str(row.get("chain") or "").strip().lower()
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    if chain in {"ethereum", "bsc", "bnb", "eth", "base", "arbitrum", "optimism", "polygon", "avalanche"}:
        token, pair = token.lower(), pair.lower()
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def _incident(code: str, severity: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "detail": detail, **extra}


def _http_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Wallet500-Watchdog/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500-Watchdog/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def github_live_status(token: str | None = None) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{LIVE_WORKFLOW}/runs?per_page=12"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Wallet500-Watchdog/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    payload = _http_json(url, headers=headers)
    runs = list(payload.get("workflow_runs") or []) if isinstance(payload, dict) else []
    latest = runs[0] if runs else {}
    completed = [r for r in runs if r.get("status") == "completed"]
    successes = [r for r in completed if r.get("conclusion") == "success"]
    last_success = successes[0] if successes else {}
    return {
        "latest_status": latest.get("status"),
        "latest_conclusion": latest.get("conclusion"),
        "latest_created_at": latest.get("created_at"),
        "latest_updated_at": latest.get("updated_at"),
        "latest_run_id": latest.get("id"),
        "last_success_at": last_success.get("updated_at") or last_success.get("created_at"),
        "last_success_run_id": last_success.get("id"),
    }


def public_status() -> dict[str, Any]:
    root = _http_text(PUBLIC_ROOT)
    real = _http_json(PUBLIC_REAL)
    return {
        "dashboard_ok": "LIVE RADAR" in root,
        "real_feed_ok": isinstance(real, dict) and isinstance(real.get("counts"), dict),
        "real_feed_generated_at": real.get("generated_at") if isinstance(real, dict) else None,
    }


def build_report(
    data_dir: Path = DATA,
    *,
    now: datetime | None = None,
    state: dict[str, Any] | None = None,
    gh: dict[str, Any] | None = None,
    public: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now = (now or _now()).astimezone(timezone.utc)
    state = dict(state or {})
    incidents: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}

    for filename, (ts_field, max_age, severity, code) in FRESHNESS.items():
        payload = _load(data_dir / filename, {})
        ts = payload.get(ts_field) if isinstance(payload, dict) else None
        age = _age_seconds(ts, now)
        ok = age is not None and -120 <= age <= max_age
        checks[filename] = {"timestamp": ts, "age_seconds": round(age, 1) if age is not None else None, "max_age_seconds": max_age, "ok": ok}
        if not ok:
            incidents.append(_incident(code, severity, f"{filename} age={round(age,1) if age is not None else 'missing'}s max={max_age}s"))

    health = _load(data_dir / "system-health.json", {})
    health_failures = list(health.get("failures") or []) if isinstance(health, dict) else []
    blockers = int(((health.get("failure_summary") or {}).get("system_production_blockers") or 0)) if isinstance(health, dict) else 0
    if blockers > 0:
        incidents.append(_incident("SYSTEM_HEALTH_PRODUCTION_BLOCKER", "CRITICAL", f"system_health reports {blockers} production blocker(s)", failures=health_failures[:8]))

    telegram = _load(data_dir / "telegram-alert-report.json", {})
    if isinstance(telegram, dict):
        if telegram.get("configured") is False:
            incidents.append(_incident("TELEGRAM_NOT_CONFIGURED", "CRITICAL", "production Telegram report says configured=false"))
        errors = int(telegram.get("error_count") or 0)
        if errors > 0:
            incidents.append(_incident("TELEGRAM_DELIVERY_ERRORS", "CRITICAL", f"Telegram delivery error_count={errors}", errors=list(telegram.get("errors") or [])[:5]))

    real = _load(data_dir / "real-alerts.json", {})
    real_rows = list(real.get("alerts") or []) if isinstance(real, dict) else []
    current_real = {_key(r) for r in real_rows if isinstance(r, dict) and _key(r)}
    previous_real = set(state.get("active_real_keys") or [])
    baseline_done = bool(state.get("baseline_initialized"))
    entered_real = sorted(current_real - previous_real) if baseline_done else []
    telegram_state = _load(data_dir / "telegram-alert-state.json", {})
    sent = telegram_state.get("sent") if isinstance(telegram_state, dict) and isinstance(telegram_state.get("sent"), dict) else {}
    missing_delivery = [k for k in entered_real if not (isinstance(sent.get(k), dict) and sent[k].get("actionable") is True)]
    if missing_delivery:
        incidents.append(_incident("NEW_REAL_ALERT_TELEGRAM_GAP", "CRITICAL", f"{len(missing_delivery)} newly-entered REAL ALERT pair(s) have no actionable Telegram state", keys=missing_delivery))

    paper = _load(data_dir / "real-alert-10usd-summary.json", {})
    paper_keys = {_key(p) for p in list(paper.get("positions") or []) if isinstance(p, dict) and _key(p)} if isinstance(paper, dict) else set()
    delivered = list(telegram.get("delivered") or []) if isinstance(telegram, dict) else []
    delivered_keys = {str(d.get("key") or "") for d in delivered if isinstance(d, dict) and d.get("sent_at")}
    paper_missing = sorted(k for k in delivered_keys if k and k not in paper_keys)
    if paper_missing:
        incidents.append(_incident("TELEGRAM_DELIVERY_PAPER_TRACKER_GAP", "CRITICAL", f"{len(paper_missing)} delivered alert(s) missing from $10 paper cohort", keys=paper_missing))

    if gh is not None:
        checks["github_live_scan"] = gh
        success_age = _age_seconds(gh.get("last_success_at"), now)
        if success_age is None or success_age > 45 * 60:
            incidents.append(_incident("LIVE_SCAN_LAST_SUCCESS_STALE", "CRITICAL", f"last successful Live Scan age={round(success_age,1) if success_age is not None else 'missing'}s", run_id=gh.get("last_success_run_id")))
        if gh.get("latest_status") == "completed" and gh.get("latest_conclusion") not in {"success", "skipped", None}:
            incidents.append(_incident("LIVE_SCAN_LATEST_FAILED", "HIGH", f"latest Live Scan conclusion={gh.get('latest_conclusion')}", run_id=gh.get("latest_run_id")))

    if public is not None:
        checks["public_surface"] = public
        if public.get("dashboard_ok") is not True:
            incidents.append(_incident("PUBLIC_DASHBOARD_UNREACHABLE_OR_WRONG_BUILD", "HIGH", "public root did not expose LIVE RADAR marker"))
        if public.get("real_feed_ok") is not True:
            incidents.append(_incident("PUBLIC_REAL_ALERT_FEED_INVALID", "CRITICAL", "public real-alerts.json is unreachable or invalid"))
        else:
            public_age = _age_seconds(public.get("real_feed_generated_at"), now)
            if public_age is None or public_age > 60 * 60:
                incidents.append(_incident("PUBLIC_REAL_ALERT_FEED_STALE", "CRITICAL", f"public REAL ALERT feed age={round(public_age,1) if public_age is not None else 'missing'}s"))

    severity_order = {"INFO": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    incidents.sort(key=lambda x: (-severity_order.get(str(x.get("severity")), 0), str(x.get("code"))))
    overall = "CRITICAL" if any(i["severity"] == "CRITICAL" for i in incidents) else ("DEGRADED" if incidents else "HEALTHY")

    active_prev = dict(state.get("active_incidents") or {})
    active_next: dict[str, Any] = {}
    notify: list[dict[str, Any]] = []
    now_iso = now.isoformat()
    for inc in incidents:
        code = str(inc["code"])
        old = dict(active_prev.get(code) or {})
        first_seen = old.get("first_seen") or now_iso
        last_notified = old.get("last_notified")
        last_notified_age = _age_seconds(last_notified, now) if last_notified else None
        repeat_after = 6 * 3600 if inc["severity"] == "CRITICAL" else 24 * 3600
        should_notify = not old or last_notified_age is None or last_notified_age >= repeat_after or severity_order.get(inc["severity"], 0) > severity_order.get(old.get("severity"), 0)
        active_next[code] = {"severity": inc["severity"], "first_seen": first_seen, "last_seen": now_iso, "last_notified": now_iso if should_notify else last_notified, "detail": inc["detail"]}
        if should_notify:
            notify.append(inc)

    recovered = sorted(set(active_prev) - set(active_next))
    next_state = {
        "version": 1,
        "updated_at": now_iso,
        "baseline_initialized": True,
        "active_real_keys": sorted(current_real),
        "active_incidents": active_next,
        "last_recovered_codes": recovered,
    }
    report = {
        "version": 1,
        "mode": "INDEPENDENT_OBSERVABILITY_NO_TRADING_POLICY_EFFECT",
        "updated_at": now_iso,
        "overall": overall,
        "incident_count": len(incidents),
        "critical_count": sum(1 for i in incidents if i["severity"] == "CRITICAL"),
        "high_count": sum(1 for i in incidents if i["severity"] == "HIGH"),
        "new_notifications": notify,
        "recovered_codes": recovered,
        "real_alert_transitions_entered": entered_real,
        "incidents": incidents,
        "checks": checks,
        "truth_contract": [
            "WATCHDOG_NEVER_CHANGES_SIGNAL_OR_TRADING_POLICY",
            "NO_TELEGRAM_MESSAGE_WHEN_HEALTHY",
            "INCIDENTS_ARE_DEDUPED_AND_RATE_LIMITED",
            "CURRENT_REAL_ALERTS_ARE_BASELINED_ON_FIRST_WATCHDOG_RUN",
            "NEW_REAL_ALERT_TELEGRAM_GAPS_ARE_DETECTED_BY_EXACT_PAIR_TRANSITION",
        ],
    }
    return report, next_state


def _format_israel(ts: datetime) -> str:
    return ts.astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y %H:%M:%S")


def send_telegram(incidents: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    if not incidents:
        return {"attempted": False, "sent": False, "reason": "NO_NEW_INCIDENTS"}
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"attempted": False, "sent": False, "reason": "TELEGRAM_SECRETS_MISSING"}
    now = now or _now()
    lines = ["🚨 Wallet500 SYSTEM WATCHDOG", f"📅 {_format_israel(now)} ישראל", f"תקלות חדשות/מתמשכות לדיווח: {len(incidents)}", ""]
    for inc in incidents[:8]:
        icon = "🔴" if inc.get("severity") == "CRITICAL" else "🟠"
        lines.append(f"{icon} {inc.get('code')}")
        lines.append(str(inc.get("detail") or "")[:300])
    lines += ["", "ה-Watchdog אינו משנה סיגנלים, שערי REAL ALERT או פעולות מסחר."]
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": "\n".join(lines)[:3900], "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
        return {"attempted": True, "sent": bool(payload.get("ok")), "message_id": ((payload.get("result") or {}).get("message_id"))}
    except Exception as exc:
        return {"attempted": True, "sent": False, "reason": type(exc).__name__, "detail": str(exc)[:300]}


def run(data_dir: Path = DATA) -> dict[str, Any]:
    now = _now()
    state = _load(data_dir / STATE.name, {})
    network_errors: list[dict[str, Any]] = []
    gh = None
    public = None
    try:
        gh = github_live_status(os.getenv("GITHUB_TOKEN"))
    except Exception as exc:
        network_errors.append(_incident("WATCHDOG_GITHUB_API_UNAVAILABLE", "HIGH", f"{type(exc).__name__}: {str(exc)[:200]}"))
    try:
        public = public_status()
    except Exception as exc:
        network_errors.append(_incident("WATCHDOG_PUBLIC_PROBE_FAILED", "HIGH", f"{type(exc).__name__}: {str(exc)[:200]}"))

    report, next_state = build_report(data_dir, now=now, state=state, gh=gh, public=public)
    if network_errors:
        report["incidents"].extend(network_errors)
        report["incident_count"] = len(report["incidents"])
        report["high_count"] = sum(1 for i in report["incidents"] if i.get("severity") == "HIGH")
        if report["overall"] == "HEALTHY":
            report["overall"] = "DEGRADED"
        for inc in network_errors:
            code = inc["code"]
            if code not in next_state["active_incidents"]:
                next_state["active_incidents"][code] = {"severity": inc["severity"], "first_seen": now.isoformat(), "last_seen": now.isoformat(), "last_notified": now.isoformat(), "detail": inc["detail"]}
                report["new_notifications"].append(inc)

    notification = send_telegram(list(report.get("new_notifications") or []), now)
    report["notification"] = notification
    _write(data_dir / REPORT.name, report)
    _write(data_dir / STATE.name, next_state)
    print(json.dumps({"overall": report["overall"], "incidents": report["incident_count"], "notification": notification}, indent=2))
    return report


if __name__ == "__main__":
    run()
