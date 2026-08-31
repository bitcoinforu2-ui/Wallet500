from wallet500.revival_1000 import (
    has_solana_only_platform,
    is_pegged_or_derivative_like,
    is_stable_like,
    score_market_signals,
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


def test_stablecoins_are_excluded_from_revival_universe():
    assert is_stable_like({"id": "usd-coin", "symbol": "USDC", "name": "USDC"})
    assert is_stable_like({"id": "tether", "symbol": "USDT", "name": "Tether"})
    assert is_stable_like({"id": "dai", "symbol": "DAI", "name": "Dai"})
    assert is_stable_like({"id": "paypal-usd", "symbol": "PYUSD", "name": "PayPal USD"})
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
    ]
    assert all(is_pegged_or_derivative_like(x) for x in bad)
    assert not is_pegged_or_derivative_like({"symbol": "PUMP", "name": "Pump.fun"})
    assert not is_pegged_or_derivative_like({"symbol": "BONK", "name": "Bonk"})


def test_solana_only_platform_footprint_rejects_cross_chain_representation():
    assert has_solana_only_platform({"solana": "So111"})
    assert has_solana_only_platform({"solana": "So111", "ethereum": ""})
    assert not has_solana_only_platform({"solana": "So111", "ethereum": "0xabc"})
    assert not has_solana_only_platform({"ethereum": "0xabc"})
