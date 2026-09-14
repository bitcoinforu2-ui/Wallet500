import pytest

from wallet500 import cex_spot_revival_adapter as mod


def test_mexc_uses_open_to_last_percentage(monkeypatch):
    monkeypatch.setattr(
        mod.base,
        "_get",
        lambda _url: [{
            "symbol": "BRUSDT",
            "lastPrice": "0.42",
            "openPrice": "0.253",
            "priceChangePercent": "0.6581",
            "quoteVolume": "100000",
        }],
    )
    row = mod.mexc_spot_fixed()[0]
    assert row["change_24h_pct"] == pytest.approx((0.42 / 0.253 - 1) * 100)


def test_mexc_fractional_fallback_is_multiplied_by_100(monkeypatch):
    monkeypatch.setattr(
        mod.base,
        "_get",
        lambda _url: [{
            "symbol": "AINUSDT",
            "lastPrice": "0.105",
            "priceChangePercent": "0.4887",
            "quoteVolume": "300000",
        }],
    )
    row = mod.mexc_spot_fixed()[0]
    assert row["change_24h_pct"] == pytest.approx(48.87)
