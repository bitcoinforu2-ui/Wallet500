from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

IDENTITY_FILE = "cex-spot-identity-radar.json"
REVIVAL_FILE = "cex-revival-radar.json"
EARLY_LEDGER_FILE = "precision-pre-wave-early-signal-ledger.json"

USD_QUOTES = {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD"}
SUPPORTED_EXECUTION_EXCHANGES = {"gate", "mexc", "kucoin", "okx"}
LEVERAGED_SUFFIXES = ("2L", "2S", "3L", "3S", "4L", "4S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN")
UA = {"Accept": "application/json", "User-Agent": "Wallet500-CEX-FinalBuy/1.0"}

DEFAULT_POLICY = {
    "enabled": True,
    "max_source_age_seconds": 35 * 60,
    "min_market_age_days": 90.0,
    "min_signal_score": 35.0,
    "min_relative_signal_score": 30.0,
    "min_coherent_confirmations": 2,
    "min_turnover_usd": 25_000.0,
    "min_relative_turnover_usd": 10_000.0,
    "min_relative_volume_multiple": 3.0,
    "min_relative_volume_acceleration_pct": 75.0,
    "min_current_ignition_change_pct": 3.0,
    "min_current_change_pct": -12.0,
    "max_current_change_pct": 35.0,
    "strong_single_min_score": 55.0,
    "strong_single_min_turnover_usd": 250_000.0,
    "single_relative_max_rank": 3,
    "max_execution_candidates_per_run": 12,
    "min_orderbook_side_depth_usd": 5_000.0,
    "max_orderbook_spread_pct": 1.25,
    "max_orderbook_price_error_pct": 2.0,
    "orderbook_depth_band_pct": 2.0,
    "required_consecutive_qualified_scans": 2,
    "confirmation_max_fade_pct": 1.0,
    "confirmation_max_gain_pct": 12.0,
    "rearm_after_observable_misses": 2,
    "telegram_pre_buy_enabled": True,
    "automatic_trade": False,
}


def load(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or not path.stat().st_size:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def policy(config: dict | None = None) -> dict:
    out = dict(DEFAULT_POLICY)
    if isinstance(config, dict):
        custom = config.get("cex_final_buy_policy")
        if isinstance(custom, dict):
            out.update(custom)
    return out


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _age_seconds(value: Any, now: datetime) -> float | None:
    dt = _parse_dt(value)
    return None if dt is None else (now - dt).total_seconds()


def _norm_symbol(value: Any) -> str:
    return str(value or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()


def _base_symbol(value: Any) -> str:
    symbol = _norm_symbol(value)
    for quote in sorted(USD_QUOTES, key=len, reverse=True):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[:-len(quote)]
    return symbol


def _quote_symbol(value: Any) -> str:
    raw = _norm_symbol(value)
    for quote in sorted(USD_QUOTES, key=len, reverse=True):
        if raw.endswith(quote) and len(raw) > len(quote):
            return quote
    return ""


def _is_leveraged(symbol: str) -> bool:
    base = _base_symbol(symbol)
    return any(base.endswith(sfx) and len(base) > len(sfx) for sfx in LEVERAGED_SUFFIXES)


def _median(values: list[float]) -> float:
    vals = sorted(v for v in values if v > 0)
    if not vals:
        return 0.0
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def asset_key(row: dict) -> str:
    symbol = _base_symbol(row.get("symbol") or row.get("base_symbol"))
    cgid = str(row.get("coingecko_id") or "").strip().lower()
    return f"cex:{cgid}:{symbol}" if cgid and symbol else ""


def _action_markets(row: dict) -> list[dict]:
    markets = [
        dict(x)
        for x in (row.get("markets") or [])
        if isinstance(x, dict)
        and _f(x.get("price")) > 0
        and str(x.get("exchange") or "").strip()
        and x.get("regional_market") is not True
        and x.get("volume_comparable_usd_like", True) is not False
    ]
    collision = row.get("symbol_collision") if isinstance(row.get("symbol_collision"), dict) else {}
    coherent = {str(x).lower() for x in (collision.get("price_coherent_exchanges") or []) if str(x).strip()}
    if collision.get("suspected") is True and coherent:
        markets = [m for m in markets if str(m.get("exchange") or "").lower() in coherent]
    return markets


def _market_turnover(row: dict) -> float:
    return max((_f(x.get("volume_24h")) for x in _action_markets(row)), default=0.0)


def _current_price(row: dict) -> float:
    return _median([_f(x.get("price")) for x in _action_markets(row)])


def _current_change(row: dict) -> float:
    values = [_f(x.get("change_24h_pct"), -999.0) for x in _action_markets(row)]
    values = [x for x in values if x > -998.0]
    if values:
        return max(values)
    return _f(row.get("current_change_24h_max_pct") or row.get("change_24h_max_pct"))


def _relative_metrics(row: dict) -> tuple[float, float]:
    multiple = max(
        _f(row.get("volume_window_multiple_max")),
        _f(row.get("volume_multiple_6h_max")),
        _f(row.get("volume_multiple_12h_max")),
        _f(row.get("volume_multiple_24h_max")),
    )
    accel = _f(row.get("volume_acceleration_max_pct"))
    return multiple, accel


def _milestone_signal(row: dict) -> dict:
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    names = (
        "first_alert",
        "first_watch",
        "first_cross_venue_slow_ignition",
        "first_shadow_watch",
        "first_anomaly",
    )
    best: dict = {}
    best_score = -1.0
    for name in names:
        item = milestones.get(name)
        if not isinstance(item, dict):
            continue
        score = _f(item.get("score"))
        if score > best_score:
            best_score = score
            best = {**item, "_milestone_name": name}
    return best


def _early_entry(ledger: dict, symbol: str) -> dict:
    symbols = ledger.get("symbols") if isinstance(ledger, dict) else {}
    if not isinstance(symbols, dict):
        return {}
    row = symbols.get(symbol)
    return row if isinstance(row, dict) else {}


def _revival_index(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in (payload.get("alerts") or []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict):
            continue
        symbol = _base_symbol(row.get("symbol"))
        if symbol:
            out[symbol] = row
    return out


def _source_status(payload: dict, now: datetime, max_age: float) -> dict:
    stamp = payload.get("generated_at") or payload.get("updated_at")
    age = _age_seconds(stamp, now)
    fresh = bool(age is not None and -120 <= age <= max_age)
    return {
        "timestamp": stamp,
        "age_seconds": round(age, 2) if age is not None else None,
        "fresh": fresh,
    }


def build_candidates(identity: dict, revival: dict, early_ledger: dict, cfg: dict) -> list[dict]:
    rev = _revival_index(revival)
    out: list[dict] = []
    for row in identity.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        symbol = _base_symbol(row.get("base_symbol") or row.get("symbol"))
        if not symbol or _is_leveraged(symbol):
            continue
        cgid = str(row.get("coingecko_id") or "").strip()
        markets = _action_markets(row)
        if not markets:
            continue
        milestone = _milestone_signal(row)
        early = _early_entry(early_ledger, symbol)
        revival_row = rev.get(symbol, {})
        signal_score = max(
            _f(row.get("spot_revival_score")),
            _f(row.get("current_score")),
            _f(row.get("score")),
            _f(row.get("first_alert_score")),
            _f(row.get("first_watch_score")),
            _f(milestone.get("score")),
            _f(early.get("first_alert_score")),
            _f(revival_row.get("cex_revival_score")),
        )
        coherent = max(
            _i(row.get("current_coherent_confirmations")),
            _i(row.get("coherent_confirmations")),
            _i(revival_row.get("coherent_confirmations")),
        )
        rank = _i(row.get("leaderboard_best_rank"), 999)
        if rank <= 0:
            rank = 999
        rel_multiple, rel_accel = _relative_metrics(row)
        if rel_multiple <= 0 and isinstance(revival_row, dict):
            rel_multiple = max(
                _f(revival_row.get("volume_window_multiple_max")),
                _f(revival_row.get("volume_multiple_6h_max")),
                _f(revival_row.get("volume_multiple_12h_max")),
                _f(revival_row.get("volume_multiple_24h_max")),
            )
        if rel_accel <= 0 and isinstance(revival_row, dict):
            rel_accel = _f(revival_row.get("volume_acceleration_max_pct"))
        current_change = _current_change(row)
        current_price = _current_price(row)
        turnover = _market_turnover(row)
        collision = row.get("symbol_collision") if isinstance(row.get("symbol_collision"), dict) else {}
        identity_preflight = bool(
            cgid
            and row.get("market_age_verified") is True
            and (
                row.get("cex_identity_preflight_verified") is True
                or isinstance(row.get("cex_identity_preflight"), dict)
            )
        )
        selected_markets = sorted(
            [
                m for m in markets
                if str(m.get("exchange") or "").lower() in SUPPORTED_EXECUTION_EXCHANGES
                and (_quote_symbol(m.get("market_id") or m.get("symbol")) in USD_QUOTES)
            ],
            key=lambda m: (_f(m.get("volume_24h")), _f(m.get("price"))),
            reverse=True,
        )
        out.append({
            "key": f"cex:{cgid.lower()}:{symbol}" if cgid else "",
            "symbol": symbol,
            "coingecko_id": cgid,
            "asset_identity_verified": identity_preflight,
            "identity_status": row.get("identity_status"),
            "identity_blocker": row.get("identity_blocker"),
            "market_age_verified": row.get("market_age_verified") is True,
            "market_age_days": _f(row.get("market_age_min_days")),
            "symbol_collision_suspected": collision.get("suspected") is True,
            "price_coherent_exchanges": list(collision.get("price_coherent_exchanges") or []),
            "signal_score": round(signal_score, 4),
            "signal_at": early.get("first_alert_observed_at") or milestone.get("observed_at") or row.get("first_alert_observed_at"),
            "signal_price": _f(early.get("first_alert_reference_price") or milestone.get("reference_price") or row.get("first_alert_reference_price")),
            "signal_milestone": "IMMUTABLE_EARLY_SIGNAL_LEDGER" if early else milestone.get("_milestone_name"),
            "coherent_confirmations": coherent,
            "leaderboard_best_rank": None if rank >= 999 else rank,
            "current_change_24h_pct": round(current_change, 4),
            "current_price": current_price,
            "turnover_24h_usd": turnover,
            "relative_volume_multiple": round(rel_multiple, 4),
            "relative_volume_acceleration_pct": round(rel_accel, 4),
            "risk_level": str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper(),
            "markets": selected_markets,
            "all_action_markets": markets,
            "raw_identity_row": row,
        })
    return out


def precheck(candidate: dict, cfg: dict) -> tuple[bool, dict]:
    blockers: list[str] = []
    symbol = str(candidate.get("symbol") or "")
    score = _f(candidate.get("signal_score"))
    coherent = _i(candidate.get("coherent_confirmations"))
    rank = _i(candidate.get("leaderboard_best_rank"), 999)
    turnover = _f(candidate.get("turnover_24h_usd"))
    multiple = _f(candidate.get("relative_volume_multiple"))
    accel = _f(candidate.get("relative_volume_acceleration_pct"))
    change = _f(candidate.get("current_change_24h_pct"))
    relative = bool(
        turnover >= _f(cfg["min_relative_turnover_usd"])
        and (
            multiple >= _f(cfg["min_relative_volume_multiple"])
            or accel >= _f(cfg["min_relative_volume_acceleration_pct"])
        )
    )
    current_ignition = bool(
        change >= _f(cfg["min_current_ignition_change_pct"])
        or rank <= 10
        or relative
    )
    multi_standard = bool(
        score >= _f(cfg["min_signal_score"])
        and coherent >= _i(cfg["min_coherent_confirmations"])
    )
    multi_relative = bool(
        score >= _f(cfg["min_relative_signal_score"])
        and coherent >= _i(cfg["min_coherent_confirmations"])
        and relative
    )
    single_relative = bool(
        score >= _f(cfg["min_signal_score"])
        and rank <= _i(cfg["single_relative_max_rank"])
        and relative
    )
    strong_single = bool(
        score >= _f(cfg["strong_single_min_score"])
        and rank <= 1
        and turnover >= _f(cfg["strong_single_min_turnover_usd"])
    )
    lanes = []
    if multi_standard:
        lanes.append("MULTI_CEX_EARLY_ALERT")
    if multi_relative:
        lanes.append("MULTI_CEX_RELATIVE_VOLUME_IGNITION")
    if single_relative:
        lanes.append("SINGLE_CEX_RELATIVE_VOLUME_IGNITION")
    if strong_single:
        lanes.append("STRONG_SINGLE_CEX_TOP1")

    if not candidate.get("key"):
        blockers.append("CEX_ASSET_KEY_MISSING")
    if _is_leveraged(symbol):
        blockers.append("LEVERAGED_PRODUCT")
    if candidate.get("asset_identity_verified") is not True:
        blockers.append("CEX_ASSET_IDENTITY_NOT_VERIFIED")
    if candidate.get("market_age_verified") is not True or _f(candidate.get("market_age_days")) < _f(cfg["min_market_age_days"]):
        blockers.append("MARKET_AGE_LT_90D_OR_UNVERIFIED")
    if candidate.get("symbol_collision_suspected") is True and len(candidate.get("price_coherent_exchanges") or []) < 2:
        blockers.append("UNRESOLVED_TICKER_COLLISION")
    if not candidate.get("markets"):
        blockers.append("NO_SUPPORTED_EXACT_CEX_MARKET")
    if _f(candidate.get("current_price")) <= 0:
        blockers.append("CURRENT_CEX_PRICE_MISSING")
    if change < _f(cfg["min_current_change_pct"]):
        blockers.append("NEGATIVE_MOVE_TOO_DEEP")
    if change > _f(cfg["max_current_change_pct"]):
        blockers.append("LATE_MOVE_DO_NOT_CHASE")
    if turnover < _f(cfg["min_turnover_usd"]) and not relative:
        blockers.append("CEX_TURNOVER_TOO_LOW")
    if not current_ignition:
        blockers.append("NO_CURRENT_CEX_IGNITION")
    if not lanes:
        blockers.append("CEX_SIGNAL_CONFLUENCE_INSUFFICIENT")
    if str(candidate.get("risk_level") or "") in {"HIGH", "CRITICAL"}:
        blockers.append("HIGH_OR_CRITICAL_RISK")

    return not blockers, {
        "blockers": sorted(set(blockers)),
        "lanes": lanes,
        "relative_volume_shock": relative,
        "current_ignition": current_ignition,
    }


def _http_json(url: str, timeout: int = 6) -> Any:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _book_levels(exchange: str, market_id: str, getter: Callable[[str], Any]) -> tuple[list, list]:
    exchange = exchange.lower()
    if exchange == "gate":
        q = urllib.parse.urlencode({"currency_pair": market_id, "limit": 100, "with_id": "true"})
        doc = getter(f"https://api.gateio.ws/api/v4/spot/order_book?{q}")
        return list((doc or {}).get("bids") or []), list((doc or {}).get("asks") or [])
    if exchange == "mexc":
        symbol = _norm_symbol(market_id)
        doc = getter(f"https://api.mexc.com/api/v3/depth?symbol={urllib.parse.quote(symbol)}&limit=100")
        return list((doc or {}).get("bids") or []), list((doc or {}).get("asks") or [])
    if exchange == "kucoin":
        raw = str(market_id or "").upper().replace("_", "-")
        if "-" not in raw:
            base = _base_symbol(raw)
            quote = _quote_symbol(raw) or "USDT"
            raw = f"{base}-{quote}"
        doc = getter(f"https://api.kucoin.com/api/v1/market/orderbook/level2_100?symbol={urllib.parse.quote(raw)}")
        data = (doc or {}).get("data") or {}
        return list(data.get("bids") or []), list(data.get("asks") or [])
    if exchange == "okx":
        raw = str(market_id or "").upper().replace("_", "-")
        if "-" not in raw:
            base = _base_symbol(raw)
            quote = _quote_symbol(raw) or "USDT"
            raw = f"{base}-{quote}"
        doc = getter(f"https://www.okx.com/api/v5/market/books?instId={urllib.parse.quote(raw)}&sz=100")
        data = (doc or {}).get("data") or []
        book = data[0] if data and isinstance(data[0], dict) else {}
        return list(book.get("bids") or []), list(book.get("asks") or [])
    raise ValueError("UNSUPPORTED_CEX_ORDERBOOK")


def _book_metrics(
    bids: list,
    asks: list,
    reference_price: float,
    cfg: dict,
) -> dict:
    parsed_bids: list[tuple[float, float]] = []
    parsed_asks: list[tuple[float, float]] = []
    for raw in bids:
        try:
            px, qty = float(raw[0]), float(raw[1])
            if px > 0 and qty > 0:
                parsed_bids.append((px, qty))
        except Exception:
            continue
    for raw in asks:
        try:
            px, qty = float(raw[0]), float(raw[1])
            if px > 0 and qty > 0:
                parsed_asks.append((px, qty))
        except Exception:
            continue
    if not parsed_bids or not parsed_asks:
        return {"execution_verified": False, "blockers": ["CEX_ORDERBOOK_EMPTY_OR_INVALID"]}

    best_bid = max(px for px, _ in parsed_bids)
    best_ask = min(px for px, _ in parsed_asks)
    mid = (best_bid + best_ask) / 2.0
    spread = (best_ask / best_bid - 1.0) * 100.0 if best_bid > 0 else 999.0
    ref = reference_price if reference_price > 0 else mid
    band = _f(cfg["orderbook_depth_band_pct"]) / 100.0
    bid_floor = ref * (1.0 - band)
    ask_ceiling = ref * (1.0 + band)
    bid_depth = sum(px * qty for px, qty in parsed_bids if px >= bid_floor)
    ask_depth = sum(px * qty for px, qty in parsed_asks if px <= ask_ceiling)
    side_depth = min(bid_depth, ask_depth)
    price_error = abs(mid / ref - 1.0) * 100.0 if ref > 0 else 999.0

    blockers = []
    if spread > _f(cfg["max_orderbook_spread_pct"]):
        blockers.append("CEX_SPREAD_TOO_WIDE")
    if side_depth < _f(cfg["min_orderbook_side_depth_usd"]):
        blockers.append("CEX_ORDERBOOK_DEPTH_TOO_LOW")
    if price_error > _f(cfg["max_orderbook_price_error_pct"]):
        blockers.append("CEX_ORDERBOOK_PRICE_INCOHERENT")
    return {
        "execution_verified": not blockers,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid,
        "reference_price": ref,
        "spread_pct": round(spread, 5),
        "bid_depth_band_usd": round(bid_depth, 2),
        "ask_depth_band_usd": round(ask_depth, 2),
        "minimum_side_depth_band_usd": round(side_depth, 2),
        "price_error_pct": round(price_error, 5),
        "blockers": blockers,
    }


def resolve_execution(
    candidate: dict,
    cfg: dict,
    getter: Callable[[str], Any] | None = None,
) -> dict:
    getter = getter or _http_json
    attempts: list[dict] = []
    best: dict | None = None
    for market in candidate.get("markets") or []:
        exchange = str(market.get("exchange") or "").lower()
        market_id = str(market.get("market_id") or market.get("raw_symbol") or market.get("symbol") or "").strip()
        if exchange not in SUPPORTED_EXECUTION_EXCHANGES or not market_id:
            continue
        try:
            bids, asks = _book_levels(exchange, market_id, getter)
            metrics = _book_metrics(bids, asks, _f(market.get("price")), cfg)
            snapshot = {
                "execution_type": "CEX_SPOT_ORDERBOOK",
                "exchange": exchange,
                "market_id": market_id,
                "symbol": market.get("symbol"),
                "quote_symbol": market.get("quote_symbol") or _quote_symbol(market_id),
                "turnover_24h_usd": _f(market.get("volume_24h")),
                **metrics,
            }
        except Exception as exc:
            snapshot = {
                "execution_type": "CEX_SPOT_ORDERBOOK",
                "exchange": exchange,
                "market_id": market_id,
                "execution_verified": False,
                "blockers": [f"CEX_ORDERBOOK_UNAVAILABLE:{type(exc).__name__}"],
            }
        attempts.append(snapshot)
        if snapshot.get("execution_verified") is True:
            snapshot["attempts"] = attempts
            return snapshot
        if best is None or _f(snapshot.get("minimum_side_depth_band_usd")) > _f(best.get("minimum_side_depth_band_usd")):
            best = snapshot
    if best is None:
        best = {
            "execution_type": "CEX_SPOT_ORDERBOOK",
            "execution_verified": False,
            "blockers": ["NO_SUPPORTED_CEX_ORDERBOOK"],
        }
    best["attempts"] = attempts
    return best


def evaluate_candidate(
    candidate: dict,
    execution: dict | None,
    prior: dict | None,
    cfg: dict,
    *,
    now: datetime,
) -> tuple[dict, dict]:
    prior = dict(prior or {})
    base_ok, gate = precheck(candidate, cfg)
    blockers = list(gate["blockers"])
    execution = dict(execution or {})
    if execution.get("execution_verified") is not True:
        blockers.extend(str(x) for x in (execution.get("blockers") or ["CEX_EXECUTION_NOT_VERIFIED"]))
        if not execution.get("blockers"):
            blockers.append("CEX_EXECUTION_NOT_VERIFIED")

    price = _f(execution.get("mid_price") or candidate.get("current_price"))
    previous_price = _f(prior.get("last_price"), 0.0)
    scan_gain = None
    if previous_price > 0 and price > 0:
        scan_gain = (price / previous_price - 1.0) * 100.0
        if int(prior.get("qualified_streak") or 0) > 0:
            if scan_gain < -_f(cfg["confirmation_max_fade_pct"]):
                blockers.append("CEX_CONFIRMATION_FADE")
            if scan_gain > _f(cfg["confirmation_max_gain_pct"]):
                blockers.append("CEX_CONFIRMATION_CHASE")

    blockers = sorted(set(blockers))
    qualified = base_ok and not blockers
    prior_streak = int(prior.get("qualified_streak") or 0)
    streak = prior_streak + 1 if qualified else 0
    required = max(1, _i(cfg["required_consecutive_qualified_scans"], 2))
    final_buy = bool(qualified and streak >= required)
    pre_buy = bool(
        cfg.get("telegram_pre_buy_enabled") is True
        and required > 1
        and qualified
        and streak == required - 1
    )

    armed = bool(prior.get("armed", True))
    pre_buy_armed = bool(prior.get("pre_buy_armed", True))
    misses = int(prior.get("observable_miss_streak") or 0)
    observable = bool(candidate.get("asset_identity_verified") and execution.get("exchange") and execution.get("market_id"))
    if qualified:
        misses = 0
    elif observable:
        misses += 1
        if misses >= max(1, _i(cfg["rearm_after_observable_misses"], 2)):
            armed = True
            pre_buy_armed = True

    alert = bool(final_buy and armed)
    pre_buy_alert = bool(pre_buy and pre_buy_armed)
    if alert:
        armed = False
    if pre_buy_alert:
        pre_buy_armed = False

    state = "BUY_ZONE" if final_buy else ("QUALIFYING" if qualified else "WATCH")
    decision = {
        "identity_key": candidate.get("key"),
        "execution_mode": "CEX_SPOT",
        "symbol": candidate.get("symbol"),
        "coingecko_id": candidate.get("coingecko_id"),
        "state": state,
        "recommended_action": "BUY" if final_buy else "WAIT",
        "alert": alert,
        "pre_buy": pre_buy,
        "pre_buy_alert": pre_buy_alert,
        "qualified_this_scan": qualified,
        "qualified_streak": streak,
        "required_streak": required,
        "blockers": blockers,
        "signal": {
            "score": candidate.get("signal_score"),
            "signal_at": candidate.get("signal_at"),
            "signal_price": candidate.get("signal_price"),
            "signal_milestone": candidate.get("signal_milestone"),
            "coherent_confirmations": candidate.get("coherent_confirmations"),
            "leaderboard_best_rank": candidate.get("leaderboard_best_rank"),
            "current_change_24h_pct": candidate.get("current_change_24h_pct"),
            "turnover_24h_usd": candidate.get("turnover_24h_usd"),
            "relative_volume_multiple": candidate.get("relative_volume_multiple"),
            "relative_volume_acceleration_pct": candidate.get("relative_volume_acceleration_pct"),
            "qualification_lanes": gate.get("lanes"),
        },
        "execution": execution,
        "scan_price_gain_pct": round(scan_gain, 5) if scan_gain is not None else None,
        "truth_contract": {
            "asset_identity_and_execution_identity_separate": True,
            "exact_dex_pair_not_required_for_cex_execution": True,
            "exact_cex_market_required": True,
            "live_cex_orderbook_required": True,
            "two_scan_confirmation_required": required >= 2,
            "late_move_chase_blocked": True,
            "automatic_trade": False,
            "manual_decision_only": True,
        },
    }

    next_state = {
        **prior,
        "identity_key": candidate.get("key"),
        "symbol": candidate.get("symbol"),
        "coingecko_id": candidate.get("coingecko_id"),
        "last_seen_at": now.isoformat(),
        "last_price": price if price > 0 else prior.get("last_price"),
        "qualified_streak": streak,
        "observable_miss_streak": misses,
        "armed": armed,
        "pre_buy_armed": pre_buy_armed,
        "last_state": state,
        "last_blockers": blockers,
        "last_execution_exchange": execution.get("exchange"),
        "last_execution_market_id": execution.get("market_id"),
    }
    if not next_state.get("first_seen_at"):
        next_state["first_seen_at"] = now.isoformat()
    if pre_buy_alert:
        next_state["last_pre_buy_alert_at"] = now.isoformat()
        next_state["last_pre_buy_alert_price"] = price
        next_state["pre_buy_episode_count"] = int(prior.get("pre_buy_episode_count") or 0) + 1
    if alert:
        next_state["last_alert_at"] = now.isoformat()
        next_state["last_alert_price"] = price
        next_state["buy_episode_count"] = int(prior.get("buy_episode_count") or 0) + 1
    return decision, next_state


def evaluate_from_files(
    root: Path,
    config: dict,
    prior_state: dict | None,
    *,
    now: datetime,
    execution_resolver: Callable[[dict, dict], dict] | None = None,
) -> dict:
    cfg = policy(config)
    if cfg.get("enabled") is not True:
        return {
            "status": "DISABLED",
            "policy": cfg,
            "decisions": [],
            "state": dict(prior_state or {}),
            "source_status": {},
        }

    data = root / "data"
    identity = load(data / IDENTITY_FILE, {})
    revival = load(data / REVIVAL_FILE, {})
    early = load(data / EARLY_LEDGER_FILE, {})
    source = {
        "identity": _source_status(identity, now, _f(cfg["max_source_age_seconds"])),
        "revival": _source_status(revival, now, _f(cfg["max_source_age_seconds"])),
        "early_ledger_updated_at": early.get("updated_at") if isinstance(early, dict) else None,
    }
    if source["identity"]["fresh"] is not True:
        return {
            "status": "BLOCKED_STALE_IDENTITY_SOURCE",
            "policy": cfg,
            "decisions": [],
            "state": dict(prior_state or {}),
            "source_status": source,
        }

    candidates = build_candidates(identity, revival, early, cfg)
    ranked = []
    for cand in candidates:
        ok, gate = precheck(cand, cfg)
        priority = (
            1 if ok else 0,
            len(gate.get("lanes") or []),
            _f(cand.get("signal_score")),
            _i(cand.get("coherent_confirmations")),
            _f(cand.get("relative_volume_multiple")),
            -_i(cand.get("leaderboard_best_rank"), 999),
            _f(cand.get("turnover_24h_usd")),
        )
        ranked.append((priority, cand, ok))
    ranked.sort(key=lambda x: x[0], reverse=True)

    execution_budget = max(1, _i(cfg["max_execution_candidates_per_run"], 12))
    resolver = execution_resolver or (lambda cand, p: resolve_execution(cand, p))
    old_state = dict(prior_state or {})
    new_state = dict(old_state)
    decisions: list[dict] = []
    executed = 0
    for _, cand, pre_ok in ranked:
        execution = None
        if pre_ok and executed < execution_budget:
            executed += 1
            execution = resolver(cand, cfg)
        elif pre_ok:
            execution = {
                "execution_verified": False,
                "blockers": ["CEX_EXECUTION_BUDGET_DEFERRED"],
            }
        decision, next_state = evaluate_candidate(
            cand,
            execution,
            old_state.get(cand.get("key")),
            cfg,
            now=now,
        )
        new_state[cand.get("key")] = next_state
        decisions.append(decision)

    return {
        "status": "OK",
        "policy": cfg,
        "source_status": source,
        "candidate_count": len(candidates),
        "execution_checked_count": executed,
        "pre_buy_count": sum(x.get("pre_buy") is True for x in decisions),
        "buy_zone_count": sum(x.get("state") == "BUY_ZONE" for x in decisions),
        "decisions": decisions,
        "state": new_state,
    }


def telegram_message(decision: dict) -> str:
    sig = decision.get("signal") if isinstance(decision.get("signal"), dict) else {}
    exe = decision.get("execution") if isinstance(decision.get("execution"), dict) else {}
    pre = decision.get("pre_buy_alert") is True
    title = (
        f"🟠⚡ רגע לפני קנייה / PRE-BUY — {decision.get('symbol')} — WALLET500"
        if pre
        else f"🟢🔥 קנייה / BUY — {decision.get('symbol')} — WALLET500"
    )
    status_line = (
        "CEX signal passed; one confirmation scan remains."
        if pre
        else "CEX FINAL BUY confirmation passed ✅"
    )
    price = _f(exe.get("mid_price"))
    depth = _f(exe.get("minimum_side_depth_band_usd"))
    spread = _f(exe.get("spread_pct"))
    return "\n".join([
        title,
        status_line,
        f"Execution: {str(exe.get('exchange') or '').upper()} • {exe.get('market_id')}",
        f"Price USD: {price:.10f}",
        f"Order-book depth ±2% minimum side USD: {depth:,.0f} | Spread: {spread:.3f}%",
        f"Signal score: {_f(sig.get('score')):.1f}/100 | CEX confirmations: {_i(sig.get('coherent_confirmations'))}",
        f"24h move now: {_f(sig.get('current_change_24h_pct')):.2f}% | Turnover USD: {_f(sig.get('turnover_24h_usd')):,.0f}",
        f"Relative volume: {_f(sig.get('relative_volume_multiple')):.2f}x | accel {_f(sig.get('relative_volume_acceleration_pct')):.1f}%",
        "Lane: " + ", ".join(str(x) for x in (sig.get("qualification_lanes") or [])),
        f"Asset ID: CoinGecko {decision.get('coingecko_id')}",
        "CEX execution identity verified; a DEX pair is not required for this CEX order.",
        "Manual decision only. No automatic trade.",
    ])
