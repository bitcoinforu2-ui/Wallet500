from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from wallet500.entry_quality import evaluate_entry_quality

DATA=Path('data'); LEDGER=DATA/'external-only-paper-ledger.json'; SUMMARY=DATA/'external-only-paper-summary.json'; POS=1.0

def load(p,d):
    try:return json.loads(p.read_text()) if p.exists() and p.stat().st_size else d
    except:return d

def write(p,d): p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
def norm(chain,x): return str(x or '').lower() if str(chain).lower() in {'ethereum','eth','bsc','bnb'} else str(x or '')
def key(chain,token,pair): return f'{str(chain).lower()}:{norm(chain,token)}:{norm(chain,pair)}'

def run():
    t=datetime.now(timezone.utc); now=t.isoformat(); ext=load(DATA/'external-signal-cohort.json',{}); tracker=load(DATA/'outcome-tracker.json',{}); records=(tracker.get('tokens') or {}) if isinstance(tracker,dict) else {}
    state=load(LEDGER,{})
    if not state: state={'version':'EXTERNAL_ONLY_PAPER_V2','created_at':now,'position_size_usd':POS,'max_positions':None,'production_change':False,'entries':[]}
    else:
        state['version']='EXTERNAL_ONLY_PAPER_V2'; state['max_positions']=None
    entries=state.setdefault('entries',[]); existing={e.get('key') for e in entries if isinstance(e,dict)}
    sources={}
    for r in (ext.get('records') or {}).values():
        if not isinstance(r,dict):continue
        k=(str(r.get('chain') or '').lower(),norm(r.get('chain'),r.get('token')))
        sources.setdefault(k,[]).append(r)
    candidates=[]
    for r in records.values():
        if not isinstance(r,dict):continue
        chain=r.get('chain'); token=r.get('token'); pair=r.get('entry_pair_address'); sk=(str(chain or '').lower(),norm(chain,token))
        if sk not in sources or not pair:continue
        if r.get('measurement_status')!='VERIFIED_EXACT_PAIR' or norm(chain,r.get('current_pair_address'))!=norm(chain,pair):continue
        hist=r.get('history') if isinstance(r.get('history'),list) else []
        if not hist:continue
        h=hist[-1] if isinstance(hist[-1],dict) else {}
        try: price=float(r.get('current_price_usd') or 0); liq=float(h.get('liquidity_usd') or h.get('live_liquidity_usd') or 0); vol=float(h.get('volume_h1') or h.get('live_volume_h1') or 0); buys=int(h.get('buys_h1') or 0); sells=int(h.get('sells_h1') or 0)
        except:continue
        snap={'price_usd':price,'liquidity_usd':liq,'volume_h1':vol,'buys_h1':buys,'sells_h1':sells}
        if price<=0 or liq<50000 or vol<15000 or buys+sells<50:continue
        q=evaluate_entry_quality(r,snap)
        if not q.get('pass'):continue
        k=key(chain,token,pair)
        candidates.append((k,r,snap,q,sources[sk]))
    for k,r,s,q,srcs in candidates:
        if k in existing:continue
        px=s['price_usd']; names=sorted(set(x.get('source') for x in srcs if x.get('source')))
        entries.append({'key':k,'chain':r.get('chain'),'token':r.get('token'),'pair_address':r.get('entry_pair_address'),'entry_at':now,'entry_price_usd':px,'entry_liquidity_usd':s['liquidity_usd'],'entry_volume_h1':s['volume_h1'],'entry_txns_h1':s['buys_h1']+s['sells_h1'],'quantity':POS/px,'cost_usd':POS,'current_price_usd':px,'current_value_usd':POS,'return_pct':0.0,'status':'LIVE','external_sources':names,'source_consensus_count':len(names),'source_first_seen_at':min((x.get('first_seen_at') for x in srcs if x.get('first_seen_at')),default=None),'entry_quality_policy':'ANTI_CHASE_V1'})
        existing.add(k)
    current={key(r.get('chain'),r.get('token'),r.get('entry_pair_address')):r for r in records.values() if isinstance(r,dict) and r.get('entry_pair_address')}
    for e in entries:
        r=current.get(e['key']);
        if not r: e['status']='UNRESOLVED'; continue
        if r.get('measurement_status')!='VERIFIED_EXACT_PAIR' or norm(r.get('chain'),r.get('current_pair_address'))!=norm(r.get('chain'),e.get('pair_address')): e['status']='UNRESOLVED'; continue
        try:px=float(r.get('current_price_usd') or 0)
        except:px=0
        if px<=0: e['status']='FAILED_SURVIVAL'; e['current_price_usd']=0; e['current_value_usd']=0; e['return_pct']=-100; continue
        val=float(e['quantity'])*px; e['current_price_usd']=px; e['current_value_usd']=round(val,10); e['return_pct']=round((val/POS-1)*100,6); e['status']='LIVE'; e['last_mark_at']=now
    state['updated_at']=now; write(LEDGER,state)
    invested=sum(float(e.get('cost_usd') or 0) for e in entries); value=sum(float(e.get('current_value_usd') or 0) for e in entries); by={}
    for e in entries:
        for s in e.get('external_sources') or []: by[s]=by.get(s,0)+1
    summary={'updated_at':now,'method':'EXTERNAL_ONLY_6H_PAPER_V2_UNCAPPED','max_positions':None,'positions':len(entries),'paper_invested_usd':round(invested,6),'paper_current_value_usd':round(value,6),'paper_pnl_usd':round(value-invested,6),'paper_roi_pct':round(((value/invested)-1)*100,4) if invested else 0,'live':sum(e.get('status')=='LIVE' for e in entries),'failed':sum(e.get('status')=='FAILED_SURVIVAL' for e in entries),'unresolved':sum(e.get('status')=='UNRESOLVED' for e in entries),'source_attribution':by,'production_change':False,'truth_note':'Isolated uncapped external-source-only paper cohort. Does not alter native Wallet500 ledger or production gates.'}; write(SUMMARY,summary); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__':run()
