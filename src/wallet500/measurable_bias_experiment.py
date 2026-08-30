from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path("data")
OUT = DATA / "measurable-vs-rest-experiment.json"
REPORT = DATA / "measurable-vs-rest-experiment.md"


def load(name, default=None):
    p = DATA / name
    if not p.exists() or p.stat().st_size == 0:
        return {} if default is None else default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def f(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def pct(n, d):
    return round(100.0 * n / d, 2) if d else None


def earliest_features(rec):
    hist = rec.get("history") if isinstance(rec.get("history"), list) else []
    if not hist:
        return None
    h = hist[0]
    liq = f(h.get("liquidity_usd"))
    vol = f(h.get("volume_h1"))
    buys = f(h.get("buys_h1"), 0.0) or 0.0
    sells = f(h.get("sells_h1"), 0.0) or 0.0
    return {
        "observed_at": h.get("observed_at"),
        "liquidity_usd": liq,
        "volume_h1": vol,
        "turnover_h1": round(vol / liq, 6) if liq and vol is not None else None,
        "buys_h1": buys,
        "sells_h1": sells,
        "buy_sell_ratio": round(buys / max(1.0, sells), 6),
        "txns_h1": buys + sells,
    }


def med(rows, field):
    xs = [f((r.get("features") or {}).get(field)) for r in rows]
    xs = [x for x in xs if x is not None]
    return round(median(xs), 6) if xs else None


def technical_summary(rows):
    n = len(rows)
    locked = sum(1 for r in rows if r.get("pair_identity_status") == "LOCKED")
    with_history = sum(1 for r in rows if r.get("features") is not None)
    with_current_pair = sum(1 for r in rows if r.get("current_pair_address"))
    chains = Counter(str(r.get("chain") or "UNKNOWN").lower() for r in rows)
    statuses = Counter(str(r.get("measurement_status") or "UNKNOWN") for r in rows)
    return {
        "n": n,
        "pair_locked_n": locked,
        "pair_locked_pct": pct(locked, n),
        "earliest_snapshot_available_n": with_history,
        "earliest_snapshot_available_pct": pct(with_history, n),
        "current_pair_available_n": with_current_pair,
        "current_pair_available_pct": pct(with_current_pair, n),
        "chains": dict(chains),
        "measurement_statuses": dict(statuses),
    }


def market_summary(rows):
    z = [r for r in rows if r.get("features") is not None]
    return {
        "comparable_n": len(z),
        "liquidity_usd_median": med(z, "liquidity_usd"),
        "volume_h1_median": med(z, "volume_h1"),
        "turnover_h1_median": med(z, "turnover_h1"),
        "buy_sell_ratio_median": med(z, "buy_sell_ratio"),
        "txns_h1_median": med(z, "txns_h1"),
    }


def ratio(a, b):
    a, b = f(a), f(b)
    return round(a / b, 6) if a is not None and b not in (None, 0) else None


def main():
    tracker = load("outcome-tracker.json")
    records = tracker.get("tokens") if isinstance(tracker.get("tokens"), dict) else {}
    rows = []
    for token_key, rec0 in records.items():
        if not isinstance(rec0, dict):
            continue
        rec = dict(rec0)
        measured = rec.get("measurement_status") == "VERIFIED_EXACT_PAIR" and rec.get("current_return_pct") is not None
        rows.append({
            "key": token_key,
            "chain": rec.get("chain"),
            "token": rec.get("token"),
            "entry_pair_address": rec.get("entry_pair_address"),
            "current_pair_address": rec.get("current_pair_address"),
            "pair_identity_status": rec.get("pair_identity_status"),
            "measurement_status": rec.get("measurement_status"),
            "first_seen": rec.get("first_seen"),
            "tracking_started_at": rec.get("tracking_started_at"),
            "measured_now": measured,
            "features": earliest_features(rec),
        })

    measured = [r for r in rows if r["measured_now"]]
    rest = [r for r in rows if not r["measured_now"]]
    tm, tr = technical_summary(measured), technical_summary(rest)
    mm, mr = market_summary(measured), market_summary(rest)

    feature_ratios = {
        "liquidity_median_ratio_measured_to_rest": ratio(mm["liquidity_usd_median"], mr["liquidity_usd_median"]),
        "volume_median_ratio_measured_to_rest": ratio(mm["volume_h1_median"], mr["volume_h1_median"]),
        "turnover_median_ratio_measured_to_rest": ratio(mm["turnover_h1_median"], mr["turnover_h1_median"]),
        "buy_sell_ratio_median_ratio_measured_to_rest": ratio(mm["buy_sell_ratio_median"], mr["buy_sell_ratio_median"]),
        "txns_median_ratio_measured_to_rest": ratio(mm["txns_h1_median"], mr["txns_h1_median"]),
    }

    coverage_gap = None
    if tm["earliest_snapshot_available_pct"] is not None and tr["earliest_snapshot_available_pct"] is not None:
        coverage_gap = round(tm["earliest_snapshot_available_pct"] - tr["earliest_snapshot_available_pct"], 2)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "MEASURABLE_VS_REST_BIAS_EXPERIMENT_V1",
        "production_change": False,
        "truth_rule": "Do not interpret measurability as alpha until technical/data-coverage bias is separated from market-feature differences.",
        "tracked_total": len(rows),
        "measured_now_n": len(measured),
        "rest_n": len(rest),
        "technical_layer": {"measured": tm, "rest": tr, "snapshot_coverage_gap_pp": coverage_gap},
        "market_layer_earliest_snapshot_only": {"measured": mm, "rest": mr, "measured_to_rest_ratios": feature_ratios},
        "interpretation_guard": "Market medians use only each token's earliest stored historical observation. Missing-history tokens are excluded from market-feature comparison and remain counted in coverage diagnostics.",
        "status": "ANALYZABLE" if len(measured) >= 100 and len(rest) >= 100 else "COLLECTING",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Wallet500 — Measurable vs Rest Experiment",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "Research only. Production policy unchanged.",
        "",
        f"Measured now: {len(measured)} / {len(rows)}",
        f"Rest: {len(rest)} / {len(rows)}",
        "",
        "## Technical/data coverage",
        f"- Pair locked: measured {tm['pair_locked_pct']}% vs rest {tr['pair_locked_pct']}%",
        f"- Earliest snapshot available: measured {tm['earliest_snapshot_available_pct']}% vs rest {tr['earliest_snapshot_available_pct']}%",
        f"- Snapshot coverage gap: {coverage_gap} percentage points",
        "",
        "## Earliest-snapshot market comparison",
        f"- Comparable N: measured {mm['comparable_n']} vs rest {mr['comparable_n']}",
        f"- Median liquidity: {mm['liquidity_usd_median']} vs {mr['liquidity_usd_median']}",
        f"- Median H1 volume: {mm['volume_h1_median']} vs {mr['volume_h1_median']}",
        f"- Median turnover: {mm['turnover_h1_median']} vs {mr['turnover_h1_median']}",
        f"- Median buy/sell ratio: {mm['buy_sell_ratio_median']} vs {mr['buy_sell_ratio_median']}",
        f"- Median H1 transactions: {mm['txns_h1_median']} vs {mr['txns_h1_median']}",
        "",
        "Do not promote any difference into a production gate until the coverage bias is understood and the candidate signal is prospectively validated.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
