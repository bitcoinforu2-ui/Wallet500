from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")


def _load(name, default):
    try:
        p = DATA / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() and p.stat().st_size else default
    except Exception:
        return default


def _write(name, payload):
    (DATA / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _reason(rec):
    status = str(rec.get("measurement_status") or "")
    locked = rec.get("pair_identity_status") == "LOCKED" or bool(rec.get("entry_pair_address"))
    hist = rec.get("history") if isinstance(rec.get("history"), list) else []
    last = hist[-1] if hist else {}
    try:
        liq = float(last.get("liquidity_usd")) if last.get("liquidity_usd") is not None else None
    except Exception:
        liq = None

    if status == "VERIFIED_EXACT_PAIR":
        return "VERIFIED_EXACT_PAIR"
    if not locked:
        return "NEVER_HAD_LOCKED_PAIR"
    if liq is not None and liq < 5000:
        return "LIQUIDITY_COLLAPSED_LT_5K"
    if hist:
        return "LOCKED_PAIR_NOT_CURRENTLY_OBSERVED"
    return "LOCKED_PAIR_NEVER_OBSERVED"


def run():
    now = datetime.now(timezone.utc).isoformat()
    tracker = _load("outcome-tracker.json", {})
    records = tracker.get("tokens") if isinstance(tracker, dict) else {}
    if not isinstance(records, dict):
        records = {}

    previous = _load("exact-pair-loss-report.json", {})
    previous_rows = previous.get("rows") if isinstance(previous, dict) else {}
    if not isinstance(previous_rows, dict):
        previous_rows = {}

    counts = Counter()
    transitions = Counter()
    rows = {}
    for key, rec in records.items():
        if not isinstance(rec, dict):
            continue
        reason = _reason(rec)
        counts[reason] += 1
        prior = previous_rows.get(key, {}) if isinstance(previous_rows.get(key), dict) else {}
        prior_reason = prior.get("reason")
        if prior_reason and prior_reason != reason:
            transitions[f"{prior_reason}->{reason}"] += 1
        rows[key] = {
            "chain": rec.get("chain"),
            "token": rec.get("token"),
            "entry_pair_address": rec.get("entry_pair_address"),
            "pair_identity_status": rec.get("pair_identity_status"),
            "measurement_status": rec.get("measurement_status"),
            "last_verified_at": rec.get("updated_at"),
            "reason": reason,
        }

    total = len(rows)
    verified = counts["VERIFIED_EXACT_PAIR"]
    locked = total - counts["NEVER_HAD_LOCKED_PAIR"]
    report = {
        "version": 1,
        "updated_at": now,
        "production_change": False,
        "purpose": "DIAGNOSE_EXACT_PAIR_MEASURABILITY_LOSS_WITHOUT_RELAXING_IDENTITY_RULES",
        "total_tracked": total,
        "locked_pair_records": locked,
        "verified_exact_pair_now": verified,
        "verified_coverage_pct": round(verified / total * 100, 4) if total else 0.0,
        "locked_pair_coverage_pct": round(locked / total * 100, 4) if total else 0.0,
        "reason_counts": dict(counts),
        "transitions_since_previous_report": dict(transitions),
        "verified_to_unmeasurable_since_previous_report": sum(v for k, v in transitions.items() if k.startswith("VERIFIED_EXACT_PAIR->")),
        "interpretation_rule": "UNMEASURABLE_IS_NOT_RUG. Rug/failed-survival requires independent evidence of liquidity/pair collapse; provider absence alone is insufficient.",
        "rows": rows,
    }
    _write("exact-pair-loss-report.json", report)
    print(json.dumps({k: report[k] for k in ("total_tracked", "locked_pair_records", "verified_exact_pair_now", "verified_coverage_pct", "reason_counts", "verified_to_unmeasurable_since_previous_report")}, indent=2))
    return report


if __name__ == "__main__":
    run()
