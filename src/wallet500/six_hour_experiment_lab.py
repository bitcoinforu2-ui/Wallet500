from __future__ import annotations
import json, statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA=Path('data'); LEDGER=DATA/'six-hour-experiment-ledger.json'; SUMMARY=DATA/'six-hour-experiment-summary.json'; POS=1.0; CAP_PER_ARM=20
ARMS={
 'QUIET_ACCUMULATION':'liq>=250K, buy_share>=55%, turnover 0.05-0.50, runup<=10%, >=2 exact-pair marks',
 'LIQUIDITY_ACCELERATION':'liquidity retention>=105%, buy_share>=52%, turnover<=1.5, runup<=25%, >=2 marks',
 'HEALTHY_RECOVERY':'runup -35%..0%, liquidity retention>=95%, buy_share>=55%, turnover<=1.2, >=2 marks',
 'SOURCE_CONSENSUS':'external source consensus>=2 plus Wallet500 hard gate and anti-chase<=25%'
}

def load(p,d):
    try:return json.loads(p.read_text()) if p.exists() and p.stat().st_size else d
    except:return d

def write(p,d): p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
def norm(chain,x): return str(x or '').lower() if str(chain).lower() in {'ethereum','eth','bsc','bnb'} else str(x or '')
def key(chain,token,pair): return f'{str(chain).lower()}:{norm(chain,token)}:{norm(chain,pair)}'

def mark(r):
    pair=r.get('entry_pair_address'); cp=r.get('current_pair_address')
    if r.get('measurement_status')!='VERIFIED_EXACT_PAIR' or not pair or norm(r.get('chain'),cp)!=norm(r.get('chain'),pair):return None
    hist=r.get('history') if isinstance(r.get('history'),list) else []
    if not hist:return None
    h=hist[-1] if isinstance(hist[-1],dict) else {}
    try:
        price=float(r.get('current_price_usd') or 0); liq=float(h.get('liquidity_usd') or h.get('live_liquidity_usd') or 0); vol=float(h.get('volume_h1') or h.get('live_volume_h1') or 0); buys=int(h.get('buys_h1') or 0); sells=int(h.get('sells_h1') or 0)
    except:return None
    if price<=0:return None
    recent=[]
    for x in hist[-4:]:
        if not isinstance(x,dict):continue
        xp=x.get('pair_address')
        if xp and norm(r.get('chain'),xp)!=norm(r.get('chain'),pair):continue
        try: recent.append(float(x.get('liquidity_usd') or x.get('live_liquidity_usd') or 0))
        except:pass
    prior=recent[:-1]; retention=(liq/statistics.median(prior)) if prior and statistics.median(prior)>0 else (1.0 if len(recent)>=2 else None)
    tx=buys+sells; buy_share=buys/tx if tx else 0; turnover=vol/liq if liq>0 else 999
    try: entry=float(r.get('entry_price_usd') or 0); runup=((price/entry)-1)*100 if entry>0 else None
    except: runup=None
    return {'price':price,'liq':liq,'vol':vol,'tx':tx,'buys':buys,'sells':sells,'buy_share':buy_share,'turnover':turnover,'retention':retention,'runup':runup,'marks':len(recent)}

def hard(m): return m and m['liq']>=50000 and m['vol']>=15000 and m['tx']>=50 and m['runup'] is not None and m['runup']<=25

def arm_hits(m,consensus):
    if not hard(m): return []
    hits=[]
    if m['marks']>=2 and m['liq']>=250000 and m['buy_share']>=.55 and .05<=m['turnover']<=.50 and m['runup']<=10:hits.append('QUIET_ACCUMULATION')
    if m['marks']>=2 and m['retention'] is not None and m['retention']>=1.05 and m['buy_share']>=.52 and m['turnover']<=1.5:hits.append('LIQUIDITY_ACCELERATION')
    if m['marks']>=2 and -35<=m['runup']<=0 and m['retention'] is not None and m['retention']>=.95 and m['buy_share']>=.55 and m['turnover']<=1.2:hits.append('HEALTHY_RECOVERY')
    if consensus>=2:hits.append('SOURCE_CONSENSUS')
    return hits

def run():
    t=datetime.now(timezone.utc); now=t.isoformat(); tracker=load(DATA/'outcome-tracker.json',{}); records=(tracker.get('tokens') or {}) if isinstance(tracker,dict) else {}; ext=load(DATA/'external-signal-cohort.json',{})
    source_map={}
    for x in (ext.get('records') or {}).values():
        if not isinstance(x,dict):continue
        sk=(str(x.get('chain') or '').lower(),norm(x.get('chain'),x.get('token'))); source_map.setdefault(sk,set()).add(x.get('source'))
    state=load(LEDGER,{})
    if not state: state={'version':'SIX_HOUR_PARALLEL_SHADOW_V1','started_at':now,'ends_at':(t+timedelta(hours=6)).isoformat(),'production_change':False,'arms':{a:[] for a in ARMS}}
    arms=state.setdefault('arms',{a:[] for a in ARMS})
    for a in ARMS: arms.setdefault(a,[])
    current={}
    for r in records.values():
        if not isinstance(r,dict) or not r.get('entry_pair_address'):continue
        m=mark(r)
        if not m:continue
        k=key(r.get('chain'),r.get('token'),r.get('entry_pair_address')); current[k]=(r,m)
        consensus=len([s for s in source_map.get((str(r.get('chain') or '').lower(),norm(r.get('chain'),r.get('token'))),set()) if s])
        for a in arm_hits(m,consensus):
            if len(arms[a])>=CAP_PER_ARM or any(e.get('key')==k for e in arms[a]):continue
            arms[a].append({'key':k,'chain':r.get('chain'),'token':r.get('token'),'pair_address':r.get('entry_pair_address'),'entry_at':now,'entry_price_usd':m['price'],'quantity':POS/m['price'],'cost_usd':POS,'entry_metrics':m,'source_consensus_count':consensus,'current_value_usd':POS,'return_pct':0.0,'status':'LIVE'})
    stats={}
    for a,entries in arms.items():
        for e in entries:
            cur=current.get(e.get('key'))
            if not cur: e['status']='UNRESOLVED'; continue
            _,m=cur; val=float(e['quantity'])*m['price']; e['current_value_usd']=round(val,10); e['return_pct']=round((val/POS-1)*100,6); e['status']='LIVE' if hard(m) else 'FAILED_GATE'; e['last_mark_at']=now
        inv=sum(float(e.get('cost_usd') or 0) for e in entries); val=sum(float(e.get('current_value_usd') or 0) for e in entries); rets=[float(e.get('return_pct') or 0) for e in entries]
        stats[a]={'rule':ARMS[a],'n':len(entries),'invested_usd':round(inv,4),'value_usd':round(val,4),'pnl_usd':round(val-inv,4),'roi_pct':round(((val/inv)-1)*100,4) if inv else 0,'positive_pct':round(100*sum(x>0 for x in rets)/len(rets),2) if rets else 0,'failed_gate':sum(e.get('status')=='FAILED_GATE' for e in entries),'unresolved':sum(e.get('status')=='UNRESOLVED' for e in entries)}
    state['updated_at']=now; write(LEDGER,state)
    summary={'updated_at':now,'method':'SIX_HOUR_PARALLEL_SHADOW_V1','started_at':state['started_at'],'ends_at':state['ends_at'],'production_change':False,'cap_per_arm':CAP_PER_ARM,'arms':stats,'truth_note':'Research-only parallel paper arms. Same candidate may appear in multiple arms; no production gate or native ledger is changed.'}; write(SUMMARY,summary); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__':run()
