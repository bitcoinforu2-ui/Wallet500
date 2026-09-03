from wallet500.hybrid_token_profile import MIN_IGNITION_VOLUME_24H_USD, build_profile


TOKEN = "11111111111111111111111111111111"
PAIR = "22222222222222222222222222222222"
OBSERVED_AT = "2026-09-04T00:45:00+00:00"


def stat(mean, var, last, count=4):
    return {"count": count, "mean": mean, "var": var, "last": last}


def mature_state():
    return {
        "observations": 4,
        "pair_address": PAIR,
        "metrics": {
            "price_usd": stat(1.0, 0.01, 1.0),
            "market_cap_usd": stat(900_000, 10_000_000_000, 900_000),
            "volume_24h_usd": stat(3_000, 1_000_000, 3_000),
            "dex_pair_liquidity_usd": stat(60_000, 25_000_000, 60_000),
            "dex_pair_volume_24h_usd": stat(80_000, 100_000_000, 80_000),
        },
    }


def coin(volume_24h_usd):
    return {
        "id": "test-token",
        "network": "solana",
        "network_verified": True,
        "solana_only_platform_verified": True,
        "token_address": TOKEN,
        "symbol": "TEST",
        "name": "Test Token",
        "price_usd": 1.2,
        "market_cap_usd": 1_000_000,
        "volume_24h_usd": volume_24h_usd,
        "change_24h_pct": 12.0,
        "change_7d_pct": 8.0,
        "change_30d_pct": 15.0,
        "drawdown_from_ath_pct": 82.0,
        "watch_score_market_only": 100.0,
        "revival_score_verified": 68.0,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "dex_pair_address": PAIR,
        "dex_pair_liquidity_usd": 80_000,
        "dex_pair_volume_24h_usd": 300_000,
        "dex_link": f"https://dexscreener.com/solana/{PAIR}",
    }


def test_below_10k_cannot_be_promoted_to_hybrid_ignition():
    profile, _ = build_profile(coin(MIN_IGNITION_VOLUME_24H_USD - 1), mature_state(), None, OBSERVED_AT)
    assert profile["baseline_ready"] is True
    assert len(profile["strong_channels"]) >= 2
    assert profile["hybrid_score_verified_normalized"] >= 70
    assert profile["promotion_gates"]["absolute_volume_ready"] is False
    assert profile["status"] == "ABNORMAL_ACTIVITY"


def test_10k_is_eligible_for_hybrid_ignition_when_other_signals_qualify():
    profile, _ = build_profile(coin(MIN_IGNITION_VOLUME_24H_USD), mature_state(), None, OBSERVED_AT)
    assert profile["promotion_gates"]["absolute_volume_ready"] is True
    assert profile["status"] == "HYBRID_IGNITION"
