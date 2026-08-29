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

def _write(path,payload):path.write_text(json.dumps(payload,indent=2))
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

def _latest_exact_pair_mark(r,pair):
    if r.get('measurement_status')!='VERIFIED_EXACT_PAIR':return None
    cp=r.get('current_pair_address')
    if not cp or str(cp).lower()!=str(pair).lower():return None
    price=r.get('current_price_usd')
    try:
        if price is None or float(price)<=0:return None
    except:return None
    hist=r.get('history') if isinstance(r.get('history'),list) else []
    last=hist[-1] if hist else {}
    lp=last.get('pair_address')
    if lp and str(lp).lower()!=str(pair).lower():return None
    return {
        'price_usd':float(price),
        'liquidity_usd':float(last.get('liquidity_usd') or 0),
        'volume_h1':float(last.get('volume_h1') or 0),
        'buys_h1':int(last.get('buys_h1') or 0),
        'sells_h1':int(last.get('sells_h1') or 0),
        'dex':last.get('dex') or r.get('entry_dex'),
        'observed_at':last.get('observed_at') or r.get('updated_at')
    }

def _market_status(live):
    reasons=[]
    if not live:return 'UNAVAILABLE_NOW',['NO_CURRENT_EXACT_PAIR_MARK_IN_IMMUTABLE_TRACKER']
    price=float(live.get('price_usd') or 0);liq=float(live.get('liquidity_usd') or 0);vol=float(live.get('volume_h1') or 0);tx=int(live.get('buys_h1') or 0)+int(live.get('sells_h1') or 0)
    if price<=0:reasons.append('PRICE_ZERO')
    if liq<MIN_LIQ:reasons.append('LIQUIDITY_LT_50K')
    if vol<MIN_VOL_H1:reasons.append('VOLUME_H1_LT_15K')
    if tx<MIN_TXNS_H1:reasons.append('TXNS_H1_LT_50')
    return ('CURRENTLY_BLOCKED',reasons) if reasons else ('CURRENTLY_TRADABLE',[])

def run():
    ledger=_load(DATA/'outcome-tracker.json',{});records=ledger.get('tokens') if isinstance(ledger,dict) else {}
    if not isinstance(records,dict):records={}
    failed=_confirmed_failed();cohort=[];quote_eligible=[];unknown=[];now=datetime.now(timezone.utc).isoformat();dead=tradable=blocked=0;missing_entry=0
    for key,r in records.items():
        if not isinstance(r,dict):continue
        chain=r.get('chain');token=r.get('token');pair=r.get('entry_pair_address');entry=r.get('entry_price_usd')
        try:entry=float(entry or 0)
        except:entry=0
        if not chain or not token or not pair or entry<=0:
            missing_entry+=1;unknown.append({'key':key,'reason':'MISSING_IMMUTABLE_ENTRY_OR_PAIR'});continue
        terminal=_k(chain,token,pair) in failed
        live=_latest_exact_pair_mark(r,pair)
        if terminal:
            ret=-100.0;marked=0.0;dead+=1;status='CONFIRMED_DEAD_CURRENT_VALUE_ZERO';reasons=['CONFIRMED_TERMINAL_PAIR_EVIDENCE'];live_price=0.0
        elif live:
            status,reasons=_market_status(live);live_price=live['price_usd'];ret=_ret(live_price,entry);marked=max(0.0,POSITION_USD*(1+ret/100))
            if status=='CURRENTLY_TRADABLE':tradable+=1
            else:blocked+=1
        else:
            unknown.append({'key':key,'chain':chain,'token':token,'pair_address':pair,'reason':'NO_CURRENT_EXACT_PAIR_MARK_AND_NO_TERMINAL_PROOF'});continue
        row={'chain':chain,'token':token,'pair_address':pair,'dex':(live or {}).get('dex') or r.get('entry_dex'),'discovery_time':r.get('first_seen'),'entry_price_usd':entry,'current_price_usd':float(live_price or 0),'current_return_pct':round(ret,4),'peak_return_pct':r.get('peak_return_pct'),'liquidity_usd':float((live or {}).get('liquidity_usd') or 0),'volume_h1':float((live or {}).get('volume_h1') or 0),'txns_h1':int((live or {}).get('buys_h1') or 0)+int((live or {}).get('sells_h1') or 0),'position_usd':POSITION_USD,'marked_value_usd':round(marked,6),'current_status':status,'reasons':reasons,'checked_at':now,'source_observed_at':(live or {}).get('observed_at'),'proof_level':'IMMUTABLE_ENTRY_PLUS_TRACKER_EXACT_PAIR_CURRENT_MARK_OR_CONFIRMED_TERMINAL_ZERO'}
        cohort.append(row)
        if status=='CURRENTLY_TRADABLE':quote_eligible.append(row)
    n=len(cohort);invested=n*POSITION_USD;value=sum(x['marked_value_usd'] for x in cohort);pnl=value-invested;roi=((value/invested)-1)*100 if invested else 0;all_n=len(records)
    payload={'updated_at':now,'method':'PERFORMANCE_SINCE_DISCOVERY_V8_LINEAR_IMMUTABLE_TRACKER','position_size_usd':POSITION_USD,'all_discoveries_count':all_n,'immutable_entry_pair_records':all_n-missing_entry,'tracked_cohort_count':n,'unknown_not_scored_count':len(unknown),'dead_zero_value_count':dead,'currently_tradable_count':tradable,'currently_blocked_but_marked_count':blocked,'market_execution_plausible_count':len(quote_eligible),'not_realizable_now_count':dead+blocked,'survivorship_bias_policy':'SOURCE IS FULL IMMUTABLE OUTCOME LEDGER. CONFIRMED DEAD PAIRS REMAIN $0/-100%. ONLY THE EXACT-PAIR MARK ALREADY VERIFIED BY PERFORMANCE_TRACKER IS USED. MISSING CURRENT MARKS STAY UNKNOWN. NO PER-TOKEN NETWORK CALLS.','current_return_portfolio':{'count':n,'investment_usd':round(invested,6),'marked_value_usd':round(value,6),'pnl_usd':round(pnl,6),'roi_pct':round(roi,4),'status':'PERFORMANCE_SINCE_DISCOVERY_CURRENT_RETURN_NOT_EXECUTED_PNL'},'current_realizability_reference':{'count':n,'investment_usd':round(invested,6),'marked_value_usd':round(value,6),'pnl_usd':round(pnl,6),'roi_pct':round(roi,4),'status':'IMMUTABLE_LEDGER_SURVIVORSHIP_CORRECTED_CURRENT_RETURN'},'historical_backtest_verified':False,'historical_backtest_status':'NOT_BACKTEST_VERIFIED','tracked_discoveries':all_n,'eligible_now':n,'blocked_now':dead+blocked,'invested_usd':0.0,'current_value_usd':0.0,'roi_pct':0.0,'truth_note':'Linear accounting over the immutable tracker only. Every valid locked-pair record is either measured, confirmed dead at $0, or explicitly UNKNOWN. No transient API miss is converted to a loss.','important_limit':'Research hold-to-now reference, not proof of executable historical buys/sells.','unknown_rows':unknown,'rows':sorted(cohort,key=lambda x:x['current_return_pct'],reverse=True),'plausible_rows':sorted(quote_eligible,key=lambda x:x['current_return_pct'],reverse=True)}
    _write(DATA/'realizable-performance.json',payload);summary={k:v for k,v in payload.items() if k not in ('rows','plausible_rows','unknown_rows')};_write(DATA/'realizable-performance-summary.json',summary);print(json.dumps(summary,indent=2));return payload
if __name__=='__main__':run()
