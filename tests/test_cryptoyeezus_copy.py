from wallet500.cryptoyeezus_copy import SOURCE_WALLET, USDC, WSOL, _copy_amount, parse_wallet_swap

TOKEN = "TokenMint1111111111111111111111111111111111"


def tx(pre_tokens, post_tokens, pre_sol=10_000_000_000, post_sol=10_000_000_000, fee=5000, signer=True):
    return {
        "blockTime": 1788320000,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": SOURCE_WALLET, "signer": signer, "writable": True},
                    {"pubkey": "Other111111111111111111111111111111111111", "signer": False, "writable": True},
                ]
            }
        },
        "meta": {
            "err": None,
            "fee": fee,
            "preBalances": [pre_sol, 0],
            "postBalances": [post_sol, 0],
            "preTokenBalances": pre_tokens,
            "postTokenBalances": post_tokens,
        },
    }


def bal(mint, raw, decimals, owner=SOURCE_WALLET):
    return {"mint": mint, "owner": owner, "uiTokenAmount": {"amount": str(raw), "decimals": decimals}}


def test_parse_sol_buy():
    data = tx([], [bal(TOKEN, 2_000_000, 6)], post_sol=8_999_995_000)
    out = parse_wallet_swap(data)
    assert out["side"] == "BUY"
    assert out["input_mint"] == WSOL
    assert out["input_amount_raw"] == 1_000_000_000
    assert out["output_mint"] == TOKEN
    assert out["output_amount_raw"] == 2_000_000
    assert out["native_notional_is_estimate"] is True


def test_parse_usdc_buy():
    data = tx(
        [bal(USDC, 20_000_000, 6)],
        [bal(USDC, 10_000_000, 6), bal(TOKEN, 5_000_000, 6)],
        post_sol=9_999_995_000,
    )
    out = parse_wallet_swap(data)
    assert out["side"] == "BUY"
    assert out["input_mint"] == USDC
    assert out["input_amount_raw"] == 10_000_000
    assert out["output_mint"] == TOKEN


def test_parse_sol_sell():
    data = tx(
        [bal(TOKEN, 5_000_000, 6)],
        [],
        pre_sol=5_000_000_000,
        post_sol=5_499_995_000,
    )
    out = parse_wallet_swap(data)
    assert out["side"] == "SELL"
    assert out["input_mint"] == TOKEN
    assert out["output_mint"] == WSOL
    assert out["output_amount_raw"] == 500_000_000


def test_non_signer_transfer_is_not_swap():
    data = tx([], [bal(TOKEN, 100, 0)], signer=False)
    assert parse_wallet_swap(data) is None


def test_ambiguous_two_bought_tokens_fails_closed():
    data = tx(
        [bal(USDC, 10_000_000, 6)],
        [bal(TOKEN, 100, 0), bal("SecondMint11111111111111111111111111111111", 200, 0)],
        post_sol=9_999_995_000,
    )
    assert parse_wallet_swap(data) is None


def test_one_percent_copy_rounds_down():
    assert _copy_amount(1_000_000_000, 0.01) == 10_000_000
    assert _copy_amount(99, 0.01) == 0
