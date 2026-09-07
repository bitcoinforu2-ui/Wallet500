from wallet500 import catalyst_identity_guard as guard


def _registry():
    return {
        "symbols": {
            "ABC": {
                "chain": "base",
                "token_address": "0x1111111111111111111111111111111111111111",
            }
        }
    }


def test_exact_registry_match_remains_eligible():
    event = {
        "event_id": "safe",
        "source_owner": "coinbase",
        "source_id": "COINBASE_PRODUCTS",
        "symbol": "ABC",
        "chain": "base",
        "contract": "0x1111111111111111111111111111111111111111",
        "preliminary_filter_pass": True,
        "alert_eligible": True,
    }
    out, ok, reason = guard.sanitize_event(event, guard._registry_symbols(_registry()))
    assert ok is True
    assert reason == "EXACT_CEX_REGISTRY_MATCH"
    assert out["symbol_contract_link_verified"] is True
    assert out["preliminary_filter_pass"] is True


def test_zec_symbol_collision_fails_closed():
    event = {
        "event_id": "zec-fake",
        "source_owner": "coinbase",
        "source_id": "COINBASE_PRODUCTS",
        "symbol": "ZEC",
        "chain": "solana",
        "contract": "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS",
        "preliminary_filter_pass": True,
        "alert_eligible": True,
    }
    out, ok, reason = guard.sanitize_event(event, guard._registry_symbols(_registry()))
    assert ok is False
    assert reason == "SYMBOL_NOT_IN_EXACT_CEX_IDENTITY_REGISTRY"
    assert out["symbol_contract_link_verified"] is False
    assert out["preliminary_filter_pass"] is False
    assert out["alert_eligible"] is False
    assert out["identity_guard_blocker"] == guard.BLOCKER


def test_registry_mismatch_fails_closed_even_for_known_symbol():
    event = {
        "event_id": "wrong-chain",
        "source_owner": "mexc",
        "source_id": "MEXC_SPOT_LISTINGS",
        "symbol": "ABC",
        "chain": "solana",
        "contract": "SomeOtherMint111111111111111111111111111111",
        "preliminary_filter_pass": True,
    }
    out, ok, reason = guard.sanitize_event(event, guard._registry_symbols(_registry()))
    assert ok is False
    assert reason == "REGISTRY_CHAIN_CONTRACT_MISMATCH"
    assert out["preliminary_filter_pass"] is False


def test_blocked_asset_is_removed_from_focus_and_pending():
    bad = {
        "event_id": "zec-fake",
        "source_owner": "coinbase",
        "source_id": "COINBASE_PRODUCTS",
        "symbol": "ZEC",
        "chain": "solana",
        "contract": "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS",
        "preliminary_filter_pass": True,
    }
    wire = {"events": [bad]}
    ledger = {"events": {"zec-fake": {"event": bad}}}
    focus = {
        "focus": {"solana:zec:coinbase": {"status": "TRACKING", "event": bad}},
        "pending": {"zec-fake": {"status": "WATCHING_SILENT", "event": bad}},
    }
    out_wire, out_ledger, out_focus, stats = guard.sanitize_payloads(wire, ledger, focus, _registry())
    assert out_wire["events"][0]["preliminary_filter_pass"] is False
    assert out_ledger["events"]["zec-fake"]["event"]["symbol_contract_link_verified"] is False
    assert out_focus["focus"] == {}
    assert out_focus["pending"] == {}
    assert stats["blocked_event_count"] == 1
    assert stats["focus_records_removed"] == 1
    assert stats["pending_records_removed"] == 1
