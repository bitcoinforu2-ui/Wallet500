from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/'data/close-watch-events.json'
REP=ROOT/'data/alpha-caller-reputation.json'
CALLS=ROOT/'data/alpha-caller-call-history.json'
UA='Wallet500-AlphaCallerReputation/1.0'

def now(): return datetime.now(timezone.utc).isoformat()
def get_json(url,timeout=12):
    try:
        with urlopen(Request(url,headers={'User-Agent':UA,'Accept':'application/json'}),timeout=timeout) as r:return json.loads(r.read().decode())
    except (HTTPError,URLError,TimeoutError,ValueError,OSError): return None

def n(v):
    try:return float(v)
    except (TypeError,ValueError):return None

def main():
    bus=json.loads(EVENTS.read_text()) if EVENTS.exists() else {'events':[]}
    rep=json.loads(REP.read_text()) if REP.exists() else {'version':1,'callers':{},'policy':{}}
    hist=json.loads(CALLS.read_text()) if CALLS.exists() else {'version':1,'calls':{}}
    callers=rep.setdefault('callers',{}); calls=hist.setdefault('calls',{})
    for e in bus.get('events') or []:
        if e.get('kind')!='verified_alpha_caller_call':continue
        cid=e.get('canonical_event_id'); caller=str(e.get('subject') or 'UNKNOWN'); source=str(e.get('source') or 'UNKNOWN')
        if cid not in calls:
            calls[cid]={'caller':caller,'source':source,'symbol':e.get('symbol'),'network':e.get('network'),'contract':e.get('contract'),'pair':e.get('pair'),'called_at':e.get('event_time'),'entry_price':None,'entry_liquidity':e.get('liquidity_usd_at_intake'),'peak_price':None,'latest_price':None,'max_multiple':None,'status':'TRACKING','last_observed_at':now()}
        c=calls[cid]; contract=c.get('contract')
        d=get_json('https://api.dexscreener.com/latest/dex/tokens/'+str(contract)) if contract else None
        pairs=(d or {}).get('pairs') or []; pair=next((p for p in pairs if str(p.get('pairAddress','')).lower()==str(c.get('pair','')).lower()),None)
        if not pair:continue
        px=n(pair.get('priceUsd'))
        if px is None or px<=0:continue
        if c.get('entry_price') is None:c['entry_price']=px
        c['latest_price']=px;c['peak_price']=max(px,n(c.get('peak_price')) or px);c['last_observed_at']=now()
        if n(c.get('entry_price')):c['max_multiple']=round(c['peak_price']/c['entry_price'],4)
    # Reputation is descriptive and forward-only. No caller gets credit from unverifiable marketing claims.
    grouped={}
    for c in calls.values():grouped.setdefault((c['source'],c['caller']),[]).append(c)
    for (source,caller),xs in grouped.items():
        resolved=[x for x in xs if n(x.get('max_multiple')) is not None]
        hits5=sum((n(x.get('max_multiple')) or 0)>=5 for x in resolved); hits10=sum((n(x.get('max_multiple')) or 0)>=10 for x in resolved)
        mults=[n(x.get('max_multiple')) for x in resolved if n(x.get('max_multiple')) is not None]
        median=sorted(mults)[len(mults)//2] if mults else None
        count=len(resolved); hit5=hits5/count if count else 0
        # Bayesian shrinkage prevents tiny samples from dominating.
        shrunk=(hits5+1)/(count+4) if count else .25
        confidence=min(90,35+count*2) if count>=5 else min(55,30+count*5)
        strength=min(90,25+65*shrunk)
        key=source+'::'+caller
        callers[key]={'source':source,'caller':caller,'calls_seen':len(xs),'resolved_calls':count,'hits_5x':hits5,'hits_10x':hits10,'hit_rate_5x':round(hit5,4),'bayesian_hit_rate_5x':round(shrunk,4),'median_max_multiple':median,'reputation_strength':round(strength,1),'reputation_confidence':round(confidence,1),'status':'ESTABLISHED' if count>=20 else ('EMERGING' if count>=5 else 'UNPROVEN'),'updated_at':now()}
    rep['updated_at']=now();hist['updated_at']=now()
    REP.write_text(json.dumps(rep,indent=2,ensure_ascii=False)+'\n');CALLS.write_text(json.dumps(hist,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':'OK','callers':len(callers),'calls_tracking':len(calls),'forward_only':True}))
if __name__=='__main__':main()
