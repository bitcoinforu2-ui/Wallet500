from __future__ import annotations
import json, urllib.request
from pathlib import Path
from datetime import datetime, timezone

UA={'User-Agent':'Wallet500/1.0','Accept':'application/json'}
def _get(url,timeout=20):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read().decode())
def _f(v):
    try:return float(v or 0)
    except:return 0.0

def gate_universe():
    rows=_get('https://api.gateio.ws/api/v4/futures/usdt/tickers')
    out=[]
    for x in rows:
        c=x.get('contract','')
        if not c.endswith('_USDT'): continue
        last=_f(x.get('last')); ch=_f(x.get('change_percentage')); vol=_f(x.get('volume_24h_quote') or x.get('volume_24h'))
        fund=_f(x.get('funding_rate')); oi=_f(x.get('total_size'))
        out.append({'exchange':'gate','symbol':c.replace('_',''),'contract':c,'price':last,'change_24h_pct':ch,'volume_24h':vol,'funding_rate':fund,'open_interest':oi})
    return out

def bybit_universe():
    d=_get('https://api.bybit.com/v5/market/tickers?category=linear')
    out=[]
    for x in (d.get('result') or {}).get('list',[]):
        s=x.get('symbol','')
        if not s.endswith('USDT'): continue
        out.append({'exchange':'bybit','symbol':s,'contract':s,'price':_f(x.get('lastPrice')),'change_24h_pct':_f(x.get('price24hPcnt'))*100,'volume_24h':_f(x.get('turnover24h')),'funding_rate':_f(x.get('fundingRate')),'open_interest':_f(x.get('openInterestValue') or x.get('openInterest'))})
    return out

def run_cex_revival(out:Path, now:str):
    sources=[]; errors=[]
    for name,fn in [('gate',gate_universe),('bybit',bybit_universe)]:
        try:sources.extend(fn())
        except Exception as e:errors.append({'exchange':name,'error':str(e)[:240]})
    groups={}
    for x in sources:groups.setdefault(x['symbol'],[]).append(x)
    alerts=[]
    for sym,rows in groups.items():
        best=max(rows,key=lambda r:r.get('volume_24h',0)); confirmations=len({r['exchange'] for r in rows})
        change=max((r.get('change_24h_pct',0) for r in rows),default=0)
        maxfund=max((abs(r.get('funding_rate',0)) for r in rows),default=0)
        score=0; reasons=[]
        if change>=10:score+=25;reasons.append(f'24h momentum {change:.1f}%')
        if change>=30:score+=15
        if maxfund>=0.0005:score+=15;reasons.append(f'funding divergence {maxfund*100:.3f}%')
        if maxfund>=0.003:score+=15
        if confirmations>=2:score+=20;reasons.append(f'{confirmations} exchange confirmation')
        if best.get('volume_24h',0)>=1_000_000:score+=10;reasons.append('meaningful futures turnover')
        if score>=45:alerts.append({'symbol':sym,'cex_revival_score':min(score,100),'reasons':reasons,'confirmations':confirmations,'markets':rows})
    alerts.sort(key=lambda x:x['cex_revival_score'],reverse=True)
    payload={'version':1,'generated_at':now,'sources':['gate','bybit'],'contracts_seen':len(sources),'symbols_seen':len(groups),'alerts_count':len(alerts),'errors':errors,'alerts':alerts}
    (out/'cex-revival-radar.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return payload
