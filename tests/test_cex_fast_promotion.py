from __future__ import annotations

from wallet500.cex_fast_promotion import (
    _canonical_symbol,
    _eligibility,
    _market_row,
)


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
