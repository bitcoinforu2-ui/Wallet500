from datetime import datetime, timezone, timedelta

from wallet500.revival_radar import (
    DEFAULT_BATCH_SIZE,
    OLD_MIN_AGE_DAYS,
    OLD_PREFERRED_AGE_DAYS,
    _score,
)


def _snap(age_days: float):
    created = datetime.now(timezone.utc) - timedelta(days=age_days)
    return {
        'chain': 'solana',
        'token': 'Token111',
        'pair_address': 'Pair111',
        'pair_created_at': int(created.timestamp() * 1000),
        'liquidity_usd': 75000,
        'volume_h1': 40000,
        'volume_h24': 120000,
        'buys_h1': 80,
        'sells_h1': 30,
        'buys_h24': 200,
        'sells_h24': 150,
        'price_change_h1': 7,
        'price_change_m5': 2,
    }


def test_old_coin_policy_is_7d_minimum_and_30d_preferred():
    now = datetime.now(timezone.utc)
    young = _score(_snap(6.9), [], now)
    assert young['revival_eligible'] is False
    assert young['old_coin_age_class'] == 'INELIGIBLE_LT_7D_OR_UNKNOWN'

    established = _score(_snap(8), [], now)
    assert established['revival_eligible'] is True
    assert established['old_coin_age_class'] == 'ESTABLISHED_7D_PLUS'

    mature = _score(_snap(31), [], now)
    assert mature['revival_eligible'] is True
    assert mature['old_coin_age_class'] == 'PREFERRED_30D_PLUS'
    assert 'established pool age 30d+' in mature['revival_reasons']


def test_revival_scan_expanded_batch_policy():
    assert OLD_MIN_AGE_DAYS == 7.0
    assert OLD_PREFERRED_AGE_DAYS == 30.0
    assert DEFAULT_BATCH_SIZE == 180
