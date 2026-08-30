from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
LEDGER = DATA / "quality-shadow-ledger.json"
SUMMARY = DATA / "quality-shadow-summary.json"


def _load(path: Path, default):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text())
    except Exception:
        return default


def _write(path: Path, payload):
    text = json.dumps(payload, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    json.loads(tmp.read_text())
    tmp.replace(path)


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _dt(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _base_gate(mark: dict) -> bool:
    return (
        _f(mark.get("price_usd")) > 0
        and _f(mark.get("liquidity_usd")) >= 50000
        and _f(mark.get("volume_h1")) >= 15000
        and int(mark.get("txns_h1") or 0) >= 50
    )


def _checkpoint_due(age_minutes: float, existing: dict):
    for label, minute in (("5m", 5), ("15m", 15), ("30m", 30), ("60m", 60)):
        if age_minutes >= minute and label not in existing:
            return label
    return None


def run():
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    perf = _load(DATA / "realizable-performance.json", {})
    delayed = perf.get("quality_delayed_rows") if isinstance(perf, dict) else []
    delayed = delayed if isinstance(delayed, list) else []

    ledger = _load(LEDGER, {})
    if not isinstance(ledger, dict) or ledger.get("version") != "QUALITY_SHADOW_V1":
        ledger = {"version": "QUALITY_SHADOW_V1", "created_at": now, "records": {}}
    records = ledger.get("records") if isinstance(ledger.get("records"), dict) else {}
    ledger["records"] = records

    current_keys = set()
    for row in delayed:
        if not isinstance(row, dict) or not row.get("key"):
            continue
        key = str(row["key"])
        current_keys.add(key)
        r = records.get(key)
        if not isinstance(r, dict):
            r = {
                "key": key,
                "chain": row.get("chain"),
                "token": row.get("token"),
                "pair_address": row.get("pair_address"),
                "first_delayed_at": now,
                "initial_reason": row.get("status"),
                "initial_reasons": row.get("reasons") or [],
                "initial_price_usd": _f(row.get("price_usd")),
                "initial_liquidity_usd": _f(row.get("liquidity_usd")),
                "initial_volume_h1": _f(row.get("volume_h1")),
                "initial_txns_h1": int(row.get("txns_h1") or 0),
                "initial_pre_runup_pct": row.get("pre_entry_runup_pct"),
                "initial_turnover_h1": row.get("turnover_h1"),
                "checkpoints": {},
                "history": [],
                "status": "WATCHING",
            }
            records[key] = r

        mark = {
            "observed_at": now,
            "price_usd": _f(row.get("price_usd")),
            "liquidity_usd": _f(row.get("liquidity_usd")),
            "volume_h1": _f(row.get("volume_h1")),
            "txns_h1": int(row.get("txns_h1") or 0),
            "pre_entry_runup_pct": row.get("pre_entry_runup_pct"),
            "turnover_h1": row.get("turnover_h1"),
            "quality_status": row.get("status"),
            "quality_reasons": row.get("reasons") or [],
        }
        p0 = _f(r.get("initial_price_usd"))
        l0 = _f(r.get("initial_liquidity_usd"))
        mark["return_since_delay_pct"] = round((mark["price_usd"] / p0 - 1) * 100, 4) if p0 > 0 else None
        mark["liquidity_retention_pct"] = round(mark["liquidity_usd"] / l0 * 100, 2) if l0 > 0 else None
        hist = r.get("history") if isinstance(r.get("history"), list) else []
        hist.append(mark)
        r["history"] = hist[-120:]
        r["last_seen_at"] = now
        r["latest"] = mark

        first = _dt(r.get("first_delayed_at")) or now_dt
        age = max(0.0, (now_dt - first).total_seconds() / 60.0)
        r["age_minutes"] = round(age, 2)
        cps = r.get("checkpoints") if isinstance(r.get("checkpoints"), dict) else {}
        due = _checkpoint_due(age, cps)
        if due:
            cps[due] = dict(mark)
        r["checkpoints"] = cps

        pre = row.get("pre_entry_runup_pct")
        pre = _f(pre, 999999.0) if pre is not None else None
        retention = mark.get("liquidity_retention_pct")
        ret = mark.get("return_since_delay_pct")
        if not _base_gate(mark) or (retention is not None and retention < 75):
            r["status"] = "DETERIORATED"
        elif age >= 5 and pre is not None and pre <= 25 and (retention is None or retention >= 90):
            r["status"] = "RECOVERED_ENTRY_WINDOW"
        elif age >= 5 and ret is not None and ret >= 10 and (retention is None or retention >= 90):
            r["status"] = "CONTINUED_STRONG_AFTER_DELAY"
        else:
            r["status"] = "WATCHING"

    # Keep disappeared candidates for audit; do not delete history.
    for key, r in records.items():
        if key not in current_keys and isinstance(r, dict) and r.get("status") == "WATCHING":
            r["status"] = "NO_LONGER_DELAYED_OR_NOT_CURRENTLY_VISIBLE"

    counts = {}
    for r in records.values():
        s = str(r.get("status") or "UNKNOWN")
        counts[s] = counts.get(s, 0) + 1

    checkpoint_stats = {}
    for label in ("5m", "15m", "30m", "60m"):
        vals = []
        for r in records.values():
            cp = (r.get("checkpoints") or {}).get(label) if isinstance(r, dict) else None
            if isinstance(cp, dict) and cp.get("return_since_delay_pct") is not None:
                vals.append(_f(cp.get("return_since_delay_pct")))
        if vals:
            checkpoint_stats[label] = {
                "n": len(vals),
                "avg_return_pct": round(sum(vals) / len(vals), 4),
                "positive_pct": round(sum(v > 0 for v in vals) / len(vals) * 100, 2),
                "continued_10pct_plus_pct": round(sum(v >= 10 for v in vals) / len(vals) * 100, 2),
            }

    ledger["updated_at"] = now
    ledger["policy"] = "SHADOW_ONLY: delayed candidates are observed at 5/15/30/60m; no production gate or historical entry is changed."
    _write(LEDGER, ledger)

    summary = {
        "updated_at": now,
        "method": "ANTI_CHASE_SHADOW_RETENTION_V1",
        "total_shadow_records": len(records),
        "currently_delayed": len(current_keys),
        "status_counts": counts,
        "checkpoint_stats": checkpoint_stats,
        "candidate_reentry_rule_under_test": "After >=5m, base gate still passes, liquidity retention >=90%, and same-pair pre-runup <=25%. Continued strength >=10% is tracked separately, not auto-promoted.",
        "production_change": False,
    }
    _write(SUMMARY, summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
