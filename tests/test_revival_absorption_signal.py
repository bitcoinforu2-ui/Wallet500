from wallet500.revival_absorption_signal import (
    apply_absorption_layer,
    compute_absorption_proxy,
    exact_pair_for_coin,
)


TOKEN = "a3W4qutoEJA4232T2gwZUfgYJTetr96pU4SJMwppump"
PAIR = "9QWcK8u4u5sR3XrC1rV1nS7VMdPh6mRjGfScPc2a1Zyz"
OTHER_PAIR = "8KMv3P7hmvS8K4XcWn77jRqbqGvwdP2tmY5cWYJt4x1E"


def whitewhale_shape():
    coin = {
        "token_address": TOKEN,
        "dex_pair_address": PAIR,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "change_24h_pct": 15.48,
        "drawdown_from_ath_pct": 99.2,
        "watch_status": "OUTSIDE_CORE_DRAWDOWN_BAND",
        "pre_alpha_eligible": False,
        "revival_score_verified": 42.0,
    }
    pair = {
        "chainId": "solana",
        "pairAddress": PAIR,
        "baseToken": {"address": TOKEN},
        "quoteToken": {"address": "So11111111111111111111111111111111111111112"},
        "txns": {
            "h24": {"buys": 279, "sells": 305},
            "h6": {"buys": 74, "sells": 83},
            "h1": {"buys": 12, "sells": 17},
        },
        "volume": {"h24": 62000},
        "liquidity": {"usd": 217000},
        "priceChange": {"h24": 15.48, "h6": 6.98, "h1": -2.46},
    }
    return coin, pair


def test_whitewhale_shape_triggers_research_absorption_proxy():
    coin, pair = whitewhale_shape()
    result = compute_absorption_proxy(coin, pair)
    assert result["signal"] is True
    assert result["signal_type"] == "SELL_COUNT_ABSORPTION_PROXY"
    assert result["sells_h24"] > result["buys_h24"]
    assert result["liquidity_usd"] == 217000
    assert result["exact_buy_sell_notional_verified"] is False
    assert result["buy_volume_24h_usd"] is None
    assert result["sell_volume_24h_usd"] is None
    assert result["strict_level"] == 2
    assert result["strict_grade"] == "STRICT-2"


def test_strict3_requires_early_premium_structure():
    coin, pair = whitewhale_shape()
    pair["volume"]["h24"] = 160000
    pair["priceChange"]["h1"] = -1.0
    result = compute_absorption_proxy(coin, pair)
    assert result["signal"] is True
    assert result["strict_level"] == 3
    assert result["strict_grade"] == "STRICT-3"
    assert result["strict_grade_reason"] == "EARLY_PREMIUM_ABSORPTION"
    assert all(result["strict_grade_criteria"]["strict3"].values())


def test_late_extended_move_does_not_upgrade_above_strict1():
    coin, pair = whitewhale_shape()
    pair["volume"]["h24"] = 160000
    pair["priceChange"]["h24"] = 60.0
    pair["priceChange"]["h1"] = 5.0
    result = compute_absorption_proxy(coin, pair)
    assert result["signal"] is True
    assert result["strict_level"] == 1
    assert result["strict_grade"] == "STRICT-1"
    assert result["strict_grade_reason"] == "BASE_ABSORPTION_ONLY"


def test_proxy_rejects_sell_pressure_with_negative_24h_price():
    coin, pair = whitewhale_shape()
    pair["priceChange"]["h24"] = -12.0
    result = compute_absorption_proxy(coin, pair)
    assert result["signal"] is False
    assert result["criteria"]["price_change_24h_positive"] is False
    assert result["strict_level"] == 0
    assert result["strict_grade"] is None


def test_exact_pair_resolution_never_switches_to_other_pool():
    coin, wanted = whitewhale_shape()
    wrong = dict(wanted)
    wrong["pairAddress"] = OTHER_PAIR
    wrong["liquidity"] = {"usd": 10_000_000}
    found = exact_pair_for_coin(coin, [wrong, wanted])
    assert found is wanted


def test_apply_layer_adds_watch_only_without_score_or_pre_alpha_promotion():
    coin, pair = whitewhale_shape()
    payload = {
        "network": "solana",
        "production_portfolio_impact": "NONE",
        "source": "fixture",
        "counts": {},
        "coins": [coin],
    }
    original_score = coin["revival_score_verified"]
    enriched = apply_absorption_layer(payload, {PAIR.lower(): pair}, [])
    out = enriched["coins"][0]
    assert out["watch_status"] == "ABSORPTION_WATCH"
    assert out["research_watch_eligible"] is True
    assert out["pre_alpha_eligible"] is False
    assert out["revival_score_verified"] == original_score
    assert out["order_flow_absorption"]["strict_grade"] == "STRICT-2"
    assert enriched["counts"]["absorption_proxy_watch"] == 1
    assert enriched["counts"]["absorption_proxy_outside_core"] == 1
    assert enriched["counts"]["absorption_strict_1"] == 0
    assert enriched["counts"]["absorption_strict_2"] == 1
    assert enriched["counts"]["absorption_strict_3"] == 0
    contract = enriched["order_flow_absorption_contract"]
    assert contract["version"] == "SELL_COUNT_ABSORPTION_PROXY_V2_STRICT_LEVELS"
    assert contract["pre_alpha_promotion"] == "FORBIDDEN"
    assert contract["production_portfolio_impact"] == "NONE"
