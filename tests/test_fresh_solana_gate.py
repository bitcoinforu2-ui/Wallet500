from datetime import datetime, timezone

from wallet500.fresh_solana_gate import evaluate


NOW = datetime(2026, 8, 27, 10, 33, 27, tzinfo=timezone.utc)


def test_extreme_buy_skew_thin_fresh_liquidity_fails():
    candidate = {
        "chain": "solana",
        "token": "bulldoge",
        "pair_created_at": 1787825047000,
        "liquidity_usd": 33580.75,
        "buys_h1": 6961,
        "sells_h1": 775,
        "price_usd": 0.0001635,
    }
    out = evaluate(candidate, {"tokens": {}}, NOW)
    assert out["fresh_solana_gate"] == "FAILED"
    assert "EXTREME_BUY_SKEW_THIN_FRESH_LIQUIDITY" in out["fresh_solana_reasons"]


def test_fresh_candidate_waits_for_verified_survival():
    candidate = {
        "chain": "solana",
        "token": "survivor",
        "pair_created_at": 1787824181000,
        "liquidity_usd": 36804.34,
        "buys_h1": 8473,
        "sells_h1": 3363,
        "price_usd": 0.0001911,
    }
    out = evaluate(candidate, {"tokens": {}}, NOW)
    assert out["fresh_solana_gate"] == "PENDING"
    assert "NEED_2_VERIFIED_OBSERVATIONS" in out["fresh_solana_reasons"]


def test_survived_candidate_becomes_active():
    candidate = {
        "chain": "solana",
        "token": "survivor",
        "pair_created_at": 1787823307000,
        "liquidity_usd": 42000,
        "buys_h1": 1200,
        "sells_h1": 700,
        "price_usd": 0.00020,
    }
    outcomes = {
        "tokens": {
            "solana:survivor": {
                "peak_price_usd": 0.00021,
                "current_price_usd": 0.00020,
                "history": [
                    {"observed_at": "2026-08-27T10:10:00+00:00", "liquidity_usd": 40000},
                    {"observed_at": "2026-08-27T10:25:00+00:00", "liquidity_usd": 42000},
                ],
            }
        }
    }
    out = evaluate(candidate, outcomes, NOW)
    assert out["fresh_solana_gate"] == "ACTIVE"
