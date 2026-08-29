from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

DATA=Path('data')
SRC=DATA/'mature-pool-research.json'
OUT=DATA/'historical-price-replay-summary.json'

def main():
    src=json.loads(SRC.read_text()) if SRC.exists() else {}
    rows=src.get('rows') if isinstance(src.get('rows'),list) else []
    windows={}
    for d in ('7','30','90'):
        vals=[]
        for r in rows:
            w=(r.get('windows') or {}).get(d) or {}
            if w.get('status')=='PRICE_REPLAY_AVAILABLE' and w.get('return_pct') is not None:
                vals.append(float(w['return_pct']))
        invested=float(len(vals))
        value=sum(1.0*(1.0+v/100.0) for v in vals)
        roi=((value/invested)-1.0)*100.0 if invested else None
        windows[d]={
            'days':int(d),'pools':len(vals),'paper_dollars_at_1_per_pool':round(invested,6),
            'current_value_usd':round(value,6),'aggregate_roi_pct':round(roi,4) if roi is not None else None,
            'wins':sum(v>0 for v in vals),'losses':sum(v<0 for v in vals),'flat':sum(v==0 for v in vals),
            'best_return_pct':round(max(vals),4) if vals else None,'worst_return_pct':round(min(vals),4) if vals else None,
        }
    out={
        'version':1,'generated_at':datetime.now(timezone.utc).isoformat(),
        'mode':'HISTORICAL_PRICE_REPLAY_REFERENCE_ONLY',
        'source':'mature-pool-research.json','exact_pool_only':True,
        'production_portfolio_impact':'NONE','verified_wallet500_backtest':False,
        'survivorship_bias_warning':'CURRENT SURVIVING MATURE POOLS; NOT WALLET500 STRATEGY PERFORMANCE',
        'windows':windows,
    }
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False))
    print(json.dumps(out,indent=2))
if __name__=='__main__': main()
