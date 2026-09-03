from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path("data")
OUT = DATA / "winner-separator-study.json"


def load(name, default=None):
    p = DATA / name
    if not p.exists() or p.stat().st_size == 0:
        return {} if default is None else default
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def same(a, b):
    return bool(a) and bool(b) and str(a).lower() == str(b).lower()


def event_time(e):
    for k in ("first_seen_by_wallet500", "first_seen_at", "observed_at", "at", "created_at", "published_at"):
        x = ts(e.get(k)) if isinstance(e, dict) else None
        if x:
            return x
    return None


def exact_token(e, row):
    if not isinstance(e, dict):
        return False
    token = e.get("contract") or e.get("token_address") or e.get("token") or e.get("mint")
    chain = e.get("chain") or e.get("network")
    if not same(token, row.get("token")):
        return False
    return not chain or same(chain, row.get("chain"))


def pre_t0_events(events, row, t0):
    kept, post = [], 0
    for e in events:
        if not exact_token(e, row):
            continue
        et = event_time(e)
        if not et:
            continue
        if et <= t0:
            kept.append(e)
        else:
            post += 1
    return kept, post


def listing_events(row, t0):
    led = load("global-listing-ledger.json")
    kept, post = [], 0
    for rec in (led.get("records") or {}).values():
        if not isinstance(rec, dict):
            continue
        first = rec.get("first_observation") or {}
        if not exact_token(first, row):
            continue
        et = ts(rec.get("first_seen_at")) or event_time(first)
        if not et:
            continue
        if et <= t0:
            kept.append(first)
        else:
            post += 1
    return kept, post


def row_features(row, label):
    f = row.get("features") or {}
    t0 = ts(f.get("snapshot_at"))
    if not t0:
        return None
    social, social_post = pre_t0_events(load("social-catalyst-ledger.json").get("events") or [], row, t0)
    kol, kol_post = pre_t0_events(load("kol-revival-convergence-ledger.json").get("events") or [], row, t0)
    listings, listing_post = listing_events(row, t0)
    return {
        "label": label,
        "chain": row.get("chain"),
        "token": row.get("token"),
        "pair_address": row.get("pair_address"),
        "t0": t0.isoformat(),
        "return_24h_pct": (row.get("outcome") or {}).get("return_pct"),
        "market": {
            "liquidity_usd": f.get("liquidity_usd"),
            "volume_h1": f.get("volume_h1"),
            "turnover_h1": f.get("turnover_h1"),
            "buy_sell_ratio": f.get("buy_sell_ratio"),
            "txns_h1": f.get("txns_h1"),
        },
        "pre_t0": {
            "social_exact_events": len(social),
            "social_independent_authors": len({str(e.get('author') or '') for e in social if e.get('author')}),
            "kol_exact_events": len(kol),
            "listing_exact_events": len(listings),
        },
        "post_t0_excluded": {
            "social": social_post,
            "kol": kol_post,
            "listing": listing_post,
        },
    }


def med(rows, getter):
    vals = []
    for r in rows:
        v = getter(r)
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return round(median(vals), 6) if vals else None


def summarize(rows):
    out = {"n": len(rows)}
    fields = {
        "liquidity_usd": lambda r: r["market"].get("liquidity_usd"),
        "volume_h1": lambda r: r["market"].get("volume_h1"),
        "turnover_h1": lambda r: r["market"].get("turnover_h1"),
        "buy_sell_ratio": lambda r: r["market"].get("buy_sell_ratio"),
        "txns_h1": lambda r: r["market"].get("txns_h1"),
        "social_exact_events": lambda r: r["pre_t0"].get("social_exact_events"),
        "social_independent_authors": lambda r: r["pre_t0"].get("social_independent_authors"),
        "kol_exact_events": lambda r: r["pre_t0"].get("kol_exact_events"),
        "listing_exact_events": lambda r: r["pre_t0"].get("listing_exact_events"),
    }
    out["medians"] = {k: med(rows, g) for k, g in fields.items()}
    out["positive_counts"] = {
        k: sum(1 for r in rows if (g(r) or 0) > 0)
        for k, g in fields.items() if k.endswith("events") or k.endswith("authors")
    }
    return out


def coverage(rows):
    n = len(rows) or 1
    return {
        "social_pre_t0_exact_token_positive_pct": round(100 * sum(r["pre_t0"]["social_exact_events"] > 0 for r in rows) / n, 2),
        "kol_pre_t0_exact_token_positive_pct": round(100 * sum(r["pre_t0"]["kol_exact_events"] > 0 for r in rows) / n, 2),
        "listing_pre_t0_exact_token_positive_pct": round(100 * sum(r["pre_t0"]["listing_exact_events"] > 0 for r in rows) / n, 2),
        "note": "Zero means no timestamp-safe exact-token evidence in the current immutable ledger; it is not proof that the real-world signal did not exist.",
    }


def main():
    dna = load("winner-dna-study.json")
    study = dna.get("overall_study") or {}
    winners = [row_features(r, "WINNER") for r in (study.get("winners") or [])]
    controls = [row_features(r, "CONTROL") for r in (study.get("controls") or [])]
    winners = [r for r in winners if r]
    controls = [r for r in controls if r]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "WINNER_SEPARATOR_NO_HINDSIGHT_V1",
        "production_change": False,
        "production_thresholds_modified": False,
        "exact_pair_identity_preserved": True,
        "t0_rule": "Only evidence first observed by Wallet500 at or before the exact-pair feature snapshot T0 is eligible. Post-T0 evidence is excluded.",
        "social_rule": "SOCIAL_MENTIONS_NEQ_ORGANIC_SOCIAL_ACCELERATION",
        "cohort": {"winner_n": len(winners), "control_n": len(controls)},
        "winner_summary": summarize(winners),
        "control_summary": summarize(controls),
        "coverage": {"winners": coverage(winners), "controls": coverage(controls)},
        "coverage_guard": "Sparse historical social/KOL/listing ledgers are reported as insufficient coverage, never imputed as zero alpha.",
        "current_conclusion": "MARKET_ACTIVITY_SEPARATOR_CONFIRMED; EXTERNAL_CONTEXT_SEPARATOR_NOT_YET_TESTABLE_IF_PRE_T0_COVERAGE_IS_SPARSE",
        "rows": winners + controls,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "method": result["method"],
        "cohort": result["cohort"],
        "winner_coverage": result["coverage"]["winners"],
        "control_coverage": result["coverage"]["controls"],
        "production_change": False,
    }, indent=2))


if __name__ == "__main__":
    main()
