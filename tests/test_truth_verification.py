from wallet500.cash_verified import STABLE, SOLANA_USDC_DECIMALS, _position_base_units
from wallet500.realizable_performance import _live_return


def test_bsc_usdt_output_uses_18_decimals():
    assert STABLE[56][1] == 18


def test_eth_usdc_output_uses_6_decimals():
    assert STABLE[1][1] == 6


def test_solana_usdc_output_uses_6_decimals():
    assert SOLANA_USDC_DECIMALS == 6


def test_position_base_units_uses_verified_token_decimals():
    assert _position_base_units(0.25, 18) == 4 * 10**18
    assert _position_base_units(0.25, 6) == 4 * 10**6


def test_live_return_is_recomputed_from_same_run_price():
    assert _live_return(2.0, 1.0) == 100.0
    assert round(_live_return(0.2248, 0.2287), 4) == -1.7053
