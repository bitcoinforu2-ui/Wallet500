from wallet500 import catalyst_focus as cf


def base_event(owner='mexc', event_id='e1', forward_new=True):
    return {'event_id':event_id,'forward_new':forward_new,'preliminary_filter_pass':True,'source_url':'https://example.com','source_owner':owner,'source_id':'X','symbol':'ABC','chain':'base','contract':'0x'+'1'*40,'event_type':'SPOT_LISTING_EXPECTED','impact_score':100}

def market(**kw):
    d={'token_identity_verified':True,'pair_address':'0xpair','url':'https://dexscreener.com/base/0xpair','price_usd':0.01,'liquidity_usd':300000,'market_cap':5000000,'fdv':5000000,'volume_h1':250000,'buys_h1':180,'sells_h1':100,'price_change_h1':5,'price_change_h24':12};d.update(kw);return d

def test_small_exchange_not_auto_focus(monkeypatch):
    monkeypatch.setattr(cf,'market_snapshot',lambda c,t:market());out=cf.score_event(base_event('weex'));assert 'EXCHANGE_IMPACT_TOO_LOW' in out['blockers'];assert out['focus_eligible'] is False

def test_large_exchange_strong_market_focus(monkeypatch):
    monkeypatch.setattr(cf,'market_snapshot',lambda c,t:market());out=cf.score_event(base_event('binance'));assert out['decision_score']>=cf.FOCUS_SCORE;assert out['focus_eligible'] is True;assert out['dex_url'].startswith('https://dexscreener.com/')

def test_overextended_market_is_penalized(monkeypatch):
    monkeypatch.setattr(cf,'market_snapshot',lambda c,t:market(price_change_h1=95,price_change_h24=260));out=cf.score_event(base_event('mexc'));assert out['headroom_score']<=15;assert 'ALREADY_OVEREXTENDED' in out['decision_reasons'];assert out['focus_eligible'] is False

def test_liquidity_floor_is_hard_block(monkeypatch):
    monkeypatch.setattr(cf,'market_snapshot',lambda c,t:market(liquidity_usd=49000));out=cf.score_event(base_event('binance'));assert 'LIQUIDITY_BELOW_50K' in out['blockers'];assert out['focus_eligible'] is False

def test_unresolved_market_stays_silent_not_promoted(monkeypatch):
    monkeypatch.setattr(cf,'market_snapshot',lambda c,t:None);out=cf.score_event(base_event('binance'));assert out['decision']=='WATCH_SILENT_NO_EXACT_MARKET';assert out['focus_eligible'] is False

def test_material_price_move_triggers_update():
    p={'decision_score':80,'market':market(price_usd=1,liquidity_usd=200000)};c={'decision_score':80,'market':market(price_usd=1.12,liquidity_usd=200000)};reason,critical=cf.material_change(c,p);assert reason and reason.startswith('PRICE_MOVE_');assert critical is False

def test_liquidity_break_is_critical():
    p={'decision_score':80,'market':market(price_usd=1,liquidity_usd=200000)};c={'decision_score':70,'market':market(price_usd=1,liquidity_usd=40000)};reason,critical=cf.material_change(c,p);assert reason=='LIQUIDITY_BROKE_50K';assert critical is True

def test_first_focus_run_baselines_history_but_keeps_current_forward_event():
    old=base_event('mexc',event_id='old',forward_new=False);new=base_event('mexc',event_id='new',forward_new=True);wire={'events':[new]};ledger={'events':{'old':{'first_seen_at':'2026-09-01T00:00:00+00:00','event':old},'new':{'first_seen_at':'2026-09-07T00:00:00+00:00','event':new}}};state={};seen={};found=cf.discover_unseen(wire,ledger,state,seen);assert set(found)=={'new'};assert 'old' in seen;assert state['ledger_baseline_complete'] is True

def test_ledger_catches_event_even_after_forward_flag_disappears():
    event=base_event('mexc',event_id='ledger-new',forward_new=False);wire={'events':[event]};ledger={'events':{'ledger-new':{'first_seen_at':'2026-09-07T00:00:00+00:00','event':event}}};state={'ledger_baseline_complete':True};seen={};found=cf.discover_unseen(wire,ledger,state,seen);assert set(found)=={'ledger-new'}

def test_routine_single_exchange_listing_stays_off_telegram():
    scored=base_event('binance');scored.update(focus_eligible=True,decision_score=84,market_readiness_score=80,risk_score=10,market=market(liquidity_usd=500000));ledger={'events':{'e1':{'event':base_event('binance')}}};notify,gate=cf.telegram_gate(scored,ledger);assert notify is False;assert gate['reason']=='ROUTINE_LISTING_SILENT'

def test_double_listing_is_telegram_relevant():
    scored=base_event('binance');scored.update(focus_eligible=True,decision_score=80,market_readiness_score=75,risk_score=10,market=market());coinbase=base_event('coinbase','e2');ledger={'events':{'e1':{'event':base_event('binance')},'e2':{'event':coinbase}}};notify,gate=cf.telegram_gate(scored,ledger);assert notify is True;assert gate['reason']=='MULTI_EXCHANGE_LISTING';assert gate['exchange_count']==2

def test_exceptional_single_listing_can_alert_but_requires_strict_market():
    scored=base_event('binance');scored.update(focus_eligible=True,decision_score=92,market_readiness_score=91,risk_score=5,market=market(liquidity_usd=900000));ledger={'events':{'e1':{'event':base_event('binance')}}};notify,gate=cf.telegram_gate(scored,ledger);assert notify is True;assert gate['reason']=='EXCEPTIONAL_SETUP'

def test_same_symbol_different_contract_is_not_double_listing():
    scored=base_event('binance');scored.update(focus_eligible=True,decision_score=80,market_readiness_score=75,risk_score=10,market=market());other=base_event('coinbase','e2');other['contract']='0x'+'2'*40;ledger={'events':{'e1':{'event':base_event('binance')},'e2':{'event':other}}};notify,gate=cf.telegram_gate(scored,ledger);assert notify is False;assert gate['exchange_count']==1
