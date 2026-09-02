from __future__ import annotations

from wallet500 import real_alerts as r


def exact_row(**kwargs):
    row = {
        "pair_address": "0xPAIR",
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "chain": "bsc",
        "token_address": "0xTOKEN",
    }
    row.update(kwargs)
    return row


def test_explicit_execution_pool_liquidity_is_authoritative():
    row = exact_row(
        execution_pool_liquidity_usd=1_100_000,
        dex_total_liquidity_usd=1_108_700,
        dex_liquidity_usd=1_100_000,
    )
    liq, total, pair, source = r._execution_liquidity_truth(row)
    assert liq == 1_100_000
    assert total == 1_108_700
    assert pair == "0xPAIR"
    assert source == "EXECUTION_POOL_LIQUIDITY_USD"


def test_total_liquidity_cannot_make_thin_execution_pool_pass():
    row = exact_row(
        execution_pool_liquidity_usd=8_700,
        dex_total_liquidity_usd=120_000,
        dex_liquidity_usd=8_700,
    )
    liq, total, _pair, _source = r._execution_liquidity_truth(row)
    assert liq == 8_700
    assert total == 120_000
    assert liq < 50_000


def test_deepest_explicit_exact_execution_pool_wins_across_rows():
    thin = exact_row(
        pair_address="0xTHIN",
        execution_pool_liquidity_usd=8_700,
        dex_total_liquidity_usd=1_108_700,
    )
    deep = exact_row(
        pair_address="0xDEEP",
        execution_pool_liquidity_usd=1_100_000,
        dex_total_liquidity_usd=1_108_700,
    )
    liq, total, pair, source = r._execution_liquidity_truth(thin, deep)
    assert pair == "0xDEEP"
    assert liq == 1_100_000
    assert total == 1_108_700
    assert source == "EXECUTION_POOL_LIQUIDITY_USD"


def test_explicit_execution_measurement_beats_stale_legacy_liquidity():
    stale_legacy = exact_row(pair_address="0xOLD", liquidity_usd=2_000_000)
    explicit = exact_row(
        pair_address="0xCURRENT",
        execution_pool_liquidity_usd=70_000,
        dex_total_liquidity_usd=100_000,
    )
    liq, _total, pair, source = r._execution_liquidity_truth(stale_legacy, explicit)
    assert pair == "0xCURRENT"
    assert liq == 70_000
    assert source == "EXECUTION_POOL_LIQUIDITY_USD"


def test_aggregate_only_liquidity_without_exact_execution_pair_never_passes():
    row = exact_row(dex_total_liquidity_usd=500_000)
    liq, total, pair, source = r._execution_liquidity_truth(row)
    assert liq == 0
    assert total is None
    assert pair is None
    assert source is None
