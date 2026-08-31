from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path("data")
OUT = DATA / "winner-dna-study.json"
LIQ_FLOOR = 50_000.0
CONTROL_MULTIPLIER = 2
FIXED_HORIZON = "24h"
WINNER_MIN_RETURN_PCT = 25.0
CONTROL_MAX_RETURN_PCT = 5.0
MIN_GROUP_N = 20


def load(name, default=None):
    p = DATA / name
    if not p.exists() or p.stat().st_size == 0:
        return {} if default is None else default
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def f(v, default=None):
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


def same(a, b):
    return bool(a) and bool(b) and str(a).lower() == str(b).lower()


def key(chain, token, pair):
    return ":".join((str(chain or "").lower(), str(token or "").lower(), str(pair or "").lower()))


def pre_outcome_features(token):
    hist = list(token.get("history") or [])
    if not hist:
        return None
    entry_pair = token.get("entry_pair_address")
    discovered = parse_ts(token.get("first_seen") or token.get("tracking_started_at"))
    verified = []
    for h in hist:
        if not isinstance(h, dict) or not same(h.get("pair_address"), entry_pair):
            continue
        observed = parse_ts(h.get("observed_at") or h.get("at") or h.get("timestamp"))
        if discovered and observed and observed < discovered:
            continue
        verified.append(h)
    if not verified:
        return None
    verified.sort(key=lambda h: parse_ts(h.get("observed_at") or h.get("at") or h.get("timestamp")) or datetime.max.replace(tzinfo=timezone.utc))
    h = verified[0]
    liq = f(h.get("liquidity_usd"), 0.0) or 0.0
    vol = f(h.get("volume_h1"), 0.0) or 0.0
    buys = f(h.get("buys_h1"), 0.0) or 0.0
    sells = f(h.get("sells_h1"), 0.0) or 0.0
    return {
        "snapshot_at": h.get("observed_at") or h.get("at") or h.get("timestamp"),
        "liquidity_usd": liq,
        "volume_h1": vol,
        "turnover_h1": round(vol / liq, 6) if liq > 0 else None,
        "buys_h1": int(buys),
        "sells_h1": int(sells),
        "buy_sell_ratio": round(buys / max(1.0, sells), 6),
        "txns_h1": int(buys + sells),
        "tradable_at_snapshot": liq >= LIQ_FLOOR,
        "exact_pair_verified": True,
    }


def fixed_horizon_return(token):
    cp = (token.get("checkpoints") or {}).get(FIXED_HORIZON)
    if not isinstance(cp, dict):
        return None
    if not same(cp.get("pair_address"), token.get("entry_pair_address")):
        return None
    return f(cp.get("return_pct"))


def distance(a, b):
    la, lb = max(f(a.get("liquidity_usd"), 1.0) or 1.0, 1.0), max(f(b.get("liquidity_usd"), 1.0) or 1.0, 1.0)
    va, vb = max(f(a.get("volume_h1"), 1.0) or 1.0, 1.0), max(f(b.get("volume_h1"), 1.0) or 1.0, 1.0)
    ta, tb = max(f(a.get("txns_h1"), 1.0) or 1.0, 1.0), max(f(b.get("txns_h1"), 1.0) or 1.0, 1.0)
    return abs(math.log(la / lb)) + abs(math.log(va / vb)) + .5 * abs(math.log(ta / tb))


def time_penalty(a, b):
    ta, tb = parse_ts(a.get("discovered_at")), parse_ts(b.get("discovered_at"))
    if not ta or not tb:
        return 2.0
    return min(abs((ta - tb).total_seconds()) / 86400.0, 30.0) / 30.0


def feature_summary(rows):
    out = {}
    for field in ("liquidity_usd", "volume_h1", "turnover_h1", "buy_sell_ratio", "txns_h1"):
        xs = [f(r["features"].get(field)) for r in rows if r.get("features", {}).get(field) is not None]
        xs = [x for x in xs if x is not None]
        out[field] = round(median(xs), 6) if xs else None
    return out


def build_candidate(o):
    pair = o.get("entry_pair_address")
    features = pre_outcome_features(o)
    horizon_return = fixed_horizon_return(o)
    if not pair or not features or horizon_return is None or not features.get("tradable_at_snapshot"):
        return None
    return {
        "key": key(o.get("chain"), o.get("token"), pair),
        "chain": str(o.get("chain") or "").lower(),
        "token": o.get("token"),
        "pair_address": pair,
        "discovered_at": o.get("first_seen") or o.get("tracking_started_at"),
        "features": features,
        "outcome": {"fixed_horizon": FIXED_HORIZON, "return_pct": horizon_return},
    }


def _feature_lifts(winners, controls):
    w = feature_summary(winners)
    c = feature_summary(controls)
    lifts = {}
    for field in w:
        a, b = w.get(field), c.get(field)
        lifts[field] = round(a / b, 6) if a is not None and b not in (None, 0) else None
    return w, c, lifts


def build_study(candidates: list[dict], chain: str | None = None) -> dict:
    eligible = [r for r in candidates if chain is None or r.get("chain") == chain]
    winners = [r for r in eligible if f((r.get("outcome") or {}).get("return_pct"), -1e99) >= WINNER_MIN_RETURN_PCT]
    controls_pool = [r for r in eligible if f((r.get("outcome") or {}).get("return_pct"), 1e99) <= CONTROL_MAX_RETURN_PCT]
    ambiguous = [r for r in eligible if r not in winners and r not in controls_pool]

    controls, used = [], set()
    for w in sorted(winners, key=lambda r: r["outcome"]["return_pct"], reverse=True):
        same_chain = [r for r in controls_pool if r.get("chain") == w.get("chain") and r["key"] not in used]
        ranked = sorted(same_chain, key=lambda r: distance(w["features"], r["features"]) + time_penalty(w, r))
        for c in ranked[:CONTROL_MULTIPLIER]:
            used.add(c["key"])
            controls.append(c)

    winner_medians, control_medians, lifts = _feature_lifts(winners, controls)
    status = "RESEARCH_READY" if len(winners) >= MIN_GROUP_N and len(controls) >= MIN_GROUP_N else "INSUFFICIENT_BALANCED_SAMPLE"
    return {
        "status": status,
        "chain": chain or "all",
        "label_rule": f"WINNER=24h return >= {WINNER_MIN_RETURN_PCT:.0f}%; CONTROL=24h return <= {CONTROL_MAX_RETURN_PCT:.0f}%; middle band excluded",
        "eligible_n": len(eligible),
        "winner_n": len(winners),
        "control_pool_n": len(controls_pool),
        "control_n": len(controls),
        "ambiguous_excluded_n": len(ambiguous),
        "minimum_group_n_for_research_ready": MIN_GROUP_N,
        "winner_feature_medians": winner_medians,
        "control_feature_medians": control_medians,
        "winner_to_control_median_ratio": lifts,
        "control_policy": "same chain; nearest pre-outcome liquidity/volume/txns plus discovery-time proximity; future return never enters matching distance",
        "winners": sorted(winners, key=lambda r: r["outcome"]["return_pct"], reverse=True)[:100],
        "controls": controls[:200],
    }


def main():
    outcomes = load("outcome-tracker.json")
    raw = [build_candidate(o) for o in (outcomes.get("tokens") or {}).values() if isinstance(o, dict)]
    candidates = [r for r in raw if r]
    overall = build_study(candidates)
    solana = build_study(candidates, "solana")
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "WINNER_DNA_SHADOW_V2",
        "production_change": False,
        "warning": "Historical label study only. Fixed exact-pair 24h outcomes and >=$50K earliest exact-pair snapshots are required. A study is blocked unless both winner and matched-control groups meet the minimum sample size. Prospective validation is still required.",
        "liquidity_floor_usd": LIQ_FLOOR,
        "winner_horizon": FIXED_HORIZON,
        "winner_min_return_pct": WINNER_MIN_RETURN_PCT,
        "control_max_return_pct": CONTROL_MAX_RETURN_PCT,
        "eligible_fixed_horizon_n": len(candidates),
        "status": overall["status"],
        "winner_n": overall["winner_n"],
        "control_n": overall["control_n"],
        "winner_feature_medians": overall["winner_feature_medians"],
        "control_feature_medians": overall["control_feature_medians"],
        "winner_to_control_median_ratio": overall["winner_to_control_median_ratio"],
        "overall_study": overall,
        "solana_study": solana,
        "next_step": "Use only RESEARCH_READY cohort differences as shadow context, then freeze rules and validate prospectively on unseen future discoveries.",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"method": result["method"], "eligible_fixed_horizon_n": len(candidates), "overall": {k: overall[k] for k in ("status", "winner_n", "control_n")}, "solana": {k: solana[k] for k in ("status", "winner_n", "control_n")}}, indent=2))


if __name__ == "__main__":
    main()
