from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

DATA = Path("data")
USER_BUY_STATE = DATA / "user-watch-final-buy-state.json"
REAL_LEDGER = DATA / "real-alert-10usd-ledger.json"
STATE_PATH = DATA / "post-buy-guardian-state.json"
REPORT_PATH = DATA / "post-buy-guardian-report.json"
MODE = "POST_BUY_GUARDIAN_V1"

TRACKING_TTL_HOURS = 72
MIN_LIQUIDITY_USD = 50_000.0
WARNING_LIQUIDITY_DROP_PCT = -15.0
EXIT_LIQUIDITY_DROP_PCT = -30.0
INVALID_LIQUIDITY_DROP_PCT = -40.0
WARNING_DRAWDOWN_FROM_PEAK_PCT = -6.0
EXIT_DRAWDOWN_FROM_PEAK_PCT = -10.0
HARD_STOP_FROM_BUY_PCT = -8.0
WARNING_RETURN_FROM_BUY_PCT = -4.0
WARNING_FAST_FLOW_RATIO = 0.90
EXIT_FAST_FLOW_RATIO = 0.70
WARNING_MOMENTUM_15M_PCT = -3.0
EXIT_MOMENTUM_15M_PCT = -5.0
MIN_FAST_FLOW_ACTIVITY = 10
DELIVERY_COOLDOWN_MINUTES = 15

NETWORKS = {
    "ethereum": "eth", "eth": "eth", "bsc": "bsc", "bnb": "bsc",
    "solana": "solana", "base": "base", "arbitrum": "arbitrum",
    "optimism": "optimism", "polygon": "polygon_pos", "avalanche": "avax",
}
EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
DEX_CHAIN_SLUGS = {
    "ethereum": "ethereum", "eth": "ethereum", "bsc": "bsc", "bnb": "bsc",
    "solana": "solana", "base": "base", "arbitrum": "arbitrum",
    "optimism": "optimism", "polygon": "polygon", "avalanche": "avalanche",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _parse_ts(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        raw = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def _norm(chain: str, value: Any) -> str:
    text = str(value or "").strip()
    return text.lower() if chain.lower() in EVM else text


def _identity_parts(key: Any) -> tuple[str, str, str] | None:
    parts = str(key or "").strip().split(":", 2)
    if len(parts) != 3:
        return None
    chain, token, pair = parts
    if not chain or not token or not pair or chain.lower() == "cex":
        return None
    return chain.lower(), _norm(chain, token), _norm(chain, pair)


def _exact_key(chain: Any, token: Any, pair: Any) -> str:
    c = str(chain or "").strip().lower()
    t, p = _norm(c, token), _norm(c, pair)
    return f"{c}:{t}:{p}" if c and t and p else ""


def _dex_url(row: dict[str, Any]) -> str:
    existing = str(row.get("dex_url") or "").strip()
    if existing.startswith(("https://", "http://")):
        return existing
    chain = str(row.get("chain") or "").strip().lower()
    pair = str(row.get("pair_address") or "").strip()
    slug = DEX_CHAIN_SLUGS.get(chain)
    if not slug or not pair:
        return ""
    return f"https://dexscreener.com/{slug}/{urllib.parse.quote(pair, safe='')}"


def _request_json(url: str, timeout: int = 12) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Wallet500/2.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _parse_tx(bucket: Any) -> tuple[int, int]:
    row = bucket if isinstance(bucket, dict) else {}
    return int(_num(row.get("buys"), 0) or 0), int(_num(row.get("sells"), 0) or 0)


def _gecko_market(row: dict[str, Any]) -> dict[str, Any] | None:
    network = NETWORKS.get(str(row.get("chain") or "").lower())
    pair = str(row.get("pair_address") or "").strip()
    if not network or not pair:
        return None
    root = f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{urllib.parse.quote(pair, safe='')}"
    pool = _request_json(root)
    if not isinstance(pool, dict):
        return None
    ohlcv = _request_json(root + "/ohlcv/minute?aggregate=5&limit=60&currency=usd&token=base")
    attrs = ((pool.get("data") or {}).get("attributes") or {})
    raw = (((ohlcv or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    candles: list[dict[str, float]] = []
    for item in raw:
        if not isinstance(item, list) or len(item) < 6:
            continue
        vals = [_num(x) for x in item[:6]]
        if any(v is None for v in vals):
            continue
        candles.append({
            "ts": int(vals[0]), "open": float(vals[1]), "high": float(vals[2]),
            "low": float(vals[3]), "close": float(vals[4]), "volume": float(vals[5]),
        })
    candles.sort(key=lambda x: x["ts"])
    tx = attrs.get("transactions") if isinstance(attrs.get("transactions"), dict) else {}
    volume = attrs.get("volume_usd") if isinstance(attrs.get("volume_usd"), dict) else {}
    m5b, m5s = _parse_tx(tx.get("m5"))
    m15b, m15s = _parse_tx(tx.get("m15"))
    h1b, h1s = _parse_tx(tx.get("h1"))
    price = _num(attrs.get("base_token_price_usd")) or (candles[-1]["close"] if candles else None)
    return {
        "price_usd": price,
        "liquidity_usd": _num(attrs.get("reserve_in_usd")),
        "volume_m5_usd": _num(volume.get("m5")),
        "volume_h1_usd": _num(volume.get("h1")),
        "buys_m5": m5b, "sells_m5": m5s,
        "buys_m15": m15b, "sells_m15": m15s,
        "buys_h1": h1b, "sells_h1": h1s,
        "candles_5m": candles,
        "source": "GECKOTERMINAL_EXACT_POOL_5M",
    }


def _dex_market(row: dict[str, Any]) -> dict[str, Any] | None:
    chain = str(row.get("chain") or "").strip().lower()
    pair = str(row.get("pair_address") or "").strip()
    if not chain or not pair:
        return None
    dex_chain = {"eth": "ethereum", "bnb": "bsc"}.get(chain, chain)
    url = f"https://api.dexscreener.com/latest/dex/pairs/{urllib.parse.quote(dex_chain, safe='')}/{urllib.parse.quote(pair, safe='')}"
    payload = _request_json(url)
    rows = payload.get("pairs") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    want = _norm(chain, pair)
    match = next((x for x in rows if isinstance(x, dict) and _norm(chain, x.get("pairAddress")) == want), None)
    if not isinstance(match, dict):
        return None
    tx = match.get("txns") if isinstance(match.get("txns"), dict) else {}
    vol = match.get("volume") if isinstance(match.get("volume"), dict) else {}
    liq = match.get("liquidity") if isinstance(match.get("liquidity"), dict) else {}
    m5b, m5s = _parse_tx(tx.get("m5"))
    h1b, h1s = _parse_tx(tx.get("h1"))
    change = match.get("priceChange") if isinstance(match.get("priceChange"), dict) else {}
    return {
        "price_usd": _num(match.get("priceUsd")),
        "liquidity_usd": _num(liq.get("usd")),
        "volume_m5_usd": _num(vol.get("m5")),
        "volume_h1_usd": _num(vol.get("h1")),
        "buys_m5": m5b, "sells_m5": m5s,
        "buys_m15": 0, "sells_m15": 0,
        "buys_h1": h1b, "sells_h1": h1s,
        "candles_5m": [],
        "price_change_m5_pct": _num(change.get("m5")),
        "price_change_h1_pct": _num(change.get("h1")),
        "source": "DEXSCREENER_EXACT_PAIR_FALLBACK",
    }


def fetch_market(row: dict[str, Any]) -> dict[str, Any] | None:
    primary = _gecko_market(row)
    if isinstance(primary, dict) and (_num(primary.get("price_usd"), 0) or 0) > 0:
        return primary
    return _dex_market(row)


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    out = sum(values[:period]) / period
    for value in values[period:]:
        out = alpha * value + (1.0 - alpha) * out
    return out


def _pct(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline <= 0:
        return None
    return (current / baseline - 1.0) * 100.0


def _flow_ratio(buys: int, sells: int) -> float | None:
    return (buys + 1.0) / (sells + 1.0) if buys + sells >= MIN_FAST_FLOW_ACTIVITY else None


def _momentum_15m(candles: list[dict[str, Any]], market: dict[str, Any]) -> float | None:
    if len(candles) >= 4:
        return _pct(_num(candles[-1].get("close")), _num(candles[-4].get("close")))
    return _num(market.get("price_change_m5_pct"))


def _source_positions(user_state: dict[str, Any], real_ledger: dict[str, Any], now: datetime) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    # Production user-watch state stores durable rows under "targets".
    # Accept the earlier "tokens" key as a migration fallback.
    if isinstance(user_state, dict) and isinstance(user_state.get("targets"), dict):
        targets = user_state.get("targets") or {}
    elif isinstance(user_state, dict) and isinstance(user_state.get("tokens"), dict):
        targets = user_state.get("tokens") or {}
    else:
        targets = {}
    for key, state in targets.items():
        if not isinstance(state, dict) or state.get("last_delivery_status") != "DELIVERED":
            continue
        alert_at = _parse_ts(state.get("last_alert_at"))
        entry = _num(state.get("last_alert_price"), 0) or 0.0
        parts = _identity_parts(state.get("identity_key") or key)
        if not alert_at or entry <= 0 or not parts or now - alert_at > timedelta(hours=TRACKING_TTL_HOURS):
            continue
        chain, token, pair = parts
        exact = _exact_key(chain, token, pair)
        out[exact] = {
            "key": exact, "symbol": str(state.get("symbol") or "TOKEN"),
            "chain": chain, "token_address": token, "pair_address": pair,
            "dex_url": state.get("dex_url") or state.get("last_dex_url"),
            "entry_price_usd": entry, "entry_time": alert_at.isoformat(),
            "entry_liquidity_hint_usd": _num(state.get("last_liquidity")),
            "source": "UNIFIED_WATCH_FINAL_BUY_DELIVERED",
        }

    for pos in (real_ledger.get("positions") or []) if isinstance(real_ledger, dict) else []:
        if not isinstance(pos, dict) or pos.get("status") != "ACTIVE_TRACKING":
            continue
        entry_at = _parse_ts(pos.get("entry_time"))
        entry = _num(pos.get("entry_price_usd"), 0) or 0.0
        exact = _exact_key(pos.get("chain"), pos.get("token_address"), pos.get("pair_address"))
        if not exact or not entry_at or entry <= 0 or now - entry_at > timedelta(hours=TRACKING_TTL_HOURS):
            continue
        out.setdefault(exact, {
            "key": exact, "symbol": str(pos.get("symbol") or "TOKEN"),
            "chain": str(pos.get("chain") or "").lower(),
            "token_address": pos.get("token_address"), "pair_address": pos.get("pair_address"),
            "dex_url": pos.get("dex_url"),
            "entry_price_usd": entry, "entry_time": entry_at.isoformat(),
            "entry_liquidity_hint_usd": _num(pos.get("entry_liquidity_usd")),
            "source": "CANONICAL_REAL_ALERT_DELIVERED",
        })
    return out


def evaluate_position(source: dict[str, Any], market: dict[str, Any] | None, prior: dict[str, Any] | None, observed_at: str) -> dict[str, Any]:
    prior = dict(prior or {})
    entry = _num(source.get("entry_price_usd"), 0) or 0.0
    if not isinstance(market, dict) or (_num(market.get("price_usd"), 0) or 0) <= 0:
        return {
            **prior, **source, "observed_at": observed_at, "risk_state": "DATA_DEGRADED",
            "risk_label": "⚪ DATA DEGRADED",
            "data_miss_streak": int(prior.get("data_miss_streak") or 0) + 1,
            "reasons": ["EXACT_PAIR_LIVE_DATA_UNAVAILABLE"],
            "manual_review_only": True, "automatic_sell": False,
        }

    current = _num(market.get("price_usd"), 0) or 0.0
    liquidity = _num(market.get("liquidity_usd"))
    baseline_liq = _num(prior.get("baseline_liquidity_usd"))
    if baseline_liq is None or baseline_liq <= 0:
        baseline_liq = _num(source.get("entry_liquidity_hint_usd")) or liquidity

    prior_peak = _num(prior.get("peak_price_usd"), entry) or entry
    peak = max(entry, prior_peak, current)
    return_from_buy = _pct(current, entry)
    drawdown_from_peak = _pct(current, peak)
    liquidity_change = _pct(liquidity, baseline_liq)

    m5b, m5s = int(market.get("buys_m5") or 0), int(market.get("sells_m5") or 0)
    m15b, m15s = int(market.get("buys_m15") or 0), int(market.get("sells_m15") or 0)
    h1b, h1s = int(market.get("buys_h1") or 0), int(market.get("sells_h1") or 0)
    fast_ratio, fast_window = _flow_ratio(m5b, m5s), "5m"
    if fast_ratio is None:
        fast_ratio, fast_window = _flow_ratio(m15b, m15s), "15m"
    if fast_ratio is None:
        fast_ratio, fast_window = _flow_ratio(h1b, h1s), "1h"

    candles = [x for x in (market.get("candles_5m") or []) if isinstance(x, dict)]
    closes = [float(x["close"]) for x in candles if _num(x.get("close")) is not None]
    ema9, ema21 = _ema(closes, 9), _ema(closes, 21)
    momentum15 = _momentum_15m(candles, market)
    structure_break = bool(ema9 is not None and ema21 is not None and current < ema9 and ema9 < ema21)

    warning: list[str] = []
    severe: list[str] = []
    invalid: list[str] = []
    if liquidity is not None and liquidity < MIN_LIQUIDITY_USD:
        invalid.append("LIQUIDITY_BELOW_50K")
    if liquidity_change is not None and liquidity_change <= INVALID_LIQUIDITY_DROP_PCT:
        invalid.append("LIQUIDITY_COLLAPSE_GE_40PCT")
    if return_from_buy is not None and return_from_buy <= HARD_STOP_FROM_BUY_PCT:
        severe.append("PRICE_BELOW_BUY_BY_8PCT")
    elif return_from_buy is not None and return_from_buy <= WARNING_RETURN_FROM_BUY_PCT:
        warning.append("PRICE_BELOW_BUY_BY_4PCT")
    if drawdown_from_peak is not None and drawdown_from_peak <= EXIT_DRAWDOWN_FROM_PEAK_PCT:
        severe.append("DRAWDOWN_FROM_PEAK_GE_10PCT")
    elif drawdown_from_peak is not None and drawdown_from_peak <= WARNING_DRAWDOWN_FROM_PEAK_PCT:
        warning.append("DRAWDOWN_FROM_PEAK_GE_6PCT")
    if liquidity_change is not None and liquidity_change <= EXIT_LIQUIDITY_DROP_PCT:
        severe.append("LIQUIDITY_DROP_GE_30PCT")
    elif liquidity_change is not None and liquidity_change <= WARNING_LIQUIDITY_DROP_PCT:
        warning.append("LIQUIDITY_DROP_GE_15PCT")
    if fast_ratio is not None and fast_ratio <= EXIT_FAST_FLOW_RATIO:
        severe.append("SELL_FLOW_DOMINANT")
    elif fast_ratio is not None and fast_ratio < WARNING_FAST_FLOW_RATIO:
        warning.append("BUY_FLOW_WEAK")
    if momentum15 is not None and momentum15 <= EXIT_MOMENTUM_15M_PCT:
        severe.append("MOMENTUM_15M_LE_-5PCT")
    elif momentum15 is not None and momentum15 <= WARNING_MOMENTUM_15M_PCT:
        warning.append("MOMENTUM_15M_LE_-3PCT")
    if structure_break:
        warning.append("5M_STRUCTURE_BROKEN")
        if momentum15 is not None and momentum15 <= EXIT_MOMENTUM_15M_PCT:
            severe.append("5M_STRUCTURE_AND_MOMENTUM_BREAK")

    if invalid:
        risk_state, label = "INVALIDATED", "🔴 INVALIDATED / EXIT REVIEW"
    elif severe and (
        len(severe) >= 2
        or "PRICE_BELOW_BUY_BY_8PCT" in severe
        or "DRAWDOWN_FROM_PEAK_GE_10PCT" in severe
        or "LIQUIDITY_DROP_GE_30PCT" in severe
    ):
        risk_state, label = "EXIT_REVIEW", "🔴 מצב הורע / EXIT REVIEW"
    elif len(warning) + len(severe) >= 2:
        risk_state, label = "CAUTION", "🟠 מצב נחלש / CAUTION"
    else:
        risk_state, label = "HEALTHY", "🟢 HEALTHY / HOLD REVIEW"

    return {
        **prior, **source, "observed_at": observed_at,
        "risk_state": risk_state, "risk_label": label,
        "manual_review_only": True, "automatic_sell": False,
        "baseline_liquidity_usd": baseline_liq,
        "peak_price_usd": round(peak, 12), "data_miss_streak": 0,
        "reasons": list(dict.fromkeys(invalid + severe + warning)),
        "market": {
            "price_usd": current, "liquidity_usd": liquidity,
            "volume_m5_usd": _num(market.get("volume_m5_usd")),
            "volume_h1_usd": _num(market.get("volume_h1_usd")),
            "return_from_buy_pct": round(return_from_buy, 4) if return_from_buy is not None else None,
            "drawdown_from_peak_pct": round(drawdown_from_peak, 4) if drawdown_from_peak is not None else None,
            "liquidity_change_from_entry_pct": round(liquidity_change, 4) if liquidity_change is not None else None,
            "fast_flow_ratio": round(fast_ratio, 4) if fast_ratio is not None else None,
            "fast_flow_window": fast_window if fast_ratio is not None else None,
            "buys_m5": m5b, "sells_m5": m5s, "buys_m15": m15b, "sells_m15": m15s,
            "buys_h1": h1b, "sells_h1": h1s,
            "momentum_15m_pct": round(momentum15, 4) if momentum15 is not None else None,
            "ema9_5m": round(ema9, 12) if ema9 is not None else None,
            "ema21_5m": round(ema21, 12) if ema21 is not None else None,
            "structure_break_5m": structure_break, "source": market.get("source"),
        },
    }


def _transition_event(current: dict[str, Any], prior: dict[str, Any] | None, now: datetime) -> str | None:
    previous = str((prior or {}).get("risk_state") or "")
    state = str(current.get("risk_state") or "")
    if state == "DATA_DEGRADED":
        # Data loss is operationally important, but it is never a sell signal.
        # Notify only when the third consecutive exact-pair miss is reached.
        misses = int(current.get("data_miss_streak") or 0)
        return "DATA_DEGRADED" if misses == 3 and (prior or {}).get("last_telegram_event") != "DATA_DEGRADED" else None
    if state in {"CAUTION", "EXIT_REVIEW", "INVALIDATED"} and state != previous:
        last = _parse_ts((prior or {}).get("last_telegram_at"))
        if state == "CAUTION" and last and (now - last).total_seconds() < DELIVERY_COOLDOWN_MINUTES * 60:
            return None
        return state
    if state == "HEALTHY" and previous in {"CAUTION", "EXIT_REVIEW", "INVALIDATED"}:
        return "RECOVERED"
    return None


def telegram_message(row: dict[str, Any], event: str) -> str:
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    title = {
        "CAUTION": "🟠 מצב נחלש / POST-BUY WARNING",
        "EXIT_REVIEW": "🔴 מצב הורע משמעותית / EXIT REVIEW",
        "INVALIDATED": "🔴 תנאי ה-BUY נשברו / INVALIDATED",
        "RECOVERED": "🟢 התאוששות / POST-BUY RECOVERED",
        "DATA_DEGRADED": "⚪ בעיית נתוני מעקב / DATA DEGRADED",
    }.get(event, "POST-BUY UPDATE")
    lines = [
        f"{title} — {row.get('symbol')} — WALLET500",
        f"FINAL BUY price: {float(row.get('entry_price_usd') or 0):.10f} USD",
    ]
    if market:
        lines.extend([
            f"Now: {float(market.get('price_usd') or 0):.10f} USD",
            f"From BUY: {market.get('return_from_buy_pct')}%",
            f"Drawdown from observed peak: {market.get('drawdown_from_peak_pct')}%",
            f"Liquidity: {float(market.get('liquidity_usd') or 0):,.0f} USD ({market.get('liquidity_change_from_entry_pct')}% from baseline)",
            f"Fast buy/sell: {market.get('fast_flow_ratio')}x ({market.get('fast_flow_window')})",
            f"15m momentum: {market.get('momentum_15m_pct')}%",
            f"5m structure broken: {'YES' if market.get('structure_break_5m') else 'NO'}",
        ])
    lines.extend([
        "Reasons: " + (", ".join(row.get("reasons") or []) or "none"),
        "Manual exit review only. No automatic sell.",
        f"CA: {row.get('token_address')}",
        f"Pair: {row.get('pair_address')}",
    ])
    dex_url = _dex_url(row)
    if dex_url:
        lines.append(f"DEX: {dex_url}")
    return "\n".join(lines)


def _send_telegram(text: str) -> tuple[bool, int | None, str | None]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return False, None, "TELEGRAM_NOT_CONFIGURED"
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if payload.get("ok") is not True:
                return False, None, "TELEGRAM_OK_FALSE"
            result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            mid = result.get("message_id")
            return True, int(mid) if mid is not None else None, None
    except Exception as exc:
        return False, None, f"{type(exc).__name__}:{str(exc)[:200]}"


def build(
    user_state: dict[str, Any],
    real_ledger: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
    *,
    fetcher: Callable[[dict[str, Any]], dict[str, Any] | None] = fetch_market,
    observed_at: str | None = None,
    send_func: Callable[[str], tuple[bool, int | None, str | None]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = observed_at or _now()
    now = _parse_ts(ts) or datetime.now(timezone.utc)
    prior_state = dict(prior_state or {})
    prior_positions = prior_state.get("positions") if isinstance(prior_state.get("positions"), dict) else {}
    sources = _source_positions(user_state, real_ledger, now)
    positions: dict[str, dict[str, Any]] = {}
    deliveries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    sender = send_func or _send_telegram

    for key, source in sources.items():
        prior = prior_positions.get(key) if isinstance(prior_positions.get(key), dict) else {}
        # A later FINAL BUY on the same exact pair is a new position episode.
        # Never inherit an old peak/baseline/alert state across entries.
        if prior and (
            str(prior.get("entry_time") or "") != str(source.get("entry_time") or "")
            or abs(float(prior.get("entry_price_usd") or 0) - float(source.get("entry_price_usd") or 0)) > 1e-15
        ):
            prior = {}
        row = evaluate_position(source, fetcher(source), prior, ts)
        event = _transition_event(row, prior, now)
        if event:
            ok, message_id, error = sender(telegram_message(row, event))
            delivery = {
                "at": ts, "key": key, "symbol": row.get("symbol"), "event": event,
                "delivered": ok, "message_id": message_id, "error": error,
            }
            deliveries.append(delivery)
            if ok:
                row["last_telegram_at"] = ts
                row["last_telegram_event"] = event
            else:
                errors.append(delivery)
        positions[key] = row

    state = {
        "version": 1, "mode": MODE, "updated_at": ts,
        "manual_review_only": True, "automatic_sell": False,
        "tracking_ttl_hours": TRACKING_TTL_HOURS, "positions": positions,
    }
    counts = {s: sum(1 for r in positions.values() if r.get("risk_state") == s)
              for s in ("HEALTHY", "CAUTION", "EXIT_REVIEW", "INVALIDATED", "DATA_DEGRADED")}
    report = {
        "version": 1, "mode": MODE, "generated_at": ts,
        "status": "OK" if not errors else "DEGRADED",
        "manual_review_only": True, "automatic_sell": False,
        "polling_cadence_target_minutes": 5,
        "tracked_count": len(positions), "state_counts": counts,
        "delivered_count": sum(1 for d in deliveries if d.get("delivered") is True),
        "deliveries": deliveries, "error_count": len(errors), "errors": errors,
        "thresholds": {
            "hard_stop_from_buy_pct": HARD_STOP_FROM_BUY_PCT,
            "warning_drawdown_from_peak_pct": WARNING_DRAWDOWN_FROM_PEAK_PCT,
            "exit_drawdown_from_peak_pct": EXIT_DRAWDOWN_FROM_PEAK_PCT,
            "warning_liquidity_drop_pct": WARNING_LIQUIDITY_DROP_PCT,
            "exit_liquidity_drop_pct": EXIT_LIQUIDITY_DROP_PCT,
            "invalid_liquidity_drop_pct": INVALID_LIQUIDITY_DROP_PCT,
            "warning_fast_flow_ratio": WARNING_FAST_FLOW_RATIO,
            "exit_fast_flow_ratio": EXIT_FAST_FLOW_RATIO,
            "warning_momentum_15m_pct": WARNING_MOMENTUM_15M_PCT,
            "exit_momentum_15m_pct": EXIT_MOMENTUM_15M_PCT,
        },
        "truth_contract": {
            "only_delivered_final_buys_are_tracked": True,
            "exact_chain_contract_pair_required": True,
            "state_transition_alerts_only": True,
            "no_automatic_sell": True,
            "data_failure_never_becomes_sell_signal": True,
            "manual_exit_review_only": True,
        },
        "positions": list(positions.values()),
    }
    return state, report


def run(data_dir: str | Path = DATA) -> tuple[dict[str, Any], dict[str, Any]]:
    data = Path(data_dir)
    state, report = build(
        _load(data / USER_BUY_STATE.name, {}),
        _load(data / REAL_LEDGER.name, {}),
        _load(data / STATE_PATH.name, {}),
    )
    _write(data / STATE_PATH.name, state)
    _write(data / REPORT_PATH.name, report)
    print(json.dumps({
        "mode": MODE, "tracked_count": report.get("tracked_count"),
        "state_counts": report.get("state_counts"),
        "delivered_count": report.get("delivered_count"),
        "error_count": report.get("error_count"),
    }, indent=2))
    return state, report


if __name__ == "__main__":
    run()
