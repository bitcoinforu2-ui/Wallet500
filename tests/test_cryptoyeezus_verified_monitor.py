from wallet500.cryptoyeezus_copy import SOURCE_WALLET, WSOL
from wallet500.cryptoyeezus_verified_monitor import has_explicit_swap_evidence, verified_parse_wallet_swap

TOKEN = "TokenMint1111111111111111111111111111111111"


def bal(mint, raw, decimals):
    return {"mint": mint, "owner": SOURCE_WALLET, "uiTokenAmount": {"amount": str(raw), "decimals": decimals}}


def tx(logs):
    return {
        "transaction": {"message": {"accountKeys": [{"pubkey": SOURCE_WALLET, "signer": True, "writable": True}]}},
        "meta": {
            "err": None,
            "fee": 5000,
            "logMessages": logs,
            "preBalances": [10_000_000_000],
            "postBalances": [8_999_995_000],
            "preTokenBalances": [],
            "postTokenBalances": [bal(TOKEN, 2_000_000, 6)],
        },
    }


def test_signer_token_receipt_plus_sol_spend_without_swap_log_is_rejected():
    data = tx(["Program log: Instruction: Transfer", "Program returned success"])
    assert has_explicit_swap_evidence(data) is False
    assert verified_parse_wallet_swap(data) is None


def test_explicit_swap_log_allows_balance_delta_parser():
    data = tx(["Program log: Instruction: Swap", "Program returned success"])
    assert has_explicit_swap_evidence(data) is True
    out = verified_parse_wallet_swap(data)
    assert out is not None
    assert out["side"] == "BUY"
    assert out["input_mint"] == WSOL
    assert out["output_mint"] == TOKEN
