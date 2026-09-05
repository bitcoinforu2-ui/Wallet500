from wallet500.survivor_wallet_transaction_intelligence_v5 import analyse_row, verified_transactions


def base_row():
    return {
        "chain": "solana",
        "token": "TokenABC",
        "pair_address": "PairXYZ",
        "liquidity_usd": 200000,
    }


def test_unverified_and_wrong_pair_transactions_are_discarded():
    rows = [{
        "chain": "solana",
        "token": "TokenABC",
        "pair_address": "PairXYZ",
        "transactions": [
            {"tx_hash": "a", "wallet": "w1", "side": "BUY", "usd_value": 1000, "verified_swap": False, "pair_address": "PairXYZ"},
            {"tx_hash": "b", "wallet": "w2", "side": "BUY", "usd_value": 1000, "verified_swap": True, "pair_address": "OtherPair"},
            {"tx_hash": "c", "wallet": "w3", "side": "BUY", "usd_value": 1500, "verified_swap": True, "pair_address": "PairXYZ"},
        ],
    }]
    txs, rejected = verified_transactions(rows, base_row())
    assert [x["tx_hash"] for x in txs] == ["c"]
    assert "UNVERIFIED_SWAP_DISCARDED" in rejected
    assert "TX_PAIR_MISMATCH" in rejected


def test_verified_exact_pair_flow_computes_capital_and_unique_buyers():
    rows = [{
        "chain": "solana",
        "token": "TokenABC",
        "pair_address": "PairXYZ",
        "transactions": [
            {"tx_hash": "1", "wallet": "w1", "side": "BUY", "usd_value": 12000, "verified_swap": True, "pair_address": "PairXYZ", "cluster_id": "c1"},
            {"tx_hash": "2", "wallet": "w2", "side": "BUY", "usd_value": 8000, "verified_swap": True, "pair_address": "PairXYZ", "cluster_id": "c2"},
            {"tx_hash": "3", "wallet": "w3", "side": "SELL", "usd_value": 5000, "verified_swap": True, "pair_address": "PairXYZ", "cluster_id": "c3"},
        ],
    }]
    out = analyse_row(base_row(), rows)
    assert out["flow"]["coverage"] == "VERIFIED_EXACT_PAIR_SWAPS"
    assert out["flow"]["buy_usd"] == 20000
    assert out["flow"]["sell_usd"] == 5000
    assert out["flow"]["net_buy_usd"] == 15000
    assert out["flow"]["unique_buyers"] == 2
    assert out["production_effect"] is False


def test_duplicate_tx_hash_is_deduplicated():
    tx = {"tx_hash": "same", "wallet": "w1", "side": "BUY", "usd_value": 1000, "verified_swap": True, "pair_address": "PairXYZ"}
    rows = [{"chain": "solana", "token": "TokenABC", "pair_address": "PairXYZ", "transactions": [tx, dict(tx)]}]
    out = analyse_row(base_row(), rows)
    assert out["flow"]["verified_swap_n"] == 1
    assert out["flow"]["buy_usd"] == 1000


def test_verified_wallet_labels_only_can_enter_smart_money_layer():
    rows = [{
        "chain": "solana",
        "token": "TokenABC",
        "pair_address": "PairXYZ",
        "transactions": [
            {"tx_hash": "1", "wallet": "elite1", "side": "BUY", "usd_value": 7000, "verified_swap": True, "pair_address": "PairXYZ", "wallet_label": "ELITE", "wallet_label_verified": True},
            {"tx_hash": "2", "wallet": "hint", "side": "BUY", "usd_value": 9000, "verified_swap": True, "pair_address": "PairXYZ", "wallet_label": "ELITE", "wallet_label_verified": False},
        ],
    }]
    out = analyse_row(base_row(), rows)
    assert out["smart_money"]["verified_labeled_wallet_n"] == 1
    assert out["smart_money"]["smart_money_buy_usd"] == 7000
