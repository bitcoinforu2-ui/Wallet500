from __future__ import annotations
import json,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from .market_data import snapshot

DATA=Path('data'); OUT=DATA/'arbitrum-revival-universe.json'; STATE=DATA/'arbitrum-revival-state.json'
CHAIN='arbitrum'; NETWORK='arbitrum'; MODE='RESEARCH_ONLY_ARBITRUM_REVIVAL_UNIVERSE_V1'
MIN_AGE_DAYS=180; MIN_LIQUIDITY=50000.0; MIN_VOLUME_H1=15000.0; MIN_TXNS_H1=50
BLOCKED={'USDC','USDT','DAI','USDE','WETH','WBTC','ARBETH','WSTETH','STETH'}

def _load(p,default):
    try:return json.loads(p.read_text()) if p.exists() else default
    except Exception:return default

def _get(url,attempts=5):
    for a in range(attempts):
        try:
            with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'Wallet500/2.0'}),timeout=20) as r:return json.loads(r.read().decode())
        except HTTPError as e:
            if e.code!=429 or a==attempts-1: raise
        except Exception:
            if a==attempts-1: raise
        time.sleep(min(12,1.5*(2**a)))

def _addr(v):
    s=str(v or '').strip().lower(); return s if s.startswith('0x') and len(s)==42 else ''

def _pair_age(ms,now):
    try:
        x=float(ms or 0); x=x/1000 if x>10_000_000_000 else x
        if x<=0:return None
        return max(0,(now-datetime.fromtimestamp(x,tz=timezone.utc)).total_seconds()/86400)
    except Exception:return None

def _extract(rel,included):
    rid=((rel or {}).get('data') or {}).get('id'); obj=included.get(rid,{}) if rid else {}; a=(obj.get('attributes') or {})
    address=_addr(a.get('address') or (rid.split('_',1)[1] if rid and '_' in rid else ''))
    return address,str(a.get('symbol') or '').upper(),a.get('name')

def discover(data_dir=DATA,pages=5):
    found={}; errors=[]
    # Seed exact Arbitrum identities already proven elsewhere in Wallet500.
    reg=_load(data_dir/'cex-identity-registry.json',{}).get('symbols') or {}
    for sym,m in reg.items():
        if isinstance(m,dict) and str(m.get('chain') or '').lower()==CHAIN:
            a=_addr(m.get('token_address'))
            if a and str(sym).upper() not in BLOCKED: found[a]={'token':a,'symbol':str(sym).upper(),'name':m.get('name'),'sources':['exact_identity_registry']}
    # Wide, rate-limit-aware pool census. Sequential by design: previous parallel feeder hit 429 on every chain.
    for endpoint in ('pools','trending_pools'):
        for page in range(1,pages+1):
            url=f"https://api.geckoterminal.com/api/v2/networks/{NETWORK}/{endpoint}?"+urlencode({'page':page,'include':'base_token,quote_token'})
            try: payload=_get(url)
            except Exception as e:
                errors.append({'source':endpoint,'page':page,'error':f'{type(e).__name__}: {e}'[:240]}); break
            included={x.get('id'):x for x in payload.get('included') or [] if isinstance(x,dict) and x.get('id')}
            rows=payload.get('data') or []
            if not rows: break
            for pool in rows:
                rel=(pool or {}).get('relationships') or {}
                for side in ('base_token','quote_token'):
                    a,sym,name=_extract(rel.get(side),included)
                    if not a or sym in BLOCKED: continue
                    row=found.setdefault(a,{'token':a,'symbol':sym,'name':name,'sources':[]})
                    src=f'geckoterminal:{endpoint}:p{page}'
                    if src not in row['sources']:row['sources'].append(src)
            time.sleep(1.1)
    return list(found.values()),errors

def classify(row,snap,now,previous=None):
    boundary={'research_only':True,'actionable':False,'production_portfolio_impact':'NONE'}
    if not snap or snap.get('token_identity_verified') is not True:
        return {**row,'status':'INELIGIBLE_FAIL_CLOSED','blockers':['NO_VERIFIED_EXACT_PAIR'],'exact_pair_verified':False,'market_age_verified':False,'revival_signal':False,**boundary}
    age=_pair_age(snap.get('pair_created_at'),now); liq=float(snap.get('liquidity_usd') or 0); vol=float(snap.get('volume_h1') or 0); tx=int(snap.get('buys_h1') or 0)+int(snap.get('sells_h1') or 0)
    blockers=[]
    if age is None or age<MIN_AGE_DAYS:blockers.append('PAIR_AGE_LT_180D_OR_UNKNOWN')
    if liq<MIN_LIQUIDITY:blockers.append('LIVE_LIQUIDITY_LT_50K')
    if vol<MIN_VOLUME_H1:blockers.append('VOLUME_H1_LT_15K')
    if tx<MIN_TXNS_H1:blockers.append('TXNS_H1_LT_50')
    prev=previous or {}; pv=float(prev.get('volume_h1') or 0); pl=float(prev.get('liquidity_usd') or 0)
    vchg=((vol/pv)-1)*100 if pv>0 else None; lchg=((liq/pl)-1)*100 if pl>0 else None
    revival=bool(not blockers and ((vchg is not None and vchg>=20) or float(snap.get('price_change_h1') or 0)>=5 or (int(snap.get('buys_h1') or 0)>=int(snap.get('sells_h1') or 0)*1.5)))
    return {**row,**{k:snap.get(k) for k in ('pair_address','dex','url','price_usd','liquidity_usd','volume_h1','volume_h24','buys_h1','sells_h1','price_change_h1','price_change_h24','pair_created_at')},'market_age_days':None if age is None else round(age,2),'market_age_verified':bool(age is not None and age>=MIN_AGE_DAYS),'exact_pair_verified':True,'volume_change_since_previous_pct':None if vchg is None else round(vchg,2),'liquidity_change_since_previous_pct':None if lchg is None else round(lchg,2),'blockers':blockers,'revival_signal':revival,'status':'REVIVAL_WATCH_RESEARCH' if revival else ('VETERAN_FILTER_PASS' if not blockers else 'INELIGIBLE_FAIL_CLOSED'),**boundary}

def run(data_dir=DATA,now=None):
    data_dir=Path(data_dir); data_dir.mkdir(parents=True,exist_ok=True); now=now or datetime.now(timezone.utc)
    old=_load(data_dir/'arbitrum-revival-state.json',{}).get('tokens') or {}
    discovered,errors=discover(data_dir); out=[]
    for i,row in enumerate(discovered):
        s=snapshot(CHAIN,row['token']); out.append(classify(row,s,now,old.get(row['token'])))
        if i and i%20==0:time.sleep(.35)
    counts={'discovered':len(discovered),'exact_pair_verified':sum(x.get('exact_pair_verified') is True for x in out),'age_180d_plus':sum(x.get('market_age_verified') is True for x in out),'liquidity_50k_plus':sum(float(x.get('liquidity_usd') or 0)>=MIN_LIQUIDITY for x in out),'full_filter_pass':sum(not x.get('blockers') for x in out),'revival_watch':sum(x.get('revival_signal') is True for x in out)}
    payload={'version':1,'generated_at':now.isoformat(),'mode':MODE,'network':CHAIN,'production_portfolio_impact':'NONE','automatic_buy':False,'no_hindsight':True,'filter_contract':{'minimum_market_age_days':MIN_AGE_DAYS,'minimum_live_liquidity_usd':MIN_LIQUIDITY,'minimum_volume_h1_usd':MIN_VOLUME_H1,'minimum_txns_h1':MIN_TXNS_H1,'exact_pair_required':True,'stable_wrapped_excluded':True},'counts':counts,'tokens':out,'errors':errors}
    (data_dir/'arbitrum-revival-universe.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    state={'version':1,'updated_at':now.isoformat(),'tokens':{x['token']:{k:x.get(k) for k in ('pair_address','price_usd','liquidity_usd','volume_h1','volume_h24','status')} for x in out if x.get('token')}}
    (data_dir/'arbitrum-revival-state.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print('ARBITRUM_REVIVAL_UNIVERSE',counts,'errors',len(errors)); return payload

if __name__=='__main__':run()
