from wallet500.revival_historical_dna import _archetypes, _forward, build
from datetime import datetime, timezone, timedelta


def point(minute, price, liquidity, volume=100, buys=10, sells=10):
    at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    return {
        "at": at,
        "at_iso": at.isoformat(),
        "price": price,
        "liquidity": liquidity,
        "volume_h1": volume,
        "buys_h1": buys,
        "sells_h1": sells,
        "txns_h1": buys + sells,
    }


def test_liquidity_can_lead_flat_price_without_future_input():
    hist = [point(0, 1.0, 100_000), point(30, 1.01, 104_000, 180, 14, 10)]
    names, features = _archetypes(hist, 1)
    assert "LIQ_LEADS" in names
    assert features["liquidity_change_pct"] > 3
    assert features["price_change_pct"] < 3


def test_strong_liquidity_volume_tx_stack_is_separate_archetype():
    hist = [point(0, 1.0, 100_000, 100, 10, 10), point(30, 1.01, 103_000, 180, 18, 12)]
    names, _ = _archetypes(hist, 1)
    assert "LIQ_PLUS_VOLUME" in names
    assert "LIQ_VOLUME_TX_STACK" in names


def test_forward_label_uses_only_later_observation_near_horizon():
    hist = [point(0, 1.0, 100_000), point(30, 1.0, 104_000), point(90, 1.25, 110_000)]
    out = _forward(hist, 1, 60)
    assert out is not None
    assert round(out["return_pct"], 2) == 25.0


def test_build_rejects_wrong_pair_history_from_feature_series():
    pair = "PAIR_A"
    token = {
        "chain": "solana",
        "token": "TOKEN_A",
        "entry_pair_address": pair,
        "first_seen": "2026-01-01T00:00:00+00:00",
        "history": [
            {"observed_at": "2026-01-01T00:00:00+00:00", "pair_address": pair, "price_usd": 1, "liquidity_usd": 100000, "volume_h1": 100, "buys_h1": 10, "sells_h1": 10},
            {"observed_at": "2026-01-01T00:30:00+00:00", "pair_address": "PAIR_B", "price_usd": 2, "liquidity_usd": 999999, "volume_h1": 999999, "buys_h1": 999, "sells_h1": 1},
            {"observed_at": "2026-01-01T01:00:00+00:00", "pair_address": pair, "price_usd": 1.01, "liquidity_usd": 104000, "volume_h1": 180, "buys_h1": 15, "sells_h1": 10},
            {"observed_at": "2026-01-01T02:00:00+00:00", "pair_address": pair, "price_usd": 1.20, "liquidity_usd": 108000, "volume_h1": 220, "buys_h1": 20, "sells_h1": 12},
        ],
    }
    payload = build({"tokens": {"x": token}})
    assert payload["network"] == "solana"
    assert payload["production_impact"] == "NONE"
    assert payload["truth_contract"]["identity"] == "SOLANA_TOKEN_PLUS_LOCKED_ENTRY_PAIR_ONLY"
