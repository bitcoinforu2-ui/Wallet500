from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'data/close-watch-intelligence-policy.json'
EVENTS = ROOT / 'data/close-watch-events.json'
OUTPUT = ROOT / 'data/close-watch-intelligence.json'


def _now(): return datetime.now(timezone.utc)

def _parse(ts):
    try: return datetime.fromisoformat(str(ts).replace('Z','+00:00'))
    except Exception: return None

def _clamp(v, lo=0.0, hi=100.0): return max(lo, min(hi, float(v)))

def _fingerprint(e):
    # Same underlying URL/event should never become many independent confirmations.
    root = str(e.get('canonical_event_id') or e.get('source_url') or '')
    if not root:
        root = '|'.join(str(e.get(k) or '') for k in ('symbol','family','kind','subject','event_time'))
    return hashlib.sha256(root.lower().strip().encode()).hexdigest()[:20]

def _freshness(e, half_life):
    t=_parse(e.get('event_time') or e.get('observed_at'))
    if not t: return 0.25
    age=max(0.0, (_now()-t).total_seconds()/60)
    return math.pow(0.5, age/max(1.0,half_life))

def _label(score, labels):
    for band,name in labels.items():
        lo,hi=map(int,band.split('-'))
        if lo <= score <= hi: return name
    return 'WATCH'

def fuse(symbol, events, policy):
    fam_cfg=policy['signal_families']; fusion=policy['fusion']
    half=float(fusion['freshness_half_life_minutes']); dedup=float(fusion['source_duplicate_discount'])
    seen={}; family_points={}; evidence=[]; contradictions=0.0; hard_risks=[]
    for e in events:
        if str(e.get('symbol','')).upper()!=symbol.upper(): continue
        fam=e.get('family')
        if fam not in fam_cfg: continue
        fp=_fingerprint(e); duplicate=fp in seen; seen[fp]=seen.get(fp,0)+1
        confidence=_clamp(e.get('confidence',50))/100
        strength=_clamp(abs(float(e.get('strength',0))))/100
        direction=-1 if float(e.get('direction',1))<0 else 1
        freshness=_freshness(e,half)
        independence=dedup if duplicate else 1.0
        raw=confidence*strength*freshness*independence
        family_points[fam]=family_points.get(fam,0.0)+direction*raw
        if direction<0 and e.get('contradicts_bullish'): contradictions += raw*100
        if e.get('hard_risk'): hard_risks.append(str(e.get('kind') or 'hard_risk'))
        evidence.append({'family':fam,'kind':e.get('kind'),'direction':direction,'raw':round(raw,4),'duplicate':duplicate,'source':e.get('source'),'event_time':e.get('event_time')})
    weighted={}
    positive_families=0
    for fam,cfg in fam_cfg.items():
        normalized=max(-1.0,min(1.0,family_points.get(fam,0.0)))
        pts=normalized*float(cfg['weight'])
        weighted[fam]=round(pts,2)
        if pts>0.5: positive_families+=1
    positive=sum(max(0,x) for x in weighted.values())
    negative=sum(abs(min(0,x)) for x in weighted.values())
    score=_clamp(positive-negative-min(float(fusion['contradiction_penalty_max']),contradictions))
    # Avoid false confidence from one rich provider/family.
    if positive_families < int(fusion['minimum_independent_families_for_strong']): score=min(score,float(fusion['single_family_score_cap']))
    if hard_risks: score=min(score,29)
    return {'symbol':symbol.upper(),'score':round(score,1),'label':_label(int(round(score)),fusion['labels']),'independent_positive_families':positive_families,'family_scores':weighted,'hard_risks':sorted(set(hard_risks)),'evidence_count':len(evidence),'evidence':sorted(evidence,key=lambda x:x['raw'],reverse=True)[:30],'updated_at':_now().isoformat()}

def main():
    policy=json.loads(POLICY.read_text())
    doc=json.loads(EVENTS.read_text()) if EVENTS.exists() else {'events':[]}
    events=doc.get('events') or []
    symbols=sorted({str(e.get('symbol','')).upper() for e in events if e.get('symbol')})
    out={'version':1,'generated_at':_now().isoformat(),'tokens':[fuse(s,events,policy) for s in symbols]}
    OUTPUT.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(out,ensure_ascii=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
