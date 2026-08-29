from wallet500.exact_pair_quote import PairState, _pair_direction, constant_product_amount_out


def test_constant_product_quote_respects_fee_and_reserves():
    out = constant_product_amount_out(1_000_000, 1_000_000_000, 2_000_000_000, 25)
    assert out > 0
    assert out < 2_000_000


def test_constant_product_zero_inputs_never_verify_output():
    assert constant_product_amount_out(0, 100, 100, 25) == 0
    assert constant_product_amount_out(100, 0, 100, 25) == 0
    assert constant_product_amount_out(100, 100, 0, 25) == 0


def test_pair_direction_requires_exact_two_tokens():
    state = PairState(
        pair='0xpair',
        token0='0xaaa',
        token1='0xbbb',
        reserve0=1000,
        reserve1=2000,
    )
    assert _pair_direction(state, '0xAAA', '0xBBB') == (1000, 2000)
    assert _pair_direction(state, '0xBBB', '0xAAA') == (2000, 1000)
    assert _pair_direction(state, '0xAAA', '0xCCC') is None
