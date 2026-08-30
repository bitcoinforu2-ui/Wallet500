from wallet500.performance_tracker import _pair_key
from wallet500.winner_dna import build_candidate, fixed_horizon_return


def test_pair_key_separates_multiple_pools():
    a = _pair_key('bsc', '0xToken', '0xPairA')
    b = _pair_key('bsc', '0xToken', '0xPairB')
    assert a != b
    assert a.endswith(':0xpaira')


def test_winner_requires_fixed_exact_pair_checkpoint_and_tradable_snapshot():
    token = {
        'chain': 'bsc', 'token': '0xT', 'entry_pair_address': '0xP',
        'first_seen': '2026-01-01T00:00:00+00:00',
        'history': [{'observed_at':'2026-01-01T00:01:00+00:00','pair_address':'0xP','liquidity_usd':60000,'volume_h1':10000,'buys_h1':10,'sells_h1':5}],
        'checkpoints': {'24h': {'pair_address':'0xP','return_pct':42}},
    }
    assert fixed_horizon_return(token) == 42
    assert build_candidate(token) is not None
    token['checkpoints']['24h']['pair_address'] = '0xWRONG'
    assert build_candidate(token) is None


def test_sub_50k_snapshot_is_not_winner_eligible():
    token = {
        'chain': 'bsc', 'token': '0xT', 'entry_pair_address': '0xP',
        'first_seen': '2026-01-01T00:00:00+00:00',
        'history': [{'observed_at':'2026-01-01T00:01:00+00:00','pair_address':'0xP','liquidity_usd':49999,'volume_h1':10000,'buys_h1':10,'sells_h1':5}],
        'checkpoints': {'24h': {'pair_address':'0xP','return_pct':999999999}},
    }
    assert build_candidate(token) is None
