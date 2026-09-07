from wallet500 import catalyst_focus as cf


def base_event(owner='mexc'):
    return {
        'event_id':'e1','forward_new':True,'preliminary_filter_pass':True,
        'source_url':'https://example.com','source_owner':owner,'source_id':'X',
        'symbol':'ABC','chain':'base','contract':'0x'+'1'*40,
        'event_type':'SPOT_LISTING_EXPECTED','impact_score':100,
    }


def market(**kw):
    d={
        'token_identity_verified':True,'pair_address':'0xpair','url':'https://dexscreener.com/base/0xpair',
        'price_usd':0.01,'liquidity_usd':300000,'market_cap':5000000,'fdv':5000000,
        'volume_h1':250000,'buys_h1':180,'sells_h1':100,'price_change_h1':5,'price_change_h24':12,
    }
    d.update(kw); return d


def test_small_exchange_not_auto_focus(monkeypatch):
    monkeypatch.setattr(cf, 'market_snapshot', lambda c,t: market())
    out=cf.score_event(base_event('weex'))
    assert out['decision_score'] < cf.FOCUS_SCORE
    assert out['focus_eligible'] is False


def test_large_exchange_strong_market_focus(monkeypatch):
    monkeypatch.setattr(cf, 'market_snapshot', lambda c,t: market())
    out=cf.score_event(base_event('binance'))
    assert out['decision_score'] >= cf.FOCUS_SCORE
    assert out['focus_eligible'] is True
    assert out['dex_url'].startswith('https://dexscreener.com/')


def test_overextended_market_is_penalized(monkeypatch):
    monkeypatch.setattr(cf, 'market_snapshot', lambda c,t: market(price_change_h1=95, price_change_h24=260))
    out=cf.score_event(base_event('mexc'))
    assert out['headroom_score'] <= 15
    assert 'ALREADY_OVEREXTENDED' in out['decision_reasons']
    assert out['focus_eligible'] is False


def test_liquidity_floor_is_hard_block(monkeypatch):
    monkeypatch.setattr(cf, 'market_snapshot', lambda c,t: market(liquidity_usd=49000))
    out=cf.score_event(base_event('binance'))
    assert 'LIQUIDITY_BELOW_50K' in out['blockers']
    assert out['focus_eligible'] is False


def test_material_price_move_triggers_update():
    p={'decision_score':80,'market':market(price_usd=1, liquidity_usd=200000)}
    c={'decision_score':80,'market':market(price_usd=1.12, liquidity_usd=200000)}
    reason, critical=cf.change(c,p)
    assert reason and reason.startswith('PRICE_MOVE_')
    assert critical is False


def test_liquidity_break_is_critical():
    p={'decision_score':80,'market':market(price_usd=1, liquidity_usd=200000)}
    c={'decision_score':70,'market':market(price_usd=1, liquidity_usd=40000)}
    reason, critical=cf.change(c,p)
    assert reason == 'LIQUIDITY_BROKE_50K'
    assert critical is True
