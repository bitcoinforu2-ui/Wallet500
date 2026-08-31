from wallet500.liquidity_reality import compute_liquidity_reality


def test_penguin_like_distribution_reveals_low_ratio_but_not_single_pool_only():
    pools = [
        {"liquidity_usd": 4_160_000},
        {"liquidity_usd": 3_030_000},
        {"liquidity_usd": 1_560_000},
        {"liquidity_usd": 116_000},
        {"liquidity_usd": 75_000},
        {"liquidity_usd": 48_000},
    ]
    r = compute_liquidity_reality(pools, market_cap_usd=555_300_000, fdv_usd=785_200_000)
    assert r["dex_total_liquidity_usd"] == 8_989_000.0
    assert 1.6 < r["dex_liquidity_to_market_cap_pct"] < 1.7
    assert 46 < r["top_pool_share_pct"] < 47
    assert r["top3_pool_share_pct"] > 97
    assert r["liquidity_concentration_level"] == "HIGH"
    assert r["execution_depth_status"] == "ROUTER_QUOTES_REQUIRED"
    assert r["liquidity_reality_mode"] == "RESEARCH_SHADOW_NO_PRODUCTION_IMPACT"


def test_many_balanced_pools_score_strong():
    pools = [{"liquidity_usd": 250_000} for _ in range(8)]
    r = compute_liquidity_reality(pools, market_cap_usd=20_000_000)
    assert r["dex_liquidity_to_market_cap_pct"] == 10.0
    assert r["top_pool_share_pct"] == 12.5
    assert r["meaningful_pool_count"] == 8
    assert r["tradable_liquidity_share_pct"] == 100.0
    assert r["liquidity_reality_score"] == 100
    assert r["liquidity_reality_level"] == "STRONG"


def test_single_pool_low_ratio_is_fragile():
    r = compute_liquidity_reality([{"liquidity_usd": 40_000}], market_cap_usd=50_000_000)
    assert r["dex_liquidity_to_market_cap_pct"] == 0.08
    assert r["top_pool_share_pct"] == 100.0
    assert r["tradable_pool_count"] == 0
    assert r["liquidity_reality_level"] == "FRAGILE"
    assert "LIQUIDITY_CONCENTRATED_IN_TOP_POOL" in r["liquidity_reality_reasons"]


def test_market_cap_missing_is_explicitly_unknown_not_fake_precision():
    r = compute_liquidity_reality([{"liquidity_usd": 100_000}, {"liquidity_usd": 100_000}])
    assert r["dex_liquidity_to_market_cap_pct"] is None
    assert r["liquidity_reality_level"] == "UNKNOWN"
    assert "MARKET_CAP_UNAVAILABLE_SCORE_PARTIAL" in r["liquidity_reality_reasons"]
