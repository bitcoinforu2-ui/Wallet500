from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import statistics
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import resilient_http

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "data" / "research"
UNIVERSE = RESEARCH / "solana-500-year-universe.json"
FINAL = RESEARCH / "solana-500-year-context-backtest.json"
PATTERNS = RESEARCH / "solana-500-year-context-patterns.json"
CANDIDATES = RESEARCH / "solana-500-year-learning-candidates.json"
LESSONS = RESEARCH / "solana-500-year-context-lessons.json"
PHASE1_PATTERNS = RESEARCH / "solana-500-context-patterns.json"

CG = "https://api.coingecko.com/api/v3"
DS = "https://api.dexscreener.com"
UA = "Wallet500-Solana500YearContext/1.0"

EXCLUDED_SYMBOLS = {
    "USDC", "USDT", "USDS", "DAI", "PYUSD", "USD1", "USDE", "FDUSD",
    "TUSD", "USDP", "USDY", "EURC", "UXD", "TGBP", "EURS", "EURT",
}
EXCLUDED_NAME_WORDS = (
    "wrapped ", "bridged ", "wormhole", "xstock", "tokenized stock",
    "tokenized equity", "tokenized treasury", "leveraged token",
)
FEATURES = (
    "volume_acceleration",
    "price_not_extended",
    "near_breakout",
    "momentum_ignition",
    "volatility_compression",
    "revival_structure",
    "volume_price_divergence",
    "positive_structure",
    "relative_strength_vs_sol",
    "sol_regime_support",
    "anti_beta_strength",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def cg_headers() -> dict:
    key = os.environ.get("COINGECKO_DEMO_API_KEY", "").strip()
    return {"x-cg-demo-api-key": key} if key else {}


def get_json(url: str, *, interval=None, attempts=5, cache_ttl=0, timeout=40):
    return resilient_http.request_json(
        url,
        timeout=timeout,
        attempts=attempts,
        cache_ttl=cache_ttl,
        min_interval=interval,
        headers=cg_headers() if "api.coingecko.com" in url else {},
        user_agent=UA,
    )


def eligible(row: dict) -> bool:
    symbol = str(row.get("symbol") or "").upper().strip()
    name = str(row.get("name") or "").lower().strip()
    if not symbol or symbol in EXCLUDED_SYMBOLS:
        return False
    if symbol.endswith(("3L", "3S", "5L", "5S")):
        return False
    if any(word in name for word in EXCLUDED_NAME_WORDS):
        return False
    # Remove obvious fiat/stable proxies without excluding ordinary crypto names.
    if symbol.endswith(("USD", "USDT", "USDC")) and len(symbol) <= 8:
        return False
    return float(row.get("market_cap") or 0) > 0


def build_universe() -> int:
    coin_list = get_json(
        f"{CG}/coins/list?include_platform=true",
        interval=2.2,
        attempts=6,
        cache_ttl=3600,
        timeout=50,
    )
    solana_ids = {}
    for row in coin_list or []:
        addr = str((row.get("platforms") or {}).get("solana") or "").strip()
        if addr:
            solana_ids[str(row.get("id") or "")] = addr

    ranked = []
    seen = set()
    for page in range(1, 61):
        q = urllib.parse.urlencode({
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "24h,7d,30d",
        })
        rows = get_json(f"{CG}/coins/markets?{q}", interval=2.2, attempts=6, cache_ttl=300)
        if not rows:
            break
        for m in rows:
            cid = str(m.get("id") or "")
            addr = solana_ids.get(cid)
            if not addr or cid in seen or not eligible(m):
                continue
            seen.add(cid)
            ranked.append({
                "coingecko_id": cid,
                "symbol": str(m.get("symbol") or "").upper(),
                "name": m.get("name"),
                "contract": addr,
                "current_price": m.get("current_price"),
                "market_cap": m.get("market_cap"),
                "global_market_cap_rank": m.get("market_cap_rank"),
                "total_volume": m.get("total_volume"),
                "change_24h_pct": m.get("price_change_percentage_24h"),
                "change_7d_pct": m.get("price_change_percentage_7d_in_currency"),
                "change_30d_pct": m.get("price_change_percentage_30d_in_currency"),
            })
        if len(ranked) >= 650:
            break
    if len(ranked) < 599:
        raise RuntimeError(f"CLEAN_SOLANA_UNIVERSE_TOO_SMALL:{len(ranked)}")

    for i, row in enumerate(ranked, 1):
        row["solana_market_cap_rank"] = i
    cohort = ranked[99:599]
    if len(cohort) != 500:
        raise RuntimeError(f"COHORT_SIZE_MISMATCH:{len(cohort)}")

    by_addr = {x["contract"]: x for x in cohort}
    addresses = list(by_addr)
    for off in range(0, len(addresses), 30):
        batch = addresses[off:off + 30]
        enc = ",".join(urllib.parse.quote(x, safe="") for x in batch)
        try:
            pairs = get_json(
                f"{DS}/tokens/v1/solana/{enc}",
                interval=0.4,
                attempts=4,
                cache_ttl=120,
                timeout=30,
            ) or []
        except Exception:
            pairs = []
        options = {x: [] for x in batch}
        batch_set = set(batch)
        for p in pairs if isinstance(pairs, list) else []:
            base = str((p.get("baseToken") or {}).get("address") or "")
            quote = str((p.get("quoteToken") or {}).get("address") or "")
            if base in batch_set:
                options[base].append(p)
            if quote in batch_set:
                options[quote].append(p)
        for addr in batch:
            if not options.get(addr):
                continue
            best = max(options[addr], key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            row = by_addr[addr]
            row.update({
                "pair": best.get("pairAddress"),
                "dex_url": best.get("url"),
                "dex_id": best.get("dexId"),
                "liquidity_usd": float((best.get("liquidity") or {}).get("usd") or 0),
                "pair_volume_h24_usd": float((best.get("volume") or {}).get("h24") or 0),
                "pair_price_usd": float(best.get("priceUsd") or 0),
            })

    resolved = sum(bool(x.get("pair")) for x in cohort)
    write(UNIVERSE, {
        "version": 2,
        "generated_at": now_iso(),
        "research_only": True,
        "production_effect": False,
        "definition": {
            "network": "solana",
            "ranking": "current Solana-platform market-cap ranks after stable/wrapped/leveraged/tokenized-equity proxy exclusions",
            "rank_start": 100,
            "rank_end_inclusive": 599,
            "count": 500,
            "survivorship_bias": True,
        },
        "coverage": {
            "clean_solana_assets_found": len(ranked),
            "cohort": len(cohort),
            "exact_pairs_resolved": resolved,
            "pair_resolution_pct": round(resolved / 500 * 100, 2),
        },
        "tokens": cohort,
        "http_metrics": resilient_http.metrics(),
    })
    print("SOLANA500_YEAR_UNIVERSE", json.dumps({"cohort": 500, "resolved": resolved, "eligible": len(ranked)}))
    return 0


def market_chart(coin_id: str):
    q = urllib.parse.urlencode({"vs_currency": "usd", "days": 365})
    url = f"{CG}/coins/{urllib.parse.quote(coin_id, safe='')}/market_chart?{q}"
    try:
        doc = get_json(url, interval=7.0, attempts=6, cache_ttl=3600, timeout=45)
    except Exception as exc:
        return [], f"{type(exc).__name__}:{str(exc)[:180]}"
    prices = (doc or {}).get("prices") or []
    volumes = (doc or {}).get("total_volumes") or []
    mcaps = (doc or {}).get("market_caps") or []
    volmap = {int(x[0]) // 86400000: float(x[1] or 0) for x in volumes if isinstance(x, list) and len(x) >= 2}
    capmap = {int(x[0]) // 86400000: float(x[1] or 0) for x in mcaps if isinstance(x, list) and len(x) >= 2}
    ded = {}
    for x in prices:
        if not isinstance(x, list) or len(x) < 2:
            continue
        day = int(x[0]) // 86400000
        price = float(x[1] or 0)
        if price <= 0:
            continue
        ded[day] = [day * 86400, price, volmap.get(day, 0.0), capmap.get(day, 0.0)]
    rows = [ded[k] for k in sorted(ded)]
    return rows, None if rows else "EMPTY_MARKET_CHART"


def history_batch(batch: int, batch_count: int) -> int:
    rows = list(load(UNIVERSE, {}).get("tokens") or [])
    subset = [x for i, x in enumerate(rows) if i % batch_count == batch]
    out = []
    ok = 0
    for n, token in enumerate(subset, 1):
        hist, err = market_chart(str(token.get("coingecko_id") or ""))
        if len(hist) >= 180:
            ok += 1
        out.append({"token": token, "daily": hist, "error": err, "history_days": len(hist)})
        print(f"YEAR_HISTORY batch={batch} {n}/{len(subset)} {token.get('symbol')} days={len(hist)} error={err or 'NONE'}")
    path = RESEARCH / f"solana-500-year-batch-{batch:02d}.json"
    write(path, {
        "version": 2,
        "generated_at": now_iso(),
        "batch": batch,
        "batch_count": batch_count,
        "coverage": {"requested": len(subset), "history_ge_180_days": ok},
        "tokens": out,
        "http_metrics": resilient_http.metrics(),
    })
    return 0


def avg(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def std(xs):
    xs = [float(x) for x in xs if x is not None]
    return statistics.pstdev(xs) if len(xs) >= 2 else 0.0


def pct(a, b):
    return None if not b else (float(a) / float(b) - 1.0) * 100.0


def med(xs):
    xs = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return statistics.median(xs) if xs else None


def sol_map():
    rows, err = market_chart("solana")
    if err or len(rows) < 180:
        raise RuntimeError(f"SOL_BENCHMARK_UNAVAILABLE:{err}:{len(rows)}")
    return {x[0] // 86400: x for x in rows}, rows


def feature_row(rows: list, i: int, sol_by_day: dict, need_future=True):
    if i < 35 or (need_future and i + 30 >= len(rows)):
        return None
    prices = [x[1] for x in rows]
    vols = [x[2] for x in rows]
    price = prices[i]
    ret7 = pct(price, prices[i - 7])
    ret30 = pct(price, prices[i - 30])
    v3 = avg(vols[i - 2:i + 1])
    vp = avg(vols[i - 19:i - 2])
    vr = v3 / vp if vp > 0 else 0.0
    prev_peak30 = max(prices[i - 30:i])
    sma7 = avg(prices[i - 6:i + 1])
    returns30 = [prices[j] / prices[j - 1] - 1 for j in range(i - 29, i + 1) if prices[j - 1] > 0]
    v30 = std(returns30)
    v7 = std(returns30[-7:])
    compression = v7 / v30 if v30 > 0 else 1.0
    trough30 = min(prices[i - 30:i + 1])
    peak30 = max(prices[i - 30:i + 1])
    drawdown30 = (trough30 / peak30 - 1) * 100 if peak30 > 0 else 0.0

    day = rows[i][0] // 86400
    sol_now = sol_by_day.get(day)
    sol_7 = sol_by_day.get(rows[i - 7][0] // 86400)
    sol_30 = sol_by_day.get(rows[i - 30][0] // 86400)
    sol_ret7 = pct(sol_now[1], sol_7[1]) if sol_now and sol_7 else None
    sol_ret30 = pct(sol_now[1], sol_30[1]) if sol_now and sol_30 else None
    rel7 = (ret7 - sol_ret7) if ret7 is not None and sol_ret7 is not None else None

    feats = {
        "volume_acceleration": vr >= 1.7,
        "price_not_extended": ret7 is not None and -12 <= ret7 <= 25 and price <= prev_peak30 * 1.10,
        "near_breakout": price >= prev_peak30 * 0.97,
        "momentum_ignition": ret7 is not None and 4 <= ret7 <= 30 and vr >= 1.5,
        "volatility_compression": compression <= 0.78,
        "revival_structure": drawdown30 <= -35 and price > sma7 and vr >= 1.5,
        "volume_price_divergence": vr >= 2.0 and abs(ret7 or 0) <= 12,
        "positive_structure": price > sma7 and (ret7 or 0) > 0,
        "relative_strength_vs_sol": rel7 is not None and rel7 >= 5,
        "sol_regime_support": sol_ret30 is not None and sol_ret30 > 0 and (sol_ret7 or 0) > -8,
        "anti_beta_strength": sol_ret7 is not None and sol_ret7 < -2 and (ret7 or 0) > 3,
    }
    out = {
        "ts": rows[i][0],
        "price": price,
        "ret7_pct": ret7,
        "ret30_pct": ret30,
        "volume_ratio": vr,
        "volatility_compression_ratio": compression,
        "drawdown_30d_pct": drawdown30,
        "sol_ret7_pct": sol_ret7,
        "sol_ret30_pct": sol_ret30,
        "relative_strength_7d_pp": rel7,
        "features": feats,
    }
    if need_future:
        future = prices[i + 1:i + 31]
        out.update({
            "future_max_30d_pct": (max(future) / price - 1) * 100,
            "future_close_30d_pct": (future[-1] / price - 1) * 100,
            "future_drawdown_30d_pct": (min(future) / price - 1) * 100,
        })
    return out


def analyze(item: dict, sol_by_day: dict):
    rows = item.get("daily") or []
    if len(rows) < 100:
        return [], {"history_days": len(rows), "history_error": item.get("error")}
    obs = [feature_row(rows, i, sol_by_day, True) for i in range(35, len(rows) - 30)]
    obs = [x for x in obs if x]
    prices = [x[1] for x in rows]
    return obs, {
        "history_days": len(rows),
        "history_start": datetime.fromtimestamp(rows[0][0], timezone.utc).date().isoformat(),
        "history_end": datetime.fromtimestamp(rows[-1][0], timezone.utc).date().isoformat(),
        "period_return_pct": pct(prices[-1], prices[0]),
        "period_max_runup_pct": (max(prices) / prices[0] - 1) * 100,
        "period_max_drawdown_pct": min((prices[j] / max(prices[:j + 1]) - 1) * 100 for j in range(len(prices))),
        "current_features": feature_row(rows, len(rows) - 1, sol_by_day, False),
    }


def stats(events, combo):
    chosen = []
    last = {}
    for token, row in events:
        if not all((row.get("features") or {}).get(f) for f in combo):
            continue
        ts = int(row.get("ts") or 0)
        if ts - int(last.get(token, 0)) < 7 * 86400:
            continue
        last[token] = ts
        chosen.append(row)
    if not chosen:
        return {"n": 0}
    mx = [x["future_max_30d_pct"] for x in chosen]
    close = [x["future_close_30d_pct"] for x in chosen]
    dd = [x["future_drawdown_30d_pct"] for x in chosen]
    return {
        "n": len(chosen),
        "hit_25pct_30d": round(sum(x >= 25 for x in mx) / len(mx), 4),
        "hit_50pct_30d": round(sum(x >= 50 for x in mx) / len(mx), 4),
        "hit_100pct_30d": round(sum(x >= 100 for x in mx) / len(mx), 4),
        "median_max_30d_pct": round(med(mx), 2),
        "median_close_30d_pct": round(med(close), 2),
        "median_drawdown_30d_pct": round(med(dd), 2),
    }


def baseline(events):
    chosen = []
    n_by = Counter()
    for token, row in events:
        if n_by[token] % 7 == 0:
            chosen.append(row)
        n_by[token] += 1
    return stats([(str(i), x) for i, x in enumerate(chosen)], ()) if chosen else {"n": 0}


def phase1_sets():
    d = load(PHASE1_PATTERNS, {})
    return {
        frozenset(p.get("features") or [])
        for p in (d.get("patterns") or [])
        if p.get("robust_candidate")
    }


def pattern_lab(rows_by_token):
    train, test = [], []
    for token, rows in rows_by_token.items():
        cut = max(1, int(len(rows) * 0.75))
        train += [(token, x) for x in rows[:cut]]
        test += [(token, x) for x in rows[cut:]]
    btr, bte = baseline(train), baseline(test)
    prior = phase1_sets()
    patterns = []
    for size in (1, 2, 3):
        for combo in itertools.combinations(FEATURES, size):
            tr, te = stats(train, combo), stats(test, combo)
            bh = float(bte.get("hit_25pct_30d") or 0)
            lift = float(te.get("hit_25pct_30d") or 0) / bh if bh else None
            robust = (
                int(tr.get("n") or 0) >= 80
                and int(te.get("n") or 0) >= 25
                and lift is not None and lift >= 1.15
                and float(te.get("median_max_30d_pct") or 0) > float(bte.get("median_max_30d_pct") or 0)
            )
            fs = frozenset(combo)
            stable = fs in prior
            patterns.append({
                "pattern": "+".join(combo),
                "features": list(combo),
                "train": tr,
                "test": te,
                "test_lift_vs_baseline_25pct": round(lift, 3) if lift is not None else None,
                "robust_candidate": robust,
                "reproduced_in_phase1_exact_pair": stable,
            })
    patterns.sort(key=lambda x: (
        bool(x["robust_candidate"]),
        bool(x["reproduced_in_phase1_exact_pair"]),
        float(x.get("test_lift_vs_baseline_25pct") or 0),
        int((x.get("test") or {}).get("n") or 0),
    ), reverse=True)
    return btr, bte, patterns


def score_candidate(token, summary, robust):
    cur = summary.get("current_features") or {}
    feats = cur.get("features") or {}
    matches = []
    score = 0.0
    for p in robust:
        req = p.get("features") or []
        if req and all(feats.get(x) for x in req):
            lift = float(p.get("test_lift_vs_baseline_25pct") or 0)
            n = int((p.get("test") or {}).get("n") or 0)
            stable = bool(p.get("reproduced_in_phase1_exact_pair"))
            matches.append({
                "pattern": p.get("pattern"),
                "lift": lift,
                "test_n": n,
                "median_max_30d_pct": (p.get("test") or {}).get("median_max_30d_pct"),
                "median_drawdown_30d_pct": (p.get("test") or {}).get("median_drawdown_30d_pct"),
                "reproduced_in_phase1_exact_pair": stable,
            })
            score += max(0, lift - 1) * min(2.5, math.log10(max(10, n))) * (1.35 if stable else 1.0)
    liq = float(token.get("liquidity_usd") or 0)
    if liq >= 100000:
        score += 0.5
    elif liq >= 50000:
        score += 0.25
    else:
        score -= 0.75
    if feats.get("price_not_extended"):
        score += 0.4
    if feats.get("relative_strength_vs_sol"):
        score += 0.3
    if cur.get("ret7_pct") is not None and float(cur["ret7_pct"]) > 45:
        score -= 1.25
    return score, matches


def live_intelligence(candidates):
    try:
        import cross_domain_intelligence_collector as cross
        trending, boosts = cross.global_attention_maps()
    except Exception:
        return candidates
    for c in candidates[:15]:
        t = {"symbol": c.get("symbol"), "network": "solana", "contract": c.get("contract"), "pair": c.get("pair")}
        try:
            hs = cross.holder_snapshot(t)
        except Exception:
            hs = None
        try:
            ns = cross.news_snapshot(t)
        except Exception:
            ns = None
        c["current_intelligence_baseline"] = {
            "captured_at": now_iso(),
            "holder": hs,
            "news": ns,
            "geckoterminal_trending_rank": trending.get(("solana", str(c.get("pair") or "").lower())),
            "dexscreener_paid_boost": boosts.get(("solana", str(c.get("contract") or ""))),
        }
    return candidates


def aggregate() -> int:
    paths = sorted((RESEARCH / "year-batches").glob("solana-500-year-batch-*.json"))
    if not paths:
        paths = sorted(RESEARCH.glob("solana-500-year-batch-*.json"))
    if not paths:
        raise RuntimeError("NO_YEAR_BATCHES")
    merged = []
    for p in paths:
        merged += list(load(p, {}).get("tokens") or [])
    sol_by_day, sol_rows = sol_map()

    rows_by_token = {}
    summaries = []
    by_contract = {}
    for item in merged:
        token = item.get("token") or {}
        key = str(token.get("contract") or token.get("coingecko_id") or "")
        by_contract[key] = token
        obs, sm = analyze(item, sol_by_day)
        if obs:
            rows_by_token[key] = obs
        summaries.append({
            "solana_market_cap_rank": token.get("solana_market_cap_rank"),
            "symbol": token.get("symbol"),
            "name": token.get("name"),
            "contract": token.get("contract"),
            "pair": token.get("pair"),
            "dex_url": token.get("dex_url"),
            "market_cap": token.get("market_cap"),
            "liquidity_usd": token.get("liquidity_usd"),
            **sm,
        })

    btr, bte, patterns = pattern_lab(rows_by_token)
    robust = [x for x in patterns if x.get("robust_candidate")][:30]
    stable = [x for x in robust if x.get("reproduced_in_phase1_exact_pair")]

    feature_counts = Counter()
    pair_counts = Counter()
    for p in robust:
        fs = p.get("features") or []
        for f in fs:
            feature_counts[f] += 1
        for a, b in itertools.combinations(sorted(fs), 2):
            pair_counts[f"{a}+{b}"] += 1

    candidates = []
    for sm in summaries:
        token = by_contract.get(str(sm.get("contract") or ""), {})
        if not token.get("pair"):
            continue
        score, matches = score_candidate(token, sm, robust)
        if not matches:
            continue
        candidates.append({
            "symbol": sm.get("symbol"),
            "name": sm.get("name"),
            "contract": sm.get("contract"),
            "pair": sm.get("pair"),
            "dex_url": sm.get("dex_url"),
            "solana_market_cap_rank": sm.get("solana_market_cap_rank"),
            "market_cap": sm.get("market_cap"),
            "liquidity_usd": sm.get("liquidity_usd"),
            "research_score": round(score, 3),
            "matched_out_of_sample_patterns": matches[:10],
            "current_features": sm.get("current_features"),
            "research_only": True,
            "telegram_eligible": False,
            "buy_signal": False,
        })
    candidates.sort(key=lambda x: x.get("research_score", -999), reverse=True)
    candidates = live_intelligence(candidates[:15])

    lessons = {
        "version": 2,
        "generated_at": now_iso(),
        "research_only": True,
        "baseline_test": bte,
        "robust_pattern_count": len(robust),
        "cross_source_reproduced_pattern_count": len(stable),
        "dominant_features": feature_counts.most_common(),
        "dominant_feature_pairs": pair_counts.most_common(20),
        "cross_source_reproduced_patterns": stable[:15],
        "interpretation_guardrails": [
            "Current-rank cohort has survivorship bias; use findings as priors, not causal proof.",
            "A pattern is stronger when it reproduces in both CoinGecko 365d market history and recent exact-pair on-chain history.",
            "BUY promotion still requires fresh cross-domain intelligence and exact-pair market confirmation.",
            "High Solana baseline volatility means raw +25% hit rate is not enough; lift over baseline and drawdown both matter.",
        ],
    }

    write(FINAL, {
        "version": 2,
        "generated_at": now_iso(),
        "mode": "RESEARCH_ONLY_SOLANA_500_365D_CONTEXT_WALK_FORWARD",
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "cohort_count": len(merged),
        "history_usable_count": len(rows_by_token),
        "sol_benchmark_days": len(sol_rows),
        "methodology": {
            "history": "CoinGecko 365d daily price/total-volume/market-cap history plus current exact Solana pair/liquidity metadata",
            "validation": "chronological 75% train / 25% out-of-sample per token",
            "primary_success": "future daily-price maximum >= +25% within 30 days",
            "relative_context": "7d/30d SOL benchmark regime and token relative strength",
            "same_pattern_overlap_control_days": 7,
            "survivorship_bias": True,
            "point_in_time_wallet_news_limit": "Historical wallet/news/social snapshots are unavailable in this pass; selected live candidates start forward intelligence capture now.",
        },
        "baseline_train": btr,
        "baseline_test": bte,
        "robust_context_patterns": robust,
        "cross_source_reproduced_patterns": stable,
        "learning_candidates_count": len(candidates),
        "token_summaries": sorted(summaries, key=lambda x: x.get("solana_market_cap_rank") or 999999),
    })
    write(PATTERNS, {
        "version": 2,
        "generated_at": now_iso(),
        "baseline_test": bte,
        "patterns": patterns[:120],
        "production_rule": "Research priors only. A historical pattern cannot itself create a BUY.",
    })
    write(CANDIDATES, {
        "version": 2,
        "generated_at": now_iso(),
        "mode": "RESEARCH_ONLY_FORWARD_LEARNING_365D",
        "telegram_eligible": False,
        "buy_signal": False,
        "candidates": candidates,
    })
    write(LESSONS, lessons)
    print("SOLANA500_YEAR_AGGREGATE", json.dumps({
        "cohort": len(merged),
        "usable": len(rows_by_token),
        "baseline": bte,
        "robust_patterns": len(robust),
        "cross_source_reproduced": len(stable),
        "learning_candidates": len(candidates),
        "top_features": feature_counts.most_common(5),
    }, ensure_ascii=False))
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", required=True, choices=["universe", "history", "aggregate"])
    p.add_argument("--batch", type=int, default=0)
    p.add_argument("--batch-count", type=int, default=10)
    a = p.parse_args()
    if a.phase == "universe":
        return build_universe()
    if a.phase == "history":
        return history_batch(a.batch, a.batch_count)
    return aggregate()


if __name__ == "__main__":
    raise SystemExit(main())
