from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")

MODE = "CEX_FAST_PROMOTION_V2_SENSOR_HANDOFF"
MIN_MARKET_AGE_DAYS = 90.0
MIN_EXECUTION_LIQUIDITY_USD = 15_000.0
MIN_SIGNAL_SCORE = 35
MAX_CURRENT_24H_CHANGE_PCT = 45.0
MAX_CEX_DEX_PRICE_ERROR_PCT = 12.0
MIN_MULTI_EXCHANGE_CONFIRMATIONS = 2
SINGLE_EXCHANGE_MIN_SCORE = 40
SINGLE_EXCHANGE_MIN_TURNOVER_USD = 250_000.0
SINGLE_EXCHANGE_MAX_SIGNAL_CHANGE_PCT = 25.0
MIN_RELATIVE_VOLUME_TURNOVER_USD = 1_000.0
MIN_RELATIVE_VOLUME_MULTIPLE = 4.0
MIN_RELATIVE_VOLUME_ACCEL_PCT = 100.0
REACTIVATION_MILESTONE_NAMES = (
    "first_cross_venue_slow_ignition",
    "first_shadow_watch",
    "first_alert",
    "first_watch",
    "first_anomaly",
)
USD_QUOTES = ("USDT", "USDC")
SUPPORTED_CHAINS = {
    "solana", "ethereum", "bsc", "base", "arbitrum", "polygon",
    "avalanche", "sui", "optimism",
}
LEVERAGED_SUFFIXES = ("2L", "2S", "3L", "3S", "4L", "4S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN")
UA = {"User-Agent": "Wallet500/cex-fast-promotion-1.0", "Accept": "application/json"}

IDENTITY_SOURCE = "cex-spot-identity-radar.json"
OUTPUT_FILE = "cex-fast-real-alerts.json"
STATE_FILE = "cex-fast-promotion-state.json"
REPORT_FILE = "cex-fast-promotion-report.json"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _f(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _i(value: object, default: int = 0) -> int:
    try:
        return int(float(value if value is not None else default))
    except (TypeError, ValueError):
        return default


def _parse_ts(value: object) -> datetime | None:
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


def _norm_symbol(value: object) -> str:
    return str(value or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()


def _base_symbol(value: object) -> str:
    symbol = _norm_symbol(value)
    for quote in USD_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[:-len(quote)]
    return symbol


def _canonical_symbol(value: object) -> str:
    base = _base_symbol(value)
    return f"{base}USDT" if base else ""


def _quote_symbol(value: object) -> str | None:
    symbol = _norm_symbol(value)
    for quote in USD_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return quote
    return None


def _is_usd_market(value: object) -> bool:
    return _quote_symbol(value) in USD_QUOTES


def _is_leveraged(value: object) -> bool:
    base = _base_symbol(value)
    return any(base.endswith(suffix) and len(base) > len(suffix) for suffix in LEVERAGED_SUFFIXES)


def _get(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _market_row(exchange: str, market_id: str, price: object, change: object, volume: object) -> dict | None:
    if not _is_usd_market(market_id):
        return None
    quote = _quote_symbol(market_id)
    base = _base_symbol(market_id)
    if not base or _is_leveraged(base):
        return None
    return {
        "exchange": exchange,
        "market_type": "spot",
        "symbol": f"{base}USDT",
        "raw_symbol": market_id,
        "market_id": market_id,
        "quote_symbol": quote,
        "price": _f(price),
        "change_24h_pct": _f(change),
        "volume_24h": _f(volume),
        "volume_comparable_usd_like": True,
        "regional_market": False,
    }


def _collect_gate() -> list[dict]:
    rows = _get("https://api.gateio.ws/api/v4/spot/tickers")
    out = []
    for x in rows if isinstance(rows, list) else []:
        row = _market_row(
            "gate",
            str(x.get("currency_pair") or ""),
            x.get("last"),
            x.get("change_percentage"),
            x.get("quote_volume"),
        )
        if row and row["quote_symbol"] == "USDC":
            out.append(row)
    return out


def _collect_bybit() -> list[dict]:
    rows = ((_get("https://api.bybit.com/v5/market/tickers?category=spot").get("result") or {}).get("list") or [])
    out = []
    for x in rows:
        row = _market_row(
            "bybit",
            str(x.get("symbol") or ""),
            x.get("lastPrice"),
            _f(x.get("price24hPcnt")) * 100.0,
            x.get("turnover24h"),
        )
        if row and row["quote_symbol"] == "USDC":
            out.append(row)
    return out


def _collect_okx() -> list[dict]:
    rows = _get("https://www.okx.com/api/v5/market/tickers?instType=SPOT").get("data", []) or []
    out = []
    for x in rows:
        market = str(x.get("instId") or "")
        if _quote_symbol(market) != "USDC":
            continue
        last = _f(x.get("last"))
        open24h = _f(x.get("open24h"))
        change = (last / open24h - 1.0) * 100.0 if last and open24h else 0.0
        row = _market_row("okx", market, last, change, x.get("volCcy24h"))
        if row:
            out.append(row)
    return out


def _collect_mexc() -> list[dict]:
    rows = _get("https://api.mexc.com/api/v3/ticker/24hr")
    if isinstance(rows, dict):
        rows = [rows]
    out = []
    for x in rows if isinstance(rows, list) else []:
        row = _market_row(
            "mexc",
            str(x.get("symbol") or ""),
            x.get("lastPrice"),
            x.get("priceChangePercent"),
            x.get("quoteVolume"),
        )
        if row and row["quote_symbol"] == "USDC":
            out.append(row)
    return out


def _collect_kucoin() -> list[dict]:
    rows = ((_get("https://api.kucoin.com/api/v1/market/allTickers").get("data") or {}).get("ticker") or [])
    out = []
    for x in rows:
        row = _market_row(
            "kucoin",
            str(x.get("symbol") or ""),
            x.get("last"),
            _f(x.get("changeRate")) * 100.0,
            x.get("volValue"),
        )
        if row and row["quote_symbol"] == "USDC":
            out.append(row)
    return out


def _collect_binance() -> list[dict]:
    rows = _get("https://api.binance.com/api/v3/ticker/24hr")
    if isinstance(rows, dict):
        rows = [rows]
    out = []
    for x in rows if isinstance(rows, list) else []:
        row = _market_row(
            "binance",
            str(x.get("symbol") or ""),
            x.get("lastPrice"),
            x.get("priceChangePercent"),
            x.get("quoteVolume"),
        )
        if row and row["quote_symbol"] == "USDC":
            out.append(row)
    return out


USDC_SOURCES = {
    "gate": _collect_gate,
    "bybit": _collect_bybit,
    "okx": _collect_okx,
    "mexc": _collect_mexc,
    "kucoin": _collect_kucoin,
    "binance": _collect_binance,
}


def collect_usdc_markets() -> tuple[list[dict], dict]:
    rows: list[dict] = []
    health: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(USDC_SOURCES)) as pool:
        futures = {pool.submit(fn): name for name, fn in USDC_SOURCES.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                got = fut.result()
                rows.extend(got)
                health[name] = {"ok": True, "markets": len(got)}
            except Exception as exc:
                health[name] = {"ok": False, "markets": 0, "error": f"{type(exc).__name__}: {exc}"[:240]}
    return rows, health


def _market_signal_score(change: float, volume: float) -> int:
    score = 0
    if change >= 8:
        score += 10
    if change >= 20:
        score += 10
    if change >= 50:
        score += 5
    if volume >= 100_000:
        score += 3
    if volume >= 1_000_000:
        score += 2
    return score


def _rank_usdc(rows: list[dict]) -> dict[str, dict]:
    by_exchange: dict[str, list[dict]] = {}
    for row in rows:
        if _f(row.get("change_24h_pct")) < 15.0 or _f(row.get("volume_24h")) < 20_000.0:
            continue
        by_exchange.setdefault(str(row.get("exchange") or ""), []).append(row)

    grouped: dict[str, dict] = {}
    for exchange, items in by_exchange.items():
        items.sort(key=lambda x: (_f(x.get("change_24h_pct")), _f(x.get("volume_24h"))), reverse=True)
        for rank, row in enumerate(items[:10], start=1):
            symbol = _canonical_symbol(row.get("symbol"))
            rec = grouped.setdefault(symbol, {
                "symbol": symbol,
                "markets": [],
                "leaderboard_best_rank": 999,
                "leaderboard_exchanges": [],
                "spot_revival_score": 0,
                "coherent_confirmations": 0,
                "exchanges": [],
                "change_24h_max_pct": 0.0,
                "reasons": [],
                "usdc_fast_discovery": True,
            })
            rec["markets"].append(row)
            rec["leaderboard_best_rank"] = min(rec["leaderboard_best_rank"], rank)
            rec["change_24h_max_pct"] = max(rec["change_24h_max_pct"], _f(row.get("change_24h_pct")))
            rec["spot_revival_score"] = max(
                rec["spot_revival_score"],
                _market_signal_score(_f(row.get("change_24h_pct")), _f(row.get("volume_24h"))) + 8,
            )
            if exchange not in rec["leaderboard_exchanges"]:
                rec["leaderboard_exchanges"].append(exchange)

    for rec in grouped.values():
        exchanges = sorted({str(x.get("exchange") or "") for x in rec["markets"] if x.get("exchange")})
        coherent = sorted({
            str(x.get("exchange") or "") for x in rec["markets"]
            if _market_signal_score(_f(x.get("change_24h_pct")), _f(x.get("volume_24h"))) >= 10
        })
        rec["exchanges"] = exchanges
        rec["coherent_confirmations"] = len(coherent)
        best_market = max(rec["markets"], key=lambda x: (_f(x.get("volume_24h")), _f(x.get("change_24h_pct"))))
        rec["milestones"] = {
            "first_alert": {
                "kind": "FIRST_ALERT",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "reference_exchange": best_market.get("exchange"),
                "reference_price": _f(best_market.get("price")),
                "reference_quote_symbol": best_market.get("quote_symbol"),
                "reference_change_24h_pct": _f(best_market.get("change_24h_pct")),
                "score": int(rec["spot_revival_score"]),
                "confirmations": len(exchanges),
                "coherent_confirmations": len(coherent),
            }
        }
        rec["reasons"] = [
            f"USDC top-10 CEX spot gainer rank #{rec['leaderboard_best_rank']}",
            f"current 24h move {rec['change_24h_max_pct']:.2f}%",
        ]
    return grouped


def _median(values: list[float]) -> float:
    values = sorted(x for x in values if x > 0)
    if not values:
        return 0.0
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2.0


def _action_market_rows(row: dict) -> list[dict]:
    markets = [
        x
        for x in row.get("markets") or []
        if isinstance(x, dict)
        and _f(x.get("price")) > 0
        and x.get("volume_comparable_usd_like", True)
        and not x.get("regional_market", False)
    ]
    collision = row.get("symbol_collision") if isinstance(row.get("symbol_collision"), dict) else {}
    coherent_exchanges = {
        str(x)
        for x in (collision.get("price_coherent_exchanges") or [])
        if str(x).strip()
    }
    if collision.get("suspected") and coherent_exchanges:
        markets = [x for x in markets if str(x.get("exchange") or "") in coherent_exchanges]
    return markets


def _cex_reference_price(row: dict) -> float:
    prices = [_f(x.get("price")) for x in _action_market_rows(row)]
    return _median(prices)


def _strict_dex_resolve(row: dict) -> dict | None:
    base = _base_symbol(row.get("symbol"))
    ref = _cex_reference_price(row)
    if not base or ref <= 0:
        return None
    try:
        payload = _get("https://api.dexscreener.com/latest/dex/search?q=" + urllib.parse.quote(base, safe=""))
    except Exception:
        return None

    matches = []
    now = datetime.now(timezone.utc)
    for pair in (payload or {}).get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        chain = str(pair.get("chainId") or "").lower().strip()
        if chain not in SUPPORTED_CHAINS:
            continue
        base_token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        if str(base_token.get("symbol") or "").upper().strip() != base:
            continue
        token = str(base_token.get("address") or "").strip()
        pair_address = str(pair.get("pairAddress") or "").strip()
        price = _f(pair.get("priceUsd"))
        created_ms = _f(pair.get("pairCreatedAt"), -1)
        if not token or not pair_address or price <= 0 or created_ms <= 0:
            continue
        try:
            created = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc)
        except Exception:
            continue
        age_days = (now - created).total_seconds() / 86400.0
        if age_days < MIN_MARKET_AGE_DAYS:
            continue
        price_error = abs(price / ref - 1.0) * 100.0
        if price_error > MAX_CEX_DEX_PRICE_ERROR_PCT:
            continue
        matches.append({
            "chain": chain,
            "token_address": token,
            "pair_address": pair_address,
            "dex": pair.get("dexId"),
            "dex_url": pair.get("url"),
            "dex_price_usd": price,
            "price_usd": price,
            "execution_pool_liquidity_usd": _f((pair.get("liquidity") or {}).get("usd")),
            "dex_liquidity_usd": _f((pair.get("liquidity") or {}).get("usd")),
            "dex_volume_h1": _f((pair.get("volume") or {}).get("h1")),
            "dex_volume_h24": _f((pair.get("volume") or {}).get("h24")),
            "pair_created_at": pair.get("pairCreatedAt"),
            "market_age_verified": True,
            "market_age_min_days": int(age_days),
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "execution_pair_price_coherent": True,
            "cex_reference_price_usd": ref,
            "cex_dex_price_ratio": round(max(ref, price) / min(ref, price), 6),
            "identity_candidate_source": "CEX_FAST_STRICT_DEXSCREENER_FALLBACK",
            "exact_token_side": "BASE",
            "market_age_evidence_at": created.isoformat(),
            "market_age_evidence_source": "DEXSCREENER_EXACT_SYMBOL_PRICE_PAIR_AGE_CEX_FAST",
            "price_error_pct": round(price_error, 4),
        })

    by_token: dict[tuple[str, str], dict] = {}
    for match in matches:
        key = (match["chain"], match["token_address"].lower())
        old = by_token.get(key)
        if old is None or (match["price_error_pct"], -match["execution_pool_liquidity_usd"]) < (
            old["price_error_pct"], -old["execution_pool_liquidity_usd"]
        ):
            by_token[key] = match
    unique = sorted(by_token.values(), key=lambda x: (x["price_error_pct"], -x["execution_pool_liquidity_usd"]))
    if not unique:
        return None
    if len(unique) > 1 and unique[1]["price_error_pct"] <= max(3.0, unique[0]["price_error_pct"] * 1.8):
        return None
    return {**row, **unique[0]}


def _index_identity(payload: dict) -> dict[str, dict]:
    out = {}
    for row in payload.get("candidates") or []:
        if isinstance(row, dict):
            symbol = _canonical_symbol(row.get("symbol"))
            if symbol:
                out[symbol] = row
    return out


def _merge_live_usdc(identity_payload: dict, usdc_groups: dict[str, dict]) -> list[dict]:
    identity = _index_identity(identity_payload)
    rows = [dict(x) for x in identity_payload.get("candidates") or [] if isinstance(x, dict)]
    for symbol, live in usdc_groups.items():
        if symbol in identity:
            base = dict(identity[symbol])
            existing = [x for x in base.get("markets") or [] if isinstance(x, dict)]
            by_key = {(str(x.get("exchange")), str(x.get("market_id"))): x for x in existing}
            for market in live.get("markets") or []:
                by_key[(str(market.get("exchange")), str(market.get("market_id")))] = market
            base["markets"] = list(by_key.values())
            base["change_24h_max_pct"] = max(_f(base.get("change_24h_max_pct")), _f(live.get("change_24h_max_pct")))
            base["leaderboard_best_rank"] = min(_i(base.get("leaderboard_best_rank"), 999), _i(live.get("leaderboard_best_rank"), 999))
            base["leaderboard_exchanges"] = sorted(set((base.get("leaderboard_exchanges") or []) + (live.get("leaderboard_exchanges") or [])))
            base["exchanges"] = sorted(set((base.get("exchanges") or []) + (live.get("exchanges") or [])))
            base["coherent_confirmations"] = max(_i(base.get("coherent_confirmations")), _i(live.get("coherent_confirmations")))
            base["spot_revival_score"] = max(_i(base.get("spot_revival_score")), _i(live.get("spot_revival_score")))
            base["usdc_fast_discovery"] = True
            for i, old in enumerate(rows):
                if _canonical_symbol(old.get("symbol")) == symbol:
                    rows[i] = base
                    break
        else:
            resolved = _strict_dex_resolve(live)
            if resolved:
                resolved["research_only"] = True
                resolved["actionable"] = False
                rows.append(resolved)
    return rows


def _milestone(row: dict) -> dict:
    """Use the freshest verified precursor instead of anchoring to a stale first alert."""
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    dated: list[tuple[datetime, int, dict]] = []
    undated: list[tuple[int, dict]] = []
    for priority, name in enumerate(REACTIVATION_MILESTONE_NAMES):
        item = milestones.get(name)
        if not isinstance(item, dict) or _f(item.get("reference_price")) <= 0:
            continue
        enriched = dict(item)
        enriched["_milestone_name"] = name
        ts = _parse_ts(item.get("observed_at"))
        if ts is not None:
            dated.append((ts, -priority, enriched))
        else:
            undated.append((-priority, enriched))
    if dated:
        return max(dated, key=lambda x: (x[0], x[1]))[2]
    if undated:
        return max(undated, key=lambda x: x[0])[1]
    return {}


def _max_turnover(row: dict) -> float:
    return max((_f(x.get("volume_24h")) for x in _action_market_rows(row)), default=0.0)


def _relative_volume_metrics(row: dict) -> dict:
    multiples = [
        _f(row.get("volume_window_multiple_max")),
        _f(row.get("volume_multiple_6h_max")),
        _f(row.get("volume_multiple_12h_max")),
        _f(row.get("volume_multiple_24h_max")),
    ]
    max_multiple = max(multiples, default=0.0)
    acceleration_pct = _f(row.get("volume_acceleration_max_pct"))
    turnover = _max_turnover(row)
    shock = bool(
        turnover >= MIN_RELATIVE_VOLUME_TURNOVER_USD
        and (
            max_multiple >= MIN_RELATIVE_VOLUME_MULTIPLE
            or acceleration_pct >= MIN_RELATIVE_VOLUME_ACCEL_PCT
        )
    )
    return {
        "shock": shock,
        "max_multiple": round(max_multiple, 4),
        "acceleration_pct": round(acceleration_pct, 4),
        "minimum_turnover_usd": MIN_RELATIVE_VOLUME_TURNOVER_USD,
    }


def _current_change(row: dict) -> float:
    changes = [_f(x.get("change_24h_pct")) for x in _action_market_rows(row)]
    return max(changes, default=_f(row.get("change_24h_max_pct")))


def _confirmation_exchanges(row: dict) -> list[str]:
    exchanges = sorted({
        str(x.get("exchange"))
        for x in _action_market_rows(row)
        if str(x.get("exchange") or "").strip()
    })
    if exchanges:
        return exchanges
    return sorted({
        str(x)
        for x in (row.get("leaderboard_usd_like_exchanges") or [])
        if str(x).strip()
    })


def _liquidity(row: dict) -> float:
    return max(
        _f(row.get("execution_pool_liquidity_usd")),
        _f(row.get("dex_pair_liquidity_usd")),
        _f(row.get("dex_liquidity_usd")),
        _f(row.get("liquidity_usd")),
    )


def _eligibility(row: object) -> tuple[bool, dict]:
    if not isinstance(row, dict):
        return False, {"blockers": ["ROW_INVALID"]}

    blockers: list[str] = []
    symbol = _canonical_symbol(row.get("symbol"))
    milestone = _milestone(row)
    signal_score = max(_i(row.get("spot_revival_score")), _i(milestone.get("score")))
    signal_change = _f(milestone.get("reference_change_24h_pct"), _current_change(row))
    current_change = _current_change(row)
    current_price = _cex_reference_price(row)
    signal_price = _f(milestone.get("reference_price"), current_price)
    turnover = _max_turnover(row)
    age_days = _f(row.get("market_age_min_days"))
    liquidity = _liquidity(row)
    exchanges = _confirmation_exchanges(row)
    observed_exchanges = sorted({str(x) for x in (row.get("exchanges") or []) if str(x).strip()})
    if not observed_exchanges:
        observed_exchanges = sorted({
            str(x.get("exchange"))
            for x in row.get("markets") or []
            if isinstance(x, dict) and x.get("exchange")
        })
    coherent = _i(row.get("coherent_confirmations"))
    best_rank = _i(row.get("leaderboard_best_rank"), 999)
    leaderboard_exchanges = sorted({str(x) for x in row.get("leaderboard_exchanges") or [] if str(x).strip()})
    risk = str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper()
    multi = coherent >= MIN_MULTI_EXCHANGE_CONFIRMATIONS or len(exchanges) >= MIN_MULTI_EXCHANGE_CONFIRMATIONS
    relative_volume = _relative_volume_metrics(row)
    relative_volume_exception = bool(multi and relative_volume["shock"])

    if not symbol:
        blockers.append("SYMBOL_MISSING")
    if _is_leveraged(symbol) or row.get("leveraged_product") is True:
        blockers.append("LEVERAGED_PRODUCT")
    if str(row.get("identity_status") or "") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
        blockers.append("EXACT_IDENTITY_NOT_VERIFIED")
    if not str(row.get("chain") or "").strip() or not str(row.get("token_address") or "").strip():
        blockers.append("CHAIN_OR_CONTRACT_MISSING")
    if not str(row.get("pair_address") or "").strip():
        blockers.append("EXACT_PAIR_MISSING")
    if row.get("execution_pair_price_coherent") is not True:
        blockers.append("CEX_DEX_PRICE_COHERENCE_NOT_VERIFIED")
    if row.get("market_age_verified") is not True or age_days < MIN_MARKET_AGE_DAYS:
        blockers.append("MARKET_AGE_LT_90D_OR_UNVERIFIED")
    if liquidity < MIN_EXECUTION_LIQUIDITY_USD:
        blockers.append("EXECUTION_LIQUIDITY_LT_15K")
    if signal_score < MIN_SIGNAL_SCORE:
        blockers.append("SIGNAL_SCORE_LT_35")
    if current_price <= 0:
        blockers.append("CURRENT_CEX_PRICE_MISSING")
    if turnover < 100_000 and not relative_volume_exception:
        blockers.append("CEX_TURNOVER_LT_100K_WITHOUT_RELATIVE_VOLUME_SHOCK")
    if current_change > MAX_CURRENT_24H_CHANGE_PCT:
        blockers.append("LATE_MOVE_DO_NOT_CHASE")
    if risk in {"HIGH", "CRITICAL"}:
        blockers.append("HIGH_OR_CRITICAL_RISK")

    single_exception = bool(
        len(exchanges) == 1
        and best_rank <= 1
        and signal_score >= SINGLE_EXCHANGE_MIN_SCORE
        and turnover >= SINGLE_EXCHANGE_MIN_TURNOVER_USD
        and signal_change <= SINGLE_EXCHANGE_MAX_SIGNAL_CHANGE_PCT
    )
    if not multi and not single_exception:
        blockers.append("CEX_CONFIRMATION_INSUFFICIENT")

    if milestone and signal_change > 35.0:
        blockers.append("EARLY_SIGNAL_ALREADY_EXTENDED")

    metrics = {
        "symbol": symbol,
        "signal_score": signal_score,
        "signal_change_24h_pct": round(signal_change, 4),
        "current_change_24h_pct": round(current_change, 4),
        "signal_price": signal_price,
        "signal_at": milestone.get("observed_at"),
        "signal_milestone": milestone.get("_milestone_name") or milestone.get("kind"),
        "current_price": current_price,
        "cex_turnover_usd": turnover,
        "relative_volume_shock": relative_volume["shock"],
        "relative_volume_max_multiple": relative_volume["max_multiple"],
        "relative_volume_acceleration_pct": relative_volume["acceleration_pct"],
        "relative_volume_turnover_exception": relative_volume_exception,
        "market_age_days": age_days,
        "execution_liquidity_usd": liquidity,
        "exchanges": exchanges,
        "observed_exchanges": observed_exchanges,
        "coherent_confirmations": coherent,
        "leaderboard_best_rank": best_rank if best_rank < 999 else None,
        "leaderboard_exchanges": leaderboard_exchanges,
        "single_exchange_exception": single_exception,
        "blockers": sorted(set(blockers)),
    }
    return not blockers, metrics


def _identity_key(row: dict) -> str:
    chain = str(row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or "").strip()
    pair = str(row.get("pair_address") or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"}:
        token, pair = token.lower(), pair.lower()
    return f"{chain}:{token}:{pair}"


def _event_id(key: str, now: str) -> str:
    return "CF-" + hashlib.sha256(f"{key}|{now}".encode("utf-8")).hexdigest()[:12].upper()


def _fmt_price(value: object) -> str:
    n = _f(value, -1)
    if n < 0:
        return "n/a"
    if n >= 1:
        return f"${n:.6f}".rstrip("0").rstrip(".")
    if n == 0:
        return "$0"
    return f"${n:.10f}".rstrip("0").rstrip(".")


def _fmt_money(value: object) -> str:
    n = _f(value)
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:.2f}"


def _message(row: dict, metrics: dict, now: str, event_id: str) -> str:
    symbol = metrics["symbol"]
    chain = str(row.get("chain") or "").upper().replace("BSC", "BNB")
    signal_price = metrics["signal_price"] or metrics["current_price"]
    current_price = metrics["current_price"]
    since = ((current_price / signal_price) - 1.0) * 100.0 if signal_price and current_price else 0.0
    source_time = metrics.get("signal_at") or now
    dex_url = str(row.get("dex_url") or row.get("url") or "")
    reason = "MULTI-EXCHANGE" if not metrics.get("single_exchange_exception") else "TOP-1 SINGLE-EXCHANGE EXCEPTION"
    lines = [
        "🚨 CEX FAST REAL ALERT — WALLET500",
        "✅ PROMOTED — NOT RESEARCH ONLY",
        "⚠️ MANUAL DECISION ONLY — NO AUTOMATIC TRADE",
        f"🧾 Alert ID: {event_id}",
        f"Token: {symbol}",
        f"Chain: {chain}",
        f"Contract: {row.get('token_address')}",
        f"Pair: {row.get('pair_address')}",
        f"DEX: {row.get('dex') or 'verified exact pair'}",
        f"🎯 ENGINE DISCOVERY PRICE: {_fmt_price(signal_price)}",
        f"📍 CURRENT PRICE: {_fmt_price(current_price)}",
        f"📈 Since discovery: {since:+.1f}%",
        f"⏱ Engine signal time: {source_time}",
        f"CEX 24h move now: {metrics['current_change_24h_pct']:+.1f}%",
        f"CEX turnover: {_fmt_money(metrics['cex_turnover_usd'])}",
        f"CEX confirmations: {max(metrics['coherent_confirmations'], len(metrics['exchanges']))} · {', '.join(metrics['exchanges'])}",
        f"Promotion proof: {reason}",
        f"Signal score: {metrics['signal_score']}/100",
        f"Market age: {metrics['market_age_days']:.0f}d ✅ min 90d",
        f"Execution liquidity: {_fmt_money(metrics['execution_liquidity_usd'])} ✅ min $15K",
        "Exact chain+contract+pair: VERIFIED ✅",
        "CEX↔DEX current price coherence: VERIFIED ✅",
        "Verified Intelligence. The Pure Truth.",
    ]
    if dex_url:
        lines.append(f"🔗 OPEN DEX: {dex_url}")
    return "\n".join(lines)


def _send(token: str, chat_id: str, text: str) -> tuple[int | None, int]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "false",
    }).encode("utf-8")
    last_error = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                raise RuntimeError(str(data)[:240])
            return (data.get("result") or {}).get("message_id"), attempt
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError(f"telegram_send_failed: {last_error}")


def run(output_dir: str | None = None, now: datetime | None = None) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", str(DATA)))
    out.mkdir(parents=True, exist_ok=True)
    now_dt = now or datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    identity_payload = _load(out / IDENTITY_SOURCE, {})
    usdc_rows, usdc_health = collect_usdc_markets()
    usdc_groups = _rank_usdc(usdc_rows)
    rows = _merge_live_usdc(identity_payload, usdc_groups)

    evaluated = []
    eligible = []
    for row in rows:
        ok, metrics = _eligibility(row)
        item = {
            "symbol": metrics.get("symbol") or _canonical_symbol(row.get("symbol")),
            "chain": row.get("chain"),
            "token_address": row.get("token_address"),
            "pair_address": row.get("pair_address"),
            "dex": row.get("dex"),
            "dex_url": row.get("dex_url") or row.get("url"),
            "status": "REAL_ALERT" if ok else "BLOCKED",
            "alert_class": "CEX_FAST_MANUAL_REAL_ALERT" if ok else "CEX_FAST_BLOCKED",
            "research_only": False if ok else True,
            "actionable": bool(ok),
            "actionable_research_alert": bool(ok),
            "manual_decision_only": True,
            "automatic_buy": False,
            **metrics,
        }
        evaluated.append(item)
        if ok:
            eligible.append((row, item))

    state_path = out / STATE_FILE
    state = _load(state_path, {})
    previous = state.get("active") if isinstance(state, dict) and isinstance(state.get("active"), dict) else {}
    active_now: dict[str, dict] = {}
    delivered = []
    errors = []

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    configured = bool(token and chat_id)

    for row, item in eligible:
        key = _identity_key(row)
        if not key.strip(":"):
            continue
        prev = previous.get(key) if isinstance(previous.get(key), dict) else {}
        active_info = dict(prev)
        active_info.update({
            "active": True,
            "last_seen_at": now_iso,
            "symbol": item.get("symbol"),
            "pair_address": row.get("pair_address"),
        })
        if prev.get("active") is not True:
            event_id = _event_id(key, now_iso)
            item["alert_event_id"] = event_id
            item["promoted_at"] = now_iso
            # CEX promotion remains internal evidence. Direct Telegram delivery is
            # disabled; only the canonical Decision Engine BUY lane may notify.
            active_info["telegram_suppressed_by_policy"] = True
            active_info["suppression_policy"] = "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE"
        active_now[key] = active_info

    for key, old in previous.items():
        if key in active_now or not isinstance(old, dict):
            continue
        cleared = dict(old)
        if old.get("active") is True:
            cleared["active"] = False
            cleared["cleared_at"] = now_iso
        active_now[key] = cleared

    _write(state_path, {"version": 1, "updated_at": now_iso, "active": active_now})

    alert_rows = [x for x in evaluated if x.get("status") == "REAL_ALERT"]
    alert_payload = {
        "version": 1,
        "generated_at": now_iso,
        "mode": MODE,
        "alerts": alert_rows,
        "count": len(alert_rows),
        "truth_contract": {
            "research_only_alerts_never_delivered": True,
            "exact_chain_contract_pair_required": True,
            "cex_dex_current_price_coherence_required": True,
            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "minimum_execution_liquidity_usd": MIN_EXECUTION_LIQUIDITY_USD,
            "minimum_signal_score": MIN_SIGNAL_SCORE,
            "relative_volume_handoff_enabled": True,
            "relative_volume_min_turnover_usd": MIN_RELATIVE_VOLUME_TURNOVER_USD,
            "relative_volume_min_multiple": MIN_RELATIVE_VOLUME_MULTIPLE,
            "relative_volume_min_acceleration_pct": MIN_RELATIVE_VOLUME_ACCEL_PCT,
            "freshest_reactivation_milestone_wins": True,
            "late_move_do_not_chase_above_24h_pct": MAX_CURRENT_24H_CHANGE_PCT,
            "multi_exchange_or_strict_top1_single_exchange_required": True,
            "manual_decision_only": True,
            "automatic_buy": False,
            "canonical_production_portfolio_impact": "NONE",
            "canonical_180d_50k_pipeline_unchanged": True,
            "usdc_quote_coverage_enabled": True,
            "no_symbol_only_promotion": True,
            "direct_telegram_delivery_disabled": True,
        },
    }
    _write(out / OUTPUT_FILE, alert_payload)

    report = {
        "version": 1,
        "generated_at": now_iso,
        "mode": MODE,
        "configured": configured,
        "telegram_delivery_enabled": False,
        "telegram_delivery_policy": "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE",
        "identity_source_generated_at": identity_payload.get("generated_at") if isinstance(identity_payload, dict) else None,
        "identity_rows_seen": len(identity_payload.get("candidates") or []) if isinstance(identity_payload, dict) else 0,
        "usdc_markets_seen": len(usdc_rows),
        "usdc_groups_seen": len(usdc_groups),
        "usdc_source_health": usdc_health,
        "evaluated_count": len(evaluated),
        "eligible_count": len(alert_rows),
        "delivered_count": len(delivered),
        "error_count": len(errors),
        "delivered": delivered,
        "errors": errors,
        "blocked_sample": [x for x in evaluated if x.get("status") != "REAL_ALERT"][:40],
        "truth_contract": alert_payload["truth_contract"],
    }
    _write(out / REPORT_FILE, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    run()
