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
    assert row["execution_pair_price_coherent"] is True
    assert row["cex_reference_price_usd"] == 0.101
    assert row["dex_price_usd"] == 0.101
    assert row["dex_pool_count"] == 1
    assert row["dex_liquidity_pools_top5"][0]["pair_address"] == "0xpair"


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


def test_reference_price_ignores_regional_non_usd_market():
    row = {
        "symbol": "CODEXUSDT",
        "markets": [
            {"exchange": "gate", "market_type": "spot", "symbol": "CODEXUSDT", "quote_symbol": "USDT", "price": 0.10, "volume_comparable_usd_like": True},
            {"exchange": "upbit", "market_type": "spot", "symbol": "CODEXKRW", "quote_symbol": "KRW", "price": 150.0, "regional_market": True, "volume_comparable_usd_like": False},
        ],
    }
    assert mod._cex_reference_price(row) == 0.10


def test_strict_fallback_expands_only_exact_price_coherent_base_token_pools(monkeypatch):
    monkeypatch.setattr(mod, "_age_days", lambda value: 200)

    def fake_get(url, timeout=15):
        if "/search?" in url:
            return {
                "pairs": [{
                    "chainId": "bsc",
                    "pairAddress": "0xold",
                    "baseToken": {"symbol": "AKE", "address": "0xtoken"},
                    "quoteToken": {"symbol": "USDT", "address": "0xusdt"},
                    "priceUsd": "0.1005",
                    "pairCreatedAt": 1,
                    "dexId": "pancakeswap",
                    "url": "https://dex.example/old",
                    "liquidity": {"usd": 30000},
                    "volume": {"h1": 1000, "h24": 40000},
                }]
            }
        return {
            "pairs": [
                {
                    "chainId": "bsc",
                    "pairAddress": "0xdeep",
                    "baseToken": {"symbol": "AKE", "address": "0xtoken"},
                    "quoteToken": {"symbol": "WBNB", "address": "0xbnb"},
                    "priceUsd": "0.101",
                    "pairCreatedAt": 2,
                    "dexId": "pancakeswap",
                    "url": "https://dex.example/deep",
                    "liquidity": {"usd": 180000},
                    "volume": {"h1": 9000, "h24": 250000},
                },
                {
                    "chainId": "bsc",
                    "pairAddress": "0xusdt",
                    "baseToken": {"symbol": "AKE", "address": "0xtoken"},
                    "quoteToken": {"symbol": "USDT", "address": "0xusdt"},
                    "priceUsd": "0.1008",
                    "pairCreatedAt": 3,
                    "dexId": "pancakeswap",
                    "url": "https://dex.example/usdt",
                    "liquidity": {"usd": 90000},
                    "volume": {"h1": 7000, "h24": 180000},
                },
                {
                    "chainId": "bsc",
                    "pairAddress": "0xwrongprice",
                    "baseToken": {"symbol": "AKE", "address": "0xtoken"},
                    "priceUsd": "0.20",
                    "liquidity": {"usd": 999999},
                },
                {
                    "chainId": "bsc",
                    "pairAddress": "0xquote",
                    "baseToken": {"symbol": "OTHER", "address": "0xother"},
                    "quoteToken": {"symbol": "AKE", "address": "0xtoken"},
                    "priceUsd": "0.101",
                    "liquidity": {"usd": 500000},
                },
            ]
        }

    monkeypatch.setattr(mod, "_get", fake_get)
    row = mod.resolve({
        "symbol": "AKEUSDT",
        "markets": [{
            "exchange": "gate",
            "market_type": "spot",
            "symbol": "AKEUSDT",
            "market_id": "AKE_USDT",
            "quote_symbol": "USDT",
            "price": 0.10,
            "volume_comparable_usd_like": True,
        }],
    })

    assert row is not None
    assert row["identity_status"] == "DEX_VERIFIED"
    assert row["execution_pair_price_coherent"] is True
    assert row["pair_address"] == "0xold"
    assert row["dex_pool_count"] == 3
    assert row["dex_total_liquidity_usd"] == 300000
    assert [x["pair_address"] for x in row["dex_liquidity_pools_top5"]] == [
        "0xdeep", "0xusdt", "0xold"
    ]
    assert all(x["exact_token_side"] == "BASE" for x in row["dex_liquidity_pools_top5"])
