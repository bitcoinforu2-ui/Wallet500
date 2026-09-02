from wallet500.hot_email_alerts import _exact_dex_identity, _is_hot


def row(**updates):
    base = {
        "status": "REAL_ALERT",
        "actionable_research_alert": True,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "market_age_verified": True,
        "market_age_days": 365,
        "liquidity_usd": 100000,
        "score": 90,
        "token_address": "0x1111111111111111111111111111111111111111",
        "pair_address": "0x2222222222222222222222222222222222222222",
        "dex": "uniswap",
        "dex_url": "https://dexscreener.com/ethereum/example",
    }
    base.update(updates)
    return base


def test_hot_email_accepts_only_strict_real_alert():
    assert _is_hot(row()) is True


def test_hot_email_rejects_underage_or_unverified_identity():
    assert _is_hot(row(market_age_days=179)) is False
    assert _is_hot(row(market_age_verified=False)) is False
    assert _is_hot(row(exact_identity_verified=False)) is False
    assert _is_hot(row(exact_pair_verified=False)) is False


def test_hot_email_rejects_cex_only_score_and_low_liquidity():
    assert _is_hot({"cex_revival_score": 100, "confirmations": 7}) is False
    assert _is_hot(row(liquidity_usd=49999)) is False
    assert _is_hot(row(status="VERIFIED_WATCH_NOT_REAL_ALERT")) is False
    assert _is_hot(row(score=74)) is False


def test_exact_dex_identity_uses_real_alert_truth_flags():
    identity = _exact_dex_identity(row())
    assert identity["verified"] is True
    assert identity["pair_address"] == "0x2222222222222222222222222222222222222222"
    assert identity["token_address"] == "0x1111111111111111111111111111111111111111"


def test_exact_dex_identity_fails_closed_without_real_alert_truth_flags():
    incomplete = row(exact_pair_verified=False)
    assert _exact_dex_identity(incomplete)["verified"] is False
