from __future__ import annotations
import gzip, json
from pathlib import Path
from datetime import datetime, timezone


def _load(p,default):
    gz=Path(str(p)+'.gz')
    try:
        if gz.exists():
            with gzip.open(gz,'rt',encoding='utf-8') as f:return json.load(f)
        if p.exists():return json.loads(p.read_text(encoding='utf-8'))
    except:return default
    return default

def _pct(a,b):
    try:
        a=float(a);b=float(b)
        return (a/b-1)*100 if b else 0.0
    except:return 0.0

def _dt(v):
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except:return None

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

def _future_path(hist,i,max_seconds):
    base_ts=_dt(hist[i].get('observed_at'))
    if base_ts is None:return []
    out=[]
    for j in range(i+1,len(hist)):
        ts=_dt(hist[j].get('observed_at'))
        if ts is None:continue
        elapsed=(ts-base_ts).total_seconds()
        if elapsed<=0:continue
        if elapsed>max_seconds:break
        out.append((j,elapsed,hist[j]))
    return out

def _nearest_at_or_after(path,target_seconds,tolerance_seconds):
    candidates=[x for x in path if x[1]>=target_seconds and x[1]<=target_seconds+tolerance_seconds]
    return min(candidates,key=lambda x:x[1],default=None)

def run_time_machine(out:Path,now:str|None=None):
    now=now or datetime.now(timezone.utc).isoformat()
    state=_load(out/'cex-state.json',{});markets=state.get('markets',{}) if isinstance(state,dict) else {}
    horizons={'15m':900,'30m':1800,'1h':3600,'2h':7200}
    tolerance={'15m':900,'30m':1200,'1h':1800,'2h':2700}
    max_window=max(horizons.values())+max(tolerance.values())
    pattern_stats={};source_stats={};samples=[]
    for key,hist in markets.items():
        if not isinstance(hist,list) or len(hist)<3:continue
        ex,sym=key.split(':',1);source_stats.setdefault(ex,{'samples':0,'wins_10pct':0,'wins_20pct':0,'sum_max_drawdown_pct':0.0})
        for i in range(1,len(hist)-1):
            base=float(hist[i].get('price',0) or 0);base_ts=_dt(hist[i].get('observed_at'))
            if base<=0 or base_ts is None:continue
            path=_future_path(hist,i,max_window)
            if not path:continue
            f=_features(hist,i);pat='>'.join(_pattern(f))
            st=pattern_stats.setdefault(pat,{'samples':0,'future_5pct':0,'future_10pct':0,'future_20pct':0,'future_30pct':0,'sum_best_future_pct':0.0,'sum_max_drawdown_pct':0.0,'horizon_returns':{h:{'samples':0,'sum_return_pct':0.0,'wins_10pct':0,'wins_20pct':0} for h in horizons}})
            returns=[]
            for _,elapsed,row in path:
                price=float(row.get('price',0) or 0)
                if price<=0:continue
                returns.append((elapsed,_pct(price,base)))
            if not returns:continue
            best_elapsed,best=max(returns,key=lambda x:x[1]);worst=min(x[1] for x in returns)
            st['samples']+=1;st['sum_best_future_pct']+=best;st['sum_max_drawdown_pct']+=worst;source_stats[ex]['samples']+=1;source_stats[ex]['sum_max_drawdown_pct']+=worst
            if best>=5:st['future_5pct']+=1
            if best>=10:st['future_10pct']+=1;source_stats[ex]['wins_10pct']+=1
            if best>=20:st['future_20pct']+=1;source_stats[ex]['wins_20pct']+=1
            if best>=30:st['future_30pct']+=1
            realized={}
            for label,seconds in horizons.items():
                hit=_nearest_at_or_after(path,seconds,tolerance[label])
                if hit is None:
                    realized[label]=None;continue
                _,elapsed,row=hit;price=float(row.get('price',0) or 0)
                if price<=0:
                    realized[label]=None;continue
                r=_pct(price,base);realized[label]=round(r,4);hs=st['horizon_returns'][label];hs['samples']+=1;hs['sum_return_pct']+=r
                if r>=10:hs['wins_10pct']+=1
                if r>=20:hs['wins_20pct']+=1
            if len(samples)<500:
                samples.append({'exchange':ex,'symbol':sym,'observed_at':hist[i].get('observed_at'),'pattern':pat,'features':f,'returns_at_horizon_pct':realized,'max_gain_pct':round(best,4),'max_drawdown_pct':round(worst,4),'time_to_peak_seconds':round(best_elapsed,1),'future_observations_checked':len(returns)})
    ranked=[]
    for pat,st in pattern_stats.items():
        n=st['samples'];st['avg_best_future_pct']=round(st.pop('sum_best_future_pct')/max(1,n),4);st['avg_max_drawdown_pct']=round(st.pop('sum_max_drawdown_pct')/max(1,n),4);st['hit_rate_10pct']=round(st['future_10pct']/max(1,n),4);st['hit_rate_20pct']=round(st['future_20pct']/max(1,n),4)
        for hs in st['horizon_returns'].values():
            hn=hs['samples'];hs['avg_return_pct']=round(hs.pop('sum_return_pct')/max(1,hn),4);hs['hit_rate_10pct']=round(hs['wins_10pct']/max(1,hn),4);hs['hit_rate_20pct']=round(hs['wins_20pct']/max(1,hn),4)
        ranked.append({'pattern':pat,**st})
    ranked.sort(key=lambda x:(x['hit_rate_20pct'],x['hit_rate_10pct'],x['avg_max_drawdown_pct'],x['samples']),reverse=True)
    for v in source_stats.values():
        n=v['samples'];v['hit_rate_10pct']=round(v['wins_10pct']/max(1,n),4);v['hit_rate_20pct']=round(v['wins_20pct']/max(1,n),4);v['avg_max_drawdown_pct']=round(v.pop('sum_max_drawdown_pct')/max(1,n),4)
    payload={'version':2,'generated_at':now,'method':'NO_HINDSIGHT_TIMESTAMP_EXACT_REPLAY','rule':'features at observation i use only i and earlier; forward outcomes use actual observed_at timestamps only','horizons_seconds':horizons,'horizon_tolerance_seconds':tolerance,'patterns_tested':len(ranked),'top_patterns':ranked[:100],'source_forward_hit_rates':source_stats,'samples':samples}
    (out/'time-machine-replay.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return payload
