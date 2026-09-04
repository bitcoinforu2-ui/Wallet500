from pathlib import Path

from wallet500 import cex_spot_revival as spot


def test_gate_spot_parses_usdt_markets(monkeypatch):
    monkeypatch.setattr(
        spot,
        "_get",
        lambda url: [
            {
                "currency_pair": "IDOS_USDT",
                "last": "0.011",
                "change_percentage": "111.5",
                "quote_volume": "281440",
            },
            {
                "currency_pair": "BTC_USDC",
                "last": "100000",
                "change_percentage": "1",
                "quote_volume": "1",
            },
        ],
    )
    rows = spot.gate_spot()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "IDOSUSDT"
    assert rows[0]["market_type"] == "spot"
    assert rows[0]["change_24h_pct"] == 111.5
    assert rows[0]["volume_24h"] == 281440.0


def test_idos_like_acceleration_reaches_dna_watch_score():
    signal = spot._market_signal(
        {
            "exchange": "gate",
            "change_24h_pct": 60.0,
            "price_delta_pct": 8.0,
            "volume24_delta_pct": 150.0,
            "volume_24h": 300000.0,
        }
    )
    assert signal["score"] >= spot.ALERT_SCORE
    assert {"MOMENTUM", "PRICE_ACCEL", "VOLUME_ACCEL"}.issubset(set(signal["hits"]))


def test_spot_output_is_research_only_and_keeps_milestones(tmp_path: Path, monkeypatch):
    rows = [
        {
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "IDOSUSDT",
            "market_id": "IDOS_USDT",
            "price": 0.008,
            "change_24h_pct": 60.0,
            "volume_24h": 100000.0,
        }
    ]
    monkeypatch.setattr(spot, "SPOT_SOURCES", [("gate", lambda: rows)])
    first = spot.run_cex_spot_revival(tmp_path, "2026-09-04T08:00:00+00:00")
    assert first["production_portfolio_impact"] == "NONE"
    assert first["symbol_only_actionable"] is False
    assert first["watch_count"] == 1

    rows[0] = {**rows[0], "price": 0.011, "change_24h_pct": 111.0, "volume_24h": 300000.0}
    second = spot.run_cex_spot_revival(tmp_path, "2026-09-04T08:15:00+00:00")
    assert second["alerts_count"] == 1
    alert = second["alerts"][0]
    assert alert["symbol"] == "IDOSUSDT"
    assert alert["actionable"] is False
    assert alert["identity_required_before_actionable"] is True
    assert alert["milestones"]["first_seen"]["observed_at"] == "2026-09-04T08:00:00+00:00"
    assert alert["milestones"]["first_alert"]["observed_at"] == "2026-09-04T08:15:00+00:00"
