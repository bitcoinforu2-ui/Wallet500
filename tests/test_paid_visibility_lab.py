from wallet500.paid_visibility_lab import (
    HORIZONS_MIN,
    PROVIDERS,
    _event_horizon_summary,
    _market_from_pair,
    _market_impact,
    _same_token,
)


def test_provider_registry_has_ten_and_dexscreener_is_automated():
    assert len(PROVIDERS) == 10
    row = next(x for x in PROVIDERS if x["provider"] == "dexscreener")
    assert row["detectability"] == "AUTOMATED_OFFICIAL_API"
    assert 0 in HORIZONS_MIN and 1440 in HORIZONS_MIN


def test_exact_base_token_identity_is_required():
    pair = {
        "pairAddress": "PAIR1",
        "dexId": "raydium",
        "baseToken": {"address": "MintA"},
        "quoteToken": {"address": "So111"},
        "priceUsd": "0.01",
        "liquidity": {"usd": 100000},
        "volume": {"h24": 20000},
        "txns": {"h24": {"buys": 50, "sells": 40}},
        "priceChange": {"h24": 5},
        "marketCap": 1000000,
        "boosts": {"active": 10},
    }
    assert _market_from_pair("solana", "MintA", pair, "2026-01-01T00:00:00+00:00") is not None
    assert _market_from_pair("solana", "MintB", pair, "2026-01-01T00:00:00+00:00") is None


def test_evm_token_identity_is_case_insensitive_but_solana_is_not():
    assert _same_token("ethereum", "0xAbC", "0xabc")
    assert not _same_token("solana", "AbC", "abc")


def test_impact_and_matched_control_excess_return():
    t0 = {"price_usd": 1, "liquidity_usd": 100, "pair_volume_24h_usd": 1000, "market_cap_usd": 1000}
    promoted = {"price_usd": 1.20, "liquidity_usd": 110, "pair_volume_24h_usd": 1500, "market_cap_usd": 1200}
    control_now = {"price_usd": 1.05, "liquidity_usd": 102, "pair_volume_24h_usd": 1100, "market_cap_usd": 1050}
    impact = _market_impact(promoted, t0)
    event = {
        "observations": [{"horizon_min": 60, "market": promoted, "impact": impact}],
        "controls": [
            {
                "t0": t0,
                "observations": [{"horizon_min": 60, "market": control_now}],
            }
        ],
    }
    row = _event_horizon_summary(event, 60)
    assert round(row["promoted_price_change_pct"], 6) == 20.0
    assert round(row["control_median_price_change_pct"], 6) == 5.0
    assert round(row["excess_price_change_pct"], 6) == 15.0
    assert row["control_count"] == 1
