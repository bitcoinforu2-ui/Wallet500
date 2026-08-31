from wallet500.revival_1000 import (
    has_solana_only_platform,
    is_pegged_or_derivative_like,
    is_stable_like,
    looks_like_solana_address,
    score_market_signals,
    score_revival_verified,
    select_best_dex_pair,
)


def test_deep_drawdown_early_awakening_scores_without_hindsight():
    score, reasons = score_market_signals({
        "drawdown_from_ath_pct": 85,
        "market_cap_usd": 100_000_000,
        "volume_24h_usd": 15_000_000,
        "change_24h_pct": 6,
        "change_7d_pct": 12,
        "change_30d_pct": 18,
    })
    assert score >= 65
    assert "DEEP_DRAWDOWN_70_95" in reasons
    assert "EARLY_24H_MOMENTUM" in reasons
    assert not any("LATE_PARABOLIC" in r for r in reasons)


def test_parabolic_move_gets_chase_penalty():
    early, _ = score_market_signals({
        "drawdown_from_ath_pct": 85,
        "market_cap_usd": 100_000_000,
        "volume_24h_usd": 30_000_000,
        "change_24h_pct": 8,
        "change_7d_pct": 15,
        "change_30d_pct": 20,
    })
    late, reasons = score_market_signals({
        "drawdown_from_ath_pct": 85,
        "market_cap_usd": 100_000_000,
        "volume_24h_usd": 30_000_000,
        "change_24h_pct": 120,
        "change_7d_pct": 140,
        "change_30d_pct": 150,
    })
    assert late < early
    assert "CHASE_RISK_24H_GE_50" in reasons
    assert "LATE_PARABOLIC_24H_GE_100" in reasons


def test_verified_composite_rewards_liquidity_pair_survival_and_volume_trend():
    pair = "BLJ2yug7QjQCxsx922uEu19n5fjHCPbmqMx4XuWB8AXy"
    current = {
        "drawdown_from_ath_pct": 85,
        "market_cap_usd": 100_000_000,
        "volume_24h_usd": 15_000_000,
        "change_24h_pct": 6,
        "change_7d_pct": 12,
        "change_30d_pct": 18,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "dex_pair_address": pair,
        "dex_pair_liquidity_usd": 500_000,
        "dex_pair_volume_24h_usd": 2_000_000,
    }
    previous = {
        "dex_pair_address": pair,
        "dex_pair_liquidity_usd": 450_000,
        "dex_pair_volume_24h_usd": 1_500_000,
    }
    score, components, reasons, coverage = score_revival_verified(current, previous)
    assert score >= 70
    assert components["pair_survival"] == 15
    assert components["pair_volume_trend"] >= 10
    assert components["holder_cluster"] == 0
    assert components["smart_money"] == 0
    assert coverage == 90
    assert "EXACT_PAIR_SURVIVED_PREVIOUS_SNAPSHOT" in reasons


def test_verified_composite_does_not_invent_missing_pair_or_onchain_evidence():
    current = {
        "drawdown_from_ath_pct": 85,
        "market_cap_usd": 100_000_000,
        "volume_24h_usd": 15_000_000,
        "change_24h_pct": 6,
        "change_7d_pct": 12,
        "change_30d_pct": 18,
        "dex_link_type": "NO_VERIFIED_DEX_PAIR",
        "dex_pair_address": None,
        "dex_pair_liquidity_usd": None,
        "dex_pair_volume_24h_usd": None,
    }
    score, components, reasons, coverage = score_revival_verified(current, None)
    assert score < 50
    assert components["liquidity_quality"] == 0
    assert components["pair_survival"] == 0
    assert components["pair_volume_trend"] == 0
    assert components["holder_cluster"] == 0
    assert components["smart_money"] == 0
    assert coverage == 60
    assert "NO_VERIFIED_PAIR" in reasons
    assert "HOLDER_CLUSTER_PENDING_VERIFIED_SOURCE" in reasons


def test_liquidity_collapse_is_penalized():
    pair = "BLJ2yug7QjQCxsx922uEu19n5fjHCPbmqMx4XuWB8AXy"
    current = {
        "drawdown_from_ath_pct": 85,
        "market_cap_usd": 100_000_000,
        "volume_24h_usd": 15_000_000,
        "change_24h_pct": 6,
        "change_7d_pct": 12,
        "change_30d_pct": 18,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "dex_pair_address": pair,
        "dex_pair_liquidity_usd": 20_000,
        "dex_pair_volume_24h_usd": 100_000,
    }
    previous = {
        "dex_pair_address": pair,
        "dex_pair_liquidity_usd": 200_000,
        "dex_pair_volume_24h_usd": 500_000,
    }
    score, components, reasons, coverage = score_revival_verified(current, previous)
    assert components["risk_penalty"] >= 10
    assert components["liquidity_change_pct"] <= -75
    assert "LIQUIDITY_COLLAPSE_PENALTY" in reasons
    assert coverage == 90


def test_stablecoins_are_excluded_from_revival_universe():
    assert is_stable_like({"id": "usd-coin", "symbol": "USDC", "name": "USDC"})
    assert is_stable_like({"id": "tether", "symbol": "USDT", "name": "Tether"})
    assert is_stable_like({"id": "dai", "symbol": "DAI", "name": "Dai"})
    assert is_stable_like({"id": "paypal-usd", "symbol": "PYUSD", "name": "PayPal USD"})
    assert is_stable_like({"id": "usx", "symbol": "USX", "name": "USX"})
    assert not is_stable_like({"id": "chainlink", "symbol": "LINK", "name": "Chainlink"})
    assert not is_stable_like({"id": "render-token", "symbol": "RENDER", "name": "Render"})


def test_wrapped_pegged_and_receipt_assets_are_excluded():
    bad = [
        {"symbol": "WBTC", "name": "Wrapped Bitcoin"},
        {"symbol": "CBBTC", "name": "Coinbase Wrapped BTC"},
        {"symbol": "WSOL", "name": "Wrapped SOL"},
        {"symbol": "BNSOL", "name": "Binance Staked SOL"},
        {"symbol": "JITOSOL", "name": "Jito Staked SOL"},
        {"symbol": "LBTC", "name": "Lombard BTC"},
        {"symbol": "JLP", "name": "Jupiter Perpetuals Liquidity Provider Token"},
        {"symbol": "SUSDE", "name": "Ethena Staked USDe"},
        {"symbol": "SYRUPUSDC", "name": "syrupUSDC"},
        {"symbol": "USYC", "name": "Circle USYC"},
        {"symbol": "USTB", "name": "Invesco Short Duration US Government Securities Fund"},
        {"symbol": "BUILD", "name": "BlackRock USD Institutional Digital Liquidity Fund"},
        {"symbol": "ONYC", "name": "OnRe Tokenized Reinsurance"},
    ]
    assert all(is_pegged_or_derivative_like(x) for x in bad)
    assert not is_pegged_or_derivative_like({"symbol": "PUMP", "name": "Pump.fun"})
    assert not is_pegged_or_derivative_like({"symbol": "BONK", "name": "Bonk"})


def test_solana_only_platform_footprint_rejects_cross_chain_representation():
    assert has_solana_only_platform({"solana": "So111"})
    assert has_solana_only_platform({"solana": "So111", "ethereum": ""})
    assert not has_solana_only_platform({"solana": "So111", "ethereum": "0xabc"})
    assert not has_solana_only_platform({"ethereum": "0xabc"})


def test_solana_address_shape_validation():
    assert looks_like_solana_address("So11111111111111111111111111111111111111112")
    assert looks_like_solana_address("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN")
    assert not looks_like_solana_address("PUMP")
    assert not looks_like_solana_address("0xabc")
    assert not looks_like_solana_address("O0Il-not-base58")


def test_dex_pair_selector_uses_exact_token_and_best_liquidity():
    token = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
    low_pair = "A55XjvzRU4KtR3Lrys8PpLZQvPojPqvnv5bJVHMYy3Jv"
    high_pair = "BLJ2yug7QjQCxsx922uEu19n5fjHCPbmqMx4XuWB8AXy"
    pairs = [
        {
            "chainId": "solana",
            "pairAddress": low_pair,
            "url": f"https://dexscreener.com/solana/{low_pair}",
            "baseToken": {"address": token},
            "quoteToken": {"address": "So11111111111111111111111111111111111111112"},
            "liquidity": {"usd": 10_000},
            "volume": {"h24": 50_000},
        },
        {
            "chainId": "solana",
            "pairAddress": high_pair,
            "url": f"https://dexscreener.com/solana/{high_pair}",
            "baseToken": {"address": token},
            "quoteToken": {"address": "So11111111111111111111111111111111111111112"},
            "liquidity": {"usd": 2_000_000},
            "volume": {"h24": 5_000_000},
        },
        {
            "chainId": "ethereum",
            "pairAddress": high_pair,
            "url": f"https://dexscreener.com/ethereum/{high_pair}",
            "baseToken": {"address": token},
            "quoteToken": {"address": "fake"},
            "liquidity": {"usd": 99_000_000},
        },
    ]
    best = select_best_dex_pair(token, pairs)
    assert best is not None
    assert best["pairAddress"] == high_pair
