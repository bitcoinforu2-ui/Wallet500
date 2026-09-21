from wallet500.evm_contract_authority_guard import evaluate_security, tri_flag


def test_tri_flag_handles_goplus_encoding():
    assert tri_flag("1") is True
    assert tri_flag("0") is False
    assert tri_flag(None) is None


def test_mature_pause_hidden_owner_is_caution_not_hard_block():
    raw = {
        "is_open_source": "1",
        "owner_address": "0xb76800000000000000000000000000000000dd2d",
        "hidden_owner": "1",
        "transfer_pausable": "1",
        "is_mintable": "0",
        "owner_change_balance": "0",
        "selfdestruct": "0",
        "can_take_back_ownership": "0",
        "is_honeypot": "0",
    }
    result = evaluate_security(raw, age_minutes=6 * 365 * 24 * 60)
    assert result["risk_score"] >= 35
    assert result["hard_risk"] is False
    assert result["buy_eligible"] is True
    assert "HIDDEN_OWNER_PLUS_TRANSFER_PAUSE" in result["dangerous_combinations"]


def test_young_hidden_owner_pause_stops_buy_on_first_observation_and_hard_blocks_on_repeat():
    raw = {
        "is_open_source": "1",
        "owner_address": "0x1111111111111111111111111111111111111111",
        "hidden_owner": "1",
        "transfer_pausable": "1",
        "is_mintable": "0",
        "owner_change_balance": "0",
        "selfdestruct": "0",
        "can_take_back_ownership": "0",
        "is_honeypot": "0",
    }
    first = evaluate_security(raw, age_minutes=30)
    assert first["buy_eligible"] is False
    assert first["hard_risk"] is False
    assert first["risk_tier"] == "CRITICAL_PENDING_RECHECK"

    second = evaluate_security(raw, age_minutes=45, previous=first)
    assert second["hard_risk"] is True
    assert second["risk_tier"] == "HARD_BLOCK"
    assert second["hard_risk_reason"] == "YOUNG_TOKEN_DANGEROUS_AUTHORITY_CONFIRMED_CONSECUTIVELY"


def test_owner_change_balance_is_immediate_hard_block():
    raw = {
        "is_open_source": "1",
        "owner_address": "0x2222222222222222222222222222222222222222",
        "owner_change_balance": "1",
        "hidden_owner": "0",
        "transfer_pausable": "0",
        "is_honeypot": "0",
    }
    result = evaluate_security(raw, age_minutes=10)
    assert result["hard_risk"] is True
    assert result["buy_eligible"] is False
    assert "owner_change_balance" in result["direct_critical_capabilities"]


def test_non_open_source_young_token_is_never_buy_eligible():
    raw = {
        "is_open_source": "0",
        "owner_address": "0x3333333333333333333333333333333333333333",
        "hidden_owner": "0",
        "transfer_pausable": "0",
        "owner_change_balance": "0",
        "selfdestruct": "0",
        "can_take_back_ownership": "0",
        "is_honeypot": "0",
    }
    result = evaluate_security(raw, age_minutes=120)
    assert result["source_coverage_ok"] is False
    assert result["buy_eligible"] is False


def test_clean_young_open_source_contract_can_pass_authority_layer():
    raw = {
        "is_open_source": "1",
        "owner_address": "",
        "hidden_owner": "0",
        "transfer_pausable": "0",
        "is_mintable": "0",
        "owner_change_balance": "0",
        "selfdestruct": "0",
        "can_take_back_ownership": "0",
        "is_honeypot": "0",
        "is_blacklisted": "0",
        "slippage_modifiable": "0",
    }
    result = evaluate_security(raw, age_minutes=60)
    assert result["hard_risk"] is False
    assert result["risk_tier"] == "CLEAR"
    assert result["buy_eligible"] is True
