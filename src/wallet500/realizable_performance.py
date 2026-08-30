from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

DATA=Path('data'); MIN_LIQ=50000.0; MIN_VOL_H1=15000.0; MIN_TXNS_H1=50; POSITION_USD=1.0

def _load(path,default):
    try:
        if not path.exists() or path.stat().st_size==0:return default
        return json.loads(path.read_text())
    except Exception:return default

def _write(path,payload):
    text=json.dumps(payload,indent=2)
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(text)
    json.loads(tmp.read_text())
    tmp.replace(path)

def _ret(cur,entry):
    try:
        cur=float(cur);entry=float(entry);return ((cur/entry)-1)*100 if cur>=0 and entry>0 else None
    except:return None

def _k(chain,token,pair):
    if chain in {'ethereum','bsc'}: token=str(token).lower();pair=str(pair).lower()
    return f'{chain}:{token}:{pair}'

def _confirmed_failed():
    out=set()
    for name in ('live-survival-failed.json','production-risk-blocked.json'):
        d=_load(DATA/name,[])
        if not isinstance(d,list):continue
        for x in d:
            if not isinstance(x,dict):continue
            c=x.get('chain');t=x.get('token') or x.get('mint');p=x.get('pair_address')
            liq=x.get('liquidity_usd');price=x.get('price_usd')
            try: terminal=(price is not None and float(price)<=0) or (liq is not None and float(liq)<1)
            except: terminal=False
            if c and t and p and terminal:out.add(_k(c,t,p))
    return out

def _snapshot(h):
    if not isinstance(h,dict):return None
    try:
        price=float(h.get('price_usd') or h.get('current_price_usd') or 0)
        liq=float(h.get('liquidity_usd') or h.get('live_liquidity_usd') or 0)
        vol=float(h.get('volume_h1') or h.get('live_volume_h1') or 0)
        buys=int(h.get('buys_h1') or 0); sells=int(h.get('sells_h1') or 0)
    except:return None
    return {'price_usd':price,'liquidity_usd':liq,'volume_h1':vol,'buys_h1':buys,'sells_h1':sells,'pair_address':h.get('pair_address'),'dex':h.get('dex'),'observed_at':h.get('observed_at') or h.get('timestamp') or h.get('checked_at')}

def _gate(s):
    if not s:return False
    return s['price_usd']>0 and s['liquidity_usd']>=MIN_LIQ and s['volume_h1']>=MIN_VOL_H1 and (s['buys_h1']+s['sells_h1'])>=MIN_TXNS_H1

def _first_eligible_mark(r,pair):
    hist=r.get('history') if isinstance(r.get('history'),list) else []
    for h in hist:
        s=_snapshot(h)
        if not s:continue
        hp=s.get('pair_address')
        if hp and str(hp).lower()!=str(pair).lower():continue
        if _gate(s):return s
    return None

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

def _market_status(live):
    reasons=[]
    if not live:return 'UNAVAILABLE_NOW',['NO_CURRENT_EXACT_PAIR_MARK_IN_IMMUTABLE_TRACKER']
    if live['price_usd']<=0:reasons.append('PRICE_ZERO')
    if live['liquidity_usd']<MIN_LIQ:reasons.append('LIQUIDITY_LT_50K')
    if live['volume_h1']<MIN_VOL_H1:reasons.append('VOLUME_H1_LT_15K')
    if live['buys_h1']+live['sells_h1']<MIN_TXNS_H1:reasons.append('TXNS_H1_LT_50')
    return ('CURRENTLY_BLOCKED',reasons) if reasons else ('CURRENTLY_TRADABLE',[])

def run():
    ledger=_load(DATA/'outcome-tracker.json',{}); records=ledger.get('tokens') if isinstance(ledger,dict) else {}
    if not isinstance(records,dict):records={}
    failed=_confirmed_failed(); research=[]; executed=[]; unknown=[]; now=datetime.now(timezone.utc).isoformat(); missing_entry=0
    for key,r in records.items():
        if not isinstance(r,dict):continue
        chain=r.get('chain'); token=r.get('token'); pair=r.get('entry_pair_address')
        discovery_entry=r.get('entry_price_usd')
        try: discovery_entry=float(discovery_entry or 0)
        except: discovery_entry=0
        if not chain or not token or not pair or discovery_entry<=0:
            missing_entry+=1; unknown.append({'key':key,'reason':'MISSING_IMMUTABLE_ENTRY_OR_PAIR'}); continue
        terminal=_k(chain,token,pair) in failed
        live=_latest_exact_pair_mark(r,pair)
        first=_first_eligible_mark(r,pair)
        if terminal:
            current_price=0.0; current_value_discovery=0.0; discovery_ret=-100.0; current_status='CONFIRMED_DEAD_CURRENT_VALUE_ZERO'; reasons=['CONFIRMED_TERMINAL_PAIR_EVIDENCE']
        elif live:
            current_price=live['price_usd']; discovery_ret=_ret(current_price,discovery_entry); current_value_discovery=max(0.0,1+discovery_ret/100); current_status,reasons=_market_status(live)
        else:
            unknown.append({'key':key,'chain':chain,'token':token,'pair_address':pair,'reason':'NO_CURRENT_EXACT_PAIR_MARK_AND_NO_TERMINAL_PROOF'}); continue
        research.append({'chain':chain,'token':token,'pair_address':pair,'entry_price_usd':discovery_entry,'current_price_usd':current_price,'current_return_pct':round(discovery_ret,4),'marked_value_usd':round(current_value_discovery,6),'current_status':current_status,'reasons':reasons})
        if not first:continue
        entry_price=first['price_usd']
        if terminal:
            ret=-100.0; marked=0.0
        else:
            ret=_ret(current_price,entry_price); marked=max(0.0,1+ret/100)
        executed.append({'chain':chain,'token':token,'pair_address':pair,'dex':first.get('dex') or (live or {}).get('dex') or r.get('entry_dex'),'entry_at':first.get('observed_at'),'entry_price_usd':entry_price,'entry_liquidity_usd':first['liquidity_usd'],'entry_volume_h1':first['volume_h1'],'entry_txns_h1':first['buys_h1']+first['sells_h1'],'current_price_usd':current_price,'current_return_pct':round(ret,4),'liquidity_usd':float((live or {}).get('liquidity_usd') or 0),'volume_h1':float((live or {}).get('volume_h1') or 0),'txns_h1':int((live or {}).get('buys_h1') or 0)+int((live or {}).get('sells_h1') or 0),'position_usd':1.0,'marked_value_usd':round(marked,6),'current_status':current_status,'reasons':reasons,'checked_at':now,'source_observed_at':(live or {}).get('observed_at'),'proof_level':'FIRST_RECORDED_EXACT_PAIR_SNAPSHOT_PASSING_LIQ_VOLUME_TX_GATE_TO_CURRENT_EXACT_PAIR_MARK'})
    n=len(research); invested=n*POSITION_USD; value=sum(x['marked_value_usd'] for x in research); pnl=value-invested; roi=((value/invested)-1)*100 if invested else 0
    en=len(executed); einv=en*POSITION_USD; eval_=sum(x['marked_value_usd'] for x in executed); epnl=eval_-einv; eroi=((eval_/einv)-1)*100 if einv else 0
    live_exec=[x for x in executed if x['current_status']=='CURRENTLY_TRADABLE']; blocked_exec=[x for x in executed if x['current_status']!='CURRENTLY_TRADABLE']
    all_n=len(records)
    payload={'updated_at':now,'method':'FIRST_ELIGIBLE_EXACT_PAIR_ENTRY_V1','position_size_usd':POSITION_USD,'all_discoveries_count':all_n,'all_discoveries_hypothetical_investment_usd':float(all_n),'immutable_entry_pair_records':all_n-missing_entry,'verified_rows_seen':n,'tracked_cohort_count':n,'unknown_not_scored_count':len(unknown),'market_execution_plausible_count':en,'not_realizable_now_count':len(blocked_exec),'eligible_investment_usd':round(einv,6),'eligible_current_value_usd':round(eval_,6),'eligible_profit_usd':round(epnl,6),'eligible_roi_pct':round(eroi,4),'entry_policy':'Paper entry occurs at the FIRST RECORDED exact-pair snapshot where liquidity >= $50K, H1 volume >= $15K, and H1 transactions >= 50. Current eligibility is NOT backdated to discovery.','current_return_portfolio':{'count':n,'investment_usd':round(invested,6),'marked_value_usd':round(value,6),'pnl_usd':round(pnl,6),'roi_pct':round(roi,4),'status':'DISCOVERY_TO_NOW_RESEARCH_REFERENCE_ONLY'},'paper_execution_portfolio':{'count':en,'investment_usd':round(einv,6),'marked_value_usd':round(eval_,6),'pnl_usd':round(epnl,6),'roi_pct':round(eroi,4),'status':'FIRST_ELIGIBLE_SNAPSHOT_PAPER_EXECUTION'},'historical_backtest_verified':False,'historical_backtest_status':'FORWARD_TRACKED_SNAPSHOT_SIMULATION_NOT_TICK_LEVEL_BACKTEST','truth_note':'ROI uses the first recorded snapshot that actually satisfied the entry gate, then marks the same locked pair to the latest verified exact-pair price. Missing marks remain UNKNOWN; confirmed dead pairs remain $0/-100%.','important_limit':'More realistic than discovery-to-now and current-eligibility backfill, but still paper execution from recorded snapshots; it does not prove fill price, slippage, gas, MEV or sell execution.','unknown_rows':unknown,'rows':sorted(research,key=lambda x:x['current_return_pct'],reverse=True),'plausible_rows':sorted(live_exec,key=lambda x:x['current_return_pct'],reverse=True),'blocked_rows':sorted(blocked_exec,key=lambda x:x['current_return_pct'],reverse=True),'executed_rows':sorted(executed,key=lambda x:x['current_return_pct'],reverse=True)}
    _write(DATA/'realizable-performance.json',payload); summary={k:v for k,v in payload.items() if k not in ('rows','plausible_rows','blocked_rows','executed_rows','unknown_rows')}; _write(DATA/'realizable-performance-summary.json',summary); print(json.dumps(summary,indent=2)); return payload

if __name__=='__main__':run()
