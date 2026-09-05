from datetime import datetime,timezone,timedelta
from wallet500 import arbitrum_revival_universe as a

def snap(age=220,liq=100000,vol=30000,buys=80,sells=40):
    created=(datetime(2026,9,6,tzinfo=timezone.utc)-timedelta(days=age)).timestamp()*1000
    return {'token_identity_verified':True,'pair_address':'0x'+'1'*40,'dex':'x','url':'x','price_usd':1,'liquidity_usd':liq,'volume_h1':vol,'volume_h24':vol*5,'buys_h1':buys,'sells_h1':sells,'price_change_h1':6,'price_change_h24':8,'pair_created_at':created}

def test_full_filter_pass_is_research_only():
    r=a.classify({'token':'0x'+'2'*40,'symbol':'TEST'},snap(),datetime(2026,9,6,tzinfo=timezone.utc))
    assert r['blockers']==[] and r['market_age_verified'] is True
    assert r['revival_signal'] is True and r['actionable'] is False and r['production_portfolio_impact']=='NONE'

def test_under_180_fails_closed():
    r=a.classify({'token':'0x'+'2'*40},snap(age=30),datetime(2026,9,6,tzinfo=timezone.utc))
    assert 'PAIR_AGE_LT_180D_OR_UNKNOWN' in r['blockers']

def test_liquidity_floor_never_relaxed():
    r=a.classify({'token':'0x'+'2'*40},snap(liq=49999),datetime(2026,9,6,tzinfo=timezone.utc))
    assert 'LIVE_LIQUIDITY_LT_50K' in r['blockers']

def test_no_pair_fails_closed_and_stays_research_only():
    r=a.classify({'token':'0x'+'2'*40},None,datetime(2026,9,6,tzinfo=timezone.utc))
    assert r['blockers']==['NO_VERIFIED_EXACT_PAIR']
    assert r['exact_pair_verified'] is False and r['market_age_verified'] is False
    assert r['revival_signal'] is False and r['research_only'] is True
    assert r['actionable'] is False and r['production_portfolio_impact']=='NONE'
