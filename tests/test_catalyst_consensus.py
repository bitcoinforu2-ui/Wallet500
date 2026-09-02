from wallet500.catalyst_dna import _consensus_profiles


def test_market_profiles_are_deduplicated_into_unique_symbol_consensus():
    profiles=[
        {'symbol':'ABCUSDT','exchange':'gate','dna_score':60,'pattern':['PRICE_BREAKOUT','VOLUME_EXPANSION'],'current_deviation':{'price_pct':10,'volume_pct':50,'oi_pct':2}},
        {'symbol':'ABCUSDT','exchange':'bybit','dna_score':50,'pattern':['PRICE_BREAKOUT'],'current_deviation':{'price_pct':8,'volume_pct':20,'oi_pct':1}},
        {'symbol':'ABCUSDT','exchange':'mexc','dna_score':40,'pattern':['PRICE_BREAKOUT','OI_EXPANSION'],'current_deviation':{'price_pct':9,'volume_pct':10,'oi_pct':15}},
        {'symbol':'XYZUSDT','exchange':'gate','dna_score':20,'pattern':['QUIET_BASELINE'],'current_deviation':{'price_pct':1,'volume_pct':2,'oi_pct':0}},
    ]
    out=_consensus_profiles(profiles)
    assert len(out)==2
    abc=next(x for x in out if x['symbol']=='ABCUSDT')
    assert abc['markets_count']==3
    assert abc['consensus_dna_score_median']==50
    price=next(x for x in abc['consensus_features'] if x['feature']=='PRICE_BREAKOUT')
    assert price['supporting_markets']==3
    assert price['support_pct']==100.0
    assert all(x['feature']!='VOLUME_EXPANSION' for x in abc['consensus_features'])
