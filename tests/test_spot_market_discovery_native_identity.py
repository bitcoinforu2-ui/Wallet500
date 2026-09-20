import json

from scripts import spot_market_discovery_collector as mod


def harmony_registry():
    return {
        "ONE": {
            "coingecko_id": "harmony",
            "symbol": "ONE",
            "chain": "harmony",
            "token_address": "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a",
            "representation_type": "CANONICAL_WRAPPED_NATIVE",
            "evidence_source": "HARMONY_OFFICIAL_DOCS_WRAPPED_ONE",
            "discovery_symbol_lookup": True,
        }
    }


def test_harmony_chain_and_addresses_are_normalized_as_evm():
    assert mod.chain_ids("Harmony") == ("harmony", "harmony")
    assert mod.same_addr(
        "harmony",
        "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a",
        "0xcf664087a5bb0237a0bad6742852ec6c8d69a27a",
    )


def test_native_one_proxy_resolves_when_gate_has_no_contract(monkeypatch):
    def fake_get(url, timeout=12):
        if "currency_chains" in url:
            return [{"chain": "Harmony", "contract_address": ""}]
        if "dexscreener.com/latest/dex/tokens/" in url:
            return {
                "pairs": [{
                    "chainId": "harmony",
                    "pairAddress": "0xpair",
                    "baseToken": {
                        "symbol": "WONE",
                        "address": "0xcf664087a5bb0237a0bad6742852ec6c8d69a27a",
                    },
                    "quoteToken": {
                        "symbol": "USDC",
                        "address": "0xquote",
                    },
                    "url": "https://dexscreener.com/harmony/0xpair",
                    "liquidity": {"usd": 42000},
                }]
            }
        raise AssertionError(url)

    monkeypatch.setattr(mod, "get_json", fake_get)
    row = mod.resolve_identity("ONE", native_registry=harmony_registry())

    assert row["identity_status"] == "RESOLVED_EXACT"
    assert row["identity_reason"] == "EXACT_CURATED_NATIVE_PROXY_PAIR_RESEARCH_ONLY"
    assert row["network"] == "harmony"
    assert row["contract"].lower() == "0xcf664087a5bb0237a0bad6742852ec6c8d69a27a"
    assert row["pair"] == "0xpair"
    assert row["native_asset_proxy"] is True
    assert row["native_asset_coingecko_id"] == "harmony"
    assert row["research_only_identity"] is True
    assert row["actionable"] is False


def test_native_proxy_requires_explicit_curated_opt_in(tmp_path):
    path = tmp_path / "native.json"
    path.write_text(json.dumps({
        "assets": {
            "harmony": {
                "symbol": "ONE",
                "chain": "harmony",
                "token_address": "0xone",
                "representation_type": "CANONICAL_WRAPPED_NATIVE",
                "discovery_symbol_lookup": False,
            }
        }
    }))
    assert mod.load_native_discovery_registry(path) == {}


def test_duplicate_curated_native_symbol_fails_closed(tmp_path):
    path = tmp_path / "native.json"
    path.write_text(json.dumps({
        "assets": {
            "one-a": {
                "symbol": "ONE",
                "chain": "harmony",
                "token_address": "0xa",
                "representation_type": "CANONICAL_WRAPPED_NATIVE",
                "discovery_symbol_lookup": True,
            },
            "one-b": {
                "symbol": "ONE",
                "chain": "other",
                "token_address": "0xb",
                "representation_type": "CANONICAL_WRAPPED_NATIVE",
                "discovery_symbol_lookup": True,
            },
        }
    }))
    assert "ONE" not in mod.load_native_discovery_registry(path)


def test_native_one_proxy_still_resolves_when_gate_chain_metadata_is_unavailable(monkeypatch):
    def fake_get(url, timeout=12):
        if "currency_chains" in url:
            return None
        if "dexscreener.com/latest/dex/tokens/" in url:
            return {
                "pairs": [{
                    "chainId": "harmony",
                    "pairAddress": "0xpair2",
                    "baseToken": {
                        "symbol": "WONE",
                        "address": "0xcf664087a5bb0237a0bad6742852ec6c8d69a27a",
                    },
                    "quoteToken": {"symbol": "USDC", "address": "0xquote"},
                    "liquidity": {"usd": 31000},
                }]
            }
        raise AssertionError(url)

    monkeypatch.setattr(mod, "get_json", fake_get)
    row = mod.resolve_identity("ONE", native_registry=harmony_registry())
    assert row["identity_status"] == "RESOLVED_EXACT"
    assert row["native_asset_proxy"] is True
    assert row["pair"] == "0xpair2"
