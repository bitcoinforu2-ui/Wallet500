from wallet500 import survivor_exact_pair_crosscheck as m


def row(chain="solana", token="TokenABC", pair="PairXYZ"):
    return {
        "chain": chain,
        "token": token,
        "pair_address": pair,
        "price_usd": 1.0,
        "liquidity_usd": 100000,
        "volume_h1": 10000,
        "volume_h24": 100000,
    }


def payload(pair="PairXYZ", base="TokenABC", quote="USDC"):
    return {
        "data": {
            "type": "pool",
            "attributes": {
                "address": pair,
                "base_token_price_usd": "1.01",
                "quote_token_price_usd": "1",
                "reserve_in_usd": "105000",
                "volume_usd": {"h1": "11000", "h24": "101000"},
                "transactions": {"h1": {"buys": 12, "sells": 7}, "h24": {"buys": 100, "sells": 80}},
            },
            "relationships": {
                "base_token": {"data": {"id": "solana_base"}},
                "quote_token": {"data": {"id": "solana_quote"}},
            },
        },
        "included": [
            {"type": "token", "id": "solana_base", "attributes": {"address": base}},
            {"type": "token", "id": "solana_quote", "attributes": {"address": quote}},
        ],
    }


def test_verified_exact_pair(monkeypatch):
    monkeypatch.setattr(m, "get_pool", lambda network, pair: payload())
    out = m.crosscheck(row())
    assert out["coverage"] == "VERIFIED_INDEPENDENT_EXACT_PAIR_CROSSCHECK"
    assert out["provider_pair_address"] == "PairXYZ"
    assert out["target_token_side"] == "BASE"
    assert out["provider_metrics"]["liquidity_usd"] == 105000
    assert out["exact_pair_only"] is True


def test_wrong_pair_fails_closed(monkeypatch):
    monkeypatch.setattr(m, "get_pool", lambda network, pair: payload(pair="OtherPair"))
    out = m.crosscheck(row())
    assert out["coverage"] == "EXACT_PAIR_IDENTITY_MISMATCH"


def test_wrong_token_fails_closed(monkeypatch):
    monkeypatch.setattr(m, "get_pool", lambda network, pair: payload(base="AAA", quote="BBB"))
    out = m.crosscheck(row())
    assert out["coverage"] == "EXACT_TOKEN_NOT_IN_PROVIDER_PAIR"


def test_evm_pair_identity_is_case_insensitive(monkeypatch):
    p = payload(pair="0xABC", base="0xTOKEN", quote="0xUSDC")
    monkeypatch.setattr(m, "get_pool", lambda network, pair: p)
    out = m.crosscheck(row(chain="ethereum", token="0xtoken", pair="0xabc"))
    assert out["coverage"] == "VERIFIED_INDEPENDENT_EXACT_PAIR_CROSSCHECK"
