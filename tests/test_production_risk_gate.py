from wallet500.production_risk_gate import evaluate


def test_below_50k_is_hard_block():
    x={'chain':'solana','token':'T','liquidity_usd':49999}
    r=evaluate(x,{})
    assert r['production_risk_blocked'] is True
    assert 'LIVE_LIQUIDITY_BELOW_50K_HARD_BLOCK' in r['production_risk_critical']


def test_liquidity_evacuation_is_hard_block():
    x={'chain':'solana','token':'T','liquidity_usd':1}
    outcomes={'tokens':{'solana:T':{'history':[{'liquidity_usd':111000},{'liquidity_usd':111000}]}}}
    r=evaluate(x,outcomes)
    assert r['production_risk_blocked'] is True
    assert 'LIQUIDITY_COLLAPSE_GT_90PCT_FROM_OBSERVED_PEAK' in r['production_risk_critical']
