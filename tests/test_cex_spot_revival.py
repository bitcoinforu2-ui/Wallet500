import json
from datetime import datetime, timedelta, timezone
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


def test_binance_spot_parses_usdt_markets(monkeypatch):
    monkeypatch.setattr(
        spot,
        "_get",
        lambda url: [
            {
                "symbol": "LSKUSDT",
                "lastPrice": "0.14",
                "priceChangePercent": "4.5",
                "quoteVolume": "12000000",
            },
            {
                "symbol": "BTCUSDC",
                "lastPrice": "100000",
                "priceChangePercent": "1",
                "quoteVolume": "1",
            },
        ],
    )
    rows = spot.binance_spot()
    assert len(rows) == 1
    assert rows[0]["exchange"] == "binance"
    assert rows[0]["symbol"] == "LSKUSDT"
    assert rows[0]["quote_symbol"] == "USDT"
    assert rows[0]["volume_comparable_usd_like"] is True


def test_upbit_spot_maps_krw_market_into_canonical_research_symbol(monkeypatch):
    def fake_get(url):
        if "market/all" in url:
            return [{"market": "KRW-LSK"}, {"market": "BTC-LSK"}]
        if "ticker?" in url:
            return [
                {
                    "market": "KRW-LSK",
                    "trade_price": 198.0,
                    "signed_change_rate": 0.031,
                    "acc_trade_price_24h": 1234567890,
                }
            ]
        raise AssertionError(url)

    monkeypatch.setattr(spot, "_get", fake_get)
    rows = spot.upbit_spot()
    assert len(rows) == 1
    row = rows[0]
    assert row["exchange"] == "upbit"
    assert row["symbol"] == "LSKUSDT"
    assert row["market_id"] == "KRW-LSK"
    assert row["quote_symbol"] == "KRW"
    assert row["regional_market"] is True
    assert row["volume_comparable_usd_like"] is False
    assert row["change_24h_pct"] == 3.1


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


def test_lsk_absorption_is_shadow_only_and_does_not_raise_score():
    signal = spot._market_signal(
        {
            "exchange": "upbit",
            "change_24h_pct": 4.0,
            "price_delta_pct": 0.5,
            "volume24_delta_pct": 30.0,
            "volume_24h": 1_000_000_000.0,
            "volume_comparable_usd_like": False,
            "history_points": 12,
            "price_window_pct": 6.0,
            "volume_window_multiple": 5.5,
        }
    )
    assert "VOLUME_PRICE_ABSORPTION_SHADOW" in signal["shadow_hits"]
    assert "VOLUME_PRICE_ABSORPTION_SHADOW" not in signal["hits"]
    assert signal["score"] == 20


def test_persistent_pressure_is_shadow_only_and_does_not_raise_score():
    signal = spot._market_signal(
        {
            "exchange": "kucoin",
            "change_24h_pct": 5.4,
            "price_delta_pct": 0.2,
            "volume24_delta_pct": 1.5,
            "volume_24h": 650_000.0,
            "volume_comparable_usd_like": True,
            "history_points": 30,
            "price_window_pct": 5.4,
            "volume_window_multiple": 1.4,
            "volume_multiple_6h": 1.25,
            "volume_multiple_12h": 1.40,
            "volume_multiple_24h": 0.0,
        }
    )
    assert "PERSISTENT_SPOT_PRESSURE_SHADOW" in signal["shadow_hits"]
    assert "PERSISTENT_SPOT_PRESSURE_MULTI_HORIZON_SHADOW" in signal["shadow_hits"]
    assert "PERSISTENT_SPOT_PRESSURE_SHADOW" not in signal["hits"]
    assert signal["score"] == 3


def test_slow_ignition_requires_cross_venue_pressure():
    one = [
        {
            "exchange": "kucoin",
            "shadow_hits": ["PERSISTENT_SPOT_PRESSURE_SHADOW"],
            "pressure_horizon_hits": ["6h"],
        }
    ]
    building = spot._slow_ignition(one)
    assert building["status"] == "BUILDING"
    assert building["confirmations"] == 1

    two = one + [
        {
            "exchange": "mexc",
            "shadow_hits": ["PERSISTENT_SPOT_PRESSURE_SHADOW"],
            "pressure_horizon_hits": ["6h", "12h"],
        }
    ]
    confirmed = spot._slow_ignition(two)
    assert confirmed["status"] == "CROSS_VENUE_PERSISTENT"
    assert confirmed["confirmations"] == 2
    assert confirmed["affects_score"] is False
    assert confirmed["actionable"] is False


def test_regional_first_marks_upbit_lead_without_score_bonus():
    local = [
        {
            "exchange": "upbit",
            "hit_count": 1,
            "hits": ["VOLUME_ACCEL"],
            "shadow_hits": ["VOLUME_PRICE_ABSORPTION_SHADOW"],
        },
        {"exchange": "binance", "hit_count": 0, "hits": [], "shadow_hits": []},
    ]
    lead = spot._regional_lead(local)
    assert lead["status"] == "REGIONAL_FIRST"
    assert lead["regional_exchanges"] == ["upbit"]
    assert lead["nonregional_coherent_confirmations"] == 0


def test_leveraged_product_suffix_detection():
    assert spot._is_leveraged_product("BEAT3SUSDT") is True
    assert spot._is_leveraged_product("FARTCOIN5SUSDT") is True
    assert spot._is_leveraged_product("BTC3LUSDT") is True
    assert spot._is_leveraged_product("RAYUSDT") is False
    assert spot._is_leveraged_product("BFCUSDT") is False


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
    assert alert["shadow_features_affect_score"] is False
    assert alert["source_coverage"]["confidence"] == "HIGH"
    assert alert["milestones"]["first_seen"]["observed_at"] == "2026-09-04T08:00:00+00:00"
    assert alert["milestones"]["first_alert"]["observed_at"] == "2026-09-04T08:15:00+00:00"


def test_shadow_watch_surfaces_below_regular_watch_score(tmp_path: Path, monkeypatch):
    base = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    state = {
        "gate": {
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "CPOOLUSDT",
            "market_id": "CPOOL_USDT",
            "price": 1.0,
            "change_24h_pct": 0.0,
            "volume_24h": 100_000.0,
            "volume_comparable_usd_like": True,
        },
        "mexc": {
            "exchange": "mexc",
            "market_type": "spot",
            "symbol": "CPOOLUSDT",
            "market_id": "CPOOLUSDT",
            "price": 1.0,
            "change_24h_pct": 0.0,
            "volume_24h": 100_000.0,
            "volume_comparable_usd_like": True,
        },
    }
    monkeypatch.setattr(
        spot,
        "SPOT_SOURCES",
        [("gate", lambda: [state["gate"]]), ("mexc", lambda: [state["mexc"]])],
    )

    report = None
    for i in range(25):
        progress = i / 24.0
        for row in state.values():
            row["price"] = 1.0 + 0.05 * progress
            row["change_24h_pct"] = 5.0 * progress
            row["volume_24h"] = 100_000.0 * (1.0 + 0.40 * progress)
        now = (base + timedelta(minutes=15 * i)).isoformat()
        report = spot.run_cex_spot_revival(tmp_path, now)

    assert report is not None
    assert report["watch_count"] == 0
    assert report["alerts_count"] == 0
    assert report["shadow_watch_count"] == 1
    shadow = report["shadow_watchlist"][0]
    assert shadow["symbol"] == "CPOOLUSDT"
    assert shadow["spot_revival_score"] < spot.WATCH_SCORE
    assert shadow["status"] == "SHADOW_WATCH_RESEARCH"
    assert shadow["slow_ignition"]["status"] == "CROSS_VENUE_PERSISTENT"
    assert shadow["slow_ignition"]["confirmations"] == 2
    assert shadow["actionable"] is False
    assert shadow["automatic_buy"] is False
    assert shadow["shadow_features_affect_score"] is False
    assert shadow["milestones"]["first_shadow_watch"]["observed_at"] == (base + timedelta(hours=6)).isoformat()

    learning = json.loads((tmp_path / "cex-spot-learning.json").read_text())
    learned_shadow = {x["symbol"] for x in learning["top_shadow_candidates"]}
    assert "CPOOLUSDT" in learned_shadow
    assert learning["slow_ignition_shadow_only"] is True
    assert learning["shadow_watch_below_watch_score_allowed"] is True


def test_leveraged_products_are_not_used_for_revival_or_learning(tmp_path: Path, monkeypatch):
    rows = [
        {
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "BEAT3SUSDT",
            "market_id": "BEAT3S_USDT",
            "price": 0.0086,
            "change_24h_pct": 137.0,
            "volume_24h": 300000.0,
        },
        {
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "BFCUSDT",
            "market_id": "BFC_USDT",
            "price": 0.038,
            "change_24h_pct": 247.0,
            "volume_24h": 300000.0,
        },
    ]
    monkeypatch.setattr(spot, "SPOT_SOURCES", [("gate", lambda: rows)])
    report = spot.run_cex_spot_revival(tmp_path, "2026-09-10T18:00:00+00:00")
    symbols = {x["symbol"] for x in report["watchlist"]}
    assert "BEAT3SUSDT" not in symbols
    assert "BFCUSDT" in symbols
    assert "BEAT3SUSDT" in report["leveraged_products_excluded"]

    learning = json.loads((tmp_path / "cex-spot-learning.json").read_text())
    learned = {x["symbol"] for x in learning["top_candidates"]}
    assert "BEAT3SUSDT" not in learned
    assert learning["leveraged_cex_products_excluded"] is True
    assert learning["new_lsk_features_shadow_only"] is True


def test_leveraged_product_acceleration_surfaces_underlying_as_shadow_without_score_boost(tmp_path: Path, monkeypatch):
    rows = [
        {
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "STRKUSDT",
            "market_id": "STRK_USDT",
            "price": 0.03,
            "change_24h_pct": 4.0,
            "volume_24h": 500_000.0,
            "quote_symbol": "USDT",
            "volume_comparable_usd_like": True,
            "regional_market": False,
        },
        {
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "STRK3LUSDT",
            "market_id": "STRK3L_USDT",
            "price": 0.4,
            "change_24h_pct": 70.0,
            "volume_24h": 100_000.0,
            "quote_symbol": "USDT",
            "volume_comparable_usd_like": True,
            "regional_market": False,
        },
    ]
    monkeypatch.setattr(spot, "SPOT_SOURCES", [("gate", lambda: rows)])
    report = spot.run_cex_spot_revival(tmp_path, "2026-09-19T07:00:00+00:00")

    assert report["watch_count"] == 0
    assert report["shadow_watch_count"] == 1
    row = report["shadow_watchlist"][0]
    assert row["symbol"] == "STRKUSDT"
    assert row["spot_revival_score"] < spot.WATCH_SCORE
    assert "LEVERAGED_UNDERLYING_MOMENTUM_SHADOW" in row["shadow_features"]
    assert row["leveraged_underlying_sensor"]["active"] is True
    assert row["leveraged_underlying_sensor"]["max_abs_change_24h_pct"] == 70.0
    assert row["leveraged_underlying_sensor"]["affects_score"] is False
    assert row["leveraged_underlying_sensor"]["actionable"] is False


def test_same_ticker_price_collision_is_not_counted_as_cross_exchange_confirmation(tmp_path: Path, monkeypatch):
    gate = [{
        "exchange": "gate",
        "market_type": "spot",
        "symbol": "EDGEUSDT",
        "market_id": "EDGE_USDT",
        "price": 0.10,
        "change_24h_pct": 50.0,
        "volume_24h": 400_000.0,
        "quote_symbol": "USDT",
        "volume_comparable_usd_like": True,
        "regional_market": False,
    }]
    okx = [{
        "exchange": "okx",
        "market_type": "spot",
        "symbol": "EDGEUSDT",
        "market_id": "EDGE-USDT",
        "price": 0.60,
        "change_24h_pct": 2.0,
        "volume_24h": 2_000_000.0,
        "quote_symbol": "USDT",
        "volume_comparable_usd_like": True,
        "regional_market": False,
    }]
    kucoin = [{
        "exchange": "kucoin",
        "market_type": "spot",
        "symbol": "EDGEUSDT",
        "market_id": "EDGE-USDT",
        "price": 0.61,
        "change_24h_pct": 2.2,
        "volume_24h": 1_000_000.0,
        "quote_symbol": "USDT",
        "volume_comparable_usd_like": True,
        "regional_market": False,
    }]
    monkeypatch.setattr(
        spot,
        "SPOT_SOURCES",
        [("gate", lambda: gate), ("okx", lambda: okx), ("kucoin", lambda: kucoin)],
    )

    report = spot.run_cex_spot_revival(tmp_path, "2026-09-19T07:00:00+00:00")
    assert report["symbol_collision_count"] == 1
    collision = report["symbol_collisions"][0]
    assert collision["symbol"] == "EDGEUSDT"
    assert collision["suspected"] is True
    assert collision["price_coherent_exchanges"] == ["kucoin", "okx"]
    assert collision["outlier_exchanges"] == ["gate"]

    row = report["shadow_watchlist"][0]
    assert row["change_24h_max_pct"] == 2.2
    assert row["observed_change_24h_max_pct_all_markets"] == 50.0
    assert row["coherent_confirmations"] == 0
    assert "SYMBOL_COLLISION_OUTLIER_SHADOW" in row["shadow_features"]


def test_regional_momentum_is_shadow_only_and_never_counts_as_action_coherence(tmp_path: Path, monkeypatch):
    rows = [
        {
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "TESTUSDT",
            "market_id": "TEST_USDT",
            "price": 0.01,
            "change_24h_pct": 9.0,
            "volume_24h": 200_000.0,
            "quote_symbol": "USDT",
            "volume_comparable_usd_like": True,
            "regional_market": False,
        },
        {
            "exchange": "upbit",
            "market_type": "spot",
            "symbol": "TESTUSDT",
            "market_id": "KRW-TEST",
            "price": 14.0,
            "change_24h_pct": 60.0,
            "volume_24h": 90_000_000_000.0,
            "quote_symbol": "KRW",
            "volume_comparable_usd_like": False,
            "regional_market": True,
        },
    ]
    monkeypatch.setattr(spot, "SPOT_SOURCES", [("gate", lambda: [rows[0]]), ("upbit", lambda: [rows[1]])])

    report = spot.run_cex_spot_revival(tmp_path, "2026-09-19T07:00:00+00:00")
    row = report["shadow_watchlist"][0]
    assert row["coherent_confirmations"] == 1
    assert row["price_coherent_confirmations"] == 1
    assert row["spot_revival_score"] == 13
    assert "REGIONAL_MOMENTUM_SHADOW" in row["shadow_features"]
    assert row["regional_spot_lead"]["status"] == "REGIONAL_CONFIRMED"
