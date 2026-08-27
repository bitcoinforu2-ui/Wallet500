from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from statistics import median
from .market_data import snapshot


def _key(chain: str, token: str) -> str:
    return f"{chain}:{token.lower() if chain in {'ethereum','bsc'} else token}"


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def _med(rows, field):
    vals=[]
    for r in rows:
        try:
            v=float(r.get(field) or 0)
            if v >= 0:
                vals.append(v)
        except Exception:
            pass
    return median(vals) if vals else 0.0


def _ratio(a, b):
    return float(a) / float(b) if b and float(b) > 0 else (10.0 if a else 0.0)


def _age_days(pair_created_at, now_dt):
    try:
        created=datetime.fromtimestamp(float(pair_created_at)/1000.0, tz=timezone.utc)
        return max(0.0, (now_dt-created).total_seconds()/86400.0)
    except Exception:
        return None


def _score(s: dict, history: list[dict], now_dt) -> dict:
    age_days=_age_days(s.get('pair_created_at'), now_dt)
    if age_days is None or age_days < 2.0:
        return {**s,'revival_score':0,'revival_eligible':False,'revival_reasons':['PAIR_TOO_NEW_OR_AGE_UNKNOWN'],'pair_age_days':round(age_days,2) if age_days is not None else None}

    v1=float(s.get('volume_h1') or 0); v24=float(s.get('volume_h24') or 0)
    liq=float(s.get('liquidity_usd') or 0)
    buys=int(s.get('buys_h1') or 0); sells=int(s.get('sells_h1') or 0)
    tx1=buys+sells
    tx24=int(s.get('buys_h24') or 0)+int(s.get('sells_h24') or 0)
    pc1=float(s.get('price_change_h1') or 0); pc5=float(s.get('price_change_m5') or 0)

    hist=history[-24:]
    base_v1=_med(hist,'volume_h1')
    base_liq=_med(hist,'liquidity_usd')
    base_tx=_med(hist,'tx_h1')

    volume_clock=_ratio(v1,max(v24/24.0,1.0))
    tx_clock=_ratio(tx1,max(tx24/24.0,1.0))
    volume_baseline=_ratio(v1,max(base_v1,1.0)) if hist else 0.0
    tx_baseline=_ratio(tx1,max(base_tx,1.0)) if hist else 0.0
    liquidity_change=((liq/base_liq)-1.0)*100.0 if base_liq>0 else 0.0
    buy_ratio=_ratio(buys,max(sells,1))

    score=0; reasons=[]
    if volume_clock>=4: score+=28; reasons.append(f'24h-normalized volume acceleration {volume_clock:.1f}x')
    elif volume_clock>=2.5: score+=20; reasons.append(f'24h-normalized volume acceleration {volume_clock:.1f}x')
    elif volume_clock>=1.8: score+=12; reasons.append(f'24h-normalized volume acceleration {volume_clock:.1f}x')

    if tx_clock>=3: score+=18; reasons.append(f'transaction acceleration {tx_clock:.1f}x')
    elif tx_clock>=1.8: score+=10; reasons.append(f'transaction acceleration {tx_clock:.1f}x')

    if hist and volume_baseline>=4: score+=22; reasons.append(f'volume vs personal baseline {volume_baseline:.1f}x')
    elif hist and volume_baseline>=2: score+=12; reasons.append(f'volume vs personal baseline {volume_baseline:.1f}x')

    if hist and tx_baseline>=3: score+=12; reasons.append(f'transactions vs personal baseline {tx_baseline:.1f}x')
    if hist and liquidity_change>=30: score+=12; reasons.append(f'liquidity inflow +{liquidity_change:.0f}% vs baseline')
    if buy_ratio>=1.6: score+=10; reasons.append(f'buyer pressure {buy_ratio:.1f}x')
    elif buy_ratio>=1.25: score+=5; reasons.append(f'buyer pressure {buy_ratio:.1f}x')
    if pc1>=12: score+=10; reasons.append(f'1h revival momentum +{pc1:.1f}%')
    elif pc1>=5: score+=5; reasons.append(f'1h revival momentum +{pc1:.1f}%')
    if pc5>=5: score+=5; reasons.append(f'5m impulse +{pc5:.1f}%')
    if liq>=20000: score+=5; reasons.append('usable liquidity')

    score=min(100,int(score))
    return {**s,'revival_score':score,'revival_eligible':True,'revival_reasons':reasons,'pair_age_days':round(age_days,2),'revival_metrics':{'volume_clock_ratio':round(volume_clock,2),'tx_clock_ratio':round(tx_clock,2),'volume_baseline_ratio':round(volume_baseline,2),'tx_baseline_ratio':round(tx_baseline,2),'liquidity_change_pct':round(liquidity_change,2),'buy_sell_ratio':round(buy_ratio,2)}}


def run_revival_scan(out: Path, discovery_state: dict, manual_watch: list[dict], now: str, batch_size: int=60, threshold: int=55) -> dict:
    path=out/'revival-state.json'; state=_load(path,{})
    if not isinstance(state,dict): state={}
    records=state.get('tokens') if isinstance(state.get('tokens'),dict) else {}
    cursor=int(state.get('cursor',0) or 0)

    pool=[]; seen=set()
    # Manual research cases are always checked first (e.g. older tokens explicitly tracked).
    for x in manual_watch:
        c=x.get('chain'); t=x.get('token') or x.get('mint')
        if c and t:
            k=_key(c,t)
            if k not in seen: pool.append((k,c,t,True)); seen.add(k)
    for k,m in sorted(((discovery_state.get('tokens') or {}).items())):
        c=m.get('chain'); t=m.get('token')
        if c and t and k not in seen: pool.append((k,c,t,False)); seen.add(k)

    manual=[x for x in pool if x[3]]
    rotating=[x for x in pool if not x[3]]
    take=max(0,batch_size-len(manual))
    selected=list(manual)
    if rotating and take:
        cursor%=len(rotating)
        for i in range(min(take,len(rotating))):
            selected.append(rotating[(cursor+i)%len(rotating)])
        next_cursor=(cursor+min(take,len(rotating)))%len(rotating)
    else:
        next_cursor=0

    now_dt=datetime.fromisoformat(now.replace('Z','+00:00'))
    snapshots=[]; alerts=[]; errors=[]
    for k,c,t,is_manual in selected:
        s=snapshot(c,t)
        if not s:
            errors.append({'chain':c,'token':t,'error':'NO_MARKET_SNAPSHOT'})
            continue
        rec=records.get(k) if isinstance(records.get(k),dict) else {}
        hist=rec.get('history') if isinstance(rec.get('history'),list) else []
        scored=_score(s,hist,now_dt)
        scored['revival_manual_watch']=is_manual
        scored['revival_observed_at']=now
        snapshots.append(scored)
        hrow={'observed_at':now,'price_usd':s.get('price_usd'),'liquidity_usd':s.get('liquidity_usd'),'volume_h1':s.get('volume_h1'),'tx_h1':int(s.get('buys_h1') or 0)+int(s.get('sells_h1') or 0),'revival_score':scored.get('revival_score')}
        hist=(hist+[hrow])[-48:]
        records[k]={'chain':c,'token':t,'history':hist,'last_score':scored.get('revival_score',0),'last_seen':now,'pair_age_days':scored.get('pair_age_days')}
        if scored.get('revival_eligible') and int(scored.get('revival_score') or 0)>=threshold:
            alerts.append(scored)

    alerts.sort(key=lambda x:(x.get('revival_score',0),x.get('volume_h1',0)),reverse=True)
    state={'version':1,'cursor':next_cursor,'updated_at':now,'batch_size':batch_size,'universe_size':len(pool),'scanned_this_run':len(snapshots),'alerts_this_run':len(alerts),'errors_this_run':len(errors),'tokens':records}
    (out/'revival-state.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    (out/'revival-radar.json').write_text(json.dumps(alerts,indent=2),encoding='utf-8')
    (out/'revival-snapshots.json').write_text(json.dumps(snapshots,indent=2),encoding='utf-8')
    return {'state':state,'snapshots':snapshots,'alerts':alerts,'errors':errors}
