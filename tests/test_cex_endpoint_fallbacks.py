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
        return {
            "retCode": 0,
            "result": {"list": [{
                "symbol": "XYZUSDC",
                "lastPrice": "0.5",
                "price24hPcnt": "0.22",
                "turnover24h": "750000",
            }]},
        }

    fake = _fake_promo(getter)
    fallback.install(fake)
    rows, health = fake.collect_usdc_markets()

    assert sorted(x["exchange"] for x in rows) == ["binance", "bybit"]
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


def test_all_official_endpoints_failed_is_reported_not_silently_accepted(monkeypatch):
    monkeypatch.setattr(fallback, "BINANCE_SPOT_TICKER_ENDPOINTS", ("https://b1.test", "https://b2.test"))
    monkeypatch.setattr(fallback, "BYBIT_SPOT_TICKER_ENDPOINTS", ("https://y1.test", "https://y2.test"))

    def getter(url):
        raise OSError(f"unreachable {url}")

    fake = _fake_promo(getter)
    fallback.install(fake)
    rows, health = fake.collect_usdc_markets()

    assert rows == []
    for name in ("binance", "bybit"):
        assert health[name]["ok"] is False
        assert health[name]["endpoint"] is None
        assert health[name]["official_endpoint_only"] is True
        assert health[name]["fallback_pool_size"] == 2
        assert health[name]["endpoint_attempts"]
