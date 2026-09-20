from __future__ import annotations

from wallet500 import cex_identity as c


def candidate():
    return {"chain": "bsc", "token_address": "0xABC", "coingecko_platform": "binance-smart-chain"}


def dex_pair(address="0xPAIR", token="0xABC", chain="bsc", liq=100000):
    return {
        "chainId": chain,
        "pairAddress": address,
        "dexId": "pancakeswap",
        "url": "https://dexscreener.com/bsc/" + address,
        "baseToken": {"address": token},
        "quoteToken": {"address": "0xUSDT"},
        "priceUsd": "0.50",
        "liquidity": {"usd": liq},
        "volume": {"h1": 1000, "h24": 50000},
        "pairCreatedAt": 1234567890000,
    }


def gt_pair(address="0xGT", liq=120000):
    return {
        **candidate(),
        "pair_address": address,
        "dex": "PancakeSwap Infinity",
        "dex_url": "https://www.geckoterminal.com/bsc/pools/" + address,
        "price_usd": 0.5,
        "liquidity_usd": liq,
        "volume_h1": 1000,
        "volume_h24": 50000,
        "pair_created_at": 123,
        "pair_provider": "GECKOTERMINAL_EXACT_TOKEN_POOLS",
        "exact_token_side": "BASE",
    }


def test_primary_token_pairs_exact_address(monkeypatch):
    monkeypatch.setattr(c, "token_pairs", lambda _chain, _token: [dex_pair()])
    monkeypatch.setattr(c, "_geckoterminal_pairs", lambda _candidate: [])
    rows = c._verified_pairs(candidate())
    assert len(rows) == 1
    assert rows[0]["pair_address"] == "0xPAIR"
    assert rows[0]["pair_provider"] == "DEXSCREENER_TOKEN_PAIRS"


def test_search_fallback_requires_exact_contract(monkeypatch):
    monkeypatch.setattr(c, "token_pairs", lambda _chain, _token: [])
    monkeypatch.setattr(c, "_get_json", lambda _url, *args, **kwargs: {
        "pairs": [
            dex_pair(address="0xWRONG", token="0xOTHER"),
            dex_pair(address="0xRIGHT", token="0xABC"),
        ]
    })
    monkeypatch.setattr(c, "_geckoterminal_pairs", lambda _candidate: [])
    rows = c._verified_pairs(candidate())
    assert [x["pair_address"] for x in rows] == ["0xRIGHT"]
    assert rows[0]["pair_provider"] == "DEXSCREENER_EXACT_ADDRESS_SEARCH"


def test_secondary_provider_used_when_dexscreener_misses(monkeypatch):
    monkeypatch.setattr(c, "token_pairs", lambda _chain, _token: [])
    monkeypatch.setattr(c, "_dexscreener_search_pairs", lambda _candidate: [])
    monkeypatch.setattr(c, "_geckoterminal_pairs", lambda _candidate: [gt_pair()])
    rows = c._verified_pairs(candidate())
    assert len(rows) == 1
    assert rows[0]["pair_address"] == "0xGT"
    assert rows[0]["pair_provider"] == "GECKOTERMINAL_EXACT_TOKEN_POOLS"


def test_secondary_provider_enriches_even_when_dexscreener_has_thin_pool(monkeypatch):
    monkeypatch.setattr(c, "token_pairs", lambda _chain, _token: [dex_pair(address="0xTHIN", liq=8700)])
    monkeypatch.setattr(c, "_geckoterminal_pairs", lambda _candidate: [gt_pair(address="0xDEEP", liq=1_100_000)])
    rows = c._verified_pairs(candidate())
    assert {x["pair_address"] for x in rows} == {"0xTHIN", "0xDEEP"}
    assert max(rows, key=lambda x: x["liquidity_usd"])["pair_address"] == "0xDEEP"


def test_symbol_like_pair_with_wrong_address_is_rejected():
    row = c._dex_pair(candidate(), dex_pair(token="UAI"), "TEST")
    assert row is None


def test_platform_catalog_is_one_batch_exact_id_lookup(monkeypatch):
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return [
            {"id": "threshold-network-token", "symbol": "t", "platforms": {"ethereum": "0xAAA"}},
            {"id": "loopring", "symbol": "lrc", "platforms": {"ethereum": "0xBBB"}},
            {"id": "wrong-t", "symbol": "t", "platforms": {"ethereum": "0xWRONG"}},
        ]

    monkeypatch.setattr(c, "_get_json", fake_get)
    catalog, error = c._platform_catalog({"threshold-network-token", "loopring"})
    assert error is None
    assert len(calls) == 1
    assert catalog["threshold-network-token"][0]["token_address"] == "0xAAA"
    assert catalog["loopring"][0]["token_address"] == "0xBBB"
    assert "wrong-t" not in catalog


def test_resolve_one_uses_catalog_without_per_coin_lookup(monkeypatch):
    monkeypatch.setattr(c, "_coin_platforms", lambda _cid: (_ for _ in ()).throw(AssertionError("single coin lookup must not run")))
    monkeypatch.setattr(c, "_verified_pairs", lambda cand: [{
        **cand,
        "pair_address": "0xPAIR",
        "dex": "uniswap",
        "dex_url": "https://dexscreener.com/ethereum/0xPAIR",
        "price_usd": 0.01,
        "liquidity_usd": 90000,
        "volume_h1": 1000,
        "volume_h24": 50000,
        "pair_created_at": 123,
        "pair_provider": "DEXSCREENER_TOKEN_PAIRS",
        "exact_token_side": "BASE",
    }])
    alert = {"symbol": "TUSDT", "coingecko_id": "threshold-network-token"}
    catalog = {"threshold-network-token": [{
        "chain": "ethereum",
        "token_address": "0xAAA",
        "coingecko_platform": "ethereum",
        "identity_candidate_source": "COINGECKO_PLATFORM_CATALOG",
    }]}
    row = c.resolve_one(alert, catalog, {}, allow_single_lookup=False)
    assert row["identity_status"] == "DEX_VERIFIED"
    assert row["token_address"] == "0xAAA"
    assert row["identity_source"].startswith("COINGECKO_PLATFORM_CATALOG")
    assert row["execution_pool_liquidity_usd"] == 90000
    assert row["dex_total_liquidity_usd"] == 90000


def test_resolve_one_selects_deepest_pool_and_keeps_total_liquidity(monkeypatch):
    monkeypatch.setattr(c, "_verified_pairs", lambda cand: [
        {
            **cand,
            "pair_address": "0xTHIN",
            "dex": "uniswap",
            "dex_url": "https://dexscreener.com/bsc/0xTHIN",
            "price_usd": 0.55,
            "liquidity_usd": 8700,
            "volume_h1": 100,
            "volume_h24": 40000,
            "pair_created_at": 123,
            "pair_provider": "DEXSCREENER_TOKEN_PAIRS",
            "exact_token_side": "BASE",
        },
        {
            **cand,
            "pair_address": "0xDEEP",
            "dex": "PancakeSwap Infinity",
            "dex_url": "https://www.geckoterminal.com/bsc/pools/0xDEEP",
            "price_usd": 0.55,
            "liquidity_usd": 1_100_000,
            "volume_h1": 20000,
            "volume_h24": 3_500_000,
            "pair_created_at": 456,
            "pair_provider": "GECKOTERMINAL_EXACT_TOKEN_POOLS",
            "exact_token_side": "BASE",
        },
    ])
    alert = {"symbol": "UAIUSDT", "coingecko_id": "unifai-network"}
    catalog = {"unifai-network": [{
        "chain": "bsc",
        "token_address": "0xABC",
        "coingecko_platform": "binance-smart-chain",
        "identity_candidate_source": "COINGECKO_PLATFORM_CATALOG",
    }]}
    row = c.resolve_one(alert, catalog, {}, allow_single_lookup=False)
    assert row["pair_address"] == "0xDEEP"
    assert row["dex_liquidity_usd"] == 1_100_000
    assert row["execution_pool_liquidity_usd"] == 1_100_000
    assert row["dex_total_liquidity_usd"] == 1_108_700
    assert row["dex_pool_count"] == 2
    assert row["dex_tradable_pool_count_50k"] == 1
    assert row["liquidity_gate_metric"] == "EXECUTION_POOL_LIQUIDITY_USD"


def test_registry_fallback_requires_exact_coingecko_id_match():
    registry = {
        "UAI": {"coingecko_id": "unifai-network", "chain": "bsc", "token_address": "0xABC"}
    }
    assert c._registry_candidates({"symbol": "UAIUSDT", "coingecko_id": "unifai-network"}, registry)[0]["token_address"] == "0xABC"
    assert c._registry_candidates({"symbol": "UAIUSDT", "coingecko_id": "different-coin"}, registry) == []


def test_native_asset_registry_requires_exact_coingecko_id_and_symbol():
    native = {
        "harmony": {
            "symbol": "ONE",
            "chain": "harmony",
            "token_address": "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a",
            "representation_type": "CANONICAL_WRAPPED_NATIVE",
            "evidence_source": "HARMONY_OFFICIAL_DOCS_WRAPPED_ONE",
        }
    }
    rows = c._native_asset_candidates(
        {"symbol": "ONEUSDT", "coingecko_id": "harmony"},
        native,
    )
    assert len(rows) == 1
    assert rows[0]["chain"] == "harmony"
    assert rows[0]["native_asset_proxy"] is True
    assert rows[0]["token_address"].lower() == "0xcf664087a5bb0237a0bad6742852ec6c8d69a27a"
    assert c._native_asset_candidates({"symbol": "ONEUSDT", "coingecko_id": "wrong"}, native) == []
    assert c._native_asset_candidates({"symbol": "FAKEUSDT", "coingecko_id": "harmony"}, native) == []


def test_dex_pair_derives_quote_side_target_price():
    cand = {
        "chain": "harmony",
        "token_address": "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a",
    }
    pair = {
        "chainId": "harmony",
        "pairAddress": "0xPAIR",
        "dexId": "sushiswap",
        "url": "https://dexscreener.com/harmony/0xPAIR",
        "baseToken": {"address": "0xUSDC", "symbol": "1USDC"},
        "quoteToken": {"address": cand["token_address"], "symbol": "WONE"},
        "priceUsd": "1.00",
        "priceNative": "200.00",
        "liquidity": {"usd": 50000},
        "volume": {"h1": 1000, "h24": 10000},
        "pairCreatedAt": 1234567890000,
    }
    row = c._dex_pair(cand, pair, "TEST")
    assert row is not None
    assert row["exact_token_side"] == "QUOTE"
    assert row["price_usd"] == 0.005


def test_harmony_one_native_bridge_resolves_to_exact_wrapped_pair(monkeypatch):
    wone = "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a"
    native = {
        "harmony": {
            "symbol": "ONE",
            "chain": "harmony",
            "token_address": wone,
            "representation_type": "CANONICAL_WRAPPED_NATIVE",
            "evidence_source": "HARMONY_OFFICIAL_DOCS_WRAPPED_ONE",
        }
    }

    def fake_pairs(cand):
        assert cand["chain"] == "harmony"
        assert cand["token_address"].lower() == wone.lower()
        assert cand["native_asset_proxy"] is True
        return [{
            **cand,
            "pair_address": "0xONEPAIR",
            "dex": "sushiswap",
            "dex_url": "https://dexscreener.com/harmony/0xONEPAIR",
            "price_usd": 0.00264,
            "liquidity_usd": 42000,
            "volume_h1": 5000,
            "volume_h24": 25000,
            "pair_created_at": 123,
            "pair_provider": "DEXSCREENER_TOKEN_PAIRS",
            "exact_token_side": "QUOTE",
        }]

    monkeypatch.setattr(c, "_verified_pairs", fake_pairs)
    row = c.resolve_one(
        {"symbol": "ONEUSDT", "coingecko_id": "harmony"},
        catalog={},
        registry={},
        native_registry=native,
        allow_single_lookup=False,
    )
    assert row["identity_status"] == "DEX_VERIFIED"
    assert row["identity_verified"] is True
    assert row["chain"] == "harmony"
    assert row["native_asset_proxy"] is True
    assert row["native_asset_representation"] == "CANONICAL_WRAPPED_NATIVE"
    assert row["pair_address"] == "0xONEPAIR"
    assert row["dex_price_usd"] == 0.00264
    assert row["actionable"] is False


def test_geckoterminal_harmony_network_id_one_resolves_wone_quote_side(monkeypatch):
    wone = "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a"
    seen = {}

    def fake_get(url, *args, **kwargs):
        seen["url"] = url
        return {
            "data": [{
                "type": "pool",
                "id": "one_0xpool",
                "attributes": {
                    "address": "0xeb049f1ed546f8efc3ad57f6c7d22f081ccc7375",
                    "base_token_price_usd": "1987.63",
                    "quote_token_price_usd": "0.1789",
                    "reserve_in_usd": "351100",
                    "volume_usd": {"h1": "5.0", "h24": "13.49"},
                    "pool_created_at": "2021-08-01T00:00:00Z",
                },
                "relationships": {
                    "base_token": {"data": {"id": "one_0x6983d1e6def3690c4d616b13597a09e6193ea013"}},
                    "quote_token": {"data": {"id": "one_0xcf664087a5bb0237a0bad6742852ec6c8d69a27a"}},
                    "dex": {"data": {"id": "sushiswap_harmony"}},
                },
            }],
            "included": [
                {
                    "type": "token",
                    "id": "one_0x6983d1e6def3690c4d616b13597a09e6193ea013",
                    "attributes": {"address": "0x6983D1E6DEf3690C4d616b13597A09e6193EA013"},
                },
                {
                    "type": "token",
                    "id": "one_0xcf664087a5bb0237a0bad6742852ec6c8d69a27a",
                    "attributes": {"address": wone},
                },
                {
                    "type": "dex",
                    "id": "sushiswap_harmony",
                    "attributes": {"name": "Sushiswap (Harmony)"},
                },
            ],
        }

    monkeypatch.setattr(c, "_get_json", fake_get)
    rows = c._geckoterminal_pairs({
        "chain": "harmony",
        "token_address": wone,
        "coingecko_platform": "native-asset-registry",
        "identity_candidate_source": "NATIVE_ASSET_CANONICAL_WRAPPER_REGISTRY",
        "native_asset_proxy": True,
    })

    assert "/networks/one/tokens/" in seen["url"]
    assert len(rows) == 1
    row = rows[0]
    assert row["pair_address"] == "0xeb049f1ed546f8efc3ad57f6c7d22f081ccc7375"
    assert row["exact_token_side"] == "QUOTE"
    assert row["price_usd"] == 0.1789
    assert row["liquidity_usd"] == 351100
    assert row["pair_provider"] == "GECKOTERMINAL_EXACT_TOKEN_POOLS"
