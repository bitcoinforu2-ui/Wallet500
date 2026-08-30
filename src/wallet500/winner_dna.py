from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path("data")
OUT = DATA / "winner-dna-study.json"
LIQ_FLOOR = 50_000.0
TOP_N = 100
CONTROL_MULTIPLIER = 3


def load(name, default=None):
    p = DATA / name
    if not p.exists() or p.stat().st_size == 0:
        return {} if default is None else default
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def f(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def key(chain, token, pair):
    return ":".join((str(chain or "").lower(), str(token or "").lower(), str(pair or "").lower()))


def pre_outcome_features(token):
    hist = list(token.get("history") or [])
    if not hist:
        return None
    h = hist[0]
    liq = f(h.get("liquidity_usd")); vol = f(h.get("volume_h1")); buys = f(h.get("buys_h1")); sells = f(h.get("sells_h1"))
    return {"liquidity_usd":liq,"volume_h1":vol,"turnover_h1":round(vol/liq,6) if liq else None,"buys_h1":int(buys),"sells_h1":int(sells),"buy_sell_ratio":round(buys/max(1.0,sells),6),"txns_h1":int(buys+sells),"tradable_at_snapshot":liq>=LIQ_FLOOR}


def distance(a,b):
    la,lb=max(f(a.get("liquidity_usd")),1),max(f(b.get("liquidity_usd")),1); va,vb=max(f(a.get("volume_h1")),1),max(f(b.get("volume_h1")),1); ta,tb=max(f(a.get("txns_h1")),1),max(f(b.get("txns_h1")),1)
    return abs(math.log(la/lb))+abs(math.log(va/vb))+.5*abs(math.log(ta/tb))


def feature_summary(rows):
    out={}
    for field in ("liquidity_usd","volume_h1","turnover_h1","buy_sell_ratio","txns_h1"):
        xs=[f(r["features"].get(field)) for r in rows if r.get("features",{}).get(field) is not None]; out[field]=round(median(xs),6) if xs else None
    return out


def main():
    outcomes=load("outcome-tracker.json"); candidates=[]
    for _,o in (outcomes.get("tokens") or {}).items():
        pair=o.get("entry_pair_address"); features=pre_outcome_features(o)
        if not pair or not features: continue
        candidates.append({"key":key(o.get("chain"),o.get("token"),pair),"chain":o.get("chain"),"token":o.get("token"),"pair_address":pair,"discovered_at":o.get("first_seen") or o.get("tracking_started_at"),"features":features,"outcome":{"peak_return_pct":f(o.get("peak_return_pct")),"current_return_pct":f(o.get("current_return_pct")),"low_return_pct":f(o.get("low_return_pct"))}})
    winners=sorted(candidates,key=lambda r:r["outcome"]["peak_return_pct"],reverse=True)[:TOP_N]; winner_keys={r["key"] for r in winners}; pool=[r for r in candidates if r["key"] not in winner_keys]; controls=[]; used=set()
    for w in winners:
        same=[r for r in pool if r["chain"]==w["chain"] and r["key"] not in used]
        for c in sorted(same,key=lambda r:distance(w["features"],r["features"]))[:CONTROL_MULTIPLIER]: used.add(c["key"]); controls.append(c)
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"method":"WINNER_DNA_SHADOW_V1","production_change":False,"warning":"Historical label study only; features/control matching use earliest stored point-in-time snapshot. Validate prospectively before production use.","liquidity_floor_usd":LIQ_FLOOR,"winner_target_n":TOP_N,"winner_n":len(winners),"control_n":len(controls),"control_policy":"same chain; nearest earliest-snapshot liquidity/volume/transaction activity; future return excluded from matching distance","winner_feature_medians":feature_summary(winners),"control_feature_medians":feature_summary(controls),"winners":winners,"controls":controls,"next_step":"derive candidate DNA differences, freeze rules, then score only new discoveries prospectively in shadow mode"}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n"); print(json.dumps({k:result[k] for k in ("method","winner_n","control_n","winner_feature_medians","control_feature_medians")},indent=2))


if __name__=="__main__": main()
