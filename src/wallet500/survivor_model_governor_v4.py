from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

DATA=Path('data')
WATCH=DATA/'survivor-wave-watch.json'
FORWARD=DATA/'survivor-forward-validation.json'
OUT=DATA/'survivor-model-governor-v4.json'


def load(p,d):
    try:return json.loads(p.read_text())
    except (OSError,json.JSONDecodeError):return d

def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

def f(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None

def clamp(v):return max(0,min(100,int(round(v))))

def med(vs):
    xs=[f(x) for x in vs];xs=[x for x in xs if x is not None]
    return median(xs) if xs else None

def ratio(a,b):
    a,b=f(a),f(b)
    if a is None or b in (None,0):return None
    return a/b

def coverage_score(row):
    fields={
        'price':row.get('price_usd') is not None,'liquidity':row.get('liquidity_usd') is not None,
        'volume_h1':row.get('volume_h1_usd') is not None,'volume_h24':row.get('volume_h24_usd') is not None,
        'buys_sells':row.get('buys_h1') is not None and row.get('sells_h1') is not None,
        'turnover':row.get('turnover_h1') is not None,'price_h1':row.get('price_change_h1_pct') is not None,
        'price_h6':row.get('price_change_h6_pct') is not None,'price_h24':row.get('price_change_h24_pct') is not None,
        'holders':row.get('holders') is not None,'organic_social':row.get('organic_acceleration_score') is not None,
        'kol':row.get('kol_independent_groups') is not None,
    }
    core=['price','liquidity','volume_h1','buys_sells','turnover','price_h1','price_h6','price_h24']
    optional=['holders','organic_social','kol','volume_h24']
    s=sum(10 for k in core if fields[k])+sum(5 for k in optional if fields[k])
    maxs=len(core)*10+len(optional)*5
    pct=clamp(s/maxs*100)
    return {'score':pct,'status':'GOOD' if pct>=80 else 'PARTIAL' if pct>=60 else 'WEAK','fields':fields}

def cohort_context(rows):
    by=defaultdict(list)
    for r in rows:by[str(r.get('chain') or '').lower()].append(r)
    ctx={}
    for chain,rs in by.items():
        ctx[chain]={
            'turnover_median':med([r.get('turnover_h1') for r in rs]),
            'volume_h1_median':med([r.get('volume_h1_usd') for r in rs]),
            'price_h1_median':med([r.get('price_change_h1_pct') for r in rs]),'n':len(rs)}
    return ctx

def relative_strength(row,ctx):
    c=ctx.get(str(row.get('chain') or '').lower()) or {}
    if c.get('n',0)<3:return {'status':'INSUFFICIENT_COHORT','score':0}
    tr=ratio(row.get('turnover_h1'),c.get('turnover_median'));vr=ratio(row.get('volume_h1_usd'),c.get('volume_h1_median'))
    ph=f(row.get('price_change_h1_pct'));pm=f(c.get('price_h1_median'));score=0;reasons=[]
    if tr is not None and tr>=1.5:score+=35;reasons.append('TURNOVER_ABOVE_CHAIN_COHORT')
    if vr is not None and vr>=1.5:score+=30;reasons.append('VOLUME_ABOVE_CHAIN_COHORT')
    if ph is not None and pm is not None and ph-pm>=5:score+=20;reasons.append('PRICE_RELATIVE_STRENGTH')
    return {'status':'OUTPERFORMING_COHORT' if score>=50 else 'NORMAL_COHORT_RANGE','score':clamp(score),'turnover_vs_chain_median':round(tr,3) if tr else None,'volume_vs_chain_median':round(vr,3) if vr else None,'price_h1_minus_chain_median_pct':round(ph-pm,3) if ph is not None and pm is not None else None,'reasons':reasons}

def disagreement(row):
    v3=row.get('intelligence_v3') or {};pre=f((row.get('pre_high') or {}).get('score')) or f(row.get('research_confidence')) or 0
    vals=[pre,f((v3.get('relative_anomaly') or {}).get('score')) or 0,f((v3.get('buy_quality') or {}).get('score')) or 0,f((v3.get('exitability') or {}).get('score')) or 0,100-(f((v3.get('failure_anti_dna') or {}).get('score')) or 0)]
    spread=max(vals)-min(vals) if vals else 0
    return {'spread':round(spread,1),'status':'HIGH_DISAGREEMENT' if spread>=60 else 'MODERATE_DISAGREEMENT' if spread>=35 else 'CONSISTENT','components':vals}

def signal_decay(row):
    a=row.get('acceleration') or {};p=f(row.get('dna_persistence_score')) or 0;stage=row.get('research_stage');score=0;reasons=[]
    if a.get('status')=='ACCELERATING':score+=40;reasons.append('ACCELERATION_ACTIVE')
    if p>=50:score+=35;reasons.append('PERSISTENCE_ACTIVE')
    if stage in {'PRE_WAVE','DNA_HIGH','CONFIRMED_WAVE'}:score+=25;reasons.append('ADVANCED_STAGE')
    return {'freshness_score':clamp(score),'status':'FRESH' if score>=65 else 'AGING' if score>=35 else 'TRANSIENT_OR_STALE','reasons':reasons}

def calibration(forward):
    events=(forward.get('events') or {}).values();eligible=[]
    for e in events:
        h=e.get('horizons') or {}
        if '24' in h and (h['24'] or {}).get('return_pct') is not None:eligible.append(e)
    n=len(eligible)
    if n<30:return {'status':'INSUFFICIENT_SAMPLE','n_24h':n,'minimum_required':30,'threshold_recommendations':None,'probability_model_enabled':False}
    returns=[f((e.get('horizons') or {}).get('24',{}).get('return_pct')) for e in eligible];returns=[x for x in returns if x is not None]
    return {'status':'RESEARCH_SAMPLE_READY','n_24h':n,'minimum_required':30,'median_return_24h_pct':round(median(returns),3) if returns else None,'threshold_recommendations':'RESEARCH_ONLY_REVIEW_REQUIRED','probability_model_enabled':False,'note':'Sample readiness does not authorize automatic threshold or production changes.'}

def drift(rows):
    highs=sum(1 for r in rows if r.get('winner_dna_match')=='HIGH');medium=sum(1 for r in rows if r.get('winner_dna_match')=='MEDIUM');n=len(rows)
    rate=(highs+medium)/n if n else 0
    return {'active_signal_rate':round(rate,4),'status':'SATURATION_REVIEW' if rate>0.6 else 'NORMAL','high_n':highs,'medium_n':medium,'survivor_n':n}

def main():
    watch=load(WATCH,{});forward=load(FORWARD,{});rows=watch.get('tokens') or [];ctx=cohort_context(rows);summary=[]
    for r in rows:
        cov=coverage_score(r);rel=relative_strength(r,ctx);dis=disagreement(r);dec=signal_decay(r)
        raw=f(r.get('net_opportunity_score')) or 0
        adjusted=clamp(raw*(0.55+0.45*cov['score']/100)*(0.75+0.25*dec['freshness_score']/100))
        if dis['status']=='HIGH_DISAGREEMENT':adjusted=clamp(adjusted*0.8)
        r['model_governor_v4']={'coverage':cov,'chain_cohort_relative_strength':rel,'ensemble_disagreement':dis,'signal_decay':dec,'coverage_adjusted_opportunity_score':adjusted,'production_effect':False}
        summary.append({'chain':r.get('chain'),'token':r.get('token'),'pair_address':r.get('pair_address'),'coverage_adjusted_opportunity_score':adjusted,'coverage_status':cov['status'],'relative_strength':rel['status'],'disagreement':dis['status'],'freshness':dec['status']})
    cal=calibration(forward);dr=drift(rows)
    watch['model_governor_v4']={'version':'MODEL_GOVERNOR_V4','research_only':True,'production_gates_changed':False,'cohort_context':ctx,'calibration':cal,'drift':dr,'policies':['COVERAGE_WEIGHTING','COHORT_RELATIVE_STRENGTH','ENSEMBLE_DISAGREEMENT','SIGNAL_DECAY','CALIBRATION_GATE','DRIFT_WATCH'],'note':'Governor scores are shadow-only and cannot alter veteran gate, exact-pair survival gate, alerts, or automatic trading.'}
    dump(WATCH,watch);dump(OUT,{'version':4,'generated_at':watch.get('generated_at'),'research_only':True,'production_gates_changed':False,'calibration':cal,'drift':dr,'tokens':summary})
    print(json.dumps({'governed':len(rows),'calibration':cal.get('status'),'drift':dr.get('status'),'production_gates_changed':False}))
if __name__=='__main__':main()
