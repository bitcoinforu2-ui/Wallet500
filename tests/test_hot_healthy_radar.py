from datetime import datetime, timedelta, timezone

import wallet500.hot_healthy_radar as radar


TOKEN = 'SoLTokenCaseSensitive111111111111111111111111'
PAIR = 'ExactPairCaseSensitive11111111111111111111111'


def _created_ms(days_ago: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp() * 1000)


def _record(pair=PAIR):
    return {
        'chain': 'solana',
        'token': TOKEN,
        'entry_pair_address': pair,
        'entry_dex': 'pumpswap',
        'entry_price_usd': 1.0,
        'history': [
            {
                'pair_address': pair,
                'price_usd': 1.0,
                'liquidity_usd': 100000,
                'volume_h1': 60000,
                'buys_h1': 250,
                'sells_h1': 120,
            }
        ],
    }


def _pair(*, pair=PAIR, days_ago=200, liquidity=120000, volume=70000, buys=260, sells=120):
    return {
        'chainId': 'solana',
        'dexId': 'pumpswap',
        'pairAddress': pair,
        'url': f'https://dexscreener.com/solana/{pair}',
        'baseToken': {'address': TOKEN, 'symbol': 'OLD'},
        'quoteToken': {'address': 'So11111111111111111111111111111111111111112', 'symbol': 'SOL'},
        'priceUsd': '1.05',
        'priceNative': '0.01',
        'liquidity': {'usd': liquidity, 'base': 50000, 'quote': 500},
        'volume': {'h1': volume, 'm5': 1000, 'h6': volume * 4, 'h24': volume * 10},
        'txns': {
            'h1': {'buys': buys, 'sells': sells},
            'h24': {'buys': buys * 10, 'sells': sells * 10},
        },
        'priceChange': {'m5': 0, 'h1': 1, 'h6': 2, 'h24': 3},
        'pairCreatedAt': _created_ms(days_ago),
    }


def test_live_mature_exact_pair_can_be_scored(monkeypatch):
    monkeypatch.setattr(radar, 'token_pairs', lambda chain, token: [_pair()])
    monkeypatch.setattr(radar, 'pair_lookup', lambda chain, pair: None)

    live, reason = radar._live_exact_pair_truth(_record())
    assert reason is None
    assert live['veteran_age_verified'] is True
    assert live['liquidity_usd'] == 120000

    scored = radar._score(_record(), live)
    assert scored is not None
    assert scored['live_token_identity_verified'] is True
    assert scored['veteran_age_verified'] is True
    assert scored['dex_url'].endswith(PAIR)


def test_under_180_day_token_is_quarantined(monkeypatch):
    monkeypatch.setattr(radar, 'token_pairs', lambda chain, token: [_pair(days_ago=20)])
    monkeypatch.setattr(radar, 'pair_lookup', lambda chain, pair: None)

    live, reason = radar._live_exact_pair_truth(_record())
    assert live is None
    assert reason == 'UNDER_180D_MARKET_AGE'


def test_stale_strong_history_cannot_override_collapsed_live_liquidity(monkeypatch):
    monkeypatch.setattr(radar, 'token_pairs', lambda chain, token: [_pair(liquidity=0)])
    monkeypatch.setattr(radar, 'pair_lookup', lambda chain, pair: None)

    # Historical record is deliberately strong; current market truth must win.
    assert radar._preeligible(_record()) is True
    live, reason = radar._live_exact_pair_truth(_record())
    assert live is None
    assert reason == 'LIVE_LIQUIDITY_BELOW_50K'


def test_live_activity_floor_is_fail_closed(monkeypatch):
    monkeypatch.setattr(radar, 'token_pairs', lambda chain, token: [_pair(volume=1000)])
    monkeypatch.setattr(radar, 'pair_lookup', lambda chain, pair: None)

    live, reason = radar._live_exact_pair_truth(_record())
    assert live is None
    assert reason == 'LIVE_VOLUME_H1_BELOW_15K'


def test_solana_pair_identity_is_case_sensitive(monkeypatch):
    lowercase_pair = PAIR.lower()
    monkeypatch.setattr(radar, 'token_pairs', lambda chain, token: [_pair(pair=lowercase_pair)])
    monkeypatch.setattr(radar, 'pair_lookup', lambda chain, pair: None)

    live, reason = radar._live_exact_pair_truth(_record(pair=PAIR))
    assert live is None
    assert reason == 'LIVE_EXACT_PAIR_OR_TOKEN_IDENTITY_UNVERIFIED'


def test_token_side_mismatch_is_fail_closed(monkeypatch):
    bad = _pair()
    bad['baseToken']['address'] = 'DifferentToken111111111111111111111111111111'
    bad['quoteToken']['address'] = 'AnotherToken11111111111111111111111111111'
    monkeypatch.setattr(radar, 'token_pairs', lambda chain, token: [bad])
    monkeypatch.setattr(radar, 'pair_lookup', lambda chain, pair: None)

    live, reason = radar._live_exact_pair_truth(_record())
    assert live is None
    assert reason == 'VETERAN_AGE_UNVERIFIED'
