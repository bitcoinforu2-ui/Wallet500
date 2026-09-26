from __future__ import annotations

import scripts.unified_watch_engine as watch
from scripts.unified_watch_engine import pool_reserve_alert_reason, pool_reserve_flow_sensor


POLICY = {
    "pool_reserve_flow_sensor_enabled": True,
    "pool_reserve_flow_min_directional_pct": 12,
    "pool_reserve_flow_strong_pct": 25,
    "pool_reserve_flow_extreme_pct": 50,
    "pool_reserve_flow_telegram_min_severity": "STRONG",
    "allow_direct_pool_reserve_anomaly_alerts": True,
}


def _live(token_reserve: float, quote_reserve: float) -> dict:
    return {
        "pool_token_reserve": token_reserve,
        "pool_quote_reserve": quote_reserve,
        "pool_quote_symbol": "SOL",
        "pool_quote_address": "So111",
        "pool_tracked_token_side": "BASE",
        "pool_reserve_source": "dexscreener",
    }


def test_first_reserve_observation_is_baseline_only():
    sensor = pool_reserve_flow_sensor(_live(1000, 100), {}, POLICY)
    assert sensor["status"] == "BASELINE"
    assert sensor["direction"] == "NEUTRAL"
    assert sensor["triggers"] == []
    assert sensor["alert_eligible"] is False


def test_accumulation_is_token_out_quote_in():
    previous = _live(1000, 100)
    current = _live(700, 140)
    sensor = pool_reserve_flow_sensor(current, previous, POLICY)
    assert sensor["direction"] == "ACCUMULATION"
    assert sensor["severity"] == "STRONG"
    assert sensor["alert_eligible"] is True
    assert sensor["triggers"] == ["POOL_RESERVE_ACCUMULATION_STRONG"]
    assert sensor["token_change_pct"] == -30.0
    assert sensor["quote_change_pct"] == 40.0
    assert pool_reserve_alert_reason({}, sensor) == "POOL_RESERVE_ANOMALY:ACCUMULATION:STRONG:FIRST"


def test_untxd_style_rotation_is_extreme_distribution():
    previous = _live(143_444_356.81, 127.49)
    current = _live(468_200_000.0, 28.09)
    sensor = pool_reserve_flow_sensor(current, previous, POLICY)
    assert sensor["direction"] == "DISTRIBUTION"
    assert sensor["severity"] == "EXTREME"
    assert sensor["alert_eligible"] is True
    assert sensor["token_change_pct"] > 220
    assert sensor["quote_change_pct"] < -77
    assert sensor["triggers"] == ["POOL_RESERVE_DISTRIBUTION_EXTREME"]


def test_same_direction_reserve_move_is_lp_shift_not_directional_signal():
    sensor = pool_reserve_flow_sensor(_live(1300, 130), _live(1000, 100), POLICY)
    assert sensor["status"] == "NON_DIRECTIONAL_RESERVE_SHIFT"
    assert sensor["direction"] == "NEUTRAL"
    assert sensor["triggers"] == []
    assert sensor["alert_eligible"] is False


def test_same_direction_and_severity_are_deduped_but_flip_realerts():
    sensor = pool_reserve_flow_sensor(_live(700, 140), _live(1000, 100), POLICY)
    last = {"direction": "ACCUMULATION", "severity": "STRONG"}
    assert pool_reserve_alert_reason(last, sensor) is None

    flip = pool_reserve_flow_sensor(_live(1000, 100), _live(700, 140), POLICY)
    assert flip["direction"] == "DISTRIBUTION"
    assert "DIRECTION_FLIP" in pool_reserve_alert_reason(last, flip)


def test_live_exact_pair_exposes_base_side_reserve_composition(monkeypatch):
    gt = {
        "data": {
            "attributes": {
                "base_token_price_usd": "1.0",
                "reserve_in_usd": "200",
                "volume_usd": {"h1": "50", "h24": "500"},
                "transactions": {"h1": {"buys": 10, "sells": 5}},
                "price_change_percentage": {"h1": "1", "h24": "2"},
            },
            "relationships": {
                "base_token": {"data": {"id": "solana_TOKEN"}},
                "quote_token": {"data": {"id": "solana_SOL"}},
            },
        }
    }
    ds = {
        "pairs": [{
            "chainId": "solana",
            "pairAddress": "PAIR",
            "baseToken": {"address": "TOKEN", "symbol": "TOK"},
            "quoteToken": {"address": "SOL", "symbol": "SOL"},
            "priceUsd": "1.0",
            "liquidity": {"usd": "200", "base": "1000", "quote": "100"},
            "volume": {"h1": "50", "h24": "500"},
            "txns": {"h1": {"buys": 10, "sells": 5}},
            "priceChange": {"h1": "1", "h24": "2"},
        }]
    }

    def fake_http(url):
        return gt if "geckoterminal" in url else ds

    monkeypatch.setattr(watch, "http_json", fake_http)
    live = watch.live_exact_pair({"network": "solana", "pair": "PAIR", "contract": "TOKEN"}, 2)
    assert live["pool_token_reserve"] == 1000
    assert live["pool_quote_reserve"] == 100
    assert live["pool_quote_symbol"] == "SOL"
    assert live["pool_tracked_token_side"] == "BASE"
    assert live["pool_reserve_source"] == "dexscreener"


def test_quote_side_reserve_composition_survives_dex_price_fail_closed(monkeypatch):
    gt = {
        "data": {
            "attributes": {
                "quote_token_price_usd": "1.0",
                "reserve_in_usd": "200",
                "volume_usd": {"h1": "50", "h24": "500"},
                "transactions": {"h1": {"buys": 10, "sells": 5}},
                "price_change_percentage": {"h1": "1", "h24": "2"},
            },
            "relationships": {
                "base_token": {"data": {"id": "solana_SOL"}},
                "quote_token": {"data": {"id": "solana_TOKEN"}},
            },
        }
    }
    ds = {
        "pairs": [{
            "chainId": "solana",
            "pairAddress": "PAIR",
            "baseToken": {"address": "SOL", "symbol": "SOL"},
            "quoteToken": {"address": "TOKEN", "symbol": "TOK"},
            "priceUsd": "100.0",
            "liquidity": {"usd": "200", "base": "50", "quote": "1000"},
            "volume": {"h1": "50", "h24": "500"},
            "txns": {"h1": {"buys": 10, "sells": 5}},
            "priceChange": {"h1": "1", "h24": "2"},
        }]
    }

    def fake_http(url):
        return gt if "geckoterminal" in url else ds

    monkeypatch.setattr(watch, "http_json", fake_http)
    live = watch.live_exact_pair({"network": "solana", "pair": "PAIR", "contract": "TOKEN"}, 2)
    assert live["single_source_degraded"] is True
    assert live["price_sources"] == ["geckoterminal"]
    assert live["pool_token_reserve"] == 1000
    assert live["pool_quote_reserve"] == 50
    assert live["pool_quote_symbol"] == "SOL"
    assert live["pool_tracked_token_side"] == "QUOTE"
