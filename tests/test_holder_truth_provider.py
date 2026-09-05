import base64

from wallet500.holder_truth_provider import (
    CMC_PROVIDER,
    SOLSCAN_PROVIDER,
    parse_program_accounts,
    reconcile_provider_results,
)


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


def test_equal_primary_peers_cross_validate_symmetrically():
    cmc = {"verified": True, "holder_count": 1000, "wallet_sample_count": 20}
    solscan = {"verified": True, "holder_count": 1080, "sample_owner_rows": 40}
    out = reconcile_provider_results(cmc, solscan)
    assert out["verified"] is True
    assert out["holder_count"] == 1000
    assert out["provider_actual"] == "CMC_SOLSCAN_EQUAL_PEER_CONSENSUS"
    assert out["cross_validation_status"] == "AGREE_WITHIN_TOLERANCE"
    assert out["provider_counts"][CMC_PROVIDER] == 1000
    assert out["provider_counts"][SOLSCAN_PROVIDER] == 1080


def test_equal_primary_peers_fail_closed_on_large_disagreement():
    cmc = {"verified": True, "holder_count": 1000}
    solscan = {"verified": True, "holder_count": 1500}
    out = reconcile_provider_results(cmc, solscan)
    assert out["verified"] is False
    assert out["status"] == "HOLDER_PROVIDER_DISAGREEMENT"
    assert out["cross_validation_status"] == "DISAGREE_ABOVE_TOLERANCE"


def test_one_equal_peer_can_still_supply_verified_truth():
    cmc = {"verified": True, "holder_count": 777}
    solscan = {"verified": False, "status": "HTTP_429"}
    out = reconcile_provider_results(cmc, solscan)
    assert out["verified"] is True
    assert out["holder_count"] == 777
    assert out["provider_actual"] == CMC_PROVIDER
    assert out["cross_validation_status"] == "SINGLE_EQUAL_PEER_AVAILABLE"
