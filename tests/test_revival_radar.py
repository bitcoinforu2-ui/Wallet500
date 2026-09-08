import json
from datetime import datetime, timezone, timedelta

from wallet500 import revival_radar as mod
from wallet500.revival_radar import (
    DEFAULT_BATCH_SIZE,
    OLD_MIN_AGE_DAYS,
    OLD_PREFERRED_AGE_DAYS,
    _score,
)


def _snap(age_days: float, pair: str = 'Pair111'):
    created = datetime.now(timezone.utc) - timedelta(days=age_days)
    return {
        'chain': 'solana',
        'token': 'Token111',
        'pair_address': pair,
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


def test_revival_policy_is_90d_veteran_only():
    now = datetime.now(timezone.utc)
    young = _score(_snap(89.9), [], now)
    assert young['revival_eligible'] is False
    assert young['old_coin_age_class'] == 'INELIGIBLE_LT_90D_OR_UNKNOWN'

    veteran = _score(_snap(91), [], now)
    assert veteran['revival_eligible'] is True
    assert veteran['old_coin_age_class'] == 'VETERAN_90D_PLUS'
    assert 'verified veteran pool age 90d+' in veteran['revival_reasons']
    assert 'tradable liquidity 15k+' in veteran['revival_reasons']


def test_revival_scan_expanded_batch_policy():
    assert OLD_MIN_AGE_DAYS == 90.0
    assert OLD_PREFERRED_AGE_DAYS == 90.0
    assert DEFAULT_BATCH_SIZE == 300


def test_revival_scan_reuses_locked_pair(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    state = {
        'version': 4,
        'cursor': 0,
        'tokens': {
            'solana:Token111': {
                'chain': 'solana',
                'token': 'Token111',
                'pair_address': 'PairLOCK',
                'history': [{'observed_at': (now - timedelta(hours=1)).isoformat(), 'volume_h1': 1000, 'liquidity_usd': 50000, 'tx_h1': 10}],
            }
        },
    }
    (tmp_path / 'revival-state.json').write_text(json.dumps(state), encoding='utf-8')
    calls = []

    def fake_snapshot(chain, token, pair_address=None):
        calls.append((chain, token, pair_address))
        return _snap(120, pair=pair_address or 'PairOTHER')

    monkeypatch.setattr(mod, 'snapshot', fake_snapshot)
    discovery = {'tokens': {'solana:Token111': {'chain': 'solana', 'token': 'Token111'}}}
    result = mod.run_revival_scan(tmp_path, discovery, manual_watch=[], now=now.isoformat(), batch_size=1)

    assert calls == [('solana', 'Token111', 'PairLOCK')]
    assert result['state']['tokens']['solana:Token111']['pair_address'] == 'PairLOCK'
    assert result['snapshots'][0]['pair_identity_locked'] is True


def test_legacy_unlocked_history_is_reset_on_first_pair_lock(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    state = {
        'version': 4,
        'cursor': 0,
        'tokens': {
            'solana:Token111': {
                'chain': 'solana',
                'token': 'Token111',
                'history': [{'observed_at': (now - timedelta(hours=1)).isoformat(), 'volume_h1': 1, 'liquidity_usd': 1, 'tx_h1': 1}],
            }
        },
    }
    (tmp_path / 'revival-state.json').write_text(json.dumps(state), encoding='utf-8')

    monkeypatch.setattr(mod, 'snapshot', lambda chain, token, pair_address=None: _snap(120, pair='PairNEW'))
    discovery = {'tokens': {'solana:Token111': {'chain': 'solana', 'token': 'Token111'}}}
    result = mod.run_revival_scan(tmp_path, discovery, manual_watch=[], now=now.isoformat(), batch_size=1)

    rec = result['state']['tokens']['solana:Token111']
    assert rec['pair_address'] == 'PairNEW'
    assert len(rec['history']) == 1
    assert rec['history'][0]['pair_address'] == 'PairNEW'
    assert result['state']['pair_lock_migrations_this_run'] == 1
