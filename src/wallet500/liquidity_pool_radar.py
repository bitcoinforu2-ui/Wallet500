from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path:Path,default):
    if not path.exists(): return default
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return default


def _write(path:Path,payload):
    path.write_text(json.dumps(payload,indent=2),encoding="utf-8")


def _pair_key(chain:str,pair:str)->str:
    pair=pair or ""
    if chain in {"ethereum","bsc"}:pair=pair.lower()
    return f"{chain}:{pair}"


def _pool_age_minutes(created_at,now_dt):
    try:
        ts=float(created_at)
        if ts>1e12:ts/=1000.0
        created=datetime.fromtimestamp(ts,tz=timezone.utc)
        return max(0.0,(now_dt-created).total_seconds()/60.0)
    except Exception:return None


def analyze_liquidity_pools(snapshots:list[dict],output_dir:Path,now:str)->dict:
    state_path=output_dir/"pool-liquidity-state.json"
    state=_load(state_path,{})
    pools_state=state.get("pools") if isinstance(state.get("pools"),dict) else {}
    now_dt=datetime.fromisoformat(now.replace("Z","+00:00"))
    signals=[]; observed=0
    for token_snap in snapshots or []:
        pools=token_snap.get("pools") if isinstance(token_snap.get("pools"),list) else []
        if not pools and token_snap.get("pair_address"):pools=[token_snap]
        for p in pools:
            chain=p.get("chain") or token_snap.get("chain"); pair=p.get("pair_address")
            token=p.get("token") or token_snap.get("token")
            if not chain or not pair or not token:continue
            observed+=1; key=_pair_key(chain,pair); prev=pools_state.get(key) or {}
            liq=float(p.get("liquidity_usd") or 0); prev_liq=float(prev.get("last_liquidity_usd") or 0)
            delta=liq-prev_liq if prev else 0.0
            pct=((liq/prev_liq)-1.0)*100.0 if prev and prev_liq>0 else None
            age=_pool_age_minutes(p.get("pair_created_at"),now_dt)
            reasons=[]; score=0
            if prev:
                if delta>=10000 and pct is not None and pct>=50:
                    reasons.append("LIQUIDITY_SURGE_50PCT_PLUS");score+=35
                if prev_liq<20000<=liq and delta>=10000:
                    reasons.append("LIQUIDITY_THRESHOLD_BREAKOUT_20K");score+=25
                if prev_liq<40000<=liq and delta>=15000:
                    reasons.append("LIQUIDITY_THRESHOLD_BREAKOUT_40K");score+=25
                if delta>=50000:
                    reasons.append("MAJOR_LIQUIDITY_INFLOW_50K");score+=40
                elif delta>=25000:
                    reasons.append("STRONG_LIQUIDITY_INFLOW_25K");score+=25
            elif age is not None and age<=120 and liq>=25000:
                reasons.append("NEW_POOL_FUNDED_25K_PLUS");score+=35
            vol=float(p.get("volume_h1") or 0); buys=int(p.get("buys_h1") or 0); sells=int(p.get("sells_h1") or 0)
            if reasons and vol>=15000:
                reasons.append("LIQUIDITY_PLUS_ACTIVE_VOLUME");score+=15
            if reasons and buys>=50 and buys>sells:
                reasons.append("BUYER_CONFIRMATION");score+=10
            score=min(100,score)
            if reasons:
                signals.append({"chain":chain,"token":token,"pair_address":pair,"dex":p.get("dex"),"url":p.get("url"),"liquidity_usd":round(liq,2),"previous_liquidity_usd":round(prev_liq,2) if prev else None,"liquidity_delta_usd":round(delta,2) if prev else None,"liquidity_change_pct":round(pct,2) if pct is not None else None,"pool_age_minutes":round(age,1) if age is not None else None,"volume_h1":vol,"buys_h1":buys,"sells_h1":sells,"liquidity_signal_score":score,"reasons":reasons,"observed_at":now})
            pools_state[key]={"chain":chain,"token":token,"pair_address":pair,"dex":p.get("dex"),"first_seen":prev.get("first_seen") or now,"last_seen":now,"observations":int(prev.get("observations") or 0)+1,"last_liquidity_usd":liq,"peak_liquidity_usd":max(float(prev.get("peak_liquidity_usd") or 0),liq),"last_price_usd":p.get("price_usd"),"last_volume_h1":vol,"pair_created_at":p.get("pair_created_at")}
    signals.sort(key=lambda x:(x.get("liquidity_signal_score",0),x.get("liquidity_delta_usd") or 0),reverse=True)
    payload={"version":1,"method":"PAIR_LEVEL_LIQUIDITY_INFLOW_RADAR","updated_at":now,"observed_pools":observed,"signals":signals[:100]}
    _write(state_path,{"version":1,"updated_at":now,"pools":pools_state})
    _write(output_dir/"pool-liquidity-radar.json",payload)
    return payload
