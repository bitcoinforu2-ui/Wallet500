from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
HORIZONS = ((5,"5m"),(15,"15m"),(30,"30m"),(60,"1h"),(240,"4h"),(720,"12h"),(1440,"24h"))


def _load(path: Path, default):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _key(chain: str, token: str) -> str:
    token = token or ""
    if chain in {"ethereum","bsc"}:
        token = token.lower()
    return f"{chain}:{token}"


def _pct(cur, base):
    try:
        cur=float(cur); base=float(base)
        return round((cur/base-1.0)*100.0, 4) if base > 0 else None
    except Exception:
        return None


def _dt(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception:
        return None


def _snapshot_sources() -> dict[str,dict]:
    rows = {}
    files = (
        "market-snapshots.json","revival-snapshots.json","fresh-solana-survival.json",
        "active-qualified-candidates.json","live-survival-pending.json","live-survival-failed.json",
        "production-risk-evaluations.json","production-risk-blocked.json"
    )
    for name in files:
        data=_load(DATA/name,[])
        if not isinstance(data,list):
            continue
        for x in data:
            if not isinstance(x,dict):
                continue
            chain=x.get("chain"); token=x.get("token") or x.get("mint")
            if chain and token and x.get("price_usd") not in (None,0,0.0):
                rows[_key(chain,token)] = x
    return rows


def _leader_row(x: dict) -> dict:
    hist=x.get("history") if isinstance(x.get("history"),list) else []
    last=hist[-1] if hist else {}
    return {
        "chain":x.get("chain"),"token":x.get("token"),
        "pair_address":x.get("entry_pair_address"),"dex":x.get("entry_dex") or last.get("dex"),
        "discovery_time":x.get("first_seen"),"tracking_started_at":x.get("tracking_started_at"),
        "entry_price_usd":x.get("entry_price_usd"),"current_price_usd":x.get("current_price_usd"),
        "current_return_pct":x.get("current_return_pct"),"peak_price_usd":x.get("peak_price_usd"),
        "peak_return_pct":x.get("peak_return_pct"),"low_price_usd":x.get("low_price_usd"),
        "low_return_pct":x.get("low_return_pct"),"liquidity_usd":last.get("liquidity_usd"),
        "volume_h1":last.get("volume_h1"),"updated_at":x.get("updated_at"),
        "measurement_status":x.get("measurement_status"),"checkpoints":x.get("checkpoints") or {}
    }


def run() -> dict:
    now=datetime.now(timezone.utc); now_s=now.isoformat()
    state=_load(DATA/"discovery-state.json",{})
    tokens=state.get("tokens") if isinstance(state,dict) and isinstance(state.get("tokens"),dict) else {}
    old=_load(DATA/"outcome-tracker.json",{})
    old_records=old.get("tokens") if isinstance(old,dict) and isinstance(old.get("tokens"),dict) else {}
    live=_snapshot_sources()

    records=dict(old_records)
    seeded=updated=0

    for key,meta in tokens.items():
        if not isinstance(meta,dict):
            continue
        try: entry=float(meta.get("entry_price_usd") or 0)
        except Exception: entry=0.0
        if entry <= 0:
            continue
        chain=meta.get("chain"); token=meta.get("token")
        if not chain or not token:
            continue
        rec=records.get(key) if isinstance(records.get(key),dict) else {}
        if not rec: seeded += 1
        entry_pair=meta.get("entry_pair_address") or rec.get("entry_pair_address")
        tracking_started=meta.get("tracking_started_at") or rec.get("tracking_started_at") or meta.get("first_seen")
        currow=live.get(key); current=None; verified=False; current_pair=None
        if isinstance(currow,dict):
            current_pair=currow.get("pair_address")
            if entry_pair and current_pair and str(entry_pair).lower()==str(current_pair).lower():
                current=currow.get("price_usd"); verified=True
        history=rec.get("history") if isinstance(rec.get("history"),list) else []
        checkpoints=rec.get("checkpoints") if isinstance(rec.get("checkpoints"),dict) else {}
        peak=float(rec.get("peak_price_usd") or entry); low=float(rec.get("low_price_usd") or entry)
        if verified and current not in (None,0,0.0):
            current=float(current); updated += 1; peak=max(peak,current); low=min(low,current); ret=_pct(current,entry)
            history.append({"observed_at":now_s,"price_usd":current,"return_pct":ret,"pair_address":current_pair,"dex":currow.get("dex"),"liquidity_usd":currow.get("liquidity_usd"),"volume_h1":currow.get("volume_h1"),"buys_h1":currow.get("buys_h1"),"sells_h1":currow.get("sells_h1")})
            history=history[-500:]
            start=_dt(tracking_started); age=max(0.0,(now-start).total_seconds()/60.0) if start else 0.0
            for mins,label in HORIZONS:
                if age >= mins and label not in checkpoints:
                    checkpoints[label]={"price_usd":current,"return_pct":ret,"captured_at":now_s,"pair_address":current_pair}
        else:
            current=rec.get("current_price_usd"); ret=rec.get("current_return_pct"); age=rec.get("age_minutes")
        records[key]={**rec,"chain":chain,"token":token,"first_seen":meta.get("first_seen") or rec.get("first_seen"),"tracking_started_at":tracking_started,"legacy_price_tracking":bool(meta.get("legacy_price_tracking",rec.get("legacy_price_tracking",False))),"entry_price_usd":entry,"entry_pair_address":entry_pair,"entry_dex":meta.get("entry_dex") or rec.get("entry_dex"),"pair_identity_status":"LOCKED" if entry_pair else "LEGACY_MISSING_IMMUTABLE_PAIR","current_pair_address":current_pair if verified else rec.get("current_pair_address"),"current_price_usd":current,"current_return_pct":ret,"peak_price_usd":peak,"peak_return_pct":_pct(peak,entry),"low_price_usd":low,"low_return_pct":_pct(low,entry),"age_minutes":round(age,2) if isinstance(age,(int,float)) else age,"checkpoints":checkpoints,"history":history,"updated_at":now_s if verified else rec.get("updated_at"),"measurement_status":"VERIFIED_EXACT_PAIR" if verified else ("AWAITING_EXACT_PAIR_OBSERVATION" if entry_pair else "LEGACY_UNVERIFIABLE_PAIR")}

    if not records and old_records: records=old_records
    verified=[x for x in records.values() if x.get("measurement_status")=="VERIFIED_EXACT_PAIR" and x.get("current_return_pct") is not None]
    positive=sum(1 for x in verified if float(x.get("current_return_pct") or 0)>0)
    negative=sum(1 for x in verified if float(x.get("current_return_pct") or 0)<0)
    flat=len(verified)-positive-negative
    payload={"version":4,"method":"IMMUTABLE_PERFORMANCE_SINCE_DISCOVERY_EXACT_PAIR","updated_at":now_s,"tracked_tokens":len(records),"seeded_from_discovery_state":seeded,"updated_this_run":updated,"verified_positive_now":positive,"verified_negative_now":negative,"verified_flat_now":flat,"anti_erasure_rule":"NON_EMPTY_TRACK_RECORD_MAY_NEVER_BE_REPLACED_BY_EMPTY_OUTPUT","tokens":records}
    _write(DATA/"outcome-tracker.json",payload)
    _write(DATA/"signal-outcomes.json",list(records.values()))
    leaders=sorted((_leader_row(x) for x in verified),key=lambda x:float(x.get("current_return_pct") or 0),reverse=True)
    win_rate=round(positive/(positive+negative)*100,2) if positive+negative else 0.0
    leaderboard={"updated_at":now_s,"verified_count":len(leaders),"verified_winners":positive,"verified_losers":negative,"verified_flat":flat,"win_rate_pct":win_rate,"best_current_return_pct":leaders[0].get("current_return_pct") if leaders else None,"best_peak_return_pct":max((float(x.get("peak_return_pct") or 0) for x in leaders),default=None),"rows":leaders}
    _write(DATA/"performance-leaderboard.json",leaderboard)
    _write(DATA/"performance-measurement-report.json",{"updated_at":now_s,"tracked_tokens":len(records),"seeded":seeded,"updated":updated,"verified_positive_now":positive,"verified_negative_now":negative,"verified_flat_now":flat,"verified_exact_pair_now":len(verified),"win_rate_pct":win_rate,"legacy_missing_pair":sum(1 for x in records.values() if x.get("pair_identity_status")!="LOCKED")})
    print(json.dumps({"tracked_tokens":len(records),"updated_this_run":updated,"verified_exact_pair_now":len(verified),"verified_positive_now":positive,"verified_negative_now":negative,"win_rate_pct":win_rate},indent=2))
    return payload


if __name__=="__main__": run()
