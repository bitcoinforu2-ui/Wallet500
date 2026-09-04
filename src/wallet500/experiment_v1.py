from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path("data")
LEDGER = DATA / "experiment-v1-ledger.json"
SCOREBOARD = DATA / "experiment-v1-scoreboard.json"
REPORT = DATA / "experiment-v1-report.md"
LIQ_FLOOR = 50_000.0
EXPERIMENTS = ("FIVE_MINUTE_FINGERPRINT", "SURVIVOR_FIRST", "SOURCE_TOURNAMENT")
IMMUTABLE_FIELDS = ("chain", "token", "pair_address", "source", "entry_at", "entry_price_usd", "entry_liquidity_usd")


def load(name: str, default=None):
    p = DATA / name
    if not p.exists() or p.stat().st_size == 0:
        return {} if default is None else default
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {} if default is None else default


def f(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def token_key(chain, token, pair=None):
    return ":".join([str(chain or "").lower(), str(token or "").lower(), str(pair or "").lower()])


def return_pct(entry, current):
    e, c = f(entry), f(current)
    return round((c / e - 1.0) * 100.0, 6) if e > 0 and c > 0 else None


def percentile(values, p):
    xs = sorted(f(x) for x in values)
    if not xs:
        return None
    if len(xs) == 1:
        return round(xs[0], 6)
    pos = (len(xs) - 1) * p
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi:
        return round(xs[lo], 6)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo), 6)


def summarize(rows):
    rs = [f(r.get("return_pct")) for r in rows if r.get("return_pct") is not None]
    verified = [r for r in rows if r.get("verified_tradable") is True]
    survivors_1h = [r for r in rows if r.get("checkpoint_1h", {}).get("survived") is True]
    survivors_6h = [r for r in rows if r.get("checkpoint_6h", {}).get("survived") is True]
    observed_1h = [r for r in rows if r.get("checkpoint_1h")]
    observed_6h = [r for r in rows if r.get("checkpoint_6h")]
    failed = [r for r in rows if r.get("failed_survival") is True]
    max_dd = [f(r.get("max_drawdown_pct")) for r in rows if r.get("max_drawdown_pct") is not None]
    return {
        "n": len(rows),
        "survival_1h_pct": round(100 * len(survivors_1h) / len(observed_1h), 2) if observed_1h else None,
        "survival_1h_observed_n": len(observed_1h),
        "survival_6h_pct": round(100 * len(survivors_6h) / len(observed_6h), 2) if observed_6h else None,
        "survival_6h_observed_n": len(observed_6h),
        "failed_survival_pct": round(100 * len(failed) / len(rows), 2) if rows else None,
        "median_roi_pct": round(median(rs), 6) if rs else None,
        "p25_roi_pct": percentile(rs, .25),
        "max_drawdown_pct": round(min(max_dd), 6) if max_dd else None,
        "verified_tradable_pct": round(100 * len(verified) / len(rows), 2) if rows else None,
    }


def history_features(o):
    hist = list(o.get("history") or [])
    if not hist:
        return {}
    t0 = parse_ts(o.get("discovered_at") or o.get("discovery_at") or o.get("entry_at"))
    first5 = []
    timestamp_verified = bool(t0)
    if t0:
        for h in hist:
            ht = parse_ts(h.get("at") or h.get("timestamp") or h.get("marked_at"))
            if not ht:
                continue
            age = (ht - t0).total_seconds() / 60.0
            if 0 <= age <= 5.25:
                first5.append(h)
    if not first5:
        first5 = hist[: min(3, len(hist))]
        timestamp_verified = False
    first, last = first5[0], first5[-1]
    p0 = f(first.get("price_usd") or first.get("price"))
    p1 = f(last.get("price_usd") or last.get("price"))
    l0 = f(first.get("liquidity_usd") or first.get("liquidity"))
    l1 = f(last.get("liquidity_usd") or last.get("liquidity"))
    buys = f(last.get("buys_h1") or last.get("buys"))
    sells = f(last.get("sells_h1") or last.get("sells"))
    vol = f(last.get("volume_h1") or last.get("volume_usd"))
    return {
        "marks_5m": len(first5),
        "provenance": "TIMESTAMP_VERIFIED_5M" if timestamp_verified else "FALLBACK_UNVERIFIED",
        "price_change_5m_pct": return_pct(p0, p1),
        "liquidity_change_5m_pct": return_pct(l0, l1),
        "liquidity_5m_usd": round(l1, 2) if l1 else None,
        "volume_h1_at_5m": round(vol, 2) if vol else None,
        "buy_sell_ratio_at_5m": round(buys / max(1.0, sells), 6),
    }


def classify_survival(row):
    entry_liq = f(row.get("entry_liquidity_usd"))
    current_liq = f(row.get("current_liquidity_usd"))
    retention = current_liq / entry_liq if entry_liq > 0 and current_liq > 0 else None
    return {
        "liquidity_retention": round(retention, 6) if retention is not None else None,
        "survivor_first_pass": bool(entry_liq >= LIQ_FLOOR and retention is not None and retention >= .90),
        "verified_tradable": bool(entry_liq >= LIQ_FLOOR and current_liq >= LIQ_FLOOR),
        "failed_survival": bool(entry_liq >= LIQ_FLOOR and current_liq > 0 and current_liq < LIQ_FLOOR),
    }


def merge_immutable(prev, row):
    rec = dict(prev)
    conflicts = list(prev.get("immutability_conflicts") or [])
    for k, v in row.items():
        if k in IMMUTABLE_FIELDS and k in prev and prev.get(k) not in (None, "") and v not in (None, "") and prev.get(k) != v:
            conflicts.append({"field": k, "original": prev.get(k), "observed": v})
            continue
        if k not in IMMUTABLE_FIELDS or k not in prev or prev.get(k) in (None, ""):
            rec[k] = v
    if conflicts:
        rec["immutability_conflicts"] = conflicts[-50:]
    return rec


def checkpoint_once(rec, label, age, row, now):
    key = f"checkpoint_{label}"
    threshold = 1.0 if label == "1h" else 6.0
    if rec.get(key) or age is None or age < threshold:
        return
    liq = f(row.get("current_liquidity_usd"))
    rec[key] = {
        "observed_at": now.isoformat(),
        "age_hours": round(age, 6),
        "liquidity_usd": liq if liq > 0 else None,
        "survived": bool(liq >= LIQ_FLOOR),
    }


def build_rows():
    outcomes = load("outcome-tracker.json")
    perf = load("realizable-performance.json")
    first = load("first-eligible-paper-ledger.json")
    external = load("external-only-paper-ledger.json")
    marks = {}
    for r in (perf.get("paper_live_rows") or []) + (perf.get("paper_failed_rows") or []):
        marks[token_key(r.get("chain"), r.get("token"), r.get("pair_address"))] = r
    rows, seen = [], set()
    for source, entries in [("NATIVE_FIRST_ELIGIBLE", first.get("entries") or []), ("EXTERNAL_ONLY", external.get("entries") or [])]:
        for e0 in entries:
            e = dict(e0)
            key = token_key(e.get("chain"), e.get("token"), e.get("pair_address"))
            if not key.strip(":") or key in seen:
                continue
            seen.add(key)
            fresh = marks.get(key, {})
            current_px = f(fresh.get("current_price_usd"), f(e.get("current_price_usd")))
            entry_px = f(e.get("entry_price_usd"))
            entry_liq = f(e.get("entry_liquidity_usd"))
            current_liq = f(fresh.get("current_liquidity_usd"), f(e.get("current_liquidity_usd")))
            row = {"key": key, "chain": e.get("chain"), "token": e.get("token"), "pair_address": e.get("pair_address"), "source": source,
                   "entry_at": e.get("entry_at"), "entry_price_usd": entry_px, "current_price_usd": current_px or None,
                   "entry_liquidity_usd": entry_liq, "current_liquidity_usd": current_liq or None,
                   "return_pct": return_pct(entry_px, current_px), "max_drawdown_pct": fresh.get("max_drawdown_pct") or e.get("max_drawdown_pct"),
                   "status": fresh.get("status") or e.get("status") or "UNKNOWN", "last_mark_at": fresh.get("last_mark_at") or e.get("last_mark_at")}
            row.update(classify_survival(row))
            simple = f"{str(e.get('chain') or '').lower()}:{str(e.get('token') or '').lower()}"
            ot = (outcomes.get("tokens") or {}).get(simple)
            if ot:
                row["five_minute"] = history_features(ot)
            rows.append(row)
    return rows


def age_hours(row, now):
    t = parse_ts(row.get("entry_at"))
    return (now - t).total_seconds() / 3600 if t else None


def main():
    now = datetime.now(timezone.utc)
    rows = build_rows()
    old = load("experiment-v1-ledger.json", {"records": []})
    old_by_key = {r.get("key"): r for r in old.get("records") or [] if r.get("key")}
    records = []
    for row in rows:
        prev = old_by_key.get(row["key"], {})
        rec = merge_immutable(prev, row)
        rec["first_seen_experiment_at"] = prev.get("first_seen_experiment_at") or now.isoformat()
        rec["last_observed_at"] = now.isoformat()
        age = age_hours(rec, now)
        checkpoint_once(rec, "1h", age, row, now)
        checkpoint_once(rec, "6h", age, row, now)
        records.append(rec)

    experiment_rows = {
        "FIVE_MINUTE_FINGERPRINT": [r for r in records if (r.get("five_minute") or {}).get("provenance") == "TIMESTAMP_VERIFIED_5M" and (r.get("five_minute") or {}).get("marks_5m", 0) > 0],
        "SURVIVOR_FIRST": [r for r in records if r.get("survivor_first_pass") is True],
        "SOURCE_TOURNAMENT": records,
    }
    source_groups = defaultdict(list)
    for r in records:
        source_groups[r.get("source") or "UNKNOWN"].append(r)
    scoreboard = []
    for name in EXPERIMENTS:
        z = summarize(experiment_rows[name]); z["experiment"] = name; z["status"] = "COLLECTING" if z["n"] < 30 else "ANALYZABLE"; scoreboard.append(z)
    sources = []
    for source, xs in sorted(source_groups.items()):
        z = summarize(xs); z["source"] = source; sources.append(z)
    ledger = {"generated_at": now.isoformat(), "method": "PROSPECTIVE_EXPERIMENT_V1", "production_change": False, "liquidity_floor_usd": LIQ_FLOOR,
              "immutability_rule": "chain/token/pair/source/entry time/entry price/entry liquidity are immutable after first observation; conflicts are retained for audit",
              "checkpoint_rule": "1h/6h checkpoints are first observation at or after threshold and are never rewritten", "records": records}
    board = {"generated_at": now.isoformat(), "method": "PROSPECTIVE_EXPERIMENT_V1", "production_change": False, "minimum_analyzable_n": 30,
             "experiments": scoreboard, "source_tournament": sources,
             "decision_rule": "No production gate changes from this report alone; require prospective sample and repeatable advantage over baseline/control."}
    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
    SCOREBOARD.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n")
    REPORT.write_text("# Wallet500 Experiment V1\n\nProspective research only — production policy unchanged.\n")
    print(json.dumps(board, indent=2))


if __name__ == "__main__":
    main()
