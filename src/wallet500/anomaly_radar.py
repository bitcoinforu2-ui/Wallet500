from __future__ import annotations
from datetime import datetime, timezone

def _ratio(a,b): return float(a)/float(b) if b else (10.0 if a else 0.0)

def score_snapshot(s:dict)->dict:
    reasons=[]; score=0.0
    liq=s.get("liquidity_usd",0); v1=s.get("volume_h1",0); v24=s.get("volume_h24",0)
    buys=s.get("buys_h1",0); sells=s.get("sells_h1",0); pc1=s.get("price_change_h1",0); pc5=s.get("price_change_m5",0)
    velocity=_ratio(v1,max(v24/24,1)); buy_ratio=_ratio(buys,max(sells,1)); turnover=_ratio(v1,max(liq,1))
    if velocity>=3: score+=25; reasons.append(f"volume acceleration {velocity:.1f}x")
    elif velocity>=1.8: score+=15; reasons.append(f"volume acceleration {velocity:.1f}x")
    if buy_ratio>=2: score+=20; reasons.append(f"buyer pressure {buy_ratio:.1f}x")
    elif buy_ratio>=1.4: score+=12; reasons.append(f"buyer pressure {buy_ratio:.1f}x")
    if turnover>=0.5: score+=18; reasons.append(f"liquidity turnover {turnover:.2f}")
    elif turnover>=0.2: score+=10; reasons.append(f"liquidity turnover {turnover:.2f}")
    if pc1>=20: score+=18; reasons.append(f"1h momentum +{pc1:.1f}%")
    elif pc1>=8: score+=10; reasons.append(f"1h momentum +{pc1:.1f}%")
    if pc5>=8: score+=10; reasons.append(f"5m impulse +{pc5:.1f}%")
    if 5000<=liq<=250000: score+=9; reasons.append("early-liquidity range")
    score=min(100.0,round(score,2))
    return {**s,"anomaly_score":score,"reasons":reasons,"volume_velocity":round(velocity,2),"buy_sell_ratio":round(buy_ratio,2),"turnover_h1":round(turnover,3),"observed_at":datetime.now(timezone.utc).isoformat()}

def rank_anomalies(snapshots:list[dict],threshold:float=45)->list[dict]:
    rows=[score_snapshot(x) for x in snapshots if x]
    rows.sort(key=lambda x:x["anomaly_score"],reverse=True)
    return [x for x in rows if x["anomaly_score"]>=threshold]
