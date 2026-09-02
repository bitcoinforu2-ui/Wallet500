from wallet500.hot_email_alerts import _exact_dex_identity, _is_hot


def test_hot_matches_live_radar_threshold():
    assert _is_hot({"cex_revival_score": 75, "confirmations": 2}) is True
    assert _is_hot({"cex_revival_score": 74, "confirmations": 5}) is False
    assert _is_hot({"cex_revival_score": 90, "confirmations": 1}) is False


def test_exact_dex_identity_fails_closed_without_pair_lock():
    row = {
        "token_address": "0x1111111111111111111111111111111111111111",
        "pair_address": "0x2222222222222222222222222222222222222222",
        "locked_pair_address": "0x3333333333333333333333333333333333333333",
        "pair_identity_locked": True,
        "dex": "uniswap",
    }
    assert _exact_dex_identity(row)["verified"] is False


def test_exact_dex_identity_requires_exact_pair():
    pair = "0x2222222222222222222222222222222222222222"
    row = {
        "token_address": "0x1111111111111111111111111111111111111111",
        "pair_address": pair,
        "locked_pair_address": pair,
        "pair_identity_locked": True,
        "dex": "uniswap",
        "url": "https://dexscreener.com/ethereum/example",
    }
    identity = _exact_dex_identity(row)
    assert identity["verified"] is True
    assert identity["pair_address"] == pair
