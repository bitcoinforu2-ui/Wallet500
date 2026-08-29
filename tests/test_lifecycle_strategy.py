from wallet500.lifecycle_strategy import initial_state, reconcile


def tracker(price=1.0, entry=0.25, liq=60000):
    return {'tokens': {'bsc:T': {
        'chain':'bsc','token':'T','entry_pair_address':'0xPAIR','entry_price_usd':entry,
        'current_price_usd':price,'measurement_status':'VERIFIED_EXACT_PAIR',
        'history':[{'liquidity_usd':liq}]
    }}}


def test_forward_baseline_does_not_create_historical_events():
    s=initial_state('2026-08-29T12:00:00+00:00')
    s,summary=reconcile(s,tracker(price=0.25), '2026-08-29T12:01:00+00:00')
    assert summary['positions_total']==1
    assert sum(1 for e in s['events'] if e['type']=='MODEL_POSITION_BASELINED')==1
    assert sum(1 for e in s['events'] if 'SELL' in e['type'])==0


def test_partial_profit_ladder():
    s=initial_state('2026-08-29T12:00:00+00:00')
    s,_=reconcile(s,tracker(price=0.25), '2026-08-29T12:01:00+00:00')
    s,summary=reconcile(s,tracker(price=0.50), '2026-08-29T12:02:00+00:00')
    p=next(iter(s['positions'].values()))
    assert p['remaining_fraction']==0.75
    assert 'TP1_2X' in p['triggered']
    assert summary['partial_sell_signals']==1


def test_liquidity_break_exits_remainder():
    s=initial_state('2026-08-29T12:00:00+00:00')
    s,_=reconcile(s,tracker(price=0.25), '2026-08-29T12:01:00+00:00')
    s,summary=reconcile(s,tracker(price=0.30,liq=49999), '2026-08-29T12:02:00+00:00')
    p=next(iter(s['positions'].values()))
    assert p['remaining_fraction']==0
    assert p['status']=='CLOSED_LIQUIDITY_EXIT_SIGNAL'
    assert summary['liquidity_exit_signals']==1


def test_losses_remain_counted():
    s=initial_state('2026-08-29T12:00:00+00:00')
    s,_=reconcile(s,tracker(price=0.25), '2026-08-29T12:01:00+00:00')
    s,summary=reconcile(s,tracker(price=0.10,liq=1000), '2026-08-29T12:02:00+00:00')
    assert summary['closed_losses']==1
    assert summary['model_pnl_usd'] < 0
