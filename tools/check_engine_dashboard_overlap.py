#!/usr/bin/env python3
"""Fail-closed Engine -> JSON -> Dashboard truth-overlap audit."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def dt(value: object) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--structural-only", action="store_true")
    ap.add_argument("--max-skew-minutes", type=float, default=30.0)
    args = ap.parse_args()
    findings: list[dict] = []

    def add(severity: str, code: str, message: str, **details: object) -> None:
        findings.append({"severity": severity, "code": code, "message": message, **details})

    real = load("real-alerts.json")
    pre = load("revival-pre-t0-evidence.json")
    ledger = load("revival-pre-t0-evidence-ledger.json")
    waking = load("waking-pre-t0-confirmation.json")
    holder = load("revival-holder-latest.json")
    revival = load("revival-1000-latest.json")

    html = (ROOT / "dashboard-revival1000.html").read_text(encoding="utf-8")
    loader = (ROOT / "dashboard-live-price.js").read_text(encoding="utf-8")
    core = (ROOT / "dashboard-live-price-core.js").read_text(encoding="utf-8")
    truth = (ROOT / "dashboard-truth-overlap.js").read_text(encoding="utf-8")
    published_core = (DATA / "dashboard-live-price-core.js").read_text(encoding="utf-8")
    published_truth = (DATA / "dashboard-truth-overlap.js").read_text(encoding="utf-8")
    live_html = (ROOT / "dashboard-live.html").read_text(encoding="utf-8")
    v2_source = (ROOT / "src/wallet500/revival_pre_t0_evidence_v2.py").read_text(encoding="utf-8")
    pre_workflow = (ROOT / ".github/workflows/revival-pre-t0-evidence.yml").read_text(encoding="utf-8")

    # Dashboard wiring / compatibility / deployment bundle.
    if "dashboard-live-price.js" not in html:
        add("CRITICAL", "REVIVAL_SHARED_LOADER_MISSING", "Revival dashboard does not load shared dashboard script")
    if "data/dashboard-live-price-core.js" not in loader or "data/dashboard-truth-overlap.js" not in loader:
        add("CRITICAL", "TRUTH_LOADER_INCOMPLETE", "Shared loader does not synchronously chain the published core + truth modules")
    if core != published_core:
        add("CRITICAL", "PUBLISHED_CORE_DRIFT", "Published data-bundle live-price core differs from source core")
    if truth != published_truth:
        add("CRITICAL", "PUBLISHED_TRUTH_DRIFT", "Published data-bundle truth module differs from source truth module")
    if "Wallet500LivePrice" not in core:
        add("CRITICAL", "LIVE_PRICE_CORE_LOST", "Preserved live-price core no longer exposes Wallet500LivePrice")
    for required in ("revival-pre-t0-evidence.json", "real-alerts.json", "revival-holder-latest.json", "waking-pre-t0-confirmation.json"):
        if required not in truth:
            add("CRITICAL", "TRUTH_SOURCE_MISSING", f"Dashboard truth layer is not wired to {required}")
    if "BUILDING / UNVERIFIED" not in truth or "holderVerified" not in truth:
        add("CRITICAL", "HOLDER_FAIL_CLOSED_UI_MISSING", "Holder badge lacks runtime verified/unverified truth guard")
    if "DEEP_WATCH = research queue membership only" not in truth:
        add("CRITICAL", "DEEP_WATCH_UI_GUARD_MISSING", "DEEP_WATCH is not explicitly rendered as research-only")
    if "HISTORICAL + LIVE RESEARCH WATCH" not in truth:
        add("WARN", "DOGE1_HISTORY_LIVE_LABEL_MISSING", "DOGE-1 case-study/live distinction is not explicit")
    if "real-alerts.json" not in live_html:
        add("CRITICAL", "LIVE_ALERT_SOURCE_MISSING", "Live dashboard is not wired to real-alerts.json")

    # PRE-T0 integrity: on PR prove the repair exists and is wired. On main require
    # the published ledger itself to be canonical after V2 has had a chance to run.
    seen: dict[str, dict] = {}
    for row in ledger.get("records") or []:
        rid = str(row.get("record_id") or "")
        if not rid:
            add("CRITICAL", "PRET0_RECORD_ID_MISSING", "Immutable PRE-T0 record has no ID")
            continue
        if rid in seen and not args.structural_only:
            add("CRITICAL", "PRET0_RECORD_ID_DUPLICATE", "Immutable PRE-T0 record ID is duplicated", record_id=rid)
        seen[rid] = row

    if args.structural_only:
        for needle, code in (
            ("PRE_T0_V2_RECORD_ID_COLLISION", "PRET0_V2_COLLISION_GUARD_MISSING"),
            ("KEEP_EARLIEST_EXACT_KEY_HASH_IDENTITY", "PRET0_V2_CANON_POLICY_MISSING"),
            ("identity_repeat_is_not_new_observation", "PRET0_V2_IDENTITY_SEMANTICS_MISSING"),
        ):
            if needle not in v2_source:
                add("CRITICAL", code, f"PRE-T0 V2 repair source is missing {needle}")
        if "python -m wallet500.revival_pre_t0_evidence_v2" not in pre_workflow:
            add("CRITICAL", "PRET0_V2_WORKFLOW_NOT_WIRED", "PRE-T0 workflow does not execute the V2 repair")
        if "tests/test_revival_pre_t0_evidence_v2.py" not in pre_workflow:
            add("CRITICAL", "PRET0_V2_TEST_NOT_WIRED", "PRE-T0 workflow does not run the V2 integrity tests")
    else:
        integrity = ledger.get("integrity") or {}
        if integrity.get("unique_record_ids") is not True:
            add("CRITICAL", "PRET0_INTEGRITY_MARKER_MISSING", "PRE-T0 ledger is not marked as canonical unique-ID state")
        if integrity.get("conflicting_same_id_policy") != "FAIL_CLOSED":
            add("CRITICAL", "PRET0_COLLISION_GUARD_MISSING", "PRE-T0 conflicting same-ID collision is not fail-closed")
        if (pre.get("integrity") or {}).get("record_ids_unique") is not True:
            add("CRITICAL", "PRET0_LATEST_INTEGRITY_MISSING", "Latest PRE-T0 snapshot lacks unique-ID integrity state")

    # Safety / no-hindsight contract.
    for name, payload in (("pre", pre), ("waking", waking), ("revival", revival)):
        if payload.get("no_hindsight") is not True or payload.get("production_portfolio_impact") != "NONE":
            add("CRITICAL", "RESEARCH_TRUTH_CONTRACT_LOST", f"{name} research truth contract changed")
    if pre.get("automatic_buy") is not False:
        add("CRITICAL", "PRET0_AUTOBUY_GUARD_LOST", "PRE-T0 automatic_buy is not false")

    real_alerts = real.get("alerts") or []
    if any(x.get("automatic_buy") is True for x in real_alerts if isinstance(x, dict)):
        add("CRITICAL", "REAL_ALERT_AUTOBUY_UNEXPECTED", "Real alert feed contains automatic-buy behavior")

    if not args.structural_only:
        now = datetime.now(timezone.utc)
        times = {k: dt(v.get("generated_at")) for k, v in (("real", real), ("pre", pre), ("waking", waking), ("revival", revival))}
        for name, stamp in times.items():
            if stamp is None:
                add("CRITICAL", "SOURCE_TIMESTAMP_INVALID", f"{name} generated_at is invalid")
                continue
            age = (now - stamp).total_seconds() / 60
            if age > 90:
                add("CRITICAL", "SOURCE_STALE", f"{name} source is stale", source=name, age_minutes=round(age, 1))
            elif age > 30:
                add("WARN", "SOURCE_AGING", f"{name} source is aging", source=name, age_minutes=round(age, 1))
        if times.get("real") and times.get("pre"):
            skew = abs((times["real"] - times["pre"]).total_seconds()) / 60
            if skew > args.max_skew_minutes:
                add("CRITICAL", "ENGINE_DASH_FRESHNESS_SKEW", "PRE-T0 materially trails production alert feed", skew_minutes=round(skew, 1))

    counts = {
        "critical": sum(x["severity"] == "CRITICAL" for x in findings),
        "warn": sum(x["severity"] == "WARN" for x in findings),
        "info": sum(x["severity"] == "INFO" for x in findings),
    }
    out = {
        "version": "ENGINE_DASHBOARD_OVERLAP_AUDIT_V2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "structural_only": args.structural_only,
        "counts": counts,
        "findings": findings,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if args.strict and counts["critical"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
