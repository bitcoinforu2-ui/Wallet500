from datetime import datetime, timezone

from wallet500.fresh_solana_gate import evaluate


NOW = datetime(2026, 8, 27, 10, 33, 27, tzinfo=timezone.utc)


def test_extreme_buy_skew_thin_fresh_liquidity_fails():
    candidate = {
        "chain": "solana",
        "token": "bulldoge",
        "pair_created_at": 1787825047000,
        "liquidity_usd": 33580.75,
        "volume_h1": 200000,
        "buys_h1": 6961,
        "sells_h1": 775,
        "price_usd": 0.0001635,
    }
    out = evaluate(candidate, {"tokens": {}}, NOW)
    assert out["fresh_solana_gate"] == "FAILED"
    assert out["live_survival_gate"] == "FAILED"
    assert "EXTREME_BUY_SKEW_THIN_FRESH_LIQUIDITY" in out["fresh_solana_reasons"]


def test_fresh_candidate_waits_for_verified_survival():
    candidate = {
        "chain": "solana",
        "token": "survivor",
        "pair_created_at": 1787824181000,
        "liquidity_usd": 36804.34,
        "volume_h1": 180000,
        "buys_h1": 8473,
        "sells_h1": 3363,
        "price_usd": 0.0001911,
    }
    out = evaluate(candidate, {"tokens": {}}, NOW)
    assert out["fresh_solana_gate"] == "PENDING"
    assert out["live_survival_gate"] == "PENDING"
    assert "NEED_2_VERIFIED_OBSERVATIONS" in out["fresh_solana_reasons"]


def test_survived_candidate_becomes_active():
    candidate = {
        "chain": "solana",
        "token": "survivor",
        "pair_created_at": 1787823307000,
        "liquidity_usd": 42000,
        "volume_h1": 90000,
        "buys_h1": 1200,
        "sells_h1": 700,
        "price_usd": 0.00020,
    }
    outcomes = {
        "tokens": {
            "solana:survivor": {
                "current_return_pct": 5.0,
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
    assert out["live_survival_gate"] == "ACTIVE"


def test_bsc_candidate_with_verified_crash_never_stays_active():
    candidate = {
        "chain": "bsc",
        "token": "0xABC",
        "liquidity_usd": 80000,
        "volume_h1": 100000,
        "buys_h1": 500,
        "sells_h1": 300,
        "price_usd": 0.0001,
        "price_change_h1": 20,
        "price_change_m5": 2,
    }
    outcomes = {
        "tokens": {
            "bsc:0xabc": {
                "current_return_pct": -96.0,
                "peak_price_usd": 0.002,
                "current_price_usd": 0.0001,
            }
        }
    }
    out = evaluate(candidate, outcomes, NOW)
    assert out["live_survival_gate"] == "FAILED"
    assert "VERIFIED_RETURN_BELOW_MINUS_25PCT" in out["live_survival_reasons"]


def test_ethereum_pump_then_fast_reversal_fails():
    candidate = {
        "chain": "ethereum",
        "token": "0xDEF",
        "liquidity_usd": 120000,
        "volume_h1": 250000,
        "buys_h1": 900,
        "sells_h1": 600,
        "price_usd": 0.01,
        "price_change_h1": 180,
        "price_change_m5": -22,
    }
    out = evaluate(candidate, {"tokens": {}}, NOW)
    assert out["live_survival_gate"] == "FAILED"
    assert "PUMP_THEN_FAST_REVERSAL" in out["live_survival_reasons"]
