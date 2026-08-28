from wallet500 import rejected_candidate_learning as r


def test_reject_key_is_exact_pair_locked():
    a={'chain':'ethereum','token_address':'0xAbC','pair_address':'0xPAIR1'}
    b={'chain':'ethereum','token_address':'0xabc','pair_address':'0xpair2'}
    assert r._key(a)=='ethereum|0xabc|0xpair1'
    assert r._key(a)!=r._key(b)


def test_snapshot_preserves_reject_source_and_market_state():
    row={'chain':'solana','mint':'Mint1','pair_address':'Pair1','price_usd':1.2,'liquidity_usd':45000,'anomaly_score':92,'production_risk_reasons':['LIVE_LIQUIDITY_BELOW_50K_HARD_BLOCK']}
    s=r._snapshot(row,'PRODUCTION_RISK_BLOCK','2026-01-01T00:00:00+00:00')
    assert s['source']=='PRODUCTION_RISK_BLOCK'
    assert s['pair_address']=='Pair1'
    assert s['price_usd']==1.2
    assert s['liquidity_usd']==45000
    assert s['production_risk_reasons']==['LIVE_LIQUIDITY_BELOW_50K_HARD_BLOCK']
