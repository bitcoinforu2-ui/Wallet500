from wallet500.cross_source_identity_guard import EVM_ZERO, sanitize


def test_zero_evm_sentinel_never_survives_as_exact_contract():
    corr = {
        "counts": {"input_evidence": 3},
        "assets": {
            f"ethereum:{EVM_ZERO}": {
                "chain": "ethereum",
                "token": EVM_ZERO,
                "identity_confidence": "EXACT_CHAIN_CONTRACT",
                "source_confirmation_count": 2,
                "exchange_confirmation_count": 2,
            },
            "ethereum:0x1111111111111111111111111111111111111111": {
                "chain": "ethereum",
                "token": "0x1111111111111111111111111111111111111111",
                "identity_confidence": "EXACT_CHAIN_CONTRACT",
                "source_confirmation_count": 1,
                "exchange_confirmation_count": 1,
            },
        },
    }
    watch = [
        {"chain": "ethereum", "token": EVM_ZERO, "source": "CROSS_SOURCE_CORRELATION", "cross_source_asset_key": f"ethereum:{EVM_ZERO}"},
        {"chain": "ethereum", "token": "0x1111111111111111111111111111111111111111", "source": "CROSS_SOURCE_CORRELATION"},
    ]
    out, rows, stats = sanitize(corr, watch)
    assert f"ethereum:{EVM_ZERO}" not in out["assets"]
    assert out["counts"]["invalid_exact_identity_dropped"] == 1
    assert stats["generated_watch_rows_removed"] == 1
    assert len(rows) == 1


def test_non_generated_native_row_is_preserved_but_cross_source_credit_removed():
    corr = {"counts": {}, "assets": {f"ethereum:{EVM_ZERO}": {"chain": "ethereum", "token": EVM_ZERO, "identity_confidence": "EXACT_CHAIN_CONTRACT"}}}
    watch = [{
        "chain": "ethereum",
        "token": EVM_ZERO,
        "symbol": "ETH",
        "source": "user-case-study",
        "cross_source_asset_key": f"ethereum:{EVM_ZERO}",
        "cross_source_confirmation_count": 2,
    }]
    _, rows, stats = sanitize(corr, watch)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "ETH"
    assert rows[0]["source"] == "user-case-study"
    assert "cross_source_asset_key" not in rows[0]
    assert stats["non_generated_rows_enrichment_stripped"] == 1


def test_blocked_catalyst_symbol_collision_is_removed_from_correlation_and_watchlist():
    token = "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS"
    key = f"solana:{token}"
    corr = {
        "counts": {},
        "assets": {
            key: {
                "asset_key": key,
                "chain": "solana",
                "token": token,
                "symbol": "ZEC",
                "identity_confidence": "EXACT_CHAIN_CONTRACT",
                "source_confirmation_count": 2,
                "exchange_confirmation_count": 2,
                "confirmation_tier": "DOUBLE_SOURCE_CONFIRMED",
                "evidence": [
                    {
                        "evidence_id": "catalyst:coinbase-zec",
                        "lane": "CATALYST_WIRE",
                        "source_owner": "coinbase",
                        "source_id": "COINBASE_PRODUCTS",
                        "source_category": "exchange",
                        "first_seen_at": "2026-09-07T03:54:21+00:00",
                        "last_seen_at": "2026-09-07T04:00:00+00:00",
                    },
                    {
                        "evidence_id": "catalyst:mexc-zec",
                        "lane": "CATALYST_WIRE",
                        "source_owner": "mexc",
                        "source_id": "MEXC_SPOT_LISTINGS",
                        "source_category": "exchange",
                        "first_seen_at": "2026-09-07T03:55:00+00:00",
                        "last_seen_at": "2026-09-07T04:00:00+00:00",
                    },
                ],
            }
        },
    }
    ledger = {
        "events": {
            "coinbase-zec": {"event": {
                "event_id": "coinbase-zec",
                "source_owner": "coinbase",
                "source_id": "COINBASE_PRODUCTS",
                "symbol": "ZEC",
                "chain": "solana",
                "contract": token,
            }},
            "mexc-zec": {"event": {
                "event_id": "mexc-zec",
                "source_owner": "mexc",
                "source_id": "MEXC_SPOT_LISTINGS",
                "symbol": "ZEC",
                "chain": "solana",
                "contract": token,
            }},
        }
    }
    registry = {"symbols": {}}
    watch = [{
        "chain": "solana",
        "token": token,
        "symbol": "ZEC",
        "source": "CROSS_SOURCE_CORRELATION",
        "cross_source_asset_key": key,
        "cross_source_confirmation_count": 2,
    }]
    out, rows, stats = sanitize(corr, watch, ledger, registry)
    assert key not in out["assets"]
    assert rows == []
    assert stats["blocked_catalyst_evidence_removed"] == 2
    assert stats["catalyst_assets_dropped"] == 1
    assert stats["generated_watch_rows_removed"] == 1
    assert out["identity_guard"]["fail_closed"] is True


def test_one_blocked_catalyst_source_downgrades_but_preserves_independent_valid_evidence():
    token = "0x1111111111111111111111111111111111111111"
    key = f"base:{token}"
    corr = {
        "counts": {},
        "assets": {
            key: {
                "asset_key": key,
                "chain": "base",
                "token": token,
                "identity_confidence": "EXACT_CHAIN_CONTRACT",
                "source_confirmation_count": 2,
                "exchange_confirmation_count": 1,
                "confirmation_tier": "DOUBLE_SOURCE_CONFIRMED",
                "evidence": [
                    {"evidence_id": "catalyst:bad", "source_owner": "coinbase", "source_id": "COINBASE_PRODUCTS", "source_category": "exchange"},
                    {"evidence_id": "external:good", "source_owner": "obscura", "source_id": "OBSCURA", "source_category": "external_alpha"},
                ],
            }
        },
    }
    ledger = {"events": {"bad": {"event": {
        "event_id": "bad", "source_owner": "coinbase", "source_id": "COINBASE_PRODUCTS",
        "symbol": "ABC", "chain": "base", "contract": token,
    }}}}
    registry = {"symbols": {}}
    out, rows, stats = sanitize(corr, [], ledger, registry)
    assert key in out["assets"]
    asset = out["assets"][key]
    assert asset["source_confirmation_count"] == 1
    assert asset["confirmation_tier"] == "SINGLE_SOURCE"
    assert asset["sources_seen"] == ["obscura"]
    assert stats["catalyst_assets_downgraded"] == 1
    assert rows == []


def test_source_ledgers_are_not_part_of_guard_mutation_contract():
    corr = {"counts": {}, "assets": {}}
    out, _, _ = sanitize(corr, [])
    assert out["identity_guard"]["source_ledgers_modified"] is False
    assert out["identity_guard"]["fail_closed"] is True
