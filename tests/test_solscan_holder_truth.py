from wallet500.solscan_holder_truth import parse_holder_response, suspicious_jump


def test_parse_solscan_holder_total_and_owner_rows():
    payload = {
        "success": True,
        "data": {
            "total": 21267,
            "items": [
                {"address": "token_account_1", "owner": "owner_A"},
                {"address": "token_account_2", "owner": "owner_B"},
            ],
        },
    }
    out = parse_holder_response(payload)
    assert out["verified"] is True
    assert out["holder_count"] == 21267
    assert out["sample_owner_rows"] == 2
    assert out["sample_unique_owners"] == 2


def test_reject_items_without_owner_semantics():
    payload = {"success": True, "data": {"total": 41556, "items": [{"address": "token_account_only"}]}}
    out = parse_holder_response(payload)
    assert out["verified"] is False
    assert out["status"] == "OWNER_FIELD_MISSING"


def test_suspicious_jump_guard_blocks_doge1_style_double_count():
    assert suspicious_jump(21267, 41556) is True
    assert suspicious_jump(20810, 21267) is False
    assert suspicious_jump(None, 21267) is False
