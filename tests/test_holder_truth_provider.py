import base64

from wallet500.holder_truth_provider import parse_program_accounts


def _row(owner_byte: int, amount: int):
    raw = bytes([owner_byte]) * 32 + int(amount).to_bytes(8, "little")
    return {"account": {"data": [base64.b64encode(raw).decode(), "base64"]}}


def test_rpc_holder_parser_counts_unique_positive_owners_not_accounts():
    payload = [
        _row(1, 10),
        _row(1, 5),
        _row(2, 7),
        _row(3, 0),
    ]
    out = parse_program_accounts(payload)
    assert out["verified"] is True
    assert out["positive_token_accounts"] == 3
    assert out["holder_count"] == 2
    assert out["sample_unique_owners"] == 2


def test_rpc_holder_parser_rejects_unusable_layout():
    out = parse_program_accounts([{"account": {"data": [base64.b64encode(b"short").decode(), "base64"]}}])
    assert out["verified"] is False
    assert out["status"] == "RPC_ACCOUNT_LAYOUT_UNUSABLE"


def test_empty_exact_mint_account_set_is_verified_zero():
    out = parse_program_accounts([])
    assert out["verified"] is True
    assert out["holder_count"] == 0
