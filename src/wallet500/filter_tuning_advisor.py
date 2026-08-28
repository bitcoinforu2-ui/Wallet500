"""Evidence-based tuning advisor for Wallet500 reject filters.

Research only. It NEVER changes production thresholds. Recommendations require
minimum sample sizes and are emitted as human-review candidates.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA=Path('data')
LEDGER=DATA/'rejected-candidate-ledger.json'
ATTR=DATA/'rejected-filter-attribution.json'
OUT=DATA/'filter-tuning-advisor.json'
MIN_SAMPLE=30
MIN_FALSE_NEGATIVES=3
HIGH_FN_RATE=10.0

def _load(p:Path,d:Any)->Any:
 try:return json.loads(p.read_text()) if p.exists() else d
 except Exception:return d

def advise(ledger:dict, attribution:dict)->dict:
 records=(ledger or {}).get('records') if isinstance((ledger or {}).get('records'),dict) else {}
 filters=(attribution or {}).get('filters') if isinstance((attribution or {}).get('filters'),dict) else {}
 proposals=[]
 for name,s in filters.items():
  if not isinstance(s,dict):continue
  n=int(s.get('records') or 0); fn=int(s.get('false_negative_winners') or 0); major=int(s.get('false_negative_major_winners') or 0); rate=float(s.get('false_negative_rate_pct') or 0)
  if n < MIN_SAMPLE:
   verdict='INSUFFICIENT_SAMPLE'
  elif fn < MIN_FALSE_NEGATIVES:
   verdict='KEEP_CURRENT_POLICY'
  elif rate >= HIGH_FN_RATE or major >= 2:
   verdict='REVIEW_THRESHOLD_CANDIDATE'
   proposals.append({'filter':name,'records':n,'false_negative_winners':fn,'major_false_negatives':major,'false_negative_rate_pct':rate,'action':'BACKTEST_ONLY','production_change_allowed':False})
  else:
   verdict='KEEP_CURRENT_POLICY'
  s['tuning_verdict']=verdict
 unresolved=sum(1 for r in records.values() if isinstance(r,dict) and r.get('classification')=='UNRESOLVED_REJECT')
 return {'mode':'RESEARCH_ADVISORY_ONLY','production_thresholds_modified':False,'minimum_sample_per_filter':MIN_SAMPLE,'minimum_false_negatives_for_review':MIN_FALSE_NEGATIVES,'filters':filters,'review_candidates':proposals,'ledger_records':len(records),'unresolved_records':unresolved}

def main()->None:
 now=datetime.now(timezone.utc).isoformat(); result=advise(_load(LEDGER,{}),_load(ATTR,{}));result['updated_at']=now;OUT.write_text(json.dumps(result,indent=2));print(json.dumps({'mode':result['mode'],'records':result['ledger_records'],'review_candidates':len(result['review_candidates'])},indent=2))

if __name__=='__main__':main()
