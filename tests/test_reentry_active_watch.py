from wallet500.reentry_active_watch import evaluate_reentry


def base():
    return {
        'current_price_usd': 0.00425,
        'watch_peak_price_usd': 0.00480,
        'pullback_low_price_usd': 0.00410,
        'signal_score': 81,
        'execution_liquidity_usd': 825900,
        'exact_identity_verified': True,
        'market_context_ok': True,
        'catalyst_scan_ok': True,
        'renewed_buy_flow': True,
        'liquidity_survival_ok': True,
    }


def test_confirmed_reentry_has_clear_action_prices():
    out=evaluate_reentry(base())
    assert out['action_state']=='RE_ENTRY'
    assert out['actionable'] is True
    assert out['target_1_price_usd'] > out['entry_price_usd']
    assert out['target_2_price_usd'] > out['target_1_price_usd']
    assert out['risk_invalidation_price_usd'] < out['entry_price_usd']
    assert out['contract']['automatic_trade'] is False


def test_no_reentry_without_market_and_catalyst_scan():
    row=base(); row['market_context_ok']=False; row['catalyst_scan_ok']=False
    out=evaluate_reentry(row)
    assert out['action_state']=='ACTIVE_WATCH'
    assert out['actionable'] is False
    assert 'MARKET_CONTEXT_NOT_CONFIRMED' in out['blockers']
    assert 'CATALYST_SCAN_NOT_CLEARED' in out['blockers']


def test_no_reentry_without_renewed_buy_flow():
    row=base(); row['renewed_buy_flow']=False
    out=evaluate_reentry(row)
    assert out['actionable'] is False
    assert 'BUY_FLOW_NOT_RENEWED' in out['blockers']
