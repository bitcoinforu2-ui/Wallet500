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


def test_primary_token_pairs_exact_address(monkeypatch):
    monkeypatch.setattr(c, "token_pairs", lambda _chain, _token: [dex_pair()])
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
    monkeypatch.setattr(c, "_geckoterminal_pairs", lambda _candidate: (_ for _ in ()).throw(AssertionError("GT should not run")))
    rows = c._verified_pairs(candidate())
    assert [x["pair_address"] for x in rows] == ["0xRIGHT"]
    assert rows[0]["pair_provider"] == "DEXSCREENER_EXACT_ADDRESS_SEARCH"


def test_secondary_provider_used_when_dexscreener_misses(monkeypatch):
    monkeypatch.setattr(c, "token_pairs", lambda _chain, _token: [])
    monkeypatch.setattr(c, "_dexscreener_search_pairs", lambda _candidate: [])
    monkeypatch.setattr(c, "_geckoterminal_pairs", lambda cand: [{
        **cand,
        "pair_address": "0xGT",
        "dex": "PancakeSwap V3",
        "dex_url": "https://www.geckoterminal.com/bsc/pools/0xGT",
        "price_usd": 0.5,
        "liquidity_usd": 120000,
        "volume_h1": 1000,
        "volume_h24": 50000,
        "pair_created_at": 123,
        "pair_provider": "GECKOTERMINAL_EXACT_TOKEN_POOLS",
        "exact_token_side": "BASE",
    }])
    rows = c._verified_pairs(candidate())
    assert len(rows) == 1
    assert rows[0]["pair_address"] == "0xGT"
    assert rows[0]["pair_provider"] == "GECKOTERMINAL_EXACT_TOKEN_POOLS"


def test_symbol_like_pair_with_wrong_address_is_rejected():
    row = c._dex_pair(candidate(), dex_pair(token="UAI"), "TEST")
    assert row is None
