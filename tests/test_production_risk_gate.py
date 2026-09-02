from wallet500.production_risk_gate import evaluate


def test_below_50k_is_hard_block():
    x={'chain':'solana','token':'T','liquidity_usd':49999}
    r=evaluate(x,{})
    assert r['production_risk_blocked'] is True
    assert 'EXECUTION_POOL_LIQUIDITY_BELOW_50K_HARD_BLOCK' in r['production_risk_critical']


def test_liquidity_evacuation_is_hard_block():
    x={'chain':'solana','token':'T','liquidity_usd':1}
    outcomes={'tokens':{'solana:T':{'history':[{'liquidity_usd':111000},{'liquidity_usd':111000}]}}}
    r=evaluate(x,outcomes)
    assert r['production_risk_blocked'] is True
    assert 'LIQUIDITY_COLLAPSE_GT_90PCT_FROM_OBSERVED_PEAK' in r['production_risk_critical']


def test_single_hot_signal_does_not_convict():
    x={'chain':'bsc','token':'0xA','liquidity_usd':60000,'volume_h1':260000,'buys_h1':200,'sells_h1':40,'age_minutes':180,'lp_verified':True}
    r=evaluate(x,{})
    assert r['production_risk_blocked'] is False


def test_young_extreme_turnover_sell_pressure_unverified_lp_blocks():
    x={'chain':'bsc','token':'0xA','liquidity_usd':60000,'volume_h1':500000,'buys_h1':400,'sells_h1':340,'age_minutes':30,'lp_verified':False}
    r=evaluate(x,{})
    assert r['production_risk_blocked'] is True
    assert r['pre_rug_danger_score'] >= 5
    assert 'PRE_RUG_COMPOSITE_SIGNATURE_HARD_BLOCK' in r['production_risk_critical']


def test_receding_liquidity_creates_exit_warning_before_50k_break():
    x={'chain':'bsc','token':'0xA','liquidity_usd':55000,'volume_h1':240000,'buys_h1':200,'sells_h1':160,'age_minutes':35,'lp_verified':True}
    outcomes={'tokens':{'bsc:0xa':{'history':[{'liquidity_usd':70000},{'liquidity_usd':70000}]}}}
    r=evaluate(x,outcomes)
    assert r['pre_rug_exit_warning'] is True
