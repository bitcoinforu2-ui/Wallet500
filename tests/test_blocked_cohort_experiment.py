from wallet500.blocked_cohort_experiment import _candidates, _initial


def _row(token, liq, vol, tx, ret):
    return {
        'chain':'bsc','token':token,'pair_address':'pair'+token,
        'current_status':'CURRENTLY_BLOCKED','current_price_usd':1.0,
        'liquidity_usd':liq,'volume_h1':vol,'txns_h1':tx,
        'current_return_pct':ret,'peak_return_pct':ret*2,
        'reasons':['TEST_BLOCK'],
    }


def test_ranking_does_not_use_historical_return():
    perf={'rows':[
        _row('strong',49000,14900,49,-90),
        _row('weak',1000,100,1,5000),
    ],'blocked_now':2}
    ranked=_candidates(perf)
    assert ranked[0]['token']=='strong'


def test_initial_cohort_is_frozen_top_ten_one_dollar_each():
    rows=[_row(f't{i:02d}',49000-i,14900-i,49,i*1000) for i in range(12)]
    ledger=_initial({'rows':rows,'blocked_now':290},'2026-08-30T00:00:00+00:00')
    assert ledger['mode']=='PAPER_ONLY_BLOCKED_COHORT_EXPERIMENT'
    assert ledger['production_bypass'] is False
    assert len(ledger['positions'])==10
    assert ledger['starting_value_usd']==10.0
    assert all(p['cost_usd']==1.0 for p in ledger['positions'])
    assert ledger['source_blocked_now']==290
