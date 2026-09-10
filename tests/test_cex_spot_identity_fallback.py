from wallet500 import cex_spot_identity_fallback as mod


def alert():
    return {
        "symbol": "CODEXUSDT",
        "markets": [
            {"exchange": "gate", "price": 0.10},
            {"exchange": "mexc", "price": 0.102},
        ],
        "spot_revival_score": 40,
        "research_only": True,
        "actionable": False,
    }


def test_strict_fallback_resolves_unique_price_coherent_old_exact_pair(monkeypatch):
    monkeypatch.setattr(mod, "_age_days", lambda value: 200)
    monkeypatch.setattr(mod, "_get", lambda url, timeout=15: {
        "pairs": [{
            "chainId": "ethereum",
            "pairAddress": "0xpair",
            "baseToken": {"symbol": "CODEX", "address": "0xtoken"},
            "quoteToken": {"symbol": "WETH", "address": "0xweth"},
            "priceUsd": "0.101",
            "pairCreatedAt": 1,
            "dexId": "uniswap",
            "url": "https://dex.example/pair",
            "liquidity": {"usd": 25000},
            "volume": {"h1": 4000, "h24": 50000},
        }]
    })
    row = mod.resolve(alert())
    assert row is not None
    assert row["identity_status"] == "DEX_VERIFIED"
    assert row["identity_verified"] is True
    assert row["token_address"] == "0xtoken"
    assert row["pair_address"] == "0xpair"
    assert row["market_age_verified"] is True


def test_fallback_rejects_price_mismatch(monkeypatch):
    monkeypatch.setattr(mod, "_age_days", lambda value: 200)
    monkeypatch.setattr(mod, "_get", lambda url, timeout=15: {
        "pairs": [{
            "chainId": "ethereum",
            "pairAddress": "0xpair",
            "baseToken": {"symbol": "CODEX", "address": "0xtoken"},
            "priceUsd": "0.20",
            "pairCreatedAt": 1,
        }]
    })
    assert mod.resolve(alert()) is None


def test_fallback_rejects_ambiguous_token_identity(monkeypatch):
    monkeypatch.setattr(mod, "_age_days", lambda value: 200)
    monkeypatch.setattr(mod, "_get", lambda url, timeout=15: {
        "pairs": [
            {"chainId": "ethereum", "pairAddress": "0xp1", "baseToken": {"symbol": "CODEX", "address": "0xt1"}, "priceUsd": "0.101", "pairCreatedAt": 1, "liquidity": {"usd": 10000}},
            {"chainId": "bsc", "pairAddress": "0xp2", "baseToken": {"symbol": "CODEX", "address": "0xt2"}, "priceUsd": "0.102", "pairCreatedAt": 1, "liquidity": {"usd": 9000}},
        ]
    })
    assert mod.resolve(alert()) is None
