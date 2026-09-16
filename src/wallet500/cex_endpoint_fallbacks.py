from __future__ import annotations

"""Resilient official public market-data coverage for Wallet500's CEX fast lane.

The GitHub-hosted runner can receive geo/WAF responses from some primary CEX
hosts. We only use documented official endpoints for the named exchange and do
not try to bypass geographic restrictions. If direct Bybit remains unavailable,
the blind spot is compensated by two additional independent official CEX feeds
(Bitget + CoinEx) while Bybit itself stays visibly fail-closed in health data.
"""

import threading
from typing import Any, Callable

BINANCE_SPOT_TICKER_ENDPOINTS = (
    "https://data-api.binance.vision/api/v3/ticker/24hr",
    "https://api-gcp.binance.com/api/v3/ticker/24hr",
    "https://api1.binance.com/api/v3/ticker/24hr",
    "https://api2.binance.com/api/v3/ticker/24hr",
    "https://api3.binance.com/api/v3/ticker/24hr",
    "https://api4.binance.com/api/v3/ticker/24hr",
    "https://api.binance.com/api/v3/ticker/24hr",
)

BYBIT_SPOT_TICKER_ENDPOINTS = (
    "https://api.bytick.com/v5/market/tickers?category=spot",
    "https://api.bybit.com/v5/market/tickers?category=spot",
)

BITGET_SPOT_TICKER_ENDPOINTS = (
    "https://api.bitget.com/api/v2/spot/market/tickers",
    "https://api.bitget.com/api/v3/market/tickers?category=SPOT",
)

COINEX_SPOT_TICKER_ENDPOINTS = (
    "https://api.coinex.com/v2/spot/ticker",
)

BYBIT_GAP_COMPENSATION_SOURCES = ("bitget", "coinex")

_LOCK = threading.Lock()
_LAST_ENDPOINT_HEALTH: dict[str, dict] = {}


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:180]


def _record(name: str, payload: dict) -> None:
    with _LOCK:
        _LAST_ENDPOINT_HEALTH[name] = dict(payload)


def _snapshot() -> dict[str, dict]:
    with _LOCK:
        return {k: dict(v) for k, v in _LAST_ENDPOINT_HEALTH.items()}


def _reset() -> None:
    with _LOCK:
        _LAST_ENDPOINT_HEALTH.clear()


def _fetch_first(
    getter: Callable[[str], Any],
    endpoints: tuple[str, ...],
    validator: Callable[[Any], bool],
) -> tuple[Any, str, list[dict]]:
    attempts: list[dict] = []
    for endpoint in endpoints:
        try:
            payload = getter(endpoint)
            if not validator(payload):
                raise ValueError("unexpected response shape")
            attempts.append({"endpoint": endpoint, "ok": True})
            return payload, endpoint, attempts
        except Exception as exc:
            attempts.append({"endpoint": endpoint, "ok": False, "error": _error_text(exc)})
    summary = "; ".join(f"{x['endpoint']} => {x.get('error', 'invalid')}" for x in attempts)
    raise RuntimeError(f"all official endpoints failed: {summary}"[:900])


def _binance_valid(payload: Any) -> bool:
    return isinstance(payload, list) and len(payload) > 0


def _bybit_valid(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if int(payload.get("retCode") or 0) != 0:
        return False
    rows = ((payload.get("result") or {}).get("list") or [])
    return isinstance(rows, list) and len(rows) > 0


def _bitget_valid(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and str(payload.get("code") or "") == "00000"
        and isinstance(payload.get("data"), list)
        and len(payload.get("data") or []) > 0
    )


def _coinex_valid(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and int(payload.get("code") or 0) == 0
        and isinstance(payload.get("data"), list)
        and len(payload.get("data") or []) > 0
    )


def _record_success(name: str, endpoint: str, attempts: list[dict], primary: str) -> None:
    _record(name, {
        "endpoint": endpoint,
        "endpoint_fallback_used": endpoint != primary,
        "endpoint_attempts": attempts,
        "official_endpoint_only": True,
    })


def _record_failure(name: str, attempts: list[dict], exc: BaseException, pool_label: str) -> None:
    _record(name, {
        "endpoint": None,
        "endpoint_fallback_used": True,
        "endpoint_attempts": attempts or [{"endpoint": pool_label, "ok": False, "error": _error_text(exc)}],
        "official_endpoint_only": True,
    })


def _collect_binance(promo) -> list[dict]:
    attempts: list[dict] = []
    try:
        payload, endpoint, attempts = _fetch_first(promo._get, BINANCE_SPOT_TICKER_ENDPOINTS, _binance_valid)
        out: list[dict] = []
        for item in payload:
            row = promo._market_row(
                "binance",
                str(item.get("symbol") or ""),
                item.get("lastPrice"),
                item.get("priceChangePercent"),
                item.get("quoteVolume"),
            )
            if row and row["quote_symbol"] == "USDC":
                row["market_data_endpoint"] = endpoint
                row["endpoint_fallback_used"] = endpoint != BINANCE_SPOT_TICKER_ENDPOINTS[0]
                out.append(row)
        _record_success("binance", endpoint, attempts, BINANCE_SPOT_TICKER_ENDPOINTS[0])
        return out
    except Exception as exc:
        _record_failure("binance", attempts, exc, "official_binance_pool")
        raise


def _collect_bybit(promo) -> list[dict]:
    attempts: list[dict] = []
    try:
        payload, endpoint, attempts = _fetch_first(promo._get, BYBIT_SPOT_TICKER_ENDPOINTS, _bybit_valid)
        rows = ((payload.get("result") or {}).get("list") or [])
        out: list[dict] = []
        for item in rows:
            row = promo._market_row(
                "bybit",
                str(item.get("symbol") or ""),
                item.get("lastPrice"),
                promo._f(item.get("price24hPcnt")) * 100.0,
                item.get("turnover24h"),
            )
            if row and row["quote_symbol"] == "USDC":
                row["market_data_endpoint"] = endpoint
                row["endpoint_fallback_used"] = endpoint != BYBIT_SPOT_TICKER_ENDPOINTS[0]
                out.append(row)
        _record_success("bybit", endpoint, attempts, BYBIT_SPOT_TICKER_ENDPOINTS[0])
        return out
    except Exception as exc:
        _record_failure("bybit", attempts, exc, "official_bybit_pool")
        raise


def _collect_bitget(promo) -> list[dict]:
    attempts: list[dict] = []
    try:
        payload, endpoint, attempts = _fetch_first(promo._get, BITGET_SPOT_TICKER_ENDPOINTS, _bitget_valid)
        out: list[dict] = []
        for item in payload.get("data") or []:
            # v2 uses lastPr/change24h/quoteVolume; v3 uses
            # lastPrice/price24hPcnt/turnover24h. Both change fields are ratios.
            last = item.get("lastPr") if item.get("lastPr") is not None else item.get("lastPrice")
            change_ratio = item.get("change24h") if item.get("change24h") is not None else item.get("price24hPcnt")
            turnover = item.get("quoteVolume") if item.get("quoteVolume") is not None else item.get("turnover24h")
            row = promo._market_row(
                "bitget",
                str(item.get("symbol") or ""),
                last,
                promo._f(change_ratio) * 100.0,
                turnover,
            )
            if row and row["quote_symbol"] == "USDC":
                row["market_data_endpoint"] = endpoint
                row["endpoint_fallback_used"] = endpoint != BITGET_SPOT_TICKER_ENDPOINTS[0]
                out.append(row)
        _record_success("bitget", endpoint, attempts, BITGET_SPOT_TICKER_ENDPOINTS[0])
        return out
    except Exception as exc:
        _record_failure("bitget", attempts, exc, "official_bitget_pool")
        raise


def _collect_coinex(promo) -> list[dict]:
    attempts: list[dict] = []
    try:
        payload, endpoint, attempts = _fetch_first(promo._get, COINEX_SPOT_TICKER_ENDPOINTS, _coinex_valid)
        out: list[dict] = []
        for item in payload.get("data") or []:
            last = promo._f(item.get("last") if item.get("last") is not None else item.get("close"))
            open24h = promo._f(item.get("open"))
            change = (last / open24h - 1.0) * 100.0 if last > 0 and open24h > 0 else 0.0
            row = promo._market_row(
                "coinex",
                str(item.get("market") or ""),
                last,
                change,
                item.get("value"),
            )
            if row and row["quote_symbol"] == "USDC":
                row["market_data_endpoint"] = endpoint
                row["endpoint_fallback_used"] = False
                out.append(row)
        _record_success("coinex", endpoint, attempts, COINEX_SPOT_TICKER_ENDPOINTS[0])
        return out
    except Exception as exc:
        _record_failure("coinex", attempts, exc, "official_coinex_pool")
        raise


def _pool_size(name: str) -> int:
    return {
        "binance": len(BINANCE_SPOT_TICKER_ENDPOINTS),
        "bybit": len(BYBIT_SPOT_TICKER_ENDPOINTS),
        "bitget": len(BITGET_SPOT_TICKER_ENDPOINTS),
        "coinex": len(COINEX_SPOT_TICKER_ENDPOINTS),
    }[name]


def install(promo) -> None:
    """Install official failover and explicit independent redundancy coverage."""
    if getattr(promo, "_wallet500_official_cex_fallbacks_installed", False):
        return

    original_collect = promo.collect_usdc_markets
    promo.USDC_SOURCES["binance"] = lambda: _collect_binance(promo)
    promo.USDC_SOURCES["bybit"] = lambda: _collect_bybit(promo)
    promo.USDC_SOURCES["bitget"] = lambda: _collect_bitget(promo)
    promo.USDC_SOURCES["coinex"] = lambda: _collect_coinex(promo)

    def collect_with_endpoint_health():
        _reset()
        rows, health = original_collect()
        endpoint_health = _snapshot()
        for name in ("binance", "bybit", "bitget", "coinex"):
            if name in endpoint_health:
                health.setdefault(name, {}).update(endpoint_health[name])
                health[name]["fallback_pool_size"] = _pool_size(name)

        bybit_direct_ok = bool((health.get("bybit") or {}).get("ok") and (health.get("bybit") or {}).get("markets", 0) > 0)
        replacement_health = {
            name: bool((health.get(name) or {}).get("ok") and (health.get(name) or {}).get("markets", 0) > 0)
            for name in BYBIT_GAP_COMPENSATION_SOURCES
        }
        two_source_compensation_ok = all(replacement_health.values())
        coverage_ok = bybit_direct_ok or two_source_compensation_ok
        health["bybit_gap_coverage"] = {
            "ok": coverage_ok,
            "direct_bybit_available": bybit_direct_ok,
            "coverage_state": (
                "DIRECT_BYBIT"
                if bybit_direct_ok
                else "INDEPENDENT_TWO_CEX_REDUNDANCY"
                if two_source_compensation_ok
                else "GAP_OPEN"
            ),
            "compensation_sources": list(BYBIT_GAP_COMPENSATION_SOURCES),
            "compensation_source_health": replacement_health,
            "minimum_independent_compensation_sources": 2,
            "geo_restriction_circumvention": False,
            "regional_bybit_endpoints_used_as_proxy": False,
            "truth_note": "Direct Bybit stays fail-closed; Bitget and CoinEx compensate market-visibility loss without being mislabeled as Bybit.",
        }
        return rows, health

    promo.collect_usdc_markets = collect_with_endpoint_health
    promo._wallet500_official_cex_fallbacks_installed = True
