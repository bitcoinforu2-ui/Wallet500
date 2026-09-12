from __future__ import annotations

import json
import math
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DATA = Path("data")
REAL_ALERTS = DATA / "real-alerts.json"
OUT = DATA / "trade-management.json"
MODE = "MANUAL_REVIEW_TRADE_MANAGEMENT_V1"
MIN_CANDLES = 20
MIN_LIQUIDITY_USD = 50_000.0
NETWORKS = {
    "ethereum": "eth", "eth": "eth", "bsc": "bsc", "bnb": "bsc",
    "solana": "solana", "base": "base", "arbitrum": "arbitrum",
    "optimism": "optimism", "polygon": "polygon_pos", "avalanche": "avax",
}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _request_json(url: str, timeout: int = 12) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _network(chain: Any) -> str | None:
    return NETWORKS.get(str(chain or "").strip().lower())


def fetch_market_bundle(row: dict[str, Any]) -> dict[str, Any] | None:
    network = _network(row.get("chain"))
    pair = str(row.get("pair_address") or "").strip()
    if not network or not pair:
        return None
    qpair = urllib.parse.quote(pair, safe="")
    root = f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{qpair}"
    pool = _request_json(root)
    ohlcv = _request_json(root + "/ohlcv/hour?aggregate=1&limit=48&currency=usd&token=base")
    if not isinstance(pool, dict) or not isinstance(ohlcv, dict):
        return None
    attrs = ((pool.get("data") or {}).get("attributes") or {})
    raw = (((ohlcv.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or [])
    candles = []
    for item in raw:
        if not isinstance(item, list) or len(item) < 6:
            continue
        vals = [_num(x) for x in item[:6]]
        if any(x is None for x in vals):
            continue
        candles.append({"ts": int(vals[0]), "open": vals[1], "high": vals[2], "low": vals[3], "close": vals[4], "volume": vals[5]})
    candles.sort(key=lambda x: x["ts"])
    tx = attrs.get("transactions") if isinstance(attrs.get("transactions"), dict) else {}
    h1tx = tx.get("h1") if isinstance(tx.get("h1"), dict) else {}
    volume = attrs.get("volume_usd") if isinstance(attrs.get("volume_usd"), dict) else {}
    return {
        "candles": candles,
        "price_usd": _num(attrs.get("base_token_price_usd")) or (candles[-1]["close"] if candles else None),
        "liquidity_usd": _num(attrs.get("reserve_in_usd")),
        "volume_h1_usd": _num(volume.get("h1")),
        "volume_h24_usd": _num(volume.get("h24")),
        "buys_h1": int(_num(h1tx.get("buys"), 0) or 0),
        "sells_h1": int(_num(h1tx.get("sells"), 0) or 0),
        "source": "GECKOTERMINAL_EXACT_POOL_OHLCV",
    }


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    out = sum(values[:period]) / period
    for value in values[period:]:
        out = alpha * value + (1.0 - alpha) * out
    return out


def _atr(candles: list[dict[str, float]], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    trs = []
    for prev, cur in zip(candles[-(period + 1):-1], candles[-period:]):
        trs.append(max(cur["high"] - cur["low"], abs(cur["high"] - prev["close"]), abs(cur["low"] - prev["close"])))
    return sum(trs) / len(trs) if trs else None


def _macd(candles: list[dict[str, float]]) -> tuple[float | None, float | None, float | None]:
    closes = [float(c["close"]) for c in candles]
    if len(closes) < 35:
        return None, None, None
    # Build a short MACD series so the signal line is calculated prospectively.
    series = []
    for i in range(26, len(closes) + 1):
        part = closes[:i]
        e12, e26 = _ema(part, 12), _ema(part, 26)
        if e12 is not None and e26 is not None:
            series.append(e12 - e26)
    macd = series[-1] if series else None
    signal = _ema(series, 9) if len(series) >= 9 else None
    hist = macd - signal if macd is not None and signal is not None else None
    return macd, signal, hist


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1.0) * 100.0


def _zone(center: float | None, atr: float | None, lower_mult: float, upper_mult: float) -> dict[str, float | None]:
    if center is None or atr is None:
        return {"low": None, "high": None}
    return {"low": round(max(0.0, center - lower_mult * atr), 10), "high": round(center + upper_mult * atr, 10)}


def analyze(alert: dict[str, Any], market: dict[str, Any] | None, observed_at: str | None = None) -> dict[str, Any]:
    now = observed_at or datetime.now(timezone.utc).isoformat()
    symbol = alert.get("symbol") or "TOKEN"
    signal_price = _num(alert.get("price_usd") or alert.get("dex_price_usd"))
    signal_liq = _num(alert.get("execution_pool_liquidity_usd") or alert.get("liquidity_usd") or alert.get("provider_reported_pool_value_usd"))
    base = {
        "symbol": symbol, "chain": alert.get("chain"), "token_address": alert.get("token_address"),
        "pair_address": alert.get("pair_address"), "dex_url": alert.get("dex_url"),
        "alert_id": alert.get("alert_id"), "signal_price_usd": signal_price,
        "signal_liquidity_usd": signal_liq, "signal_generated_at": alert.get("generated_at") or alert.get("promoted_at"),
        "readiness": "7/7", "manual_review_only": True, "automatic_buy": False, "automatic_sell": False,
        "observed_at": now,
    }
    if not isinstance(market, dict) or len(market.get("candles") or []) < MIN_CANDLES:
        return {**base, "trade_state": "DATA_INSUFFICIENT", "state_label": "⚪ DATA INSUFFICIENT", "decision_reason": "Exact-pair OHLCV is not yet sufficient; fail closed.", "entry_plan": None, "exit_plan": None}

    candles = market["candles"]
    closes = [float(c["close"]) for c in candles]
    current = _num(market.get("price_usd")) or closes[-1]
    liq = _num(market.get("liquidity_usd"))
    ema5, ema10, ema20, ema30 = (_ema(closes, p) for p in (5, 10, 20, 30))
    atr = _atr(candles, 14)
    macd, macd_signal, macd_hist = _macd(candles)
    recent = candles[-12:] if len(candles) >= 12 else candles
    recent_high = max(float(c["high"]) for c in recent)
    prior_high = max(float(c["high"]) for c in candles[-13:-1]) if len(candles) >= 13 else recent_high
    drawdown = _pct(current, recent_high)
    signal_move = _pct(current, signal_price)
    liq_change = _pct(liq, signal_liq)
    volume_h1 = _num(market.get("volume_h1_usd"))
    vol_hist = [float(c["volume"]) for c in candles[-13:-1] if _num(c.get("volume")) is not None]
    vol_median = statistics.median(vol_hist) if vol_hist else None
    volume_ratio = (volume_h1 / vol_median) if volume_h1 is not None and vol_median and vol_median > 0 else None
    buys, sells = int(market.get("buys_h1") or 0), int(market.get("sells_h1") or 0)
    buy_ratio = buys / max(1, buys + sells)
    atr_pct = (atr / current * 100.0) if atr and current else None

    z1 = _zone(ema10, atr, 0.45, 0.20)
    z2 = _zone(ema20, atr, 0.45, 0.20)
    breakout = prior_high
    invalidation = None
    if ema30 is not None and atr is not None:
        invalidation = max(0.0, ema30 - 0.75 * atr)
    target1 = recent_high
    target2 = recent_high + atr if atr is not None else None
    target3 = recent_high + 2 * atr if atr is not None else None

    liquidity_bad = liq is None or liq < MIN_LIQUIDITY_USD or (liq_change is not None and liq_change <= -40)
    structure_broken = ema30 is not None and atr is not None and current < ema30 - 0.5 * atr
    momentum_negative = macd_hist is not None and macd_hist < 0 and ema10 is not None and current < ema10
    extended = ema10 is not None and atr is not None and current > ema10 + max(0.75 * atr, current * 0.03)
    parabolic_signal = signal_move is not None and signal_move >= 12
    support_zone = z1["low"] is not None and z1["low"] <= current <= z1["high"]
    deeper_support = z2["low"] is not None and z2["low"] <= current <= z2["high"]
    support_healthy = not liquidity_bad and buy_ratio >= 0.45 and (macd_hist is None or macd_hist >= 0 or current >= (ema20 or current))
    breakout_retest = breakout is not None and atr is not None and current >= breakout - 0.35 * atr and current <= breakout + 0.35 * atr and buy_ratio >= 0.5 and not liquidity_bad
    profit_fade = signal_move is not None and signal_move >= 15 and drawdown is not None and drawdown <= -6 and macd_hist is not None and macd_hist < 0

    if liquidity_bad or (structure_broken and momentum_negative):
        state, label, reason = "INVALIDATED", "🔴 EXIT / INVALIDATED", "Liquidity or 1h structure failed the post-alert guardrails."
    elif profit_fade:
        state, label, reason = "EXIT_REVIEW", "🔴 TAKE PROFIT / EXIT REVIEW", "The move remains profitable from signal but momentum has rolled over from the recent high."
    elif (support_zone or deeper_support) and support_healthy:
        state, label, reason = "BUY_ZONE", "🟢 BUY ZONE", "Price retested dynamic support while liquidity and transaction balance remain acceptable."
    elif breakout_retest and current > (signal_price or 0):
        state, label, reason = "BREAKOUT_RETEST", "🟢 BREAKOUT RETEST", "Price is retesting the recent breakout with acceptable liquidity and buy/sell balance."
    elif extended or parabolic_signal:
        state, label, reason = "WAIT_FOR_RETEST", "🟡 WAIT FOR RETEST", "The 7/7 signal is valid, but price is extended from dynamic support; do not chase."
    else:
        state, label, reason = "WAIT_FOR_ENTRY", "🟡 WAIT FOR ENTRY", "Signal remains valid but no high-quality support/retest entry is confirmed yet."

    return {
        **base,
        "trade_state": state, "state_label": label, "decision_reason": reason,
        "market": {
            "current_price_usd": round(current, 10), "liquidity_usd": liq,
            "liquidity_change_from_signal_pct": round(liq_change, 3) if liq_change is not None else None,
            "volume_h1_usd": volume_h1, "volume_h24_usd": _num(market.get("volume_h24_usd")),
            "volume_vs_12h_median": round(volume_ratio, 3) if volume_ratio is not None else None,
            "buys_h1": buys, "sells_h1": sells, "buy_ratio": round(buy_ratio, 4),
            "move_from_signal_pct": round(signal_move, 3) if signal_move is not None else None,
            "drawdown_from_12h_high_pct": round(drawdown, 3) if drawdown is not None else None,
            "source": market.get("source"),
        },
        "technicals_1h": {
            "ema5": round(ema5, 10) if ema5 is not None else None,
            "ema10": round(ema10, 10) if ema10 is not None else None,
            "ema20": round(ema20, 10) if ema20 is not None else None,
            "ema30": round(ema30, 10) if ema30 is not None else None,
            "atr14": round(atr, 10) if atr is not None else None,
            "atr14_pct": round(atr_pct, 3) if atr_pct is not None else None,
            "macd": round(macd, 10) if macd is not None else None,
            "macd_signal": round(macd_signal, 10) if macd_signal is not None else None,
            "macd_hist": round(macd_hist, 10) if macd_hist is not None else None,
            "recent_high_12h": round(recent_high, 10), "prior_high": round(prior_high, 10),
            "candle_count": len(candles),
        },
        "entry_plan": {
            "zone_1": z1, "zone_2": z2,
            "breakout_retest_reference": round(breakout, 10) if breakout is not None else None,
            "invalidation_reference": round(invalidation, 10) if invalidation is not None else None,
            "policy": "MANUAL_REVIEW_ONLY_DYNAMIC_LEVELS_NOT_ORDERS",
        },
        "exit_plan": {
            "target_1_recent_high": round(target1, 10),
            "target_2_plus_1atr": round(target2, 10) if target2 is not None else None,
            "target_3_plus_2atr": round(target3, 10) if target3 is not None else None,
            "policy": "PARTIAL_PROFIT_OR_EXIT_REVIEW_ONLY_NO_AUTOMATIC_SELL",
        },
    }


def build(real_alerts: dict[str, Any], fetcher: Callable[[dict[str, Any]], dict[str, Any] | None] = fetch_market_bundle, observed_at: str | None = None) -> dict[str, Any]:
    alerts = real_alerts.get("alerts") if isinstance(real_alerts, dict) and isinstance(real_alerts.get("alerts"), list) else []
    rows = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        readiness = int(alert.get("readiness_passed") or alert.get("canonical_readiness_passed") or 7)
        total = int(alert.get("readiness_total") or alert.get("canonical_readiness_total") or 7)
        if readiness != 7 or total != 7 or not alert.get("token_address") or not alert.get("pair_address"):
            continue
        rows.append(analyze(alert, fetcher(alert), observed_at=observed_at))
    return {
        "version": 1, "mode": MODE, "generated_at": observed_at or datetime.now(timezone.utc).isoformat(),
        "manual_review_only": True, "automatic_trade": False,
        "truth_contract": {
            "input_requires_real_alert_7_of_7": True, "exact_pair_required": True,
            "minimum_liquidity_usd": MIN_LIQUIDITY_USD, "ohlcv_timeframe": "1h",
            "no_automatic_buy": True, "no_automatic_sell": True, "signal_gate_unchanged": True,
            "recommendations_are_execution_timing_support_not_new_signal": True,
        },
        "managed_count": len(rows),
        "state_counts": {state: sum(1 for r in rows if r.get("trade_state") == state) for state in sorted({r.get("trade_state") for r in rows})},
        "positions": rows,
    }


def run(data_dir: str | Path = DATA) -> dict[str, Any]:
    data = Path(data_dir)
    payload = build(_load(data / REAL_ALERTS.name, {}))
    _write(data / OUT.name, payload)
    print(json.dumps({"mode": payload["mode"], "managed_count": payload["managed_count"], "state_counts": payload["state_counts"]}, indent=2))
    return payload


if __name__ == "__main__":
    run()
