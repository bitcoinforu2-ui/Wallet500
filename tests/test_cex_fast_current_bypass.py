from __future__ import annotations

from wallet500 import cex_fast_current_bypass as bypass
from wallet500.cex_fast_current_bypass import (
    _milestone_score,
    _priority_candidates,
    _resolve_many,
    _verified_identity_index,
)


def _row(**overrides):
    row = {
        "symbol": "TESTUSDT",
        "spot_revival_score": 28,
        "coherent_confirmations": 2,
        "change_24h_max_pct": 8.0,
        "leveraged_product": False,
        "milestones": {
            "first_alert": {
                "score": 45,
                "reference_price": 0.01,
                "reference_change_24h_pct": 4.0,
            }
        },
        "markets": [
            {"exchange": "gate", "price": 0.011, "volume_24h": 300_000},
            {"exchange": "kucoin", "price": 0.0111, "volume_24h": 250_000},
        ],
    }
    row.update(overrides)
    return row


def test_immutable_first_alert_can_prioritize_current_watch_even_if_current_score_falls():
    row = _row(spot_revival_score=28)
    assert _milestone_score(row) == 45
    chosen = _priority_candidates({"watchlist": [row]})
    assert len(chosen) == 1
    assert chosen[0]["symbol"] == "TESTUSDT"


def test_late_current_move_is_not_spent_on_identity_resolution():
    row = _row(change_24h_max_pct=72.0)
    assert _priority_candidates({"watchlist": [row]}) == []


def test_leveraged_product_never_enters_bypass():
    row = _row(leveraged_product=True)
    assert _priority_candidates({"watchlist": [row]}) == []


def test_missing_live_cex_price_never_enters_bypass():
    row = _row(markets=[])
    assert _priority_candidates({"watchlist": [row]}) == []


def test_leveraged_underlying_sensor_does_not_consume_fast_identity_budget():
    row = _row(
        spot_revival_score=12,
        milestones={},
        leveraged_underlying_sensor={
            "active": True,
            "max_abs_change_24h_pct": 68.0,
            "affects_score": False,
            "actionable": False,
        },
    )
    assert _priority_candidates({"watchlist": [], "shadow_watchlist": [row]}) == []


def test_w3gg_like_absorption_shadow_prioritizes_identity_before_breakout():
    row = _row(
        symbol="W3GGUSDT",
        spot_revival_score=20,
        milestones={},
        change_24h_max_pct=0.48,
        coherent_confirmations=1,
        shadow_features=["VOLUME_PRICE_ABSORPTION_SHADOW"],
        volume_acceleration_max_pct=178.1256,
        volume_window_multiple_max=1.4,
    )
    chosen = _priority_candidates({"watchlist": [], "shadow_watchlist": [row]})
    assert len(chosen) == 1
    assert chosen[0]["symbol"] == "W3GGUSDT"
    assert chosen[0]["_fast_priority_reason"] == "PREWAVE_SPOT_SHADOW"
    assert chosen[0]["_prewave_shadow_priority"] >= 178.0


def test_prewave_fast_lane_cannot_starve_already_qualified_current_signals():
    prewave = [
        _row(
            symbol=f"PW{i}USDT",
            spot_revival_score=20,
            milestones={},
            change_24h_max_pct=1.0,
            shadow_features=["VOLUME_PRICE_ABSORPTION_SHADOW"],
            volume_acceleration_max_pct=100.0 + i,
        )
        for i in range(20)
    ]
    regular = [
        _row(
            symbol=f"REG{i}USDT",
            spot_revival_score=45,
            milestones={},
            change_24h_max_pct=10.0,
            shadow_features=[],
        )
        for i in range(20)
    ]

    chosen = _priority_candidates({"watchlist": regular, "shadow_watchlist": prewave})
    prewave_count = sum(x["symbol"].startswith("PW") for x in chosen)
    regular_count = sum(x["symbol"].startswith("REG") for x in chosen)

    assert len(chosen) == bypass.MAX_STRICT_RESOLVES_PER_RUN
    assert prewave_count == bypass.MAX_PREWAVE_STRICT_RESOLVES_PER_RUN
    assert regular_count == (
        bypass.MAX_STRICT_RESOLVES_PER_RUN
        - bypass.MAX_PREWAVE_STRICT_RESOLVES_PER_RUN
    )


def test_existing_exact_identity_is_reused_without_new_symbol_search(monkeypatch):
    source = _row(
        markets=[
            {
                "exchange": "gate",
                "price": 0.0100,
                "volume_24h": 300_000,
                "volume_comparable_usd_like": True,
            },
            {
                "exchange": "kucoin",
                "price": 0.0101,
                "volume_24h": 250_000,
                "volume_comparable_usd_like": True,
            },
        ]
    )
    payload = {
        "candidates": [{
            "symbol": "TESTUSDT",
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "base",
            "token_address": "0xTOKEN",
            "pair_address": "0xPAIR",
            "dex": "uniswap",
            "dex_url": "https://dexscreener.com/base/0xPAIR",
            "dex_price_usd": 0.01005,
            "execution_pool_liquidity_usd": 100_000,
            "market_age_verified": True,
            "market_age_min_days": 200,
            "execution_pair_price_coherent": True,
        }]
    }

    def should_not_run(_row):
        raise AssertionError("strict symbol search should not run when exact cached identity is coherent")

    monkeypatch.setattr(bypass, "_strict_dex_resolve", should_not_run)
    resolved, failures, hits = _resolve_many([source], _verified_identity_index(payload))

    assert hits == 1
    assert failures == []
    assert len(resolved) == 1
    assert resolved[0]["token_address"] == "0xTOKEN"
    assert resolved[0]["fast_identity_bypass_source"] == "CURRENT_CEX_SPOT_WATCHLIST_EXISTING_EXACT_IDENTITY"


def test_mismatched_cached_identity_is_not_reused(monkeypatch):
    source = _row(
        markets=[{
            "exchange": "gate",
            "price": 0.0100,
            "volume_24h": 300_000,
            "volume_comparable_usd_like": True,
        }]
    )
    payload = {
        "candidates": [{
            "symbol": "TESTUSDT",
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "base",
            "token_address": "0xWRONG",
            "pair_address": "0xWRONGPAIR",
            "dex_price_usd": 0.50,
        }]
    }
    calls = []

    def strict(row):
        calls.append(row["symbol"])
        return {
            **row,
            "chain": "base",
            "token_address": "0xRIGHT",
            "pair_address": "0xRIGHTPAIR",
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
        }

    monkeypatch.setattr(bypass, "_strict_dex_resolve", strict)
    resolved, failures, hits = _resolve_many([source], _verified_identity_index(payload))

    assert hits == 0
    assert calls == ["TESTUSDT"]
    assert failures == []
    assert resolved[0]["token_address"] == "0xRIGHT"



def test_low_score_live_top_gainer_pre_resolves_identity_before_buy_threshold():
    row = _row(
        symbol="EARLYUSDT",
        spot_revival_score=20,
        milestones={},
        coherent_confirmations=1,
        leaderboard_best_rank=2,
        leaderboard_watch=True,
        change_24h_max_pct=12.0,
        markets=[
            {
                "exchange": "gate",
                "price": 0.0105,
                "volume_24h": 85_000,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            }
        ],
    )

    chosen = _priority_candidates({"watchlist": [row]})

    assert len(chosen) == 1
    assert chosen[0]["symbol"] == "EARLYUSDT"
    assert chosen[0]["_fast_priority_reason"] == "LIVE_LEADERBOARD_PREBUY_IDENTITY"
    assert chosen[0]["_live_leaderboard_priority"] is True
    assert chosen[0]["_fast_priority_score"] < bypass.MIN_PRIORITY_SCORE


def test_live_top_gainer_priority_still_refuses_already_extended_move():
    row = _row(
        symbol="LATEUSDT",
        spot_revival_score=20,
        milestones={},
        leaderboard_best_rank=1,
        leaderboard_watch=True,
        change_24h_max_pct=68.0,
        markets=[
            {
                "exchange": "gate",
                "price": 0.0200,
                "volume_24h": 900_000,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            }
        ],
    )

    assert _priority_candidates({"watchlist": [row]}) == []
