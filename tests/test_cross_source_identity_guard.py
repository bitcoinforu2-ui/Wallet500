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


def test_source_ledgers_are_not_part_of_guard_mutation_contract():
    corr = {"counts": {}, "assets": {}}
    out, _, _ = sanitize(corr, [])
    assert out["identity_guard"]["source_ledgers_modified"] is False
    assert out["identity_guard"]["fail_closed"] is True
