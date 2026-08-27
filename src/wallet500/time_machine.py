from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone


def _load(p,default):
    try:return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
    except:return default

def _pct(a,b):
    try:
        a=float(a);b=float(b)
        return (a/b-1)*100 if b else 0.0
    except:return 0.0

def _features(hist,i):
    cur=hist[i];prev=hist[i-1] if i>0 else {}
    return {
        'price_acceleration_pct':_pct(cur.get('price',0),prev.get('price',0)) if prev else 0.0,
        'volume_acceleration_pct':_pct(cur.get('volume_24h',0),prev.get('volume_24h',0)) if prev else 0.0,
        'oi_acceleration_pct':_pct(cur.get('open_interest',0),prev.get('open_interest',0)) if prev and cur.get('open_interest') and prev.get('open_interest') else 0.0,
        'funding_rate':float(cur.get('funding_rate',0) or 0),
    }

def _pattern(f):
    p=[]
    if f['price_acceleration_pct']>=2:p.append('PRICE_ACCEL')
    if f['volume_acceleration_pct']>=8:p.append('VOLUME_ACCEL')
    if f['oi_acceleration_pct']>=5:p.append('OI_ACCEL')
    if abs(f['funding_rate'])>=.0005:p.append('FUNDING_DIVERGENCE')
    if f['funding_rate']<=-.003 and f['price_acceleration_pct']>0:p.append('SHORT_SQUEEZE')
    if f['funding_rate']>=.001 and f['price_acceleration_pct']>0:p.append('CROWDED_LONG')
    return p or ['NONE']

def run_time_machine(out:Path,now:str|None=None):
    now=now or datetime.now(timezone.utc).isoformat()
    state=_load(out/'cex-state.json',{});markets=state.get('markets',{}) if isinstance(state,dict) else {}
    horizons=(1,2,4,8);thresholds=(5,10,20,30)
    pattern_stats={};source_stats={};samples=[]
    for key,hist in markets.items():
        if not isinstance(hist,list) or len(hist)<3:continue
        ex,sym=key.split(':',1);source_stats.setdefault(ex,{'samples':0,'wins_10pct':0,'wins_20pct':0})
        for i in range(1,len(hist)-1):
            base=float(hist[i].get('price',0) or 0)
            if base<=0:continue
            f=_features(hist,i);pat='>'.join(_pattern(f));st=pattern_stats.setdefault(pat,{'samples':0,'future_5pct':0,'future_10pct':0,'future_20pct':0,'future_30pct':0,'avg_best_future_pct':0.0,'sum_best_future_pct':0.0})
            best=-999.0;available=0
            for h in horizons:
                j=i+h
                if j>=len(hist):continue
                available+=1;best=max(best,_pct(hist[j].get('price',0),base))
            if not available:continue
            st['samples']+=1;st['sum_best_future_pct']+=best;source_stats[ex]['samples']+=1
            if best>=5:st['future_5pct']+=1
            if best>=10:st['future_10pct']+=1;source_stats[ex]['wins_10pct']+=1
            if best>=20:st['future_20pct']+=1;source_stats[ex]['wins_20pct']+=1
            if best>=30:st['future_30pct']+=1
            if len(samples)<500:samples.append({'exchange':ex,'symbol':sym,'observed_at':hist[i].get('observed_at'),'pattern':pat,'features':f,'best_future_pct':round(best,4),'future_points_checked':available})
    ranked=[]
    for pat,st in pattern_stats.items():
        n=st['samples'];st['avg_best_future_pct']=round(st.pop('sum_best_future_pct')/max(1,n),4);st['hit_rate_10pct']=round(st['future_10pct']/max(1,n),4);st['hit_rate_20pct']=round(st['future_20pct']/max(1,n),4);ranked.append({'pattern':pat,**st})
    ranked.sort(key=lambda x:(x['hit_rate_20pct'],x['hit_rate_10pct'],x['samples']),reverse=True)
    for v in source_stats.values():
        v['hit_rate_10pct']=round(v['wins_10pct']/max(1,v['samples']),4);v['hit_rate_20pct']=round(v['wins_20pct']/max(1,v['samples']),4)
    payload={'version':1,'generated_at':now,'method':'NO_HINDSIGHT_SEQUENTIAL_REPLAY','rule':'features at observation i are computed only from i and earlier; outcomes are measured only afterward','horizon_points':[1,2,4,8],'note':'with ~15m cadence these roughly represent 15m/30m/1h/2h; actual timestamps should replace cadence assumptions in a later version','patterns_tested':len(ranked),'top_patterns':ranked[:100],'source_forward_hit_rates':source_stats,'samples':samples}
    (out/'time-machine-replay.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return payload
