from __future__ import annotations
import json, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA=Path('data'); OUT=DATA/'external-signal-cohort.json'; SUMMARY=DATA/'external-signal-cohort-summary.json'
CHAINS={'solana':'solana','eth':'ethereum','ethereum':'ethereum','bsc':'bsc'}

def now(): return datetime.now(timezone.utc)
def load(p,d):
    try:return json.loads(p.read_text()) if p.exists() else d
    except:return d

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Wallet500/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)

def collect_gecko():
    out=[]
    for net,chain in [('solana','solana'),('eth','ethereum'),('bsc','bsc')]:
        try:
            d=get(f'https://api.geckoterminal.com/api/v2/networks/{net}/trending_pools?page=1')
            for rank,x in enumerate(d.get('data') or [],1):
                a=x.get('attributes') or {}; rel=x.get('relationships') or {}
                token=((rel.get('base_token') or {}).get('data') or {}).get('id','').split('_')[-1]
                out.append({'source':'GECKOTERMINAL_TRENDING','source_rank':rank,'chain':chain,'token':token,'pair_address':a.get('address'),'price_usd':a.get('base_token_price_usd'),'liquidity_usd':a.get('reserve_in_usd'),'volume_h1':((a.get('volume_usd') or {}).get('h1')),'txns_h1':sum(int(v or 0) for v in (((a.get('transactions') or {}).get('h1')) or {}).values())})
        except Exception: pass
    return out

def collect_dexscreener():
    out=[]
    for endpoint,src in [('token-boosts/top/v1','DEXSCREENER_BOOSTED'),('token-profiles/latest/v1','DEXSCREENER_PROFILES')]:
        try:
            d=get('https://api.dexscreener.com/'+endpoint)
            for rank,x in enumerate((d if isinstance(d,list) else []),1):
                chain=CHAINS.get(str(x.get('chainId') or '').lower())
                if chain: out.append({'source':src,'source_rank':rank,'chain':chain,'token':x.get('tokenAddress'),'pair_address':None})
        except Exception: pass
    return out

def run():
    t=now(); state=load(OUT,{})
    if not state:
        state={'method':'EXTERNAL_SIGNAL_COHORT_6H_V1','started_at':t.isoformat(),'ends_at':(t+timedelta(hours=6)).isoformat(),'production_change':False,'records':{}}
    records=state.setdefault('records',{})
    fresh=collect_gecko()+collect_dexscreener()
    for x in fresh:
        if not x.get('token'): continue
        key=f"{x['source']}|{x['chain']}|{str(x['token']).lower()}|{str(x.get('pair_address') or '').lower()}"
        r=records.get(key)
        if not r:
            r=dict(x); r['first_seen_at']=t.isoformat(); r['observations']=0; records[key]=r
        r['last_seen_at']=t.isoformat(); r['observations']=int(r.get('observations') or 0)+1
        for k,v in x.items():
            if v not in (None,''): r[k]=v
    by={}
    for r in records.values(): by[r['source']]=by.get(r['source'],0)+1
    state['last_ingest_at']=t.isoformat(); state['last_ingest_count']=len(fresh); state['source_counts']=by
    OUT.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
    summary={'updated_at':t.isoformat(),'method':state['method'],'started_at':state['started_at'],'ends_at':state['ends_at'],'elapsed_minutes':round((t-datetime.fromisoformat(state['started_at'])).total_seconds()/60,2),'total_unique_source_candidates':len(records),'source_counts':by,'last_ingest_count':len(fresh),'production_change':False,'rule':'External sources nominate candidates only; Wallet500 hard gates remain authoritative.'}
    SUMMARY.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n'); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__':run()
