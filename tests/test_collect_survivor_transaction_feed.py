from wallet500.collect_survivor_transaction_feed import normalize_trade, pair_query


def row(chain="solana", token="TokenABC", pair="PairXYZ"):
    return {"chain": chain, "token": token, "pair_address": pair}


def test_query_is_exact_pool_and_one_hour_scoped():
    q = pair_query("Solana", "PairXYZ", hours=1, limit=500)
    assert 'Pool: {Address: {is: "PairXYZ"}}' in q
    assert 'Market: {Network: {is: "Solana"}}' in q
    assert 'hours_ago: 1' in q
    assert 'count: 500' in q
    # Market.Address is not a portable pool identifier on EVM.
    assert 'Market: {Address:' not in q


def test_normalize_base_token_trade_preserves_side_and_usd():
    trade = {
        "Side": "Buy",
        "Block": {"Time": "2026-09-05T07:00:00Z"},
        "Trader": {"Address": "wallet1"},
        "AmountsInUsd": {"Base": 1234.5, "Quote": 1234.5},
        "Pair": {
            "Token": {"Address": "TokenABC"},
            "QuoteToken": {"Address": "USDC"},
            "Pool": {"Address": "PairXYZ", "Id": "pool-id"},
            "Market": {"Address": "factory", "Program": "program", "Protocol": "dex"},
        },
        "TransactionHeader": {"Hash": "tx1"},
    }
    out = normalize_trade(trade, row())
    assert out["side"] == "BUY"
    assert out["usd_value"] == 1234.5
    assert out["verified_swap"] is True
    assert out["pair_address"] == "PairXYZ"
    assert out["pool_address_verified"] == "PairXYZ"
    assert out["market_address"] == "factory"


def test_normalize_quote_token_trade_inverts_side():
    trade = {
        "Side": "Buy",
        "Trader": {"Address": "wallet1"},
        "AmountsInUsd": {"Base": 900, "Quote": 900},
        "Pair": {
            "Token": {"Address": "OTHER"},
            "QuoteToken": {"Address": "TokenABC"},
            "Pool": {"Address": "PairXYZ"},
            "Market": {"Address": "factory"},
        },
        "TransactionHeader": {"Hash": "tx2"},
    }
    out = normalize_trade(trade, row())
    assert out["side"] == "SELL"
    assert out["usd_value"] == 900


def test_wrong_pool_or_unrelated_token_is_rejected():
    wrong_pool = {
        "Side": "Buy", "Trader": {"Address": "w"}, "AmountsInUsd": {"Base": 1},
        "Pair": {
            "Token": {"Address": "TokenABC"},
            "QuoteToken": {"Address": "USDC"},
            "Pool": {"Address": "OtherPair"},
            "Market": {"Address": "PairXYZ"},
        },
        "TransactionHeader": {"Hash": "x"},
    }
    unrelated = {
        "Side": "Buy", "Trader": {"Address": "w"}, "AmountsInUsd": {"Base": 1, "Quote": 1},
        "Pair": {
            "Token": {"Address": "AAA"},
            "QuoteToken": {"Address": "BBB"},
            "Pool": {"Address": "PairXYZ"},
            "Market": {"Address": "factory"},
        },
        "TransactionHeader": {"Hash": "y"},
    }
    assert normalize_trade(wrong_pool, row()) is None
    assert normalize_trade(unrelated, row()) is None
