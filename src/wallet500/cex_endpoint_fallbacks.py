from __future__ import annotations

"""Official public-endpoint failover for Wallet500 CEX market data.

The GitHub-hosted runner can receive geo/WAF responses from some primary CEX
hosts even though equivalent official public market-data endpoints are available.
This module keeps exchange identity unchanged: Binance data only comes from
official Binance hosts, and Bybit data only comes from official Bybit hosts.
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
        _record("binance", {
            "endpoint": endpoint,
            "endpoint_fallback_used": endpoint != BINANCE_SPOT_TICKER_ENDPOINTS[0],
            "endpoint_attempts": attempts,
            "official_endpoint_only": True,
        })
        return out
    except Exception as exc:
        _record("binance", {
            "endpoint": None,
            "endpoint_fallback_used": True,
            "endpoint_attempts": attempts or [{"endpoint": "official_binance_pool", "ok": False, "error": _error_text(exc)}],
            "official_endpoint_only": True,
        })
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
        _record("bybit", {
            "endpoint": endpoint,
            "endpoint_fallback_used": endpoint != BYBIT_SPOT_TICKER_ENDPOINTS[0],
            "endpoint_attempts": attempts,
            "official_endpoint_only": True,
        })
        return out
    except Exception as exc:
        _record("bybit", {
            "endpoint": None,
            "endpoint_fallback_used": True,
            "endpoint_attempts": attempts or [{"endpoint": "official_bybit_pool", "ok": False, "error": _error_text(exc)}],
            "official_endpoint_only": True,
        })
        raise


def install(promo) -> None:
    """Install failover collectors and expose endpoint telemetry in source health."""
    if getattr(promo, "_wallet500_official_cex_fallbacks_installed", False):
        return

    original_collect = promo.collect_usdc_markets
    promo.USDC_SOURCES["binance"] = lambda: _collect_binance(promo)
    promo.USDC_SOURCES["bybit"] = lambda: _collect_bybit(promo)

    def collect_with_endpoint_health():
        _reset()
        rows, health = original_collect()
        endpoint_health = _snapshot()
        for name in ("binance", "bybit"):
            if name in endpoint_health:
                health.setdefault(name, {}).update(endpoint_health[name])
                health[name]["fallback_pool_size"] = (
                    len(BINANCE_SPOT_TICKER_ENDPOINTS) if name == "binance" else len(BYBIT_SPOT_TICKER_ENDPOINTS)
                )
        return rows, health

    promo.collect_usdc_markets = collect_with_endpoint_health
    promo._wallet500_official_cex_fallbacks_installed = True
