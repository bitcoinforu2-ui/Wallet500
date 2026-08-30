from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500.entry_quality import evaluate_entry_quality

DATA=Path('data'); MIN_LIQ=50000.0; MIN_VOL_H1=15000.0; MIN_TXNS_H1=50; POSITION_USD=1.0
PAPER_LEDGER=DATA/'first-eligible-paper-ledger.json'

def _load(path,default):
    try:
        if not path.exists() or path.stat().st_size==0:return default
        return json.loads(path.read_text())
    except Exception:return default

def _write(path,payload):
    text=json.dumps(payload,indent=2)
    tmp=path.with_name(path.name+'.tmp'); tmp.write_text(text); json.loads(tmp.read_text()); tmp.replace(path)

def _live_return(current_price,entry_price):
    try:
        current=float(current_price); entry=float(entry_price)
    except (TypeError,ValueError):
        return None
    if entry<=0:return None
    return ((current/entry)-1.0)*100.0

def _k(chain,token,pair):
    chain=str(chain or '').lower(); token=str(token or ''); pair=str(pair or '')
    if chain in {'ethereum','eth','bsc','bnb'}: token=token.lower(); pair=pair.lower()
    return f'{chain}:{token}:{pair}'

def _snapshot(h):
    if not isinstance(h,dict):return None
    try:
        price=float(h.get('price_usd') or h.get('current_price_usd') or 0)
        liq=float(h.get('liquidity_usd') or h.get('live_liquidity_usd') or 0)
        vol=float(h.get('volume_h1') or h.get('live_volume_h1') or 0)
        buys=int(h.get('buys_h1') or 0); sells=int(h.get('sells_h1') or 0)
    except:return None
    return {'price_usd':price,'liquidity_usd':liq,'volume_h1':vol,'buys_h1':buys,'sells_h1':sells,'pair_address':h.get('pair_address'),'dex':h.get('dex'),'observed_at':h.get('observed_at') or h.get('timestamp') or h.get('checked_at')}

def _latest_exact_pair_mark(r,pair):
    if r.get('measurement_status')!='VERIFIED_EXACT_PAIR':return None
    cp=r.get('current_pair_address')
    if not cp or str(cp).lower()!=str(pair).lower():return None
    try: price=float(r.get('current_price_usd') or 0)
    except:return None
    if price<=0:return None
    hist=r.get('history') if isinstance(r.get('history'),list) else []
    last=_snapshot(hist[-1]) if hist else None
    if not last:return None
    lp=last.get('pair_address')
    if lp and str(lp).lower()!=str(pair).lower():return None
    last['price_usd']=price
    return last

def _gate(s):
    return bool(s) and s['price_usd']>0 and s['liquidity_usd']>=MIN_LIQ and s['volume_h1']>=MIN_VOL_H1 and (s['buys_h1']+s['sells_h1'])>=MIN_TXNS_H1

def _confirmed_failed():
    out=set()
    for name in ('live-survival-failed.json','production-risk-blocked.json'):
        d=_load(DATA/name,[])
        if not isinstance(d,list):continue
        for x in d:
            if not isinstance(x,dict):continue
            c=x.get('chain');t=x.get('token') or x.get('mint');p=x.get('pair_address')
            try: terminal=(x.get('price_usd') is not None and float(x.get('price_usd'))<=0) or (x.get('liquidity_usd') is not None and float(x.get('liquidity_usd'))<1)
            except: terminal=False
            if c and t and p and terminal:out.add(_k(c,t,p))
    return out

def run():
    tracker=_load(DATA/'outcome-tracker.json',{}); records=tracker.get('tokens') if isinstance(tracker,dict) else {}
    if not isinstance(records,dict):records={}
    now=datetime.now(timezone.utc).isoformat(); failed=_confirmed_failed(); current={}; unknown=[]; valid_records=0
    for raw_key,r in records.items():
        if not isinstance(r,dict):continue
        chain=r.get('chain'); token=r.get('token'); pair=r.get('entry_pair_address')
        try: discovery=float(r.get('entry_price_usd') or 0)
        except: discovery=0
        if not chain or not token or not pair or discovery<=0:
            unknown.append({'key':raw_key,'reason':'MISSING_IMMUTABLE_ENTRY_OR_PAIR'}); continue
        valid_records+=1; k=_k(chain,token,pair); live=_latest_exact_pair_mark(r,pair); current[k]=(r,live)
        if live is None and k not in failed: unknown.append({'key':k,'reason':'NO_CURRENT_EXACT_PAIR_MARK_AND_NO_TERMINAL_PROOF'})

    ledger=_load(PAPER_LEDGER,{})
    if not isinstance(ledger,dict) or ledger.get('version')!='FIRST_ELIGIBLE_FORWARD_V1':
        ledger={'version':'FIRST_ELIGIBLE_FORWARD_V1','created_at':now,'policy_activated_at':now,'position_size_usd':POSITION_USD,'entries':[]}
    entries=ledger.get('entries') if isinstance(ledger.get('entries'),list) else []; ledger['entries']=entries
    existing={str(x.get('key')) for x in entries if isinstance(x,dict)}
    quality_delayed=[]

    # PROSPECTIVE ONLY. Existing entries remain immutable. A newly base-eligible
    # candidate must also pass the Anti-Chase quality layer before a $1 entry.
    for k,(r,live) in current.items():
        if k in existing or not _gate(live):continue
        quality=evaluate_entry_quality(r,live)
        if not quality.get('pass'):
            quality_delayed.append({'key':k,'chain':r.get('chain'),'token':r.get('token'),'pair_address':r.get('entry_pair_address'),'price_usd':live.get('price_usd'),'liquidity_usd':live.get('liquidity_usd'),'volume_h1':live.get('volume_h1'),'txns_h1':int(live.get('buys_h1') or 0)+int(live.get('sells_h1') or 0),**quality})
            continue
        chain=r.get('chain'); token=r.get('token'); pair=r.get('entry_pair_address'); px=float(live['price_usd'])
        entries.append({'key':k,'chain':chain,'token':token,'pair_address':pair,'dex':live.get('dex') or r.get('entry_dex'),'entry_at':now,'source_observed_at_entry':live.get('observed_at'),'entry_price_usd':px,'entry_liquidity_usd':float(live['liquidity_usd']),'entry_volume_h1':float(live['volume_h1']),'entry_txns_h1':int(live['buys_h1']+live['sells_h1']),'entry_pre_runup_pct':quality.get('pre_entry_runup_pct'),'entry_turnover_h1':quality.get('turnover_h1'),'entry_quality_policy':'ANTI_CHASE_V1','quantity':POSITION_USD/px,'cost_usd':POSITION_USD,'current_price_usd':px,'current_liquidity_usd':float(live['liquidity_usd']),'current_value_usd':POSITION_USD,'return_pct':0.0,'status':'LIVE','valuation_status':'FRESH_EXACT_PAIR','last_mark_at':now})
        existing.add(k)

    for p in entries:
        if not isinstance(p,dict):continue
        k=str(p.get('key') or ''); cur=current.get(k); live=cur[1] if cur else None
        if k in failed:
            p['current_price_usd']=0.0; p['current_liquidity_usd']=0.0; p['current_value_usd']=0.0; p['return_pct']=-100.0; p['status']='FAILED_SURVIVAL'; p['valuation_status']='CONFIRMED_TERMINAL_ZERO'; p['last_mark_at']=now
            if not p.get('failed_at'):p['failed_at']=now
            continue
        if not live:
            p['valuation_status']='STALE_LAST_MARK_NO_CURRENT_PROOF'; p['status']='UNRESOLVED'; continue
        try: qty=float(p.get('quantity') or 0); cost=float(p.get('cost_usd') or POSITION_USD); px=float(live['price_usd'])
        except: continue
        value=max(0.0,qty*px); p['current_price_usd']=px; p['current_liquidity_usd']=float(live['liquidity_usd']); p['current_value_usd']=round(value,10); p['return_pct']=round(((value/cost)-1)*100,6) if cost>0 else None; p['last_mark_at']=now; p['valuation_status']='FRESH_EXACT_PAIR'
        if _gate(live): p['status']='LIVE'
        else:
            p['status']='FAILED_SURVIVAL'
            if not p.get('failed_at'):p['failed_at']=now

    ledger['updated_at']=now; ledger['new_entry_quality_policy']='ANTI_CHASE_V1'; _write(PAPER_LEDGER,ledger)
    paper=[p for p in entries if isinstance(p,dict)]; fresh=[p for p in paper if p.get('valuation_status') in {'FRESH_EXACT_PAIR','CONFIRMED_TERMINAL_ZERO'}]; unresolved=[p for p in paper if p.get('valuation_status')=='STALE_LAST_MARK_NO_CURRENT_PROOF']; live_rows=[p for p in paper if p.get('status')=='LIVE']; failed_rows=[p for p in paper if p.get('status')=='FAILED_SURVIVAL']
    invested=sum(float(p.get('cost_usd') or 0) for p in paper); marked=sum(float(p.get('current_value_usd') or 0) for p in paper); pnl=marked-invested; roi=((marked/invested)-1)*100 if invested else 0.0
    all_n=len(records)
    payload={'updated_at':now,'method':'FIRST_ELIGIBLE_FORWARD_PERSISTENT_LEDGER_V1','position_size_usd':POSITION_USD,'all_discoveries_count':all_n,'all_discoveries_hypothetical_investment_usd':float(all_n)*POSITION_USD,'immutable_entry_pair_records':valid_records,'verified_rows_seen':sum(1 for _,live in current.values() if live is not None),'tracked_cohort_count':sum(1 for _,live in current.values() if live is not None),'unknown_not_scored_count':len(unknown),'paper_entries_count':len(paper),'paper_invested_usd':round(invested,6),'paper_current_value_usd':round(marked,6),'paper_profit_usd':round(pnl,6),'paper_roi_pct':round(roi,4),'paper_live_count':len(live_rows),'failed_after_entry_count':len(failed_rows),'paper_unresolved_count':len(unresolved),'market_execution_plausible_count':len(live_rows),'not_realizable_now_count':len(failed_rows)+len(unresolved),'quality_delayed_now_count':len(quality_delayed),'eligible_investment_usd':round(invested,6),'eligible_current_value_usd':round(marked,6),'eligible_profit_usd':round(pnl,6),'eligible_roi_pct':round(roi,4),'entry_policy':'PROSPECTIVE ONLY. Base gate remains VERIFIED EXACT PAIR + liquidity >= $50K + H1 volume >= $15K + H1 transactions >= 50. New entries additionally use ANTI_CHASE_V1: delay if same-pair run-up since discovery >25%; delay if liquidity < $100K with H1 turnover >2x; quarantine extreme discovery/entry ratios. Existing entries are never rewritten.','paper_execution_portfolio':{'count':len(paper),'investment_usd':round(invested,6),'marked_value_usd':round(marked,6),'pnl_usd':round(pnl,6),'roi_pct':round(roi,4),'fresh_marks':len(fresh),'unresolved_marks':len(unresolved),'status':'FORWARD_FIRST_ELIGIBLE_PAPER_EXECUTION'},'historical_backtest_verified':False,'historical_backtest_status':'FORWARD_SNAPSHOT_SIMULATION_NOT_TICK_LEVEL_EXECUTION','truth_note':'Persistent forward ledger. Entry price/time never change after creation. Same exact pair is marked on later runs; confirmed terminal pairs are $0/-100%; missing current proof stays unresolved and retains its last known mark instead of being fabricated as a loss.','important_limit':'Paper execution only; fill price, slippage, gas, MEV and sell execution are not proven.','paper_live_rows':sorted(live_rows,key=lambda x:float(x.get('return_pct') or 0),reverse=True),'paper_failed_rows':sorted(failed_rows,key=lambda x:float(x.get('return_pct') or 0),reverse=True),'paper_unresolved_rows':unresolved,'quality_delayed_rows':quality_delayed,'plausible_rows':sorted(live_rows,key=lambda x:float(x.get('return_pct') or 0),reverse=True),'blocked_rows':sorted(failed_rows,key=lambda x:float(x.get('return_pct') or 0),reverse=True),'unknown_rows':unknown}
    _write(DATA/'realizable-performance.json',payload); summary={k:v for k,v in payload.items() if k not in ('paper_live_rows','paper_failed_rows','paper_unresolved_rows','quality_delayed_rows','plausible_rows','blocked_rows','unknown_rows')}; _write(DATA/'realizable-performance-summary.json',summary); print(json.dumps(summary,indent=2)); return payload

if __name__=='__main__':run()
