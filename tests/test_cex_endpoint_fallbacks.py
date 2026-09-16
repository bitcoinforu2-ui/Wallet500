from __future__ import annotations

from types import SimpleNamespace

from wallet500 import cex_fast_promotion as core
from wallet500 import cex_endpoint_fallbacks as fallback


def _fake_promo(getter):
    fake = SimpleNamespace()
    fake._get = getter
    fake._market_row = core._market_row
    fake._f = core._f
    fake.USDC_SOURCES = {
        "binance": lambda: [],
        "bybit": lambda: [],
    }

    def collect():
        rows = []
        health = {}
        for name, fn in fake.USDC_SOURCES.items():
            try:
                got = fn()
                rows.extend(got)
                health[name] = {"ok": True, "markets": len(got)}
            except Exception as exc:
                health[name] = {"ok": False, "markets": 0, "error": f"{type(exc).__name__}: {exc}"}
        return rows, health

    fake.collect_usdc_markets = collect
    return fake


def test_binance_and_bybit_use_next_official_endpoint_when_first_fails(monkeypatch):
    monkeypatch.setattr(
        fallback,
        "BINANCE_SPOT_TICKER_ENDPOINTS",
        ("https://binance-primary.test", "https://binance-fallback.test"),
    )
    monkeypatch.setattr(
        fallback,
        "BYBIT_SPOT_TICKER_ENDPOINTS",
        ("https://bybit-primary.test", "https://bybit-fallback.test"),
    )
    monkeypatch.setattr(fallback, "BITGET_SPOT_TICKER_ENDPOINTS", ("https://bitget.test",))
    monkeypatch.setattr(fallback, "COINEX_SPOT_TICKER_ENDPOINTS", ("https://coinex.test",))

    def getter(url):
        if url.endswith("primary.test"):
            raise RuntimeError("blocked")
        if "binance" in url:
            return [{
                "symbol": "ABCUSDC",
                "lastPrice": "1.25",
                "priceChangePercent": "18.5",
                "quoteVolume": "500000",
            }]
        if "bybit" in url:
            return {
                "retCode": 0,
                "result": {"list": [{
                    "symbol": "XYZUSDC",
                    "lastPrice": "0.5",
                    "price24hPcnt": "0.22",
                    "turnover24h": "750000",
                }]},
            }
        if "bitget" in url:
            return {"code": "00000", "data": [{
                "symbol": "BITUSDC", "lastPr": "2", "change24h": "0.10", "quoteVolume": "300000"
            }]}
        if "coinex" in url:
            return {"code": 0, "data": [{
                "market": "CEXUSDC", "last": "1.1", "open": "1.0", "value": "220000"
            }]}
        raise AssertionError(url)

    fake = _fake_promo(getter)
    fallback.install(fake)
    rows, health = fake.collect_usdc_markets()

    assert sorted(x["exchange"] for x in rows) == ["binance", "bitget", "bybit", "coinex"]
    assert health["binance"]["ok"] is True
    assert health["binance"]["endpoint"] == "https://binance-fallback.test"
    assert health["binance"]["endpoint_fallback_used"] is True
    assert len(health["binance"]["endpoint_attempts"]) == 2
    assert health["binance"]["official_endpoint_only"] is True
    assert health["bybit"]["ok"] is True
    assert health["bybit"]["endpoint"] == "https://bybit-fallback.test"
    assert health["bybit"]["endpoint_fallback_used"] is True
    assert len(health["bybit"]["endpoint_attempts"]) == 2
    assert health["bybit"]["official_endpoint_only"] is True
    assert health["bitget"]["ok"] is True
    assert health["coinex"]["ok"] is True
    assert health["bybit_gap_coverage"]["ok"] is True
    assert health["bybit_gap_coverage"]["coverage_state"] == "DIRECT_BYBIT"


def test_bybit_direct_failure_is_compensated_by_two_independent_official_cex_feeds(monkeypatch):
    monkeypatch.setattr(fallback, "BINANCE_SPOT_TICKER_ENDPOINTS", ("https://binance.test",))
    monkeypatch.setattr(fallback, "BYBIT_SPOT_TICKER_ENDPOINTS", ("https://bybit-a.test", "https://bybit-b.test"))
    monkeypatch.setattr(fallback, "BITGET_SPOT_TICKER_ENDPOINTS", ("https://bitget.test",))
    monkeypatch.setattr(fallback, "COINEX_SPOT_TICKER_ENDPOINTS", ("https://coinex.test",))

    def getter(url):
        if "bybit" in url:
            raise PermissionError("geo blocked")
        if "binance" in url:
            return [{
                "symbol": "ABCUSDC", "lastPrice": "1", "priceChangePercent": "5", "quoteVolume": "500000"
            }]
        if "bitget" in url:
            return {"code": "00000", "data": [{
                "symbol": "MOVEUSDC", "lastPr": "0.25", "change24h": "0.18", "quoteVolume": "600000"
            }]}
        if "coinex" in url:
            return {"code": 0, "data": [{
                "market": "MOVEUSDC", "last": "0.251", "open": "0.213", "value": "450000"
            }]}
        raise AssertionError(url)

    fake = _fake_promo(getter)
    fallback.install(fake)
    rows, health = fake.collect_usdc_markets()

    assert health["bybit"]["ok"] is False
    assert health["bybit"]["official_endpoint_only"] is True
    assert health["bitget"]["ok"] is True and health["bitget"]["markets"] == 1
    assert health["coinex"]["ok"] is True and health["coinex"]["markets"] == 1
    coverage = health["bybit_gap_coverage"]
    assert coverage["ok"] is True
    assert coverage["direct_bybit_available"] is False
    assert coverage["coverage_state"] == "INDEPENDENT_TWO_CEX_REDUNDANCY"
    assert coverage["compensation_source_health"] == {"bitget": True, "coinex": True}
    assert coverage["geo_restriction_circumvention"] is False
    assert coverage["regional_bybit_endpoints_used_as_proxy"] is False
    assert sorted({x["exchange"] for x in rows}) == ["binance", "bitget", "coinex"]


def test_all_official_endpoints_failed_is_reported_not_silently_accepted(monkeypatch):
    monkeypatch.setattr(fallback, "BINANCE_SPOT_TICKER_ENDPOINTS", ("https://b1.test", "https://b2.test"))
    monkeypatch.setattr(fallback, "BYBIT_SPOT_TICKER_ENDPOINTS", ("https://y1.test", "https://y2.test"))
    monkeypatch.setattr(fallback, "BITGET_SPOT_TICKER_ENDPOINTS", ("https://g1.test", "https://g2.test"))
    monkeypatch.setattr(fallback, "COINEX_SPOT_TICKER_ENDPOINTS", ("https://c1.test",))

    def getter(url):
        raise OSError(f"unreachable {url}")

    fake = _fake_promo(getter)
    fallback.install(fake)
    rows, health = fake.collect_usdc_markets()

    assert rows == []
    for name in ("binance", "bybit", "bitget", "coinex"):
        assert health[name]["ok"] is False
        assert health[name]["endpoint"] is None
        assert health[name]["official_endpoint_only"] is True
        assert health[name]["endpoint_attempts"]
    assert health["binance"]["fallback_pool_size"] == 2
    assert health["bybit"]["fallback_pool_size"] == 2
    assert health["bitget"]["fallback_pool_size"] == 2
    assert health["coinex"]["fallback_pool_size"] == 1
    assert health["bybit_gap_coverage"]["ok"] is False
    assert health["bybit_gap_coverage"]["coverage_state"] == "GAP_OPEN"
