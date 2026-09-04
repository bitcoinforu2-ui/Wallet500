from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path('data')
OUT = DATA / 'predictive-validation.json'
MIN_N = 30
PROMOTION_N = 100


def load(name, default=None):
    p = DATA / name
    if not p.exists() or not p.stat().st_size:
        return {} if default is None else default
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None


def metrics(rows):
    roi=[f(r.get('return_pct')) for r in rows]
    roi=[x for x in roi if x is not None]
    verified=sum(r.get('verified_tradable') is True for r in rows)
    failed=sum(r.get('failed_survival') is True for r in rows)
    return {'n':len(rows),'median_roi_pct':round(median(roi),4) if roi else None,
            'verified_tradable_pct':round(100*verified/len(rows),2) if rows else None,
            'failed_survival_pct':round(100*failed/len(rows),2) if rows else None}


def edge(candidate, baseline):
    c,b=metrics(candidate),metrics(baseline)
    roi_edge=(c['median_roi_pct']-b['median_roi_pct']) if c['median_roi_pct'] is not None and b['median_roi_pct'] is not None else None
    trad_edge=(c['verified_tradable_pct']-b['verified_tradable_pct']) if c['verified_tradable_pct'] is not None and b['verified_tradable_pct'] is not None else None
    fail_edge=(b['failed_survival_pct']-c['failed_survival_pct']) if c['failed_survival_pct'] is not None and b['failed_survival_pct'] is not None else None
    repeated_positive=all(x is not None and x>0 for x in (roi_edge,trad_edge,fail_edge))
    status='COLLECTING'
    if c['n']>=MIN_N and b['n']>=MIN_N: status='ANALYZABLE'
    if c['n']>=PROMOTION_N and b['n']>=PROMOTION_N and repeated_positive: status='EDGE_CANDIDATE'
    return {'candidate':c,'baseline':b,'median_roi_edge_pp':roi_edge,'verified_tradable_edge_pp':trad_edge,
            'failed_survival_improvement_pp':fail_edge,'status':status,
            'production_eligible':status=='EDGE_CANDIDATE'}


def main():
    ledger=load('experiment-v1-ledger.json',{'records':[]})
    rows=ledger.get('records') or []
    # Prospective-only comparison: survivor-first decisions versus the same ledger's non-passing observations.
    candidate=[r for r in rows if r.get('survivor_first_pass') is True]
    baseline=[r for r in rows if r.get('survivor_first_pass') is not True]
    result=edge(candidate,baseline)
    out={'generated_at':datetime.now(timezone.utc).isoformat(),'method':'PROSPECTIVE_PREDICTIVE_VALIDATION_V1',
         'production_change':False,'anti_leakage_rule':'Only decisions already present in the prospective experiment ledger are evaluated; future outcome fields never select the candidate cohort.',
         'promotion_rule':'At least 100 candidate and 100 baseline observations plus positive median ROI, verified-tradable, and failed-survival edges. Promotion still requires human review.',
         'survivor_first_vs_baseline':result,
         'system_status':'EDGE_NOT_PROVEN' if result['status']!='EDGE_CANDIDATE' else 'EDGE_CANDIDATE_NOT_PRODUCTION'}
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__': main()
