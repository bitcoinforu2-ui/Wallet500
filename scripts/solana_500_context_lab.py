from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import statistics
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import resilient_http

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "data" / "research"
UNIVERSE = RESEARCH / "solana-500-universe.json"
FINAL = RESEARCH / "solana-500-context-backtest.json"
PATTERNS = RESEARCH / "solana-500-context-patterns.json"
CANDIDATES = RESEARCH / "solana-500-learning-candidates.json"

CG = "https://api.coingecko.com/api/v3"
DS = "https://api.dexscreener.com"
GT = "https://api.geckoterminal.com/api/v2"
UA = "Wallet500-Solana500ContextLab/1.0"

EXCLUDED_SYMBOLS = {
    "USDC", "USDT", "USDS", "DAI", "PYUSD", "USD1", "USDE", "FDUSD",
    "TUSD", "USDP", "USDY", "EURC", "UXD",
}
EXCLUDED_NAME_WORDS = ("wrapped ", "bridged ", "wormhole")
FEATURES = (
    "volume_acceleration",
    "price_not_extended",
    "near_breakout",
    "momentum_ignition",
    "volatility_compression",
    "revival_structure",
    "volume_price_divergence",
    "positive_structure",
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


def get_json(url: str, *, interval=None, attempts=4, cache_ttl=0, headers=None, timeout=30):
    return resilient_http.request_json(
        url,
        timeout=timeout,
        attempts=attempts,
        cache_ttl=cache_ttl,
        min_interval=interval,
        headers=headers or {},
        user_agent=UA,
    )


def eligible_market_row(row: dict) -> bool:
    symbol = str(row.get("symbol") or "").upper()
    name = str(row.get("name") or "").lower()
    if not symbol or symbol in EXCLUDED_SYMBOLS:
        return False
    if symbol.endswith(("3L", "3S", "5L", "5S")):
        return False
    if any(x in name for x in EXCLUDED_NAME_WORDS):
        return False
    return float(row.get("market_cap") or 0) > 0


def build_universe() -> int:
    coin_list = get_json(
        f"{CG}/coins/list?include_platform=true",
        interval=1.25,
        attempts=5,
        cache_ttl=3600,
        headers=cg_headers(),
        timeout=45,
    )
    solana_ids = {}
    for row in coin_list or []:
        addr = str((row.get("platforms") or {}).get("solana") or "").strip()
        if addr:
            solana_ids[str(row.get("id"))] = addr

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
        rows = get_json(
            f"{CG}/coins/markets?{q}",
            interval=1.25,
            attempts=5,
            cache_ttl=300,
            headers=cg_headers(),
        )
        if not rows:
            break
        for m in rows:
            cid = str(m.get("id") or "")
            addr = solana_ids.get(cid)
            if not addr or cid in seen or not eligible_market_row(m):
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
        if len(ranked) >= 620:
            break

    if len(ranked) < 599:
        raise RuntimeError(f"SOLANA_UNIVERSE_TOO_SMALL:{len(ranked)}")

    for rank, row in enumerate(ranked, 1):
        row["solana_market_cap_rank"] = rank

    # Exactly 500 assets: ranks 100..599 inclusive.
    cohort = ranked[99:599]
    if len(cohort) != 500:
        raise RuntimeError(f"COHORT_SIZE_MISMATCH:{len(cohort)}")

    by_addr = {x["contract"]: x for x in cohort}
    addresses = list(by_addr)
    for offset in range(0, len(addresses), 30):
        batch = addresses[offset:offset + 30]
        enc = ",".join(urllib.parse.quote(x, safe="") for x in batch)
        try:
            pairs = get_json(
                f"{DS}/tokens/v1/solana/{enc}",
                interval=0.35,
                attempts=4,
                cache_ttl=120,
                timeout=25,
            ) or []
        except Exception:
            pairs = []
        choices = {a: [] for a in batch}
        batch_set = set(batch)
        for p in pairs if isinstance(pairs, list) else []:
            base = str((p.get("baseToken") or {}).get("address") or "")
            quote = str((p.get("quoteToken") or {}).get("address") or "")
            if base in batch_set:
                choices[base].append(p)
            if quote in batch_set:
                choices[quote].append(p)
        for addr in batch:
            opts = choices.get(addr) or []
            if not opts:
                continue
            best = max(opts, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            base = str((best.get("baseToken") or {}).get("address") or "")
            r = by_addr[addr]
            r.update({
                "pair": best.get("pairAddress"),
                "dex_id": best.get("dexId"),
                "dex_url": best.get("url"),
                "ohlcv_token_side": "base" if base == addr else "quote",
                "liquidity_usd": float((best.get("liquidity") or {}).get("usd") or 0),
                "pair_volume_h24_usd": float((best.get("volume") or {}).get("h24") or 0),
                "pair_price_usd": float(best.get("priceUsd") or 0),
                "pair_change_h24_pct": float((best.get("priceChange") or {}).get("h24") or 0),
                "pair_created_at": best.get("pairCreatedAt"),
            })

    resolved = sum(bool(x.get("pair")) for x in cohort)
    write(UNIVERSE, {
        "version": 1,
        "generated_at": now_iso(),
        "research_only": True,
        "production_effect": False,
        "definition": {
            "network": "solana",
            "ranking": "current Solana-native coins ordered by CoinGecko market cap after stable/wrapped/leveraged exclusions",
            "rank_start": 100,
            "rank_end_inclusive": 599,
            "count": 500,
            "survivorship_bias": True,
            "note": "Fast current-rank cohort; delisted/dead historical assets are not represented.",
        },
        "coverage": {
            "eligible_solana_assets_found": len(ranked),
            "cohort": len(cohort),
            "exact_pairs_resolved": resolved,
            "pair_resolution_pct": round(resolved / 500 * 100, 2),
        },
        "tokens": cohort,
        "http_metrics": resilient_http.metrics(),
    })
    print("SOLANA500_UNIVERSE_READY", resolved, "/500")
    return 0


def fetch_ohlcv(token: dict):
    pair = str(token.get("pair") or "")
    if not pair:
        return [], "NO_EXACT_PAIR"
    q = urllib.parse.urlencode({
        "aggregate": 1,
        "limit": 365,
        "currency": "usd",
        "token": str(token.get("ohlcv_token_side") or "base"),
    })
    url = f"{GT}/networks/solana/pools/{urllib.parse.quote(pair, safe='')}/ohlcv/day?{q}"
    try:
        doc = get_json(url, interval=2.5, attempts=3, cache_ttl=3600, timeout=30)
        rows = (((doc or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
        out = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                continue
            try:
                ts, op, hi, lo, cl, vol = row[:6]
                if float(cl) > 0:
                    out.append([int(ts), float(op), float(hi), float(lo), float(cl), float(vol or 0)])
            except Exception:
                pass
        out.sort(key=lambda x: x[0])
        return out, None if out else "EMPTY_OHLCV"
    except Exception as exc:
        return [], f"{type(exc).__name__}:{str(exc)[:160]}"


def history_batch(batch: int, batch_count: int) -> int:
    universe = load(UNIVERSE, {})
    rows = list(universe.get("tokens") or [])
    subset = [x for i, x in enumerate(rows) if i % batch_count == batch]
    result = []
    ok = 0
    for n, token in enumerate(subset, 1):
        candles, error = fetch_ohlcv(token)
        if candles:
            ok += 1
        result.append({"token": token, "candles": candles, "error": error, "history_days": len(candles)})
        print(f"HISTORY batch={batch} item={n}/{len(subset)} symbol={token.get('symbol')} days={len(candles)} error={error or 'NONE'}")
    path = RESEARCH / f"solana-500-batch-{batch:02d}.json"
    write(path, {
        "version": 1,
        "generated_at": now_iso(),
        "batch": batch,
        "batch_count": batch_count,
        "coverage": {"requested": len(subset), "ohlcv_ok": ok},
        "tokens": result,
        "http_metrics": resilient_http.metrics(),
    })
    return 0


def avg(vals) -> float:
    vals = [float(x) for x in vals if x is not None]
    return sum(vals) / len(vals) if vals else 0.0


def stdev(vals) -> float:
    vals = [float(x) for x in vals if x is not None]
    return statistics.pstdev(vals) if len(vals) >= 2 else 0.0


def pct(a, b):
    return None if not b else (float(a) / float(b) - 1) * 100


def med(vals):
    vals = [float(x) for x in vals if x is not None and math.isfinite(float(x))]
    return statistics.median(vals) if vals else None


def feature_row(candles: list, i: int, need_future: bool = True):
    if i < 35 or (need_future and i + 30 >= len(candles)):
        return None
    closes = [x[4] for x in candles]
    highs = [x[2] for x in candles]
    lows = [x[3] for x in candles]
    vols = [x[5] for x in candles]
    close = closes[i]
    ret7 = pct(close, closes[i - 7])
    ret30 = pct(close, closes[i - 30])
    v3 = avg(vols[i - 2:i + 1])
    vprior = avg(vols[i - 19:i - 2])
    vr = v3 / vprior if vprior > 0 else 0.0
    prev_high30 = max(highs[i - 30:i])
    sma7 = avg(closes[i - 6:i + 1])
    returns30 = [closes[j] / closes[j - 1] - 1 for j in range(i - 29, i + 1) if closes[j - 1] > 0]
    vol30 = stdev(returns30)
    vol7 = stdev(returns30[-7:])
    compression = vol7 / vol30 if vol30 > 0 else 1.0
    peak30 = max(highs[i - 30:i + 1])
    trough30 = min(lows[i - 30:i + 1])
    trough_dd = (trough30 / peak30 - 1) * 100 if peak30 > 0 else 0.0

    feats = {
        "volume_acceleration": vr >= 1.7,
        "price_not_extended": ret7 is not None and -12 <= ret7 <= 25 and close <= prev_high30 * 1.10,
        "near_breakout": close >= prev_high30 * 0.97,
        "momentum_ignition": ret7 is not None and 4 <= ret7 <= 30 and vr >= 1.5,
        "volatility_compression": compression <= 0.78,
        "revival_structure": trough_dd <= -35 and close > sma7 and vr >= 1.5,
        "volume_price_divergence": vr >= 2.0 and abs(ret7 or 0) <= 12,
        "positive_structure": close > sma7 and (ret7 or 0) > 0,
    }
    row = {
        "ts": candles[i][0],
        "close": close,
        "ret7_pct": ret7,
        "ret30_pct": ret30,
        "volume_ratio": vr,
        "volatility_compression_ratio": compression,
        "trough_drawdown_30d_pct": trough_dd,
        "features": feats,
    }
    if need_future:
        future30 = closes[i + 1:i + 31]
        future_lows30 = lows[i + 1:i + 31]
        row.update({
            "future_max_30d_pct": ((max(future30) / close) - 1) * 100,
            "future_close_30d_pct": ((future30[-1] / close) - 1) * 100,
            "future_drawdown_30d_pct": ((min(future_lows30) / close) - 1) * 100,
        })
    return row


def token_analysis(item: dict):
    candles = item.get("candles") or []
    if len(candles) < 70:
        return [], {"history_days": len(candles)}
    obs = [feature_row(candles, i, True) for i in range(35, len(candles) - 30)]
    obs = [x for x in obs if x]
    closes = [x[4] for x in candles]
    highs = [x[2] for x in candles]
    lows = [x[3] for x in candles]
    peak = highs[0]
    maxdd = 0.0
    for lo, hi in zip(lows, highs):
        peak = max(peak, hi)
        maxdd = min(maxdd, (lo / peak - 1) * 100 if peak > 0 else 0)
    return obs, {
        "history_days": len(candles),
        "history_start": datetime.fromtimestamp(candles[0][0], timezone.utc).date().isoformat(),
        "history_end": datetime.fromtimestamp(candles[-1][0], timezone.utc).date().isoformat(),
        "period_return_pct": pct(closes[-1], closes[0]),
        "period_max_runup_pct": (max(highs) / closes[0] - 1) * 100,
        "period_max_drawdown_from_high_pct": maxdd,
        "current_features": feature_row(candles, len(candles) - 1, False),
    }


def event_stats(events: list, combo: tuple):
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
    mx = [r["future_max_30d_pct"] for r in chosen]
    dd = [r["future_drawdown_30d_pct"] for r in chosen]
    close = [r["future_close_30d_pct"] for r in chosen]
    return {
        "n": len(chosen),
        "hit_25pct_30d": round(sum(x >= 25 for x in mx) / len(mx), 4),
        "hit_50pct_30d": round(sum(x >= 50 for x in mx) / len(mx), 4),
        "hit_100pct_30d": round(sum(x >= 100 for x in mx) / len(mx), 4),
        "median_max_30d_pct": round(med(mx), 2),
        "median_close_30d_pct": round(med(close), 2),
        "median_drawdown_30d_pct": round(med(dd), 2),
    }


def baseline_stats(events: list):
    chosen = []
    counters = {}
    for token, row in events:
        n = counters.get(token, 0)
        if n % 7 == 0:
            chosen.append(row)
        counters[token] = n + 1
    if not chosen:
        return {"n": 0}
    mx = [r["future_max_30d_pct"] for r in chosen]
    return {
        "n": len(chosen),
        "hit_25pct_30d": round(sum(x >= 25 for x in mx) / len(mx), 4),
        "hit_50pct_30d": round(sum(x >= 50 for x in mx) / len(mx), 4),
        "median_max_30d_pct": round(med(mx), 2),
    }


def pattern_lab(rows_by_token: dict):
    train, test = [], []
    for token, rows in rows_by_token.items():
        cut = max(1, int(len(rows) * 0.75))
        train.extend((token, x) for x in rows[:cut])
        test.extend((token, x) for x in rows[cut:])
    base_train = baseline_stats(train)
    base_test = baseline_stats(test)
    combos = []
    for size in (1, 2, 3):
        combos.extend(itertools.combinations(FEATURES, size))
    patterns = []
    for combo in combos:
        tr = event_stats(train, combo)
        te = event_stats(test, combo)
        bh = float(base_test.get("hit_25pct_30d") or 0)
        lift = float(te.get("hit_25pct_30d") or 0) / bh if bh > 0 else None
        robust = (
            int(tr.get("n") or 0) >= 40
            and int(te.get("n") or 0) >= 20
            and lift is not None
            and lift >= 1.20
            and float(te.get("median_max_30d_pct") or 0) > float(base_test.get("median_max_30d_pct") or 0)
        )
        patterns.append({
            "pattern": "+".join(combo),
            "features": list(combo),
            "train": tr,
            "test": te,
            "test_lift_vs_baseline_25pct": round(lift, 3) if lift is not None else None,
            "robust_candidate": robust,
        })
    patterns.sort(key=lambda x: (bool(x["robust_candidate"]), float(x.get("test_lift_vs_baseline_25pct") or 0), int((x.get("test") or {}).get("n") or 0)), reverse=True)
    return base_train, base_test, patterns


def score_candidate(token: dict, summary: dict, robust: list):
    cur = summary.get("current_features") or {}
    feats = cur.get("features") or {}
    matches = []
    score = 0.0
    for p in robust:
        required = p.get("features") or []
        if required and all(feats.get(x) for x in required):
            lift = float(p.get("test_lift_vs_baseline_25pct") or 0)
            n = int((p.get("test") or {}).get("n") or 0)
            matches.append({
                "pattern": p.get("pattern"),
                "lift": lift,
                "test_n": n,
                "median_max_30d_pct": (p.get("test") or {}).get("median_max_30d_pct"),
            })
            score += max(0.0, lift - 1.0) * min(2.0, math.log10(max(10, n)))
    liq = float(token.get("liquidity_usd") or 0)
    score += 0.35 if liq >= 100000 else (0.15 if liq >= 50000 else -0.5)
    if feats.get("price_not_extended"):
        score += 0.4
    if cur.get("ret7_pct") is not None and float(cur["ret7_pct"]) > 45:
        score -= 1.0
    return score, matches[:8]


def add_current_intelligence(candidates: list) -> list:
    try:
        import cross_domain_intelligence_collector as cross
        trending, boosts = cross.global_attention_maps()
    except Exception:
        return candidates
    for c in candidates[:20]:
        t = {"symbol": c.get("symbol"), "network": "solana", "contract": c.get("contract"), "pair": c.get("pair")}
        try:
            holder = cross.holder_snapshot(t)
        except Exception:
            holder = None
        try:
            news = cross.news_snapshot(t)
        except Exception:
            news = None
        c["current_intelligence_baseline"] = {
            "captured_at": now_iso(),
            "holder": holder,
            "news": news,
            "geckoterminal_trending_rank": trending.get(("solana", str(c.get("pair") or "").lower())),
            "dexscreener_paid_boost": boosts.get(("solana", str(c.get("contract") or ""))),
            "research_only": True,
        }
    return candidates


def aggregate() -> int:
    paths = sorted((RESEARCH / "batches").glob("solana-500-batch-*.json"))
    if not paths:
        paths = sorted(RESEARCH.glob("solana-500-batch-*.json"))
    if not paths:
        raise RuntimeError("NO_HISTORY_BATCHES")
    merged = []
    for path in paths:
        merged.extend(load(path, {}).get("tokens") or [])

    rows_by_token = {}
    summaries = []
    tokens_by_contract = {}
    for item in merged:
        token = item.get("token") or {}
        key = str(token.get("contract") or token.get("coingecko_id") or "")
        tokens_by_contract[key] = token
        obs, summary = token_analysis(item)
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
            "history_error": item.get("error"),
            **summary,
        })

    base_train, base_test, patterns = pattern_lab(rows_by_token)
    robust = [p for p in patterns if p.get("robust_candidate")][:20]

    candidates = []
    for s in summaries:
        token = tokens_by_contract.get(str(s.get("contract") or ""), {})
        score, matches = score_candidate(token, s, robust)
        if not matches:
            continue
        candidates.append({
            "symbol": s.get("symbol"),
            "name": s.get("name"),
            "contract": s.get("contract"),
            "pair": s.get("pair"),
            "dex_url": s.get("dex_url"),
            "solana_market_cap_rank": s.get("solana_market_cap_rank"),
            "market_cap": s.get("market_cap"),
            "liquidity_usd": s.get("liquidity_usd"),
            "research_score": round(score, 3),
            "matched_out_of_sample_patterns": matches,
            "current_features": s.get("current_features"),
            "research_only": True,
            "telegram_eligible": False,
        })
    candidates.sort(key=lambda x: x.get("research_score", -999), reverse=True)
    candidates = add_current_intelligence(candidates[:20])

    conclusions = [{
        "pattern": p.get("pattern"),
        "test_n": (p.get("test") or {}).get("n"),
        "test_hit_25pct_30d": (p.get("test") or {}).get("hit_25pct_30d"),
        "baseline_hit_25pct_30d": base_test.get("hit_25pct_30d"),
        "lift": p.get("test_lift_vs_baseline_25pct"),
        "median_max_30d_pct": (p.get("test") or {}).get("median_max_30d_pct"),
        "median_drawdown_30d_pct": (p.get("test") or {}).get("median_drawdown_30d_pct"),
    } for p in robust[:10]]

    write(FINAL, {
        "version": 1,
        "generated_at": now_iso(),
        "mode": "RESEARCH_ONLY_SOLANA_500_CONTEXT_WALK_FORWARD",
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "cohort_count": len(merged),
        "history_usable_count": len(rows_by_token),
        "methodology": {
            "ranking": "current Solana-native market-cap ranks 100..599 inclusive",
            "history": "up to 365 daily on-chain OHLCV candles from exact highest-liquidity current pair",
            "anti_lookahead": True,
            "validation": "chronological 75% train / 25% out-of-sample test per token",
            "same_pattern_overlap_control_days": 7,
            "primary_success": "future maximum >= +25% within 30 days",
            "survivorship_bias": True,
            "historical_intelligence_limit": "wallet/social/news point-in-time history is not reconstructed; live intelligence is captured prospectively for learning candidates",
        },
        "baseline_train": base_train,
        "baseline_test": base_test,
        "robust_context_patterns": robust,
        "conclusions": conclusions,
        "learning_candidates_count": len(candidates),
        "token_summaries": sorted(summaries, key=lambda x: x.get("solana_market_cap_rank") or 999999),
    })
    write(PATTERNS, {
        "version": 1,
        "generated_at": now_iso(),
        "mode": "RESEARCH_ONLY_PATTERN_PRIORS",
        "baseline_test": base_test,
        "patterns": patterns[:80],
        "production_rule": "Backtest patterns are priors only; never auto-promote to BUY without fresh cross-domain intelligence alignment.",
    })
    write(CANDIDATES, {
        "version": 1,
        "generated_at": now_iso(),
        "mode": "RESEARCH_ONLY_FORWARD_LEARNING",
        "telegram_eligible": False,
        "candidates": candidates,
    })
    print("SOLANA500_AGGREGATE", json.dumps({
        "cohort": len(merged),
        "history_usable": len(rows_by_token),
        "robust_patterns": len(robust),
        "learning_candidates": len(candidates),
        "baseline_test": base_test,
    }, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["universe", "history", "aggregate"])
    ap.add_argument("--batch", type=int, default=0)
    ap.add_argument("--batch-count", type=int, default=10)
    args = ap.parse_args()
    if args.phase == "universe":
        return build_universe()
    if args.phase == "history":
        return history_batch(args.batch, args.batch_count)
    return aggregate()


if __name__ == "__main__":
    raise SystemExit(main())
