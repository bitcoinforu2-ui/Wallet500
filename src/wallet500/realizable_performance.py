from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .market_data import snapshot

DATA=Path('data'); MIN_LIQ=50000.0; MIN_VOL_H1=15000.0; MIN_TXNS_H1=50; POSITION_USD=1.0

def _load(path,default):
    try:
        if not path.exists() or path.stat().st_size==0:return default
        return json.loads(path.read_text())
    except Exception:return default

def _write(path,payload):path.write_text(json.dumps(payload,indent=2))
def _live_return(cur,entry):
    try:
        cur=float(cur);entry=float(entry);return ((cur/entry)-1)*100 if cur>0 and entry>0 else None
    except:return None

def _status(live):
    reasons=[]
    if not live:return 'DEAD_OR_UNAVAILABLE',['LOCKED_PAIR_NOT_RETURNED']
    price=float(live.get('price_usd') or 0);liq=float(live.get('liquidity_usd') or 0);vol=float(live.get('volume_h1') or 0);tx=int(live.get('buys_h1') or 0)+int(live.get('sells_h1') or 0)
    if price<=0:reasons.append('PRICE_ZERO_OR_UNAVAILABLE')
    if liq<MIN_LIQ:reasons.append('LIQUIDITY_LT_50K')
    if vol<MIN_VOL_H1:reasons.append('VOLUME_H1_LT_15K')
    if tx<MIN_TXNS_H1:reasons.append('TXNS_H1_LT_50')
    return ('CURRENTLY_BLOCKED',reasons) if reasons else ('CURRENTLY_TRADABLE',[])

def run():
    src=_load(DATA/'performance-leaderboard.json',{});rows=src.get('rows') if isinstance(src,dict) else []
    if not isinstance(rows,list):rows=[]
    cohort=[];quote_eligible=[];now=datetime.now(timezone.utc).isoformat();dead=unknown=tradable=blocked=0
    for r in rows:
        if not isinstance(r,dict):continue
        chain=r.get('chain');token=r.get('token');pair=r.get('pair_address');entry=r.get('entry_price_usd')
        if not chain or not token or not pair or not entry:
            unknown+=1;continue
        live=snapshot(chain,token,pair);status,reasons=_status(live);live_price=(live or {}).get('price_usd');ret=_live_return(live_price,entry)
        if status=='DEAD_OR_UNAVAILABLE' or (live and float(live.get('price_usd') or 0)<=0):
            ret=-100.0;marked=0.0;dead+=1;status='DEAD_CURRENT_VALUE_ZERO'
        elif ret is None:
            unknown+=1;continue
        else:
            marked=max(0.0,POSITION_USD*(1+ret/100))
            if status=='CURRENTLY_TRADABLE':tradable+=1
            else:blocked+=1
        row={'chain':chain,'token':token,'pair_address':pair,'dex':(live or {}).get('dex') or r.get('dex'),'discovery_time':r.get('discovery_time'),'entry_price_usd':entry,'current_price_usd':live_price or 0,'current_return_pct':round(ret,4),'peak_return_pct':r.get('peak_return_pct'),'liquidity_usd':float((live or {}).get('liquidity_usd') or 0),'volume_h1':float((live or {}).get('volume_h1') or 0),'txns_h1':int((live or {}).get('buys_h1') or 0)+int((live or {}).get('sells_h1') or 0),'position_usd':POSITION_USD,'marked_value_usd':round(marked,6),'current_status':status,'reasons':reasons,'checked_at':now,'proof_level':'IMMUTABLE_ENTRY_TO_CURRENT_EXACT_PAIR_MARK_OR_ZERO_IF_DEAD'}
        cohort.append(row)
        if status=='CURRENTLY_TRADABLE':quote_eligible.append(row)
    n=len(cohort);invested=n*POSITION_USD;value=sum(x['marked_value_usd'] for x in cohort);pnl=value-invested;roi=((value/invested)-1)*100 if invested else 0
    all_n=int(src.get('all_discoveries_hypothetical_investment_usd') or 0)
    payload={'updated_at':now,'method':'PERFORMANCE_SINCE_DISCOVERY_CURRENT_RETURN_V6_SURVIVORSHIP_CORRECTED','position_size_usd':POSITION_USD,'all_discoveries_count':all_n,'verified_rows_seen':len(rows),'tracked_cohort_count':n,'unknown_not_scored_count':unknown,'dead_zero_value_count':dead,'currently_tradable_count':tradable,'currently_blocked_but_marked_count':blocked,'market_execution_plausible_count':len(quote_eligible),'not_realizable_now_count':dead+blocked,'survivorship_bias_policy':'VALID IMMUTABLE ENTRY NEVER DISAPPEARS; DEAD/UNAVAILABLE LOCKED PAIR = CURRENT VALUE $0; UNKNOWN ENTRY EVIDENCE IS EXCLUDED AND DISCLOSED','current_return_portfolio':{'count':n,'investment_usd':round(invested,6),'marked_value_usd':round(value,6),'pnl_usd':round(pnl,6),'roi_pct':round(roi,4),'status':'PERFORMANCE_SINCE_DISCOVERY_CURRENT_RETURN_NOT_EXECUTED_PNL'},'current_realizability_reference':{'count':n,'investment_usd':round(invested,6),'marked_value_usd':round(value,6),'pnl_usd':round(pnl,6),'roi_pct':round(roi,4),'status':'SURVIVORSHIP_CORRECTED_CURRENT_RETURN_REFERENCE'},'historical_backtest_verified':False,'historical_backtest_status':'NOT_BACKTEST_VERIFIED','tracked_discoveries':all_n,'eligible_now':n,'blocked_now':dead+blocked,'invested_usd':0.0,'current_value_usd':0.0,'roi_pct':0.0,'truth_note':'Current-return cohort includes every leaderboard row with valid immutable entry evidence. Dead/unavailable locked pairs stay at $0 (-100%). Low-liquidity survivors stay marked to current exact-pair price. Unknown entry evidence is excluded and disclosed.','important_limit':'Research hold-to-now reference, not proof of executable historical buys/sells.','rows':sorted(cohort,key=lambda x:x['current_return_pct'],reverse=True),'plausible_rows':sorted(quote_eligible,key=lambda x:x['current_return_pct'],reverse=True)}
    _write(DATA/'realizable-performance.json',payload)
    summary={k:v for k,v in payload.items() if k not in ('rows','plausible_rows')};_write(DATA/'realizable-performance-summary.json',summary)
    print(json.dumps(summary,indent=2));return payload
if __name__=='__main__':run()
