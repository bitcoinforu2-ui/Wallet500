from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

DATA = Path("data")
OUT_JSON = DATA / "cohort-research.json"
OUT_MD = DATA / "cohort-research.md"


def load(name: str):
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else {}


def f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def i(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def pct(v):
    return round(f(v), 4)


def token_key(chain, token):
    return f"{str(chain or '').lower()}:{str(token or '').lower()}"


def summarize(rows):
    if not rows:
        return {"n": 0, "invested_usd": 0, "value_usd": 0, "pnl_usd": 0, "roi_pct": 0, "win_rate_pct": 0, "median_return_pct": 0}
    inv = sum(f(r.get("cost_usd"), 1.0) for r in rows)
    val = sum(f(r.get("current_value_usd"), f(r.get("cost_usd"), 1.0)) for r in rows)
    returns = [f(r.get("return_pct")) for r in rows]
    return {
        "n": len(rows),
        "invested_usd": round(inv, 6),
        "value_usd": round(val, 6),
        "pnl_usd": round(val - inv, 6),
        "roi_pct": round(((val / inv) - 1) * 100, 4) if inv else 0,
        "win_rate_pct": round(sum(x > 0 for x in returns) / len(returns) * 100, 2),
        "median_return_pct": round(median(returns), 4),
    }


def feature_stats(rows):
    def stats(field):
        vals = [f(r.get(field)) for r in rows if r.get(field) is not None]
        return {"mean": round(mean(vals), 4), "median": round(median(vals), 4)} if vals else None
    return {
        "entry_liquidity_usd": stats("entry_liquidity_usd"),
        "entry_volume_h1": stats("entry_volume_h1"),
        "entry_txns_h1": stats("entry_txns_h1"),
        "turnover_h1": stats("turnover_h1"),
        "pre_entry_runup_pct": stats("pre_entry_runup_pct"),
    }


def bucket(rows, label, predicate):
    x = [r for r in rows if predicate(r)]
    z = summarize(x)
    z["bucket"] = label
    return z


def counterfactual(name, rows, predicate):
    x = [r for r in rows if predicate(r)]
    z = summarize(x)
    z["rule"] = name
    z["removed"] = len(rows) - len(x)
    return z


def main():
    paper = load("first-eligible-paper-ledger.json")
    perf = load("realizable-performance.json")
    outcomes = load("outcome-tracker.json")

    entries = list(paper.get("entries") or [])
    by_key = {}
    for r in (perf.get("paper_live_rows") or []) + (perf.get("paper_failed_rows") or []):
        by_key[str(r.get("key") or "").lower()] = r

    outcome_tokens = outcomes.get("tokens") or {}
    enriched = []
    for e0 in entries:
        e = dict(e0)
        fresh = by_key.get(str(e.get("key") or "").lower())
        if fresh:
            for k in ("current_price_usd", "current_liquidity_usd", "current_value_usd", "return_pct", "status", "valuation_status", "last_mark_at"):
                if fresh.get(k) is not None:
                    e[k] = fresh[k]
        liq = f(e.get("entry_liquidity_usd"))
        vol = f(e.get("entry_volume_h1"))
        e["turnover_h1"] = round(vol / liq, 6) if liq else None
        ok = outcome_tokens.get(token_key(e.get("chain"), e.get("token")))
        if ok:
            discovery_px = f(ok.get("entry_price_usd"))
            same_pair = str(ok.get("entry_pair_address") or "").lower() == str(e.get("pair_address") or "").lower()
            if discovery_px > 0 and same_pair:
                e["discovery_price_usd"] = discovery_px
                e["pre_entry_runup_pct"] = round((f(e.get("entry_price_usd")) / discovery_px - 1) * 100, 4)
            e["discovery_peak_return_pct"] = ok.get("peak_return_pct")
            e["discovery_current_return_pct"] = ok.get("current_return_pct")
        enriched.append(e)

    baseline = summarize(enriched)
    winners = [r for r in enriched if f(r.get("return_pct")) > 0]
    losers = [r for r in enriched if f(r.get("return_pct")) < 0]
    severe = [r for r in enriched if f(r.get("return_pct")) <= -20]

    rules = [
        ("baseline", lambda r: True),
        ("liq>=75k", lambda r: f(r.get("entry_liquidity_usd")) >= 75000),
        ("liq>=100k", lambda r: f(r.get("entry_liquidity_usd")) >= 100000),
        ("liq>=250k", lambda r: f(r.get("entry_liquidity_usd")) >= 250000),
        ("liq>=500k", lambda r: f(r.get("entry_liquidity_usd")) >= 500000),
        ("vol>=25k", lambda r: f(r.get("entry_volume_h1")) >= 25000),
        ("vol>=50k", lambda r: f(r.get("entry_volume_h1")) >= 50000),
        ("vol>=100k", lambda r: f(r.get("entry_volume_h1")) >= 100000),
        ("tx>=100", lambda r: i(r.get("entry_txns_h1")) >= 100),
        ("tx>=250", lambda r: i(r.get("entry_txns_h1")) >= 250),
        ("tx>=500", lambda r: i(r.get("entry_txns_h1")) >= 500),
        ("turnover>=0.25", lambda r: f(r.get("turnover_h1")) >= .25),
        ("turnover>=0.5", lambda r: f(r.get("turnover_h1")) >= .5),
        ("turnover>=1", lambda r: f(r.get("turnover_h1")) >= 1),
        ("turnover<=1", lambda r: f(r.get("turnover_h1")) <= 1),
        ("turnover<=2", lambda r: f(r.get("turnover_h1")) <= 2),
        ("pre-runup<=10%", lambda r: r.get("pre_entry_runup_pct") is not None and f(r.get("pre_entry_runup_pct")) <= 10),
        ("pre-runup<=25%", lambda r: r.get("pre_entry_runup_pct") is not None and f(r.get("pre_entry_runup_pct")) <= 25),
        ("pre-runup<=50%", lambda r: r.get("pre_entry_runup_pct") is not None and f(r.get("pre_entry_runup_pct")) <= 50),
        ("pre-runup<=100%", lambda r: r.get("pre_entry_runup_pct") is not None and f(r.get("pre_entry_runup_pct")) <= 100),
        ("liq>=100k & vol>=50k", lambda r: f(r.get("entry_liquidity_usd")) >= 100000 and f(r.get("entry_volume_h1")) >= 50000),
        ("liq>=100k & tx>=250", lambda r: f(r.get("entry_liquidity_usd")) >= 100000 and i(r.get("entry_txns_h1")) >= 250),
        ("liq>=250k & vol>=100k", lambda r: f(r.get("entry_liquidity_usd")) >= 250000 and f(r.get("entry_volume_h1")) >= 100000),
    ]
    cfs = [counterfactual(n, enriched, p) for n, p in rules]
    for z in cfs:
        z["roi_delta_vs_baseline_pp"] = round(z["roi_pct"] - baseline["roi_pct"], 4)
    ranked = sorted([z for z in cfs if z["n"] >= 5 and z["rule"] != "baseline"], key=lambda z: (z["roi_pct"], z["n"]), reverse=True)

    chain_groups = []
    for chain in sorted({str(r.get("chain") or "unknown") for r in enriched}):
        z = summarize([r for r in enriched if str(r.get("chain") or "unknown") == chain]); z["chain"] = chain; chain_groups.append(z)

    liq_buckets = [
        bucket(enriched, "50-75k", lambda r: 50000 <= f(r.get("entry_liquidity_usd")) < 75000),
        bucket(enriched, "75-100k", lambda r: 75000 <= f(r.get("entry_liquidity_usd")) < 100000),
        bucket(enriched, "100-250k", lambda r: 100000 <= f(r.get("entry_liquidity_usd")) < 250000),
        bucket(enriched, "250-500k", lambda r: 250000 <= f(r.get("entry_liquidity_usd")) < 500000),
        bucket(enriched, ">=500k", lambda r: f(r.get("entry_liquidity_usd")) >= 500000),
    ]
    turnover_buckets = [
        bucket(enriched, "<0.25", lambda r: f(r.get("turnover_h1")) < .25),
        bucket(enriched, "0.25-0.5", lambda r: .25 <= f(r.get("turnover_h1")) < .5),
        bucket(enriched, "0.5-1", lambda r: .5 <= f(r.get("turnover_h1")) < 1),
        bucket(enriched, "1-2", lambda r: 1 <= f(r.get("turnover_h1")) < 2),
        bucket(enriched, ">=2", lambda r: f(r.get("turnover_h1")) >= 2),
    ]

    paper_tokens = {token_key(r.get("chain"), r.get("token")) for r in enriched}
    missed = []
    gate_counts = Counter()
    for tk, o in outcome_tokens.items():
        if tk.lower() in paper_tokens:
            continue
        cur = f(o.get("current_return_pct"), -999999)
        peak = f(o.get("peak_return_pct"), -999999)
        if cur < 10 and peak < 25:
            continue
        hist = o.get("history") or []
        last = hist[-1] if hist else {}
        liq = f(last.get("liquidity_usd"))
        vol = f(last.get("volume_h1"))
        tx = i(last.get("buys_h1")) + i(last.get("sells_h1"))
        gates = []
        if liq < 50000: gates.append("LIQ_LT_50K")
        if vol < 15000: gates.append("VOL_LT_15K")
        if tx < 50: gates.append("TX_LT_50")
        if not hist: gates.append("NO_LATEST_MARK")
        if not gates: gates.append("BASE_GATE_NOW_PASS_OTHER_OR_TIMING")
        gate_counts.update(gates)
        missed.append({
            "chain": o.get("chain"), "token": o.get("token"), "pair_address": o.get("entry_pair_address"),
            "current_return_pct": round(cur, 4), "peak_return_pct": round(peak, 4), "low_return_pct": round(f(o.get("low_return_pct")), 4),
            "latest_liquidity_usd": round(liq, 2), "latest_volume_h1": round(vol, 2), "latest_txns_h1": tx,
            "latest_buy_sell_ratio": round(i(last.get("buys_h1")) / max(1, i(last.get("sells_h1"))), 4),
            "why_not_base_gate_now": gates,
        })
    missed_current = sorted(missed, key=lambda r: r["current_return_pct"], reverse=True)[:25]
    missed_peak = sorted(missed, key=lambda r: r["peak_return_pct"], reverse=True)[:25]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_at": perf.get("updated_at"),
        "method": "FORWARD_COHORT_COUNTERFACTUAL_AUDIT_V1",
        "warning": "Research only. Small sample and post-hoc rule search can overfit. No production gate is changed by this report.",
        "baseline": baseline,
        "status_counts": dict(Counter(str(r.get("status") or "UNKNOWN") for r in enriched)),
        "winner_feature_stats": feature_stats(winners),
        "loser_feature_stats": feature_stats(losers),
        "severe_loser_feature_stats": feature_stats(severe),
        "chain_performance": chain_groups,
        "liquidity_buckets": liq_buckets,
        "turnover_buckets": turnover_buckets,
        "counterfactuals": cfs,
        "best_counterfactuals_min5": ranked[:10],
        "paper_rows": enriched,
        "missed_star_count": len(missed),
        "missed_star_gate_counts": dict(gate_counts),
        "top_missed_by_current_return": missed_current,
        "top_missed_by_peak_return": missed_peak,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    md = ["# Wallet500 Cohort Research", "", f"Generated: {result['generated_at']}", f"Source snapshot: {result['source_snapshot_at']}", "", "## Baseline", f"- N={baseline['n']} ROI={baseline['roi_pct']}% P/L=${baseline['pnl_usd']}", "", "## Best post-hoc counterfactuals (min 5 retained)"]
    for z in ranked[:10]:
        md.append(f"- {z['rule']}: N={z['n']} ROI={z['roi_pct']}% delta={z['roi_delta_vs_baseline_pp']}pp")
    md += ["", "## Missed-star scan", f"- Candidates: {len(missed)}", f"- Gate reasons now: {dict(gate_counts)}", "", "Research only; validate prospectively before changing production gates."]
    OUT_MD.write_text("\n".join(md) + "\n")
    print(json.dumps({"baseline": baseline, "best": ranked[:5], "missed": len(missed), "gate_counts": dict(gate_counts)}, indent=2))


if __name__ == "__main__":
    main()
