from wallet500.production_risk_gate import evaluate


def test_below_50k_is_hard_block():
    x={'chain':'solana','token':'T','liquidity_usd':14999}
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


def test_solana_unknown_mint_authority_truth_fails_closed():
    x={'chain':'solana','token':'T','liquidity_usd':90000,'lp_verified':True}
    r=evaluate(x,{})
    assert r['production_risk_blocked'] is True
    assert r['solana_mint_authority_state']=='UNKNOWN'
    assert 'MINT_AUTHORITY_TRUTH_UNKNOWN_FAIL_CLOSED' in r['production_risk_critical']


def test_verified_revoked_mint_passes_authority_hard_gate_but_unknown_freeze_is_not_safe():
    x={'chain':'solana','token':'T','liquidity_usd':90000,'lp_verified':True,'mintability_verified':True,'mintability_status':'NON_MINTABLE_VERIFIED','mintable':False,'mint_authority':None}
    r=evaluate(x,{})
    assert 'MINT_AUTHORITY_TRUTH_UNKNOWN_FAIL_CLOSED' not in r['production_risk_critical']
    assert r['solana_mint_authority_state']=='REVOKED'
    assert r['solana_freeze_authority_state']=='UNKNOWN'
    assert 'FREEZE_AUTHORITY_TRUTH_UNKNOWN_NOT_SAFE' in r['production_risk_reasons']


def test_wallet_evidence_is_never_a_real_alert_promotion():
    x={'chain':'bsc','token':'0xA','liquidity_usd':90000,'lp_verified':True,'cluster_accumulation':True,'strong_wallet_count':5,'wallet_cluster_score':95}
    r=evaluate(x,{})
    shadow=r['wallet_discovery_shadow']
    assert shadow['detected'] is True
    assert shadow['ranking_only'] is True
    assert shadow['real_alert_eligible'] is False
    assert shadow['auto_promote'] is False
