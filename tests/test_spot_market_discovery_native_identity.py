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


def test_missing_gate_contract_self_recovers_via_coingecko_exact_platform(monkeypatch):
    token = "0x1111111111111111111111111111111111111111"
    pair = "0x2222222222222222222222222222222222222222"

    def fake_get(url, timeout=12):
        if "currency_chains" in url:
            return [{"chain": "ETH", "contract_address": ""}]
        if "dexscreener.com/latest/dex/tokens/" in url:
            return {
                "pairs": [{
                    "chainId": "ethereum",
                    "pairAddress": pair,
                    "baseToken": {"address": token},
                    "quoteToken": {"address": "0xquote"},
                    "priceUsd": "0.101",
                    "url": "https://dexscreener.com/ethereum/" + pair,
                    "liquidity": {"usd": 125000},
                }]
            }
        raise AssertionError(url)

    def fake_cg(url, timeout=12):
        if "/coins/markets?" in url:
            return [{
                "id": "example-token",
                "symbol": "abc",
                "current_price": 0.10,
                "market_cap": 1000000,
            }]
        if "/coins/example-token?" in url:
            return {"platforms": {"ethereum": token}}
        raise AssertionError(url)

    monkeypatch.setattr(mod, "get_json", fake_get)
    monkeypatch.setattr(mod, "coingecko_get_json", fake_cg)
    row = mod.resolve_identity("ABC", native_registry={}, cex_price=0.10)

    assert row["identity_status"] == "RESOLVED_EXACT"
    assert row["identity_reason"] == "EXACT_IDENTITY_RECOVERED_FROM_COINGECKO_PLATFORM"
    assert row["network"] == "eth"
    assert row["contract"] == token
    assert row["pair"] == pair
    assert row["identity_recovery_attempted"] is True
    assert row["identity_recovery_method"] == "UNIQUE_COINGECKO_SYMBOL"


def test_ambiguous_coingecko_recovery_fails_closed(monkeypatch):
    def fake_get(url, timeout=12):
        if "currency_chains" in url:
            return [{"chain": "ETH", "contract_address": ""}]
        raise AssertionError(url)

    def fake_cg(url, timeout=12):
        if "/coins/markets?" in url:
            return [
                {"id": "abc-one", "symbol": "abc", "current_price": 0.100},
                {"id": "abc-two", "symbol": "abc", "current_price": 0.105},
            ]
        raise AssertionError(url)

    monkeypatch.setattr(mod, "get_json", fake_get)
    monkeypatch.setattr(mod, "coingecko_get_json", fake_cg)
    row = mod.resolve_identity("ABC", native_registry={}, cex_price=0.102)

    assert row["identity_status"] == "UNRESOLVED"
    assert row["identity_recovery_attempted"] is True
    assert row["identity_recovery_blocker"] == "COINGECKO_SYMBOL_AMBIGUOUS_FAIL_CLOSED"



def test_cumulative_quarter_wave_crossing_is_caught_before_24h_momentum_filter():
    old = {"first_seen_price": 0.02836}
    just_below = {"discovery_price": 0.03544, "change_24h_pct": 0.5}
    first_cross = {"discovery_price": 0.03580, "change_24h_pct": 0.5}

    assert mod.cumulative_gain_from_first_seen(old, just_below) < 25.0
    assert mod.should_force_cumulative_hot_watch(old, just_below, 25.0) is False
    assert mod.cumulative_gain_from_first_seen(old, first_cross) > 25.0
    assert mod.should_force_cumulative_hot_watch(old, first_cross, 25.0) is True


def test_cumulative_quarter_wave_never_arms_without_valid_anchor():
    assert mod.cumulative_gain_from_first_seen({}, {"discovery_price": 1.0}) is None
    assert mod.should_force_cumulative_hot_watch({}, {"discovery_price": 1.0}, 25.0) is False
    assert mod.should_force_cumulative_hot_watch(
        {"first_seen_price": 0.0},
        {"discovery_price": 1.0},
        25.0,
    ) is False



def test_earlier_unified_anchor_repairs_newer_spot_collector_anchor():
    old = {
        "first_seen_at": "2026-09-21T03:46:41+00:00",
        "first_seen_price": 0.03884,
    }
    canonical = {
        "first_seen_at": "2026-09-15T12:38:51+00:00",
        "first_seen_price": 0.02836,
    }
    fixed = mod.earlier_anchor(old, {"symbol": "PHA"}, canonical)
    assert fixed["first_seen_at"] == canonical["first_seen_at"]
    assert fixed["first_seen_price"] == 0.02836
    assert fixed["canonical_anchor_recovered"] is True
    assert mod.should_force_cumulative_hot_watch(
        fixed,
        {"discovery_price": 0.03580},
        25.0,
    ) is True
