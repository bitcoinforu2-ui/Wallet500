from wallet500.truth_contract import (
    RESEARCH_MIN_MARKET_AGE_DAYS,
    RESEARCH_MIN_LIQUIDITY_USD,
    PRODUCTION_MIN_MARKET_AGE_DAYS,
    PRODUCTION_MIN_LIQUIDITY_USD,
    AUTOMATIC_BUY_ALLOWED,
    verified_market_age,
)


def test_policy_constants_never_weaken():
    assert RESEARCH_MIN_MARKET_AGE_DAYS == 90
    assert RESEARCH_MIN_LIQUIDITY_USD == 15000
    assert PRODUCTION_MIN_MARKET_AGE_DAYS == 180
    assert PRODUCTION_MIN_LIQUIDITY_USD == 50000
    assert AUTOMATIC_BUY_ALLOWED is False


def test_legacy_60d_alias_cannot_prove_90d_without_numeric_age():
    assert verified_market_age({"market_age_verified_60d_plus": True}) is False
    assert verified_market_age({"market_age_verified_60d_plus": True, "market_age_days": 61}) is False
    assert verified_market_age({"market_age_verified_60d_plus": True, "market_age_days": 90}) is True


def test_production_age_requires_180_even_with_verified_flag():
    row = {"market_age_verified": True, "market_age_min_days": 179}
    assert verified_market_age(row, minimum_days=180) is False
    row["market_age_min_days"] = 180
    assert verified_market_age(row, minimum_days=180) is True
