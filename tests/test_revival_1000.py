from wallet500.revival_1000 import is_stable_like, score_market_signals


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
