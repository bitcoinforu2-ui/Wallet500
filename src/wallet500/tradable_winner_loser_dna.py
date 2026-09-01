from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path("data")
OUT = DATA / "tradable-winner-loser-dna.json"
MIN_LIQUIDITY_USD = 50000.0


def _load(name, default):
    try:
        p = DATA / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() and p.stat().st_size else default
    except Exception:
        return default


def _f(v):
    try:
        return float(v)
    except Exception:
        return None


def _stats(rows, field):
    vals = [_f(r.get(field)) for r in rows]
    vals = [x for x in vals if x is not None]
    if not vals:
        return {"n": 0, "median": None}
    return {"n": len(vals), "median": round(median(vals), 6)}


def _first_checkpoint(rec, labels=("1h", "4h", "12h", "24h")):
    cp = rec.get("checkpoints") if isinstance(rec.get("checkpoints"), dict) else {}
    for label in labels:
        row = cp.get(label)
        if isinstance(row, dict) and _f(row.get("return_pct")) is not None:
            return label, row
    return None, None


def _entry_features(rec):
    hist = rec.get("history") if isinstance(rec.get("history"), list) else []
    first = hist[0] if hist else {}
    liq = _f(first.get("liquidity_usd"))
    vol = _f(first.get("volume_h1"))
    buys = _f(first.get("buys_h1")) or 0.0
    sells = _f(first.get("sells_h1")) or 0.0
    txns = buys + sells
    turnover = (vol / liq) if liq and vol is not None else None
    return {
        "entry_observed_liquidity_usd": liq,
        "entry_observed_volume_h1": vol,
        "entry_observed_txns_h1": txns,
        "entry_observed_turnover_h1": turnover,
    }


def run():
    now = datetime.now(timezone.utc).isoformat()
    tracker = _load("outcome-tracker.json", {})
    tokens = tracker.get("tokens") if isinstance(tracker, dict) else {}
    if not isinstance(tokens, dict):
        tokens = {}

    rows = []
    excluded = Counter()
    for key, rec in tokens.items():
        if not isinstance(rec, dict):
            continue
        if rec.get("measurement_status") != "VERIFIED_EXACT_PAIR":
            excluded["NOT_CURRENTLY_VERIFIED_EXACT_PAIR"] += 1
            continue
        if rec.get("pair_identity_status") != "LOCKED" or not rec.get("entry_pair_address"):
            excluded["PAIR_NOT_IMMUTABLY_LOCKED"] += 1
            continue

        hist = rec.get("history") if isinstance(rec.get("history"), list) else []
        last = hist[-1] if hist else {}
        current_liq = _f(last.get("liquidity_usd"))
        if current_liq is None:
            excluded["NO_CURRENT_LIQUIDITY"] += 1
            continue
        if current_liq < MIN_LIQUIDITY_USD:
            excluded["CURRENT_LIQUIDITY_LT_50K"] += 1
            continue

        horizon, cp = _first_checkpoint(rec)
        if not cp:
            excluded["NO_FIXED_HORIZON_CHECKPOINT"] += 1
            continue
        ret = _f(cp.get("return_pct"))
        if ret is None:
            excluded["NO_FIXED_HORIZON_RETURN"] += 1
            continue

        entry = _entry_features(rec)
        status = "TRADABLE_WINNER" if ret > 0 else "TRADABLE_LOSER" if ret < 0 else "TRADABLE_FLAT"
        rows.append({
            "key": key,
            "chain": rec.get("chain"),
            "token": rec.get("token"),
            "pair_address": rec.get("entry_pair_address"),
            "horizon": horizon,
            "return_pct": ret,
            "status": status,
            "current_liquidity_usd": current_liq,
            **entry,
        })

    winners = [r for r in rows if r["status"] == "TRADABLE_WINNER"]
    losers = [r for r in rows if r["status"] == "TRADABLE_LOSER"]
    flats = [r for r in rows if r["status"] == "TRADABLE_FLAT"]

    fields = (
        "entry_observed_liquidity_usd",
        "entry_observed_volume_h1",
        "entry_observed_txns_h1",
        "entry_observed_turnover_h1",
        "current_liquidity_usd",
        "return_pct",
    )

    def block(group):
        return {f: _stats(group, f) for f in fields}

    result = {
        "version": 1,
        "generated_at": now,
        "production_change": False,
        "method": "VERIFIED_TRADABLE_FIXED_HORIZON_WINNER_LOSER_DNA_V1",
        "hard_rules": {
            "exact_pair_required": True,
            "immutable_pair_lock_required": True,
            "current_liquidity_min_usd": MIN_LIQUIDITY_USD,
            "fixed_horizon_only": ["1h", "4h", "12h", "24h"],
            "lifetime_peak_not_used_for_classification": True,
        },
        "warning": "Research only. This report does not prove predictive edge and must not change production gates without prospective validation.",
        "eligible_count": len(rows),
        "winner_count": len(winners),
        "loser_count": len(losers),
        "flat_count": len(flats),
        "excluded_counts": dict(excluded),
        "winner_medians": block(winners),
        "loser_medians": block(losers),
        "flat_medians": block(flats),
        "chain_counts": dict(Counter(str(r.get("chain") or "unknown") for r in rows)),
        "horizon_counts": dict(Counter(r["horizon"] for r in rows)),
        "rows": rows,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "eligible_count": result["eligible_count"],
        "winner_count": result["winner_count"],
        "loser_count": result["loser_count"],
        "flat_count": result["flat_count"],
        "excluded_counts": result["excluded_counts"],
    }, indent=2))
    return result


if __name__ == "__main__":
    run()
