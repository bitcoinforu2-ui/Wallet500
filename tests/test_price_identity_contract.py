from wallet500 import performance_tracker
from wallet500 import realizable_performance


def test_tracker_rejects_legacy_quote_side_price():
    row={
        "price_usd":100.0,
        "base_token_address":"BASE",
        "quote_token_address":"TOKEN",
    }
    assert performance_tracker._identity_verified_snapshot("solana","TOKEN",row) is False


def test_tracker_accepts_identity_verified_quote_side_price():
    row={
        "price_usd":50.0,
        "token_identity_verified":True,
        "target_token_side":"QUOTE",
        "base_token_address":"BASE",
        "quote_token_address":"TOKEN",
    }
    assert performance_tracker._identity_verified_snapshot("solana","TOKEN",row) is True


def test_realizable_rejects_pre_v2_pair_only_mark():
    record={
        "chain":"solana",
        "measurement_status":"VERIFIED_EXACT_PAIR",
        "current_pair_address":"PairABC",
        "current_price_usd":999999.0,
        "history":[{
            "pair_address":"PairABC",
            "price_usd":999999.0,
            "liquidity_usd":100000.0,
            "volume_h1":50000.0,
            "buys_h1":100,
            "sells_h1":100,
        }],
    }
    assert realizable_performance._latest_exact_pair_mark(record,"PairABC") is None


def test_realizable_accepts_v2_identity_verified_mark():
    record={
        "chain":"solana",
        "measurement_status":"VERIFIED_EXACT_PAIR",
        "price_identity_contract_version":2,
        "current_pair_address":"PairABC",
        "current_price_usd":2.0,
        "history":[{
            "pair_address":"PairABC",
            "price_usd":2.0,
            "liquidity_usd":100000.0,
            "volume_h1":50000.0,
            "buys_h1":100,
            "sells_h1":100,
            "token_identity_verified":True,
            "target_token_side":"BASE",
            "price_identity_contract_version":2,
        }],
    }
    mark=realizable_performance._latest_exact_pair_mark(record,"PairABC")
    assert mark is not None
    assert mark["price_usd"]==2.0


def test_solana_pair_comparison_is_case_sensitive():
    record={
        "chain":"solana",
        "measurement_status":"VERIFIED_EXACT_PAIR",
        "price_identity_contract_version":2,
        "current_pair_address":"PairABC",
        "current_price_usd":2.0,
        "history":[{
            "pair_address":"PairABC",
            "price_usd":2.0,
            "liquidity_usd":100000.0,
            "volume_h1":50000.0,
            "buys_h1":100,
            "sells_h1":100,
            "token_identity_verified":True,
            "price_identity_contract_version":2,
        }],
    }
    assert realizable_performance._latest_exact_pair_mark(record,"pairabc") is None
