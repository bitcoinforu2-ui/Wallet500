from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DATA=Path('data'); EVM={'ethereum','eth','bsc','bnb','base','arbitrum','optimism','polygon','avalanche'}

def load(p:Path,d:Any):
    try:return json.loads(p.read_text()) if p.exists() and p.stat().st_size else d
    except Exception:return d
def write(p:Path,x:Any):p.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def key(r):
    c=str(r.get('chain') or r.get('network') or '').strip().lower(); t=str(r.get('token_address') or r.get('token') or r.get('mint') or '').strip(); p=str(r.get('pair_address') or '').strip()
    if c in EVM:t,p=t.lower(),p.lower()
    return f'{c}:{t}:{p}' if c and t and p else (f'{c}:{t}' if c and t else '')
def index(items):
    exact={}; token={}
    for r in items:
        if not isinstance(r,dict):continue
        k=key(r)
        if k:exact[k]=r
        parts=k.split(':')
        if len(parts)>=2:token[':'.join(parts[:2])]=r
    exact.update({k:v for k,v in token.items() if k not in exact});return exact
def lookup(ix,r):
    k=key(r); return ix.get(k) or ix.get(':'.join(k.split(':')[:2])) or {}
def enrich(r,intel):
    x=dict(r); c=lookup(intel,r)
    if c:
        x['signal_dna']=c.get('signal_dna');x['wallet_intent']=c.get('wallet_intent');x['revival_phase']=c.get('revival_phase');x['expected_value']=c.get('expected_value');x['signal_intelligence_observed_at']=c.get('observed_at')
    return x
def apply(real:dict[str,Any],signal:dict[str,Any])->dict[str,Any]:
    out=dict(real or {}); alerts=[x for x in out.get('alerts',[]) if isinstance(x,dict)]; watch=[x for x in out.get('verified_watch',[]) if isinstance(x,dict)]; intel=index(signal.get('candidates') or [] if isinstance(signal,dict) else [])
    alerts=[enrich(x,intel) for x in alerts];watch=[enrich(x,intel) for x in watch]
    h=signal.get('data_health') if isinstance(signal.get('data_health'),dict) else {}; safe=h.get('production_safe') is True; demoted=[]
    if not safe:
        for r in alerts:
            x=dict(r);x['status']='DATA_DEGRADED_NOT_REAL_ALERT';x['actionable_research_alert']=False;x['blockers']=sorted(set(list(x.get('blockers') or [])+['DATA_DEGRADED_FAIL_CLOSED']));x['data_health_status']=h.get('status') or 'DATA_DEGRADED_FAIL_CLOSED';demoted.append(x)
        watch=demoted+watch;alerts=[]
    model=signal.get('self_learning_model') if isinstance(signal.get('self_learning_model'),dict) else {}
    if model.get('validated') is True and model.get('ranking_effect') is True:
        alerts.sort(key=lambda x:float(((x.get('expected_value') or {}).get('expected_return_scenario_pct') or 0)),reverse=True)
    counts=dict(out.get('counts') or {});counts['real_alerts']=len(alerts);counts['verified_watch_not_real']=len(watch);counts['data_degraded_demotions']=len(demoted)
    truth=dict(out.get('truth_contract') or {});truth.update({'signal_intelligence_data_health_required':True,'stale_required_decision_inputs_fail_closed':True,'self_learning_can_rank_but_never_auto_promote':True})
    out.update({'signal_guard_version':1,'data_health':h,'signal_intelligence_summary':{'mode':signal.get('mode'),'model_status':model.get('status'),'model_validated':model.get('validated') is True,'winner_loser_dna_status':(signal.get('winner_loser_dna') or {}).get('status') if isinstance(signal.get('winner_loser_dna'),dict) else None,'false_negative_winners':(signal.get('missed_winner_lab') or {}).get('false_negative_winners') if isinstance(signal.get('missed_winner_lab'),dict) else None},'truth_contract':truth,'counts':counts,'alerts':alerts,'verified_watch':watch[:100],'latest_real_alert':alerts[0] if alerts else None})
    return out
def run(root:Path=DATA):
    real=load(root/'real-alerts.json',{});signal=load(root/'signal-intelligence.json',{});out=apply(real,signal);write(root/'real-alerts.json',out);return {'real_alerts':out.get('counts',{}).get('real_alerts',0),'data_health':(out.get('data_health') or {}).get('status'),'demoted':out.get('counts',{}).get('data_degraded_demotions',0)}
if __name__=='__main__':print(json.dumps(run(),indent=2))
