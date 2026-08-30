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
    # Both rows pass fresh entry revalidation. The stronger current market row
    # must outrank the huge historical winner, proving hindsight is not used.
    perf={'rows':[
        _row('strong',90000,80000,300,-90),
        _row('weak',50000,1000,10,5000),
    ],'blocked_now':2}
    accepted, rejected=_candidates(perf)
    assert not rejected
    assert accepted[0]['token']=='strong'


def test_initial_cohort_is_revalidated_top_ten_one_dollar_each():
    rows=[_row(f't{i:02d}',90000-i,80000-i,300-i,i*1000) for i in range(12)]
    ledger=_initial({'rows':rows,'blocked_now':290},'2026-08-30T00:00:00+00:00')
    assert ledger['mode']=='PAPER_ONLY_REVALIDATED_TOP10_EXPERIMENT_V2'
    assert ledger['production_bypass'] is False
    assert ledger['paper_only'] is True
    assert ledger['selection_policy']=='TOP10_ONLY_AFTER_FRESH_EXACT_PAIR_REVALIDATION_LIQ50K_SURVIVAL_ACTIVE_NO_HINDSIGHT'
    assert ledger['eligible_revalidated_pool']==12
    assert ledger['rejected_at_entry_count']==0
    assert len(ledger['positions'])==10
    assert ledger['starting_value_usd']==10.0
    assert all(p['cost_usd']==1.0 for p in ledger['positions'])
    assert all(p['entry_liquidity_usd']>=50000 for p in ledger['positions'])
    assert all(p['entry_verified_at']=='2026-08-30T00:00:00+00:00' for p in ledger['positions'])
