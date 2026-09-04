#!/usr/bin/env python3
"""Wallet500 engine -> JSON -> dashboard overlap audit.

Research/observability only. This tool never changes trading state, scores, alerts,
or portfolio decisions. It checks that dashboard surfaces are wired to the engine
outputs they claim to represent and highlights freshness/truth-contract drift.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def parse_ts(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def minutes_between(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    return abs((a - b).total_seconds()) / 60.0


def add(findings: list[dict], severity: str, code: str, message: str, **details: object) -> None:
    findings.append({"severity": severity, "code": code, "message": message, **details})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit non-zero when CRITICAL findings exist")
    ap.add_argument("--freshness-minutes", type=float, default=30.0)
    args = ap.parse_args()

    findings: list[dict] = []
    now = datetime.now(timezone.utc)

    real = load_json("real-alerts.json")
    revival = load_json("revival-1000-latest.json")
    waking = load_json("waking-confirmation-latest.json")
    pret0 = load_json("revival-pre-t0-evidence.json")
    ledger = load_json("revival-pre-t0-evidence-ledger.json")
    holders = load_json("revival-holder-latest.json")

    home = (ROOT / "index.html").read_text(encoding="utf-8")
    live_dash = (ROOT / "dashboard-live.html").read_text(encoding="utf-8")
    revival_dash = (ROOT / "dashboard-revival1000.html").read_text(encoding="utf-8")

    # 1) Source wiring: dashboard must read the engine outputs it claims to show.
    if "real-alerts.json" not in live_dash:
        add(findings, "CRITICAL", "LIVE_SOURCE_MISSING", "Live dashboard is not wired to real-alerts.json")
    if "real-alerts.json" not in home:
        add(findings, "WARN", "HOME_LIVE_SOURCE_MISSING", "Home page is not wired to real-alerts.json")
    if "revival-1000-latest.json" not in revival_dash:
        add(findings, "CRITICAL", "REVIVAL_SOURCE_MISSING", "Revival dashboard is not wired to revival-1000-latest.json")

    # PRE-T0 is research-only, so it must not leak into REAL alerts, but its health
    # should still be observable somewhere on the research dashboard.
    pret0_visible = (
        "revival-pre-t0-evidence.json" in revival_dash
        or "waking-pre-t0-confirmation.json" in revival_dash
    )
    if not pret0_visible:
        add(findings, "WARN", "PRET0_NOT_OBSERVABLE", "PRE-T0 research health/binding is not visible on the Revival dashboard")

    # 2) Freshness overlap between engine layers.
    ts_real = parse_ts(real.get("generated_at"))
    ts_waking = parse_ts(waking.get("generated_at"))
    ts_pret0 = parse_ts(pret0.get("generated_at"))
    ts_revival = parse_ts(revival.get("generated_at"))

    for label, ts in (("real-alerts", ts_real), ("waking-confirmation", ts_waking), ("revival", ts_revival), ("pre-t0", ts_pret0)):
        if ts is None:
            add(findings, "CRITICAL", "TIMESTAMP_INVALID", f"{label} has no valid generated_at")
        else:
            age = (now - ts).total_seconds() / 60.0
            if age > 90:
                add(findings, "WARN", "SOURCE_STALE", f"{label} is stale", age_minutes=round(age, 1))

    skew = minutes_between(ts_real, ts_pret0)
    if skew is not None and skew > args.freshness_minutes:
        add(findings, "CRITICAL", "PRET0_FRESHNESS_SKEW", "PRE-T0 is materially behind the production alert feed", skew_minutes=round(skew, 1))

    # 3) Immutable ledger identity: record_id must be globally unique.
    ids: dict[str, int] = {}
    for row in ledger.get("records") or []:
        rid = row.get("record_id")
        if not rid:
            add(findings, "CRITICAL", "PRET0_RECORD_ID_MISSING", "PRE-T0 ledger contains a record without record_id")
            continue
        ids[str(rid)] = ids.get(str(rid), 0) + 1
    dupes = sorted(rid for rid, count in ids.items() if count > 1)
    if dupes:
        add(findings, "CRITICAL", "PRET0_RECORD_ID_DUPLICATE", "PRE-T0 ledger contains duplicate immutable record IDs", duplicate_count=len(dupes), examples=dupes[:5])

    # 4) Truth contract / safety overlap.
    if pret0.get("no_hindsight") is not True:
        add(findings, "CRITICAL", "PRET0_NO_HINDSIGHT_LOST", "PRE-T0 no_hindsight guard is not true")
    if pret0.get("production_portfolio_impact") != "NONE" or pret0.get("automatic_buy") is not False:
        add(findings, "CRITICAL", "PRET0_RESEARCH_BOUNDARY_LOST", "PRE-T0 research-only safety boundary changed")

    # 5) Holder truth: dashboard must not visually claim VERIFIED when the provider
    # is not configured / holder count is unavailable.
    provider_configured = bool(holders.get("provider_configured"))
    if not provider_configured and "FORWARD VERIFIED" in revival_dash:
        add(findings, "CRITICAL", "HOLDER_BADGE_OVERCLAIM", "Dashboard says FORWARD VERIFIED while holder provider is not configured")

    # 6) Status semantics: DEEP_WATCH is research queue membership, not a green/positive verdict.
    deep_watch_green = bool(re.search(r"DEEP_WATCH.{0,220}(green|#22c55e|#16a34a)", revival_dash, flags=re.I | re.S))
    if deep_watch_green:
        add(findings, "WARN", "DEEP_WATCH_GREEN", "DEEP_WATCH is rendered with positive/green semantics although it is research-only")

    # 7) Production truth overlap: if confirmation says zero eligible, real alerts
    # should not fabricate an eligible production card.
    waking_counts = waking.get("counts") or {}
    real_counts = real.get("counts") or {}
    waking_eligible = waking_counts.get("eligible")
    real_eligible = real_counts.get("eligible_count", real.get("eligible_count"))
    alerts = real.get("alerts") or []
    if waking_eligible in (0, None) and any(
        row.get("status") == "eligible" and row.get("execution_target") == "PRODUCTION"
        for row in alerts
    ):
        add(findings, "CRITICAL", "PRODUCTION_DASH_MISMATCH", "Production alert exists while WAKING confirmation has no eligible target")

    summary = {
        "version": "ENGINE_DASHBOARD_OVERLAP_AUDIT_V1",
        "generated_at": now.isoformat(),
        "research_only": True,
        "sources": {
            "real_alerts_generated_at": real.get("generated_at"),
            "waking_generated_at": waking.get("generated_at"),
            "revival_generated_at": revival.get("generated_at"),
            "pre_t0_generated_at": pret0.get("generated_at"),
        },
        "counts": {
            "critical": sum(1 for x in findings if x["severity"] == "CRITICAL"),
            "warn": sum(1 for x in findings if x["severity"] == "WARN"),
            "info": sum(1 for x in findings if x["severity"] == "INFO"),
        },
        "findings": findings,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.strict and summary["counts"]["critical"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
