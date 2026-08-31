from datetime import datetime, timedelta, timezone

from wallet500.revival_liquidity_learning import (
    choose_baseline,
    classify_signal,
    liquidity_market_cap_pct,
    pct_change,
    ratio_bucket,
)


def test_liquidity_market_cap_ratio_is_percentage():
    assert liquidity_market_cap_pct(5_000_000, 100_000_000) == 5.0
    assert liquidity_market_cap_pct(500_000, 100_000_000) == 0.5
    assert liquidity_market_cap_pct(1, 0) is None


def test_ratio_buckets_are_stable():
    assert ratio_bucket(None) == "N/A"
    assert ratio_bucket(0.49) == "LT_0_5PCT"
    assert ratio_bucket(0.5) == "0_5_TO_2PCT"
    assert ratio_bucket(2.0) == "2_TO_5PCT"
    assert ratio_bucket(5.0) == "5_TO_10PCT"
    assert ratio_bucket(10.0) == "GE_10PCT"


def test_signal_labels_do_not_overclaim():
    assert classify_signal(None, None) == "BUILDING_BASELINE"
    assert classify_signal(6, 1) == "LIQ_LEADS"
    assert classify_signal(6, 7) == "CO_MOVE_STRONG"
    assert classify_signal(1, 7) == "PRICE_LEADS"
    assert classify_signal(-7, -4) == "CO_MOVE_DOWN"
    assert classify_signal(-7, 1) == "LIQ_DRAIN"
    assert classify_signal(1, 1) == "NEUTRAL"


def test_pct_change_uses_prior_observation_only():
    assert round(pct_change(105, 100), 6) == 5.0
    assert round(pct_change(95, 100), 6) == -5.0
    assert pct_change(100, 0) is None


def test_baseline_selects_nearest_observation_to_30_minutes():
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    history = [
        {"at": (now - timedelta(minutes=26)).isoformat(), "price_usd": 1},
        {"at": (now - timedelta(minutes=31)).isoformat(), "price_usd": 2},
        {"at": (now - timedelta(minutes=44)).isoformat(), "price_usd": 3},
    ]
    baseline = choose_baseline(history, now)
    assert baseline is not None
    assert baseline["price_usd"] == 2
