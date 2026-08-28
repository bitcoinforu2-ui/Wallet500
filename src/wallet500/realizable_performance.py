from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .market_data import snapshot

DATA=Path('data')
MIN_LIQ=50000.0
MIN_VOL_H1=15000.0
MIN_TXNS_H1=50
POSITION_USD=1.0


def _load(path, default):
    try:
        if not path.exists() or path.stat().st_size==0: return default
        return json.loads(path.read_text())
    except Exception:
        return default


def _write(path,payload):
    path.write_text(json.dumps(payload,indent=2))


def _status(live):
    reasons=[]
    if not live: return 'NOT_REALIZABLE_NOW',['LOCKED_PAIR_NOT_RETURNED']
    price=float(live.get('price_usd') or 0); liq=float(live.get('liquidity_usd') or 0)
    vol=float(live.get('volume_h1') or 0); tx=int(live.get('buys_h1') or 0)+int(live.get('sells_h1') or 0)
    if price<=0: reasons.append('PRICE_ZERO_OR_UNAVAILABLE')
    if liq<MIN_LIQ: reasons.append('LIQUIDITY_LT_50K')
    if vol<MIN_VOL_H1: reasons.append('VOLUME_H1_LT_15K')
    if tx<MIN_TXNS_H1: reasons.append('TXNS_H1_LT_50')
    if liq>0 and POSITION_USD/liq>0.0001: reasons.append('POSITION_TOO_LARGE_FOR_VISIBLE_LIQUIDITY')
    return ('NOT_REALIZABLE_NOW',reasons) if reasons else ('MARKET_EXECUTION_PLAUSIBLE',[])


def run():
    src=_load(DATA/'performance-leaderboard.json',{})
    rows=src.get('rows') if isinstance(src,dict) else []
    if not isinstance(rows,list): rows=[]
    plausible=[]; blocked=[]; now=datetime.now(timezone.utc).isoformat()
    for r in rows:
        if not isinstance(r,dict): continue
        chain=r.get('chain'); token=r.get('token'); pair=r.get('pair_address')
        live=snapshot(chain,token,pair) if chain and token and pair else None
        status,reasons=_status(live)
        ret=float(r.get('current_return_pct') or 0)
        marked=max(0.0,POSITION_USD*(1.0+ret/100.0))
        row={'chain':chain,'token':token,'pair_address':pair,'dex':(live or {}).get('dex') or r.get('dex'),'discovery_time':r.get('discovery_time'),'entry_price_usd':r.get('entry_price_usd'),'current_price_usd':(live or {}).get('price_usd') or r.get('current_price_usd'),'current_return_pct':ret,'peak_return_pct':r.get('peak_return_pct'),'liquidity_usd':float((live or {}).get('liquidity_usd') or 0),'volume_h1':float((live or {}).get('volume_h1') or 0),'txns_h1':int((live or {}).get('buys_h1') or 0)+int((live or {}).get('sells_h1') or 0),'position_usd':POSITION_USD,'marked_value_usd':round(marked,6),'execution_status':status,'block_reasons':reasons,'checked_at':now,'proof_level':'MARKET_DATA_PROXY_ONLY_NOT_ROUTER_QUOTE'}
        (plausible if status=='MARKET_EXECUTION_PLAUSIBLE' else blocked).append(row)
    all_discoveries=int(src.get('all_discoveries_hypothetical_investment_usd') or 0)
    verified_n=len(rows); eligible_n=len(plausible)
    eligible_invested=eligible_n*POSITION_USD
    eligible_value=sum(x['marked_value_usd'] for x in plausible)
    eligible_profit=eligible_value-eligible_invested
    eligible_roi=((eligible_value/eligible_invested)-1)*100 if eligible_invested else 0.0
    paper_invested=verified_n*POSITION_USD
    paper_value=sum(x['marked_value_usd'] for x in plausible+blocked)
    payload={'updated_at':now,'method':'REALIZABLE_PERFORMANCE_GATE_V2_TRUTHFUL_COHORT_ACCOUNTING','position_size_usd':POSITION_USD,
      'all_discoveries_count':all_discoveries,'all_discoveries_hypothetical_investment_usd':round(all_discoveries*POSITION_USD,6),
      'verified_rows_seen':verified_n,'paper_verified_investment_usd':round(paper_invested,6),'paper_verified_value_usd':round(paper_value,6),
      'market_execution_plausible_count':eligible_n,'not_realizable_now_count':len(blocked),
      'eligible_investment_usd':round(eligible_invested,6),'eligible_current_value_usd':round(eligible_value,6),'eligible_profit_usd':round(eligible_profit,6),'eligible_roi_pct':round(eligible_roi,4),
      'truth_note':'ELIGIBLE ROI denominator is only $1 positions that currently pass market-quality execution checks. Blocked rows are excluded, never treated as a $0 sale. This is still not cash-execution proof.',
      'important_limit':'NOT CASH-EXECUTION VERIFIED: no router quote / honeypot / tax / transfer-restriction proof yet',
      'rules':{'min_liquidity_usd':MIN_LIQ,'min_volume_h1_usd':MIN_VOL_H1,'min_txns_h1':MIN_TXNS_H1,'max_position_fraction_of_liquidity':0.0001},
      'plausible_rows':sorted(plausible,key=lambda x:x['current_return_pct'],reverse=True),'blocked_rows':sorted(blocked,key=lambda x:x['current_return_pct'],reverse=True)}
    _write(DATA/'realizable-performance.json',payload)
    keys=('updated_at','position_size_usd','all_discoveries_count','all_discoveries_hypothetical_investment_usd','verified_rows_seen','paper_verified_investment_usd','paper_verified_value_usd','market_execution_plausible_count','not_realizable_now_count','eligible_investment_usd','eligible_current_value_usd','eligible_profit_usd','eligible_roi_pct','truth_note','important_limit')
    _write(DATA/'realizable-performance-summary.json',{k:payload[k] for k in keys})
    print(json.dumps(_load(DATA/'realizable-performance-summary.json',{}),indent=2)); return payload

if __name__=='__main__': run()
