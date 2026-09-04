from __future__ import annotations

import json
import math
import statistics
import subprocess
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
WINNER_STUDY = DATA / "winner-separator-study.json"
SURVIVOR = DATA / "survivor-wave-watch.json"
OUT = DATA / "veteran-prehigh-backtest.json"
MIN_AGE_DAYS = 180.0
LIQ_FLOOR = 50_000.0
MAX_LEAD_HOURS = 6.0


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def f(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def norm(v):
    return str(v or "").lower()


def parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def http_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def exact_pair_meta(chain: str, pair: str):
    chain_id = {"bsc": "bsc", "solana": "solana", "ethereum": "ethereum"}.get(norm(chain), norm(chain))
    try:
        d = http_json(f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pair}")
        rows = d.get("pairs") or []
        row = next((x for x in rows if norm(x.get("pairAddress")) == norm(pair)), None)
        if not row:
            return None, "PAIR_NOT_RETURNED"
        created_ms = f(row.get("pairCreatedAt"))
        created = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc) if created_ms else None
        return {
            "pair_created_at": iso(created),
            "dex": row.get("dexId"),
            "url": row.get("url"),
        }, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def git_snapshots():
    try:
        raw = subprocess.check_output(
            ["git", "log", "--format=%H", "--reverse", "--", str(SURVIVOR)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []

    by_generated = {}
    for sha in [x.strip() for x in raw.splitlines() if x.strip()]:
        try:
            txt = subprocess.check_output(
                ["git", "show", f"{sha}:{SURVIVOR}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            d = json.loads(txt)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        ts = parse_ts(d.get("generated_at"))
        if not ts:
            continue
        d["_commit_sha"] = sha
        by_generated[iso(ts)] = d
    return [by_generated[k] for k in sorted(by_generated)]


def age_days(created_at, observed_at):
    created = parse_ts(created_at)
    observed = parse_ts(observed_at) if not isinstance(observed_at, datetime) else observed_at
    if not created or not observed:
        return None
    return (observed - created).total_seconds() / 86400.0


def high_dna(row):
    turnover = f(row.get("turnover_h1"))
    ratio = f(row.get("buy_sell_ratio_h1"))
    return bool(turnover is not None and ratio is not None and turnover >= 0.75 and ratio >= 1.25)


def threshold_grid():
    for turnover in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60):
        for ratio in (1.25, 1.35, 1.40, 1.50):
            for liq_retention in (0.90, 0.95, 1.00):
                yield turnover, ratio, liq_retention


def qualifies_pre_high(point, turnover_min, ratio_min, liq_retention_min):
    turnover = f(point.get("turnover_h1"))
    ratio = f(point.get("buy_sell_ratio_h1"))
    retention = f(point.get("liquidity_retention_vs_previous"))
    liq = f(point.get("liquidity_usd"), 0.0) or 0.0
    if turnover is None or ratio is None or retention is None:
        return False
    return (
        liq >= LIQ_FLOOR
        and turnover_min <= turnover < 0.75
        and ratio >= ratio_min
        and retention >= liq_retention_min
    )


def median_or_none(values):
    vals = [float(x) for x in values if x is not None]
    return round(statistics.median(vals), 4) if vals else None


def main():
    study = load(WINNER_STUDY, {})
    winners = [x for x in study.get("rows") or [] if isinstance(x, dict) and x.get("label") == "WINNER"]
    controls = [x for x in study.get("rows") or [] if isinstance(x, dict) and x.get("label") == "CONTROL"]
    identities = {}
    for w in winners:
        token, pair, chain = w.get("token"), w.get("pair_address"), w.get("chain")
        if token and pair and chain:
            identities[(norm(chain), norm(token), norm(pair))] = w

    pair_meta = {}
    meta_errors = []
    for key, w in identities.items():
        meta, err = exact_pair_meta(w.get("chain"), w.get("pair_address"))
        if err:
            meta_errors.append({"chain": w.get("chain"), "token": w.get("token"), "pair": w.get("pair_address"), "error": err})
        pair_meta[key] = meta or {}

    snapshots = git_snapshots()
    series = defaultdict(list)
    for snap in snapshots:
        ts = parse_ts(snap.get("generated_at"))
        if not ts:
            continue
        for row in snap.get("tokens") or []:
            if not isinstance(row, dict):
                continue
            key = (norm(row.get("chain")), norm(row.get("token")), norm(row.get("pair_address")))
            if key not in identities:
                continue
            meta = pair_meta.get(key) or {}
            age = age_days(meta.get("pair_created_at"), ts)
            p = dict(row)
            p["observed_at"] = iso(ts)
            p["commit_sha"] = snap.get("_commit_sha")
            p["market_age_days"] = round(age, 4) if age is not None else None
            p["veteran_eligible"] = bool(age is not None and age >= MIN_AGE_DAYS)
            series[key].append(p)

    token_rows = []
    veteran_keys = []
    veteran_high_keys = []
    for key, points in series.items():
        points.sort(key=lambda x: x.get("observed_at") or "")
        prev = None
        for p in points:
            if prev is not None:
                prev_liq = f(prev.get("liquidity_usd"))
                cur_liq = f(p.get("liquidity_usd"))
                prev_ts = parse_ts(prev.get("observed_at"))
                cur_ts = parse_ts(p.get("observed_at"))
                gap_h = ((cur_ts - prev_ts).total_seconds() / 3600.0) if prev_ts and cur_ts else None
                if prev_liq and cur_liq is not None and gap_h is not None and gap_h <= 2.5:
                    p["liquidity_retention_vs_previous"] = round(cur_liq / prev_liq, 6)
                else:
                    p["liquidity_retention_vs_previous"] = None
            else:
                p["liquidity_retention_vs_previous"] = None
            prev = p

        w = identities[key]
        eligible_points = [p for p in points if p.get("veteran_eligible")]
        high_points = [p for p in eligible_points if high_dna(p)]
        if eligible_points:
            veteran_keys.append(key)
        if high_points:
            veteran_high_keys.append(key)
        token_rows.append({
            "chain": w.get("chain"),
            "token": w.get("token"),
            "pair_address": w.get("pair_address"),
            "historical_winner_return_24h_pct": w.get("return_24h_pct"),
            "pair_created_at": (pair_meta.get(key) or {}).get("pair_created_at"),
            "snapshots": len(points),
            "veteran_snapshots": len(eligible_points),
            "veteran_high_dna_snapshots": len(high_points),
            "first_veteran_high_at": high_points[0].get("observed_at") if high_points else None,
            "age_status": "VETERAN_IN_SAVED_WINDOW" if eligible_points else ("PAIR_AGE_UNVERIFIED" if not (pair_meta.get(key) or {}).get("pair_created_at") else "UNDER_180D_IN_SAVED_WINDOW"),
        })

    grid_rows = []
    for turnover_min, ratio_min, liq_retention_min in threshold_grid():
        leads = []
        future_returns_6h = []
        hits = []
        for key in veteran_high_keys:
            pts = series[key]
            highs = [p for p in pts if p.get("veteran_eligible") and high_dna(p)]
            if not highs:
                continue
            first_high = highs[0]
            high_ts = parse_ts(first_high.get("observed_at"))
            candidates = []
            for p in pts:
                if not p.get("veteran_eligible"):
                    continue
                ts = parse_ts(p.get("observed_at"))
                if not ts or not high_ts or ts >= high_ts:
                    continue
                lead_h = (high_ts - ts).total_seconds() / 3600.0
                if lead_h > MAX_LEAD_HOURS:
                    continue
                if qualifies_pre_high(p, turnover_min, ratio_min, liq_retention_min):
                    candidates.append((ts, p, lead_h))
            if not candidates:
                continue
            ts, signal, lead_h = sorted(candidates, key=lambda x: x[0])[0]
            signal_price = f(signal.get("price_usd"))
            future_prices = []
            if signal_price and signal_price > 0:
                for q in pts:
                    qts = parse_ts(q.get("observed_at"))
                    if not qts or qts <= ts:
                        continue
                    dh = (qts - ts).total_seconds() / 3600.0
                    if dh <= 6.0:
                        qp = f(q.get("price_usd"))
                        if qp is not None:
                            future_prices.append(qp)
            max_ret = ((max(future_prices) / signal_price) - 1.0) * 100.0 if future_prices and signal_price else None
            leads.append(lead_h)
            future_returns_6h.append(max_ret)
            w = identities[key]
            hits.append({
                "chain": w.get("chain"),
                "token": w.get("token"),
                "signal_at": signal.get("observed_at"),
                "high_at": first_high.get("observed_at"),
                "lead_hours": round(lead_h, 4),
                "turnover_h1": signal.get("turnover_h1"),
                "buy_sell_ratio_h1": signal.get("buy_sell_ratio_h1"),
                "liquidity_retention_vs_previous": signal.get("liquidity_retention_vs_previous"),
                "price_change_h1_pct": signal.get("price_change_h1_pct"),
                "max_saved_price_return_next_6h_pct": round(max_ret, 4) if max_ret is not None else None,
            })
        denominator = len(veteran_high_keys)
        coverage = (len(hits) / denominator) if denominator else 0.0
        grid_rows.append({
            "turnover_min": turnover_min,
            "turnover_max_exclusive": 0.75,
            "buy_sell_ratio_min": ratio_min,
            "liquidity_retention_min": liq_retention_min,
            "veteran_high_event_tokens": denominator,
            "prehigh_hits": len(hits),
            "coverage_pct": round(coverage * 100.0, 2),
            "median_lead_hours": median_or_none(leads),
            "median_max_saved_return_next_6h_pct": median_or_none(future_returns_6h),
            "hits": hits,
        })

    grid_rows.sort(key=lambda x: (x.get("coverage_pct") or 0, x.get("median_lead_hours") or 0, x.get("buy_sell_ratio_min") or 0, x.get("liquidity_retention_min") or 0), reverse=True)
    sample_sufficient = len(veteran_high_keys) >= 5
    best = grid_rows[0] if grid_rows else None
    recommendation = (
        "SHADOW_CANDIDATE_ONLY_NO_PRODUCTION_CHANGE" if sample_sufficient and best and best.get("prehigh_hits", 0) >= 3
        else "INSUFFICIENT_VETERAN_HIGH_SAMPLE_NO_THRESHOLD_PROMOTION"
    )

    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "VETERAN_PREHIGH_NO_HINDSIGHT_BACKTEST_V1",
        "production_change": False,
        "automatic_buy": False,
        "truth_contract": {
            "winner_source": "winner-separator-study.json",
            "saved_hourly_source": "git history of exact-pair survivor-wave-watch.json",
            "veteran_market_age_min_days": MIN_AGE_DAYS,
            "exact_pair_required": True,
            "liquidity_floor_usd": LIQ_FLOOR,
            "prehigh_must_precede_high": True,
            "max_lead_hours": MAX_LEAD_HOURS,
            "high_dna_rule": "TURNOVER_H1>=0.75 AND BUY_SELL_RATIO_H1>=1.25",
            "prehigh_rule_grid": "TURNOVER_MIN<=TURNOVER_H1<0.75 + BUY_SELL_RATIO_MIN + LIQUIDITY_RETENTION_VS_PREVIOUS",
            "unknown_age_policy": "FAIL_CLOSED_EXCLUDED",
            "no_hindsight": True,
        },
        "cohort": {
            "winner_n": len(winners),
            "control_n_available_in_separator": len(controls),
            "winner_exact_pair_identities": len(identities),
            "saved_hourly_snapshots": len(snapshots),
            "winners_with_saved_series": len(series),
            "veteran_winners_in_saved_window": len(veteran_keys),
            "veteran_winners_with_high_dna_event": len(veteran_high_keys),
        },
        "control_precision_status": "NOT_HISTORICALLY_TESTABLE_FROM_SURVIVOR_FILE_BECAUSE_ONLY_WINNERS_WERE_TRACKED_HOURLY",
        "recommendation": recommendation,
        "best_shadow_candidate": best,
        "threshold_grid_top10": grid_rows[:10],
        "winner_age_rows": sorted(token_rows, key=lambda x: (x.get("age_status") == "VETERAN_IN_SAVED_WINDOW", x.get("historical_winner_return_24h_pct") or 0), reverse=True),
        "pair_metadata_errors": meta_errors,
        "next_validation": "Track the same PRE-HIGH rules prospectively on a veteran winner+control shadow cohort before any production threshold change.",
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "winner_n": len(winners),
        "saved_snapshots": len(snapshots),
        "veteran_winners": len(veteran_keys),
        "veteran_high_tokens": len(veteran_high_keys),
        "recommendation": recommendation,
        "best": best,
    }, indent=2))


if __name__ == "__main__":
    main()
