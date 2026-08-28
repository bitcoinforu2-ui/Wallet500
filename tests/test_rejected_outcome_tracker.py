from wallet500 import rejected_outcome_tracker as r


def test_gain_uses_peak_and_latest_observation():
    peak,current=r._gain(1,[{'price_usd':1.2},{'price_usd':5},{'price_usd':2}])
    assert peak==400
    assert current==100


def test_gain_rejects_missing_or_zero_entry():
    assert r._gain(None,[{'price_usd':2}])==(None,None)
    assert r._gain(0,[{'price_usd':2}])==(None,None)


def test_exact_pair_key_prevents_pool_mixing():
    a={'chain':'bsc','token':'0xABC','pair_address':'0xPAIR1'}
    b={'chain':'bsc','token':'0xabc','pair_address':'0xpair2'}
    assert r._key(a)=='bsc|0xabc|0xpair1'
    assert r._key(a)!=r._key(b)
