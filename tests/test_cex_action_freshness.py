from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts import run_cex_action_guarded as guard


def _row(observed_at: str, changes: tuple[float, float]) -> dict:
    return {
        "symbol": "TESTUSDT",
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "execution_pair_price_coherent": True,
        "market_age_verified": True,
        "market_age_min_days": 226,
        "chain": "bsc",
        "token_address": "0xc51a9250795c0186a6fb4a7d20a90330651e4444",
        "pair_address": "0xa651C8Deb3ff9F8D56a26E72042b7A8A1f433480",
        "execution_pool_liquidity_usd": 988_000,
        "spot_revival_score": 58,
        "coherent_confirmations": 2,
        "exchanges": ["gate", "mexc"],
        "leaderboard_best_rank": 2,
        "markets": [
            {
                "exchange": "gate",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST_USDT",
                "quote_symbol": "USDT",
                "price": 0.01282,
                "change_24h_pct": changes[0],
                "volume_24h": 1_770_000,
                "volume_comparable_usd_like": True,
            },
            {
                "exchange": "mexc",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TESTUSDT",
                "quote_symbol": "USDT",
                "price": 0.012827,
                "change_24h_pct": changes[1],
                "volume_24h": 800_000,
                "volume_comparable_usd_like": True,
            },
        ],
        "milestones": {
            "first_alert": {
                "observed_at": observed_at,
                "reference_price": 0.012974,
                "reference_change_24h_pct": 13.79,
                "score": 58,
            }
        },
    }


def test_twelve_day_old_signal_with_flat_current_market_is_not_actionable():
    observed = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
    ok, metrics = guard.action_eligibility(_row(observed, (-0.1, -0.2)))
    assert ok is False
    assert "STALE_SIGNAL_NO_FRESH_REACTIVATION" in metrics["blockers"]
    assert metrics["action_state"] == "WAIT_FRESH_REACTIVATION"
    assert metrics["signal_age_hours"] > guard.MAX_FRESH_SIGNAL_AGE_HOURS
    assert metrics["fresh_reactivation_confirmations"] == 0


def test_stale_signal_can_reenter_only_after_fresh_multi_cex_momentum():
    observed = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
    ok, metrics = guard.action_eligibility(_row(observed, (7.0, 6.0)))
    assert ok is True
    assert metrics["blockers"] == []
    assert metrics["action_state"] == "REENTRY_ZONE"
    assert metrics["action_basis"] == "FRESH_MULTI_CEX_REACTIVATION"
    assert metrics["fresh_reactivation_confirmations"] == 2
    assert metrics["fresh_reactivation_exchanges"] == ["gate", "mexc"]


def test_fresh_signal_keeps_normal_buy_zone():
    observed = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    ok, metrics = guard.action_eligibility(_row(observed, (4.0, 3.5)))
    assert ok is True
    assert metrics["action_state"] == "BUY_ZONE"
    assert metrics["action_basis"] == "FRESH_SIGNAL"
    assert metrics["signal_freshness"] == "FRESH"
