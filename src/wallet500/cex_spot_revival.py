from __future__ import annotations

import gzip
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

UA = {"User-Agent": "Wallet500/1.5", "Accept": "application/json"}
WATCH_SCORE = 25
ALERT_SCORE = 35


def _get(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _f(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _pct(cur, prev):
    try:
        cur = float(cur)
        prev = float(prev)
        if prev == 0:
            return 0.0
        return (cur / prev - 1.0) * 100.0
    except Exception:
        return 0.0


def _norm_symbol(symbol: str) -> str:
    return (symbol or "").upper().strip().replace("-", "").replace("_", "").replace("/", "")


def _row(exchange: str, symbol: str, price=0, change=0, volume=0, market_id=None):
    return {
        "exchange": exchange,
        "market_type": "spot",
        "symbol": _norm_symbol(symbol),
        "market_id": market_id or symbol,
        "price": _f(price),
        "change_24h_pct": _f(change),
        "volume_24h": _f(volume),
    }


def gate_spot():
    rows = _get("https://api.gateio.ws/api/v4/spot/tickers")
    return [
        _row(
            "gate",
            x.get("currency_pair", ""),
            x.get("last"),
            x.get("change_percentage"),
            x.get("quote_volume"),
            x.get("currency_pair"),
        )
        for x in rows
        if str(x.get("currency_pair", "")).endswith("_USDT")
    ]


def bybit_spot():
    rows = ((_get("https://api.bybit.com/v5/market/tickers?category=spot").get("result") or {}).get("list") or [])
    return [
        _row(
            "bybit",
            x.get("symbol", ""),
            x.get("lastPrice"),
            _f(x.get("price24hPcnt")) * 100.0,
            x.get("turnover24h"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("USDT")
    ]


def okx_spot():
    rows = _get("https://www.okx.com/api/v5/market/tickers?instType=SPOT").get("data", []) or []
    out = []
    for x in rows:
        market = str(x.get("instId", ""))
        if not market.endswith("-USDT"):
            continue
        last = _f(x.get("last"))
        open24h = _f(x.get("open24h"))
        change = (last / open24h - 1.0) * 100.0 if last and open24h else 0.0
        out.append(_row("okx", market, last, change, x.get("volCcy24h"), market))
    return out


def mexc_spot():
    rows = _get("https://api.mexc.com/api/v3/ticker/24hr")
    if isinstance(rows, dict):
        rows = [rows]
    return [
        _row(
            "mexc",
            x.get("symbol", ""),
            x.get("lastPrice"),
            x.get("priceChangePercent"),
            x.get("quoteVolume"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("USDT")
    ]


def kucoin_spot():
    rows = ((_get("https://api.kucoin.com/api/v1/market/allTickers").get("data") or {}).get("ticker") or [])
    return [
        _row(
            "kucoin",
            x.get("symbol", ""),
            x.get("last"),
            _f(x.get("changeRate")) * 100.0,
            x.get("volValue"),
            x.get("symbol"),
        )
        for x in rows
        if str(x.get("symbol", "")).endswith("-USDT")
    ]


SPOT_SOURCES = [
    ("gate", gate_spot),
    ("bybit", bybit_spot),
    ("okx", okx_spot),
    ("mexc", mexc_spot),
    ("kucoin", kucoin_spot),
]


def _load_state(path: Path, default):
    gz = Path(str(path) + ".gz")
    try:
        if gz.exists():
            with gzip.open(gz, "rt", encoding="utf-8") as f:
                return json.load(f)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _write_state(path: Path, state: dict) -> None:
    gz = Path(str(path) + ".gz")
    tmp = Path(str(gz) + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(state, f, separators=(",", ":"))
    tmp.replace(gz)
    if path.exists():
        path.unlink()


def _enrich(rows: list[dict], state: dict, now: str):
    histories = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    enriched = []
    for row in rows:
        key = f"spot:{row['exchange']}:{row['symbol']}"
        hist = histories.get(key) if isinstance(histories.get(key), list) else []
        prev = hist[-1] if hist else {}
        enriched.append(
            {
                **row,
                "price_delta_pct": round(_pct(row.get("price"), prev.get("price")), 4) if prev else 0.0,
                "volume24_delta_pct": round(_pct(row.get("volume_24h"), prev.get("volume_24h")), 4) if prev else 0.0,
                "history_points": len(hist),
            }
        )
        hist.append(
            {
                "observed_at": now,
                "price": row.get("price"),
                "change_24h_pct": row.get("change_24h_pct"),
                "volume_24h": row.get("volume_24h"),
            }
        )
        histories[key] = hist[-96:]
    return enriched, {
        "version": 1,
        "updated_at": now,
        "markets": histories,
        "signal_milestones": state.get("signal_milestones") if isinstance(state.get("signal_milestones"), dict) else {},
    }


def _market_signal(row: dict) -> dict:
    change = _f(row.get("change_24h_pct"))
    price_acc = _f(row.get("price_delta_pct"))
    volume_acc = _f(row.get("volume24_delta_pct"))
    volume = _f(row.get("volume_24h"))
    score = 0
    hits = []
    reasons = []

    if change >= 8:
        score += 10
        hits.append("MOMENTUM")
        reasons.append(f"24h spot momentum {change:.1f}%")
    if change >= 20:
        score += 10
    if change >= 50:
        score += 5
    if price_acc >= 2:
        score += 15
        hits.append("PRICE_ACCEL")
        reasons.append(f"spot price acceleration {price_acc:.2f}%/scan")
    if price_acc >= 5:
        score += 10
    if volume_acc >= 8:
        score += 12
        hits.append("VOLUME_ACCEL")
        reasons.append(f"spot volume acceleration {volume_acc:.1f}%/scan")
    if volume_acc >= 25:
        score += 8
    if volume >= 100_000:
        score += 3
        reasons.append("spot turnover >= $100k")
    if volume >= 1_000_000:
        score += 2

    return {
        "exchange": row.get("exchange"),
        "score": score,
        "hits": hits,
        "hit_count": len(hits),
        "reasons": reasons,
        "change": change,
        "price_acc": price_acc,
        "volume_acc": volume_acc,
    }


def _snapshot(now: str, markets: list[dict], score: int, coherent_conf: int, kind: str, best: dict) -> dict:
    ref = max(markets, key=lambda x: (_f(x.get("volume_24h")), _f(x.get("price"))), default={})
    return {
        "kind": kind,
        "observed_at": now,
        "reference_exchange": ref.get("exchange"),
        "reference_price": _f(ref.get("price")),
        "reference_change_24h_pct": _f(ref.get("change_24h_pct")),
        "score": min(int(score), 100),
        "confirmations": len({x.get("exchange") for x in markets}),
        "coherent_confirmations": coherent_conf,
        "coherent_exchange": best.get("exchange"),
        "coherent_feature_hits": best.get("hits", []),
        "price_acceleration_max_pct": round(max((_f(x.get("price_delta_pct")) for x in markets), default=0), 4),
        "volume_acceleration_max_pct": round(max((_f(x.get("volume24_delta_pct")) for x in markets), default=0), 4),
        "change_24h_max_pct": round(max((_f(x.get("change_24h_pct")) for x in markets), default=0), 4),
    }


def run_cex_spot_revival(out: Path, now: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    errors = []
    health = {}
    with ThreadPoolExecutor(max_workers=len(SPOT_SOURCES)) as pool:
        futures = {pool.submit(fn): name for name, fn in SPOT_SOURCES}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                got = fut.result()
                rows.extend(got)
                health[name] = {"ok": bool(got), "markets": len(got)}
            except Exception as exc:
                errors.append({"exchange": name, "error": str(exc)[:300]})
                health[name] = {"ok": False, "markets": 0}

    state_path = out / "cex-spot-state.json"
    rows, state = _enrich(rows, _load_state(state_path, {}), now)
    milestones = state["signal_milestones"]
    groups = {}
    for row in rows:
        if row.get("symbol", "").endswith("USDT"):
            groups.setdefault(row["symbol"], []).append(row)

    watchlist = []
    alerts = []
    for symbol, markets in groups.items():
        local = [_market_signal(x) for x in markets]
        best = max(local, key=lambda x: (x["score"], x["hit_count"]), default={"score": 0, "hit_count": 0, "reasons": []})
        coherent = [x for x in local if x.get("hit_count", 0) > 0]
        coherent_conf = len({x.get("exchange") for x in coherent if x.get("exchange")})
        score = int(best.get("score", 0))
        reasons = list(best.get("reasons") or [])
        if coherent_conf >= 2:
            score += 8
            reasons.append(f"{coherent_conf} coherent spot exchange confirmation")
        if coherent_conf >= 4:
            score += 8
        score = min(score, 100)

        ms = milestones.setdefault(symbol, {})
        first = _snapshot(now, markets, score, coherent_conf, "FIRST_SEEN", best)
        if "first_seen" not in ms:
            ms["first_seen"] = first
        if best.get("hit_count") and "first_anomaly" not in ms:
            ms["first_anomaly"] = {**first, "kind": "FIRST_ANOMALY"}
        if score >= WATCH_SCORE and "first_watch" not in ms:
            ms["first_watch"] = {**first, "kind": "FIRST_WATCH"}
        if score >= ALERT_SCORE and "first_alert" not in ms:
            ms["first_alert"] = {**first, "kind": "FIRST_ALERT"}

        record = {
            "symbol": symbol,
            "market_type": "spot",
            "spot_revival_score": score,
            "status": "DNA_WATCH_RESEARCH" if score >= ALERT_SCORE else "MOMENTUM_WATCH_RESEARCH",
            "research_only": True,
            "actionable": False,
            "identity_required_before_actionable": True,
            "reasons": reasons,
            "confirmations": len({x.get("exchange") for x in markets}),
            "coherent_confirmations": coherent_conf,
            "coherent_exchange": best.get("exchange"),
            "coherent_feature_hits": best.get("hits", []),
            "change_24h_max_pct": round(max((_f(x.get("change_24h_pct")) for x in markets), default=0), 4),
            "price_acceleration_max_pct": round(max((_f(x.get("price_delta_pct")) for x in markets), default=0), 4),
            "volume_acceleration_max_pct": round(max((_f(x.get("volume24_delta_pct")) for x in markets), default=0), 4),
            "exchanges": sorted({x.get("exchange") for x in markets if x.get("exchange")}),
            "milestones": ms,
            "markets": markets,
        }
        if score >= WATCH_SCORE:
            watchlist.append(record)
        if score >= ALERT_SCORE:
            alerts.append(record)

    _write_state(state_path, state)
    watchlist.sort(key=lambda x: (x["spot_revival_score"], x["coherent_confirmations"], x["confirmations"]), reverse=True)
    alerts.sort(key=lambda x: (x["spot_revival_score"], x["coherent_confirmations"], x["confirmations"]), reverse=True)

    payload = {
        "version": 1,
        "generated_at": now,
        "mode": "RESEARCH_ONLY_CEX_SPOT_REVIVAL_V1",
        "production_portfolio_impact": "NONE",
        "symbol_only_actionable": False,
        "identity_rule": "EXACT_CHAIN_CONTRACT_AND_PAIR_REQUIRED_BEFORE_ANY_ACTIONABLE_PROMOTION",
        "requested_sources": [name for name, _ in SPOT_SOURCES],
        "source_health": health,
        "healthy_sources": sum(1 for x in health.values() if x.get("ok")),
        "markets_seen": len(rows),
        "symbols_seen": len(groups),
        "watch_score": WATCH_SCORE,
        "alert_score": ALERT_SCORE,
        "watch_count": len(watchlist),
        "alerts_count": len(alerts),
        "watchlist": watchlist[:100],
        "alerts": alerts[:100],
        "errors": errors,
    }
    (out / "cex-spot-revival-radar.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    learning = {
        "version": 1,
        "updated_at": now,
        "purpose": "learn whether spot price+volume acceleration predicts veteran-token revival before late pumps",
        "research_only": True,
        "no_hindsight": True,
        "features": ["spot_24h_momentum", "spot_price_acceleration", "spot_volume_acceleration", "cross_exchange_spot_confirmation"],
        "top_candidates": [
            {
                "symbol": x["symbol"],
                "score": x["spot_revival_score"],
                "status": x["status"],
                "confirmations": x["confirmations"],
                "coherent_confirmations": x["coherent_confirmations"],
                "coherent_feature_hits": x["coherent_feature_hits"],
                "change_24h_max_pct": x["change_24h_max_pct"],
                "price_acceleration_max_pct": x["price_acceleration_max_pct"],
                "volume_acceleration_max_pct": x["volume_acceleration_max_pct"],
                "milestones": x.get("milestones", {}),
            }
            for x in watchlist[:50]
        ],
    }
    (out / "cex-spot-learning.json").write_text(json.dumps(learning, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    from datetime import datetime, timezone

    print(json.dumps(run_cex_spot_revival(Path("data"), datetime.now(timezone.utc).isoformat()), indent=2))
