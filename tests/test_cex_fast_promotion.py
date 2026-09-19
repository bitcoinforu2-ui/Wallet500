from __future__ import annotations

from datetime import datetime, timedelta, timezone

from wallet500.cex_fast_promotion import (
    _canonical_symbol,
    _eligibility,
    _market_row,
)
from wallet500.cex_reactivation_hold import evaluate_hold


def _row(**overrides):
    base = {
        "symbol": "TESTUSDT",
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "execution_pair_price_coherent": True,
        "market_age_verified": True,
        "market_age_min_days": 240,
        "chain": "solana",
        "token_address": "So11111111111111111111111111111111111111112",
        "pair_address": "Pair111111111111111111111111111111111111111",
        "execution_pool_liquidity_usd": 80_000,
        "spot_revival_score": 42,
        "coherent_confirmations": 2,
        "exchanges": ["gate", "kucoin"],
        "leaderboard_best_rank": 2,
        "markets": [
            {
                "exchange": "gate",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST_USDT",
                "quote_symbol": "USDT",
                "price": 0.012,
                "change_24h_pct": 18.0,
                "volume_24h": 500_000,
                "volume_comparable_usd_like": True,
            },
            {
                "exchange": "kucoin",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST-USDT",
                "quote_symbol": "USDT",
                "price": 0.0121,
                "change_24h_pct": 17.7,
                "volume_24h": 300_000,
                "volume_comparable_usd_like": True,
            },
        ],
        "milestones": {
            "first_alert": {
                "observed_at": "2026-09-14T12:00:00+00:00",
                "reference_price": 0.010,
                "reference_change_24h_pct": 5.0,
                "score": 40,
            }
        },
    }
    base.update(overrides)
    return base


def test_verified_multi_exchange_candidate_promotes():
    ok, metrics = _eligibility(_row())
    assert ok is True
    assert metrics["blockers"] == []
    assert metrics["signal_price"] == 0.010
    assert metrics["current_price"] > 0


def test_late_move_is_blocked_even_when_identity_is_verified():
    row = _row()
    for market in row["markets"]:
        market["change_24h_pct"] = 68.0
    ok, metrics = _eligibility(row)
    assert ok is False
    assert "LATE_MOVE_DO_NOT_CHASE" in metrics["blockers"]


def test_symbol_only_or_unverified_identity_never_promotes():
    ok, metrics = _eligibility(_row(identity_status="IDENTITY_PENDING", identity_verified=False))
    assert ok is False
    assert "EXACT_IDENTITY_NOT_VERIFIED" in metrics["blockers"]


def test_single_exchange_requires_strict_top1_exception():
    row = _row(
        coherent_confirmations=1,
        exchanges=["gate"],
        leaderboard_best_rank=1,
        spot_revival_score=45,
        markets=[{
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "TESTUSDT",
            "market_id": "TEST_USDT",
            "quote_symbol": "USDT",
            "price": 0.012,
            "change_24h_pct": 20.0,
            "volume_24h": 300_000,
            "volume_comparable_usd_like": True,
        }],
    )
    ok, metrics = _eligibility(row)
    assert ok is True
    assert metrics["single_exchange_exception"] is True

    row["leaderboard_best_rank"] = 4
    ok, metrics = _eligibility(row)
    assert ok is False
    assert "CEX_CONFIRMATION_INSUFFICIENT" in metrics["blockers"]


def test_usdc_market_is_canonicalized_into_same_token_group():
    row = _market_row("gate", "REZ_USDC", 0.004, 22, 450_000)
    assert row is not None
    assert row["symbol"] == "REZUSDT"
    assert row["quote_symbol"] == "USDC"
    assert _canonical_symbol("REZ/USDC") == "REZUSDT"


def test_research_source_only_promotes_after_hard_truth_gates_pass():
    row = _row(research_only=True)
    ok, metrics = _eligibility(row)
    assert ok is True

    row["execution_pair_price_coherent"] = False
    ok, metrics = _eligibility(row)
    assert ok is False
    assert "CEX_DEX_PRICE_COHERENCE_NOT_VERIFIED" in metrics["blockers"]


def test_reactivation_first_observation_is_pending_not_confirmed():
    now = datetime(2026, 9, 16, 17, 17, tzinfo=timezone.utc)
    decision = evaluate_hold(
        None,
        now=now,
        pair_address="0xPAIR",
        current_pair_price=0.0041665,
    )
    assert decision["state"] == "PENDING_HOLD"
    assert decision["confirmed"] is False
    assert decision["entry"]["trigger_price_usd"] == 0.0041665


def test_reactivation_followup_too_early_stays_pending_and_trigger_is_immutable():
    now = datetime(2026, 9, 16, 17, 17, tzinfo=timezone.utc)
    first = evaluate_hold(None, now=now, pair_address="0xPAIR", current_pair_price=0.0041665)
    follow = evaluate_hold(
        first["entry"],
        now=now + timedelta(minutes=3),
        pair_address="0xPAIR",
        current_pair_price=0.00420,
    )
    assert follow["state"] == "PENDING_HOLD"
    assert follow["confirmed"] is False
    assert follow["entry"]["triggered_at"] == first["entry"]["triggered_at"]
    assert follow["entry"]["trigger_price_usd"] == first["entry"]["trigger_price_usd"]


def test_reactivation_followup_after_delay_confirms_only_when_exact_pair_holds():
    now = datetime(2026, 9, 16, 17, 17, tzinfo=timezone.utc)
    first = evaluate_hold(None, now=now, pair_address="0xPAIR", current_pair_price=0.0041665)
    held = evaluate_hold(
        first["entry"],
        now=now + timedelta(minutes=10),
        pair_address="0xPAIR",
        current_pair_price=0.00422,
    )
    assert held["state"] == "CONFIRMED_HOLD"
    assert held["confirmed"] is True
    assert held["change_since_trigger_pct"] > 0


def test_reactivation_followup_below_trigger_is_fade_and_requires_reclaim():
    now = datetime(2026, 9, 16, 17, 17, tzinfo=timezone.utc)
    first = evaluate_hold(None, now=now, pair_address="0xPAIR", current_pair_price=0.0041665)
    faded = evaluate_hold(
        first["entry"],
        now=now + timedelta(minutes=10),
        pair_address="0xPAIR",
        current_pair_price=0.003924,
    )
    assert faded["state"] == "FADE_RECLAIM_REQUIRED"
    assert faded["confirmed"] is False
    assert faded["entry"]["trigger_price_usd"] == 0.0041665

    reclaimed = evaluate_hold(
        faded["entry"],
        now=now + timedelta(minutes=14),
        pair_address="0xPAIR",
        current_pair_price=0.00418,
    )
    assert reclaimed["state"] == "CONFIRMED_HOLD"
    assert reclaimed["confirmed"] is True


def test_reactivation_pair_change_or_expired_window_starts_new_trigger():
    now = datetime(2026, 9, 16, 17, 17, tzinfo=timezone.utc)
    first = evaluate_hold(None, now=now, pair_address="0xPAIR1", current_pair_price=0.0040)
    changed = evaluate_hold(
        first["entry"],
        now=now + timedelta(minutes=10),
        pair_address="0xPAIR2",
        current_pair_price=0.0041,
    )
    assert changed["state"] == "PENDING_HOLD"
    assert changed["entry"]["pair_address"] == "0xPAIR2"
    assert changed["entry"]["trigger_price_usd"] == 0.0041

    expired = evaluate_hold(
        changed["entry"],
        now=now + timedelta(minutes=31),
        pair_address="0xPAIR2",
        current_pair_price=0.0042,
    )
    assert expired["state"] == "PENDING_HOLD"
    assert expired["entry"]["trigger_price_usd"] == 0.0042


def test_regional_native_quote_exchange_does_not_satisfy_multi_exchange_gate():
    row = _row(
        coherent_confirmations=1,
        exchanges=["gate", "upbit"],
        leaderboard_best_rank=2,
        markets=[
            {
                "exchange": "gate",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST_USDT",
                "quote_symbol": "USDT",
                "price": 0.012,
                "change_24h_pct": 18.0,
                "volume_24h": 500_000,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            },
            {
                "exchange": "upbit",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "KRW-TEST",
                "quote_symbol": "KRW",
                "price": 17.0,
                "change_24h_pct": 70.0,
                "volume_24h": 90_000_000_000,
                "volume_comparable_usd_like": False,
                "regional_market": True,
            },
        ],
    )
    ok, metrics = _eligibility(row)
    assert ok is False
    assert metrics["exchanges"] == ["gate"]
    assert metrics["observed_exchanges"] == ["gate", "upbit"]
    assert "CEX_CONFIRMATION_INSUFFICIENT" in metrics["blockers"]
    assert metrics["current_change_24h_pct"] == 18.0


def test_same_ticker_collision_outlier_is_excluded_from_current_action_metrics():
    row = _row(
        coherent_confirmations=2,
        exchanges=["gate", "okx", "kucoin"],
        symbol_collision={
            "suspected": True,
            "price_coherent_exchanges": ["okx", "kucoin"],
            "outlier_exchanges": ["gate"],
        },
        markets=[
            {
                "exchange": "gate",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST_USDT",
                "quote_symbol": "USDT",
                "price": 0.10,
                "change_24h_pct": 70.0,
                "volume_24h": 5_000_000,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            },
            {
                "exchange": "okx",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST-USDT",
                "quote_symbol": "USDT",
                "price": 0.012,
                "change_24h_pct": 18.0,
                "volume_24h": 500_000,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            },
            {
                "exchange": "kucoin",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST-USDT",
                "quote_symbol": "USDT",
                "price": 0.0121,
                "change_24h_pct": 17.7,
                "volume_24h": 300_000,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            },
        ],
    )
    ok, metrics = _eligibility(row)
    assert ok is True
    assert metrics["exchanges"] == ["kucoin", "okx"]
    assert metrics["observed_exchanges"] == ["gate", "kucoin", "okx"]
    assert metrics["current_change_24h_pct"] == 18.0
    assert metrics["current_price"] < 0.02
    assert "LATE_MOVE_DO_NOT_CHASE" not in metrics["blockers"]


def test_fresh_cross_venue_reactivation_milestone_beats_stale_first_alert():
    row = _row(
        spot_revival_score=63,
        milestones={
            "first_alert": {
                "observed_at": "2026-09-05T18:55:50.520435+00:00",
                "reference_price": 0.000362,
                "reference_change_24h_pct": -0.54,
                "score": 35,
            },
            "first_cross_venue_slow_ignition": {
                "observed_at": "2026-09-18T04:17:00.898003+00:00",
                "reference_price": 0.000239,
                "reference_change_24h_pct": 12.73,
                "score": 18,
                "exchanges": ["gate", "kucoin"],
            },
        },
    )
    ok, metrics = _eligibility(row)
    assert ok is True
    assert metrics["signal_milestone"] == "first_cross_venue_slow_ignition"
    assert metrics["signal_at"] == "2026-09-18T04:17:00.898003+00:00"
    assert metrics["signal_price"] == 0.000239


def test_relative_volume_shock_allows_low_absolute_turnover_handoff_before_late_move():
    row = _row(
        spot_revival_score=63,
        coherent_confirmations=2,
        exchanges=["gate", "kucoin"],
        execution_pool_liquidity_usd=18_000,
        volume_multiple_6h_max=5.72,
        volume_acceleration_max_pct=142.7,
        milestones={
            "first_cross_venue_slow_ignition": {
                "observed_at": "2026-09-18T04:17:00.898003+00:00",
                "reference_price": 0.000239,
                "reference_change_24h_pct": 12.73,
                "score": 18,
            }
        },
        markets=[
            {
                "exchange": "gate",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST_USDT",
                "quote_symbol": "USDT",
                "price": 0.0003083,
                "change_24h_pct": 25.88,
                "volume_24h": 1802.33,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            },
            {
                "exchange": "kucoin",
                "market_type": "spot",
                "symbol": "TESTUSDT",
                "market_id": "TEST-USDT",
                "quote_symbol": "USDT",
                "price": 0.000306,
                "change_24h_pct": 24.8,
                "volume_24h": 1175.42,
                "volume_comparable_usd_like": True,
                "regional_market": False,
            },
        ],
    )
    ok, metrics = _eligibility(row)
    assert ok is True
    assert metrics["cex_turnover_usd"] < 100_000
    assert metrics["relative_volume_shock"] is True
    assert metrics["relative_volume_turnover_exception"] is True
    assert "CEX_TURNOVER_LT_100K_WITHOUT_RELATIVE_VOLUME_SHOCK" not in metrics["blockers"]
    assert "LATE_MOVE_DO_NOT_CHASE" not in metrics["blockers"]
