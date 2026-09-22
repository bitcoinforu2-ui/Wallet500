from wallet500 import cex_revival as revival
from wallet500.cex_revival import _market_signal


def test_market_signal_keeps_features_on_same_exchange():
    price_only={
        'exchange':'gate','change_24h_pct':30,'price_delta_pct':4,
        'volume24_delta_pct':0,'oi_delta_pct':0,'funding_rate':0,'volume_24h':1_000_000,
    }
    oi_volume_only={
        'exchange':'mexc','change_24h_pct':0,'price_delta_pct':0,
        'volume24_delta_pct':20,'oi_delta_pct':10,'funding_rate':0,'volume_24h':1_000_000,
    }
    a=_market_signal(price_only);b=_market_signal(oi_volume_only)
    assert set(a['hits'])=={'MOMENTUM','PRICE_ACCEL'}
    assert set(b['hits'])=={'VOLUME_ACCEL','OI_ACCEL'}
    # No helper is allowed to synthesize one venue carrying all four features.
    assert max(a['hit_count'],b['hit_count'])==2


def test_extreme_dispersion_is_not_a_positive_feature():
    # Dispersion itself is deliberately absent from _market_signal feature hits.
    row={
        'exchange':'gate','change_24h_pct':40,'price_delta_pct':0,
        'volume24_delta_pct':0,'oi_delta_pct':0,'funding_rate':0,'volume_24h':0,
    }
    signal=_market_signal(row)
    assert 'DISPERSION' not in signal['hits']


def test_current_derivatives_movers_enter_research_watch_before_alert_threshold(tmp_path, monkeypatch):
    rows = [
        revival._row("bitget", "DELTAUSDT", price=0.023, change=57.9, vol=410_780),
        revival._row("bitget", "PAIRUSDT", price=0.0064, change=37.0, vol=94_250),
    ]
    monkeypatch.setattr(revival, "SOURCES", [("bitget", lambda: rows)])

    report = revival.run_cex_revival(tmp_path, "2026-09-22T15:00:00+00:00")

    watched = {row["symbol"]: row for row in report["watchlist"]}
    assert {"DELTAUSDT", "PAIRUSDT"}.issubset(watched)
    assert watched["DELTAUSDT"]["research_only"] is True
    assert watched["PAIRUSDT"]["research_only"] is True
    assert watched["PAIRUSDT"]["watch_reason"] == "CURRENT_MOVER_WATCH"
    assert watched["PAIRUSDT"]["actionable"] is False
    assert watched["PAIRUSDT"]["automatic_buy"] is False
    assert report["watch_count"] == 2

    # Discovery coverage is widened without weakening the real-alert threshold.
    alerted = {row["symbol"] for row in report["alerts"]}
    assert "PAIRUSDT" not in alerted
