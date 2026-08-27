import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .market_pipeline import run_market_scan


def _write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_json(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default


def _load_manual_watchlist(out: Path) -> list[dict]:
    data = _load_json(out / "manual-watchlist.json", [])
    return data if isinstance(data, list) else []


def _token_key(chain: str, token: str) -> str:
    token = token or ""
    if chain in {"ethereum", "bsc"}: token = token.lower()
    return f"{chain}:{token}"


def _snapshot_map(snapshots: list[dict]) -> dict[str, dict]:
    out={}
    for x in snapshots:
        chain=x.get("chain"); token=x.get("token") or x.get("mint")
        if chain and token: out[_token_key(chain,token)]=x
    return out


def _pct(cur, base):
    try:
        cur=float(cur); base=float(base)
        if base<=0: return None
        return round((cur/base-1.0)*100.0,4)
    except Exception:
        return None


def _update_discovery_state(out: Path, universe: list[dict], snapshots: list[dict], next_pages: dict, now: str):
    path=out/"discovery-state.json"; state=_load_json(path,{})
    if not isinstance(state,dict): state={}
    tokens=state.get("tokens") if isinstance(state.get("tokens"),dict) else {}
    snap=_snapshot_map(snapshots)
    new_count=revisited_count=0
    by_chain={"solana":{"new":0,"revisited":0},"ethereum":{"new":0,"revisited":0},"bsc":{"new":0,"revisited":0}}
    annotated=[]
    for row in universe:
        chain=row.get("chain"); token=row.get("token") or row.get("mint"); key=_token_key(chain,token); prev=tokens.get(key)
        price=(snap.get(key) or {}).get("price_usd")
        if prev:
            revisited_count+=1; by_chain.setdefault(chain,{"new":0,"revisited":0})["revisited"]+=1
            first_seen=prev.get("first_seen",now); scan_count=int(prev.get("scan_count",0))+1; status="REVISITED"
            entry_price=prev.get("entry_price_usd"); tracking_started_at=prev.get("tracking_started_at")
            legacy=bool(prev.get("legacy_price_tracking",False))
            if entry_price is None and price not in (None,0,0.0):
                entry_price=price; tracking_started_at=now; legacy=True
        else:
            new_count+=1; by_chain.setdefault(chain,{"new":0,"revisited":0})["new"]+=1
            first_seen=now; scan_count=1; status="NEW"
            entry_price=price if price not in (None,0,0.0) else None
            tracking_started_at=now if entry_price is not None else None; legacy=False
        tokens[key]={"chain":chain,"token":token,"first_seen":first_seen,"last_seen":now,"scan_count":scan_count,"last_source":row.get("source"),"last_discovery_page":row.get("discovery_page"),"entry_price_usd":entry_price,"tracking_started_at":tracking_started_at,"legacy_price_tracking":legacy}
        annotated.append({**row,"discovery_status":status,"first_seen":first_seen,"last_seen":now,"scan_count":scan_count,"entry_price_usd":entry_price,"tracking_started_at":tracking_started_at,"legacy_price_tracking":legacy})
    runs=int(state.get("runs",0))+1
    state={"version":2,"runs":runs,"updated_at":now,"source_cursor":next_pages or state.get("source_cursor",{}),"unique_tokens_total":len(tokens),"last_run":{"discovered":len(universe),"new":new_count,"revisited":revisited_count,"new_ratio":round(new_count/len(universe),4) if universe else 0.0,"by_chain":by_chain},"tokens":tokens}
    _write(path,state); return state,annotated


def _update_outcomes(out: Path, state: dict, snapshots: list[dict], now: str) -> dict:
    path=out/"outcome-tracker.json"; tracker=_load_json(path,{})
    if not isinstance(tracker,dict): tracker={}
    records=tracker.get("tokens") if isinstance(tracker.get("tokens"),dict) else {}
    snap=_snapshot_map(snapshots)
    horizons=((5,"5m"),(15,"15m"),(30,"30m"),(60,"1h"),(240,"4h"),(720,"12h"),(1440,"24h"))
    now_dt=datetime.fromisoformat(now.replace("Z","+00:00")); updated=0
    for key,s in snap.items():
        meta=(state.get("tokens") or {}).get(key) or {}; entry=meta.get("entry_price_usd"); current=s.get("price_usd")
        if entry in (None,0,0.0) or current in (None,0,0.0): continue
        rec=records.get(key) if isinstance(records.get(key),dict) else {}
        tracking_started_at=meta.get("tracking_started_at") or rec.get("tracking_started_at") or now
        try: start_dt=datetime.fromisoformat(tracking_started_at.replace("Z","+00:00"))
        except Exception: start_dt=now_dt
        age_min=max(0.0,(now_dt-start_dt).total_seconds()/60.0)
        peak=max(float(rec.get("peak_price_usd") or current),float(current)); low=min(float(rec.get("low_price_usd") or current),float(current))
        checkpoints=rec.get("checkpoints") if isinstance(rec.get("checkpoints"),dict) else {}
        for mins,label in horizons:
            if age_min>=mins and label not in checkpoints: checkpoints[label]={"price_usd":current,"return_pct":_pct(current,entry),"captured_at":now}
        history=rec.get("history") if isinstance(rec.get("history"),list) else []
        history.append({"observed_at":now,"price_usd":current,"return_pct":_pct(current,entry),"liquidity_usd":s.get("liquidity_usd"),"volume_h1":s.get("volume_h1"),"buys_h1":s.get("buys_h1"),"sells_h1":s.get("sells_h1")}); history=history[-200:]
        records[key]={"chain":meta.get("chain") or s.get("chain"),"token":meta.get("token") or s.get("token") or s.get("mint"),"first_seen":meta.get("first_seen"),"tracking_started_at":tracking_started_at,"legacy_price_tracking":bool(meta.get("legacy_price_tracking",False)),"entry_price_usd":entry,"current_price_usd":current,"current_return_pct":_pct(current,entry),"peak_price_usd":peak,"peak_return_pct":_pct(peak,entry),"low_price_usd":low,"low_return_pct":_pct(low,entry),"age_minutes":round(age_min,2),"checkpoints":checkpoints,"history":history,"updated_at":now}; updated+=1
    tracker={"version":1,"method":"VERIFIED_POST_DISCOVERY_PRICE_TRACKING","note":"Legacy tokens without a stored historical discovery price begin verified price tracking from the first scan after this feature was deployed; no retroactive entry price is invented.","updated_at":now,"tracked_tokens":len(records),"updated_this_run":updated,"tokens":records}
    _write(path,tracker); _write(out/"signal-outcomes.json",list(records.values())); return tracker


def _pump_dump_risk(x: dict, outcomes: dict) -> dict:
    """Heuristic manipulation gate using only verified market/outcome data we actually have.
    It is intentionally conservative: high momentum alone never blocks a token.
    """
    chain=x.get("chain"); token=x.get("token") or x.get("mint"); key=_token_key(chain,token)
    rec=((outcomes or {}).get("tokens") or {}).get(key) or {}
    liq=float(x.get("liquidity_usd") or 0); vol=float(x.get("volume_h1") or 0)
    buys=int(x.get("buys_h1") or 0); sells=int(x.get("sells_h1") or 0); tx=buys+sells
    h1=float(x.get("price_change_h1") or 0); m5=float(x.get("price_change_m5") or 0)
    turnover=(vol/max(liq,1.0)) if vol>0 else 0.0; ratio=(buys/max(sells,1)) if buys or sells else 0.0
    score=0; reasons=[]; critical=[]

    if liq<=0:
        score+=100; critical.append("ZERO_LIQUIDITY")
    elif liq<10000:
        score+=35; reasons.append("VERY_LOW_LIQUIDITY")
    elif liq<20000:
        score+=15; reasons.append("LOW_LIQUIDITY")

    if turnover>=25:
        score+=30; reasons.append("EXTREME_VOLUME_TO_LIQUIDITY")
    elif turnover>=12:
        score+=18; reasons.append("HIGH_VOLUME_TO_LIQUIDITY")

    # Extreme pump is only suspicious when paired with weak market structure.
    if h1>=1000 and (liq<50000 or turnover>=8):
        score+=35; reasons.append("EXTREME_1H_PUMP_WITH_FRAGILE_STRUCTURE")
    elif h1>=400 and (liq<30000 or turnover>=12):
        score+=22; reasons.append("PARABOLIC_1H_MOVE")

    if h1>150 and m5<=-12:
        score+=28; reasons.append("PUMP_THEN_5M_REVERSAL")
    if sells>=80 and ratio<0.70:
        score+=25; reasons.append("SELL_PRESSURE_DOMINANT")
    if tx>=100 and ratio<0.50:
        score+=20; reasons.append("SEVERE_BUYER_EXHAUSTION")

    entry=float(rec.get("entry_price_usd") or 0); cur=float(rec.get("current_price_usd") or 0); peak=float(rec.get("peak_price_usd") or 0)
    if peak>0 and cur>0:
        drawdown=(cur/peak-1.0)*100.0
        if drawdown<=-60:
            score+=55; critical.append("POST_DISCOVERY_CRASH_GT_60PCT")
        elif drawdown<=-40:
            score+=35; reasons.append("POST_DISCOVERY_DRAWDOWN_GT_40PCT")
        elif drawdown<=-25:
            score+=18; reasons.append("POST_DISCOVERY_DRAWDOWN_GT_25PCT")
    if entry>0 and cur>0 and _pct(cur,entry) is not None and _pct(cur,entry)<=-50:
        score+=30; reasons.append("LOSS_FROM_VERIFIED_ENTRY_GT_50PCT")

    history=rec.get("history") if isinstance(rec.get("history"),list) else []
    if len(history)>=2:
        prev=history[-2]; prev_liq=float(prev.get("liquidity_usd") or 0); prev_buys=int(prev.get("buys_h1") or 0)
        if prev_liq>=20000 and liq>0 and liq/prev_liq<=0.55:
            score+=45; critical.append("LIQUIDITY_REMOVAL_GT_45PCT")
        if prev_buys>=100 and buys/prev_buys<=0.35 and sells>buys:
            score+=25; reasons.append("BUYER_ACTIVITY_COLLAPSE")

    score=min(100,int(score)); blocked=score>=70 or bool(critical)
    level="CRITICAL" if critical or score>=85 else "HIGH" if score>=70 else "MEDIUM" if score>=40 else "LOW"
    return {"pump_dump_risk_score":score,"pump_dump_risk_level":level,"pump_dump_blocked":blocked,"pump_dump_reasons":critical+reasons,"pump_dump_critical":critical}


def _qualify(x: dict, now: str, outcomes: dict) -> dict:
    score=float(x.get("anomaly_score") or 0); liq=float(x.get("liquidity_usd") or 0); vol=float(x.get("volume_h1") or 0)
    buys=int(x.get("buys_h1") or 0); sells=int(x.get("sells_h1") or 0); tx=buys+sells
    risk=_pump_dump_risk(x,outcomes); failed=[]
    if score < 80: failed.append("ANOMALY_SCORE_LT_80")
    if liq < 20000: failed.append("LIQUIDITY_LT_20K")
    if vol < 15000: failed.append("VOLUME_1H_LT_15K")
    if tx < 50: failed.append("ACTIVITY_LT_50_TX_1H")
    if risk["pump_dump_blocked"]: failed.append("PUMP_DUMP_RISK_GATE")
    status="PUMP_DUMP_RISK" if risk["pump_dump_blocked"] else ("QUALIFIED" if not failed else "REJECTED")
    return {**x,**risk,"qualification":status,"qualification_reasons":failed or ["PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION"],"qualified_at":now if status=="QUALIFIED" else None,"evaluated_at":now}


def run():
    cfg=Settings(); out=Path(cfg.output_dir); out.mkdir(parents=True,exist_ok=True); now=datetime.now(timezone.utc).isoformat()
    previous=_load_json(out/"discovery-state.json",{}); start_pages=previous.get("source_cursor",{}) if isinstance(previous,dict) else {}
    market=run_market_scan(limit_per_chain=120,threshold=45.0,start_pages=start_pages); snapshots=market["snapshots"]
    state,universe=_update_discovery_state(out,market["universe"],snapshots,market.get("next_pages",{}),now)
    outcomes=_update_outcomes(out,state,snapshots,now); anomalies=market["anomalies"]

    qualification=[_qualify(x,now,outcomes) for x in anomalies]
    qualified=[x for x in qualification if x["qualification"]=="QUALIFIED"]
    pump_dump=[x for x in qualification if x["qualification"]=="PUMP_DUMP_RISK"]
    rejected=[x for x in qualification if x["qualification"]=="REJECTED"]

    automatic_watch=[{**x,"watch_source":"ANOMALY_RADAR"} for x in anomalies[:100]]
    manual_watch=_load_manual_watchlist(out); seen={(x.get("chain"),x.get("token") or x.get("mint")) for x in automatic_watch}; watch=list(automatic_watch)
    for x in manual_watch:
        key=(x.get("chain"),x.get("token") or x.get("mint"))
        if key not in seen: watch.append({**x,"watch_source":"MANUAL_RESEARCH"}); seen.add(key)

    review=[{**x,"stage":"HISTORICAL_DEEP_SCAN_QUEUED","queued_at":now,"next_stage":"WALLET_DISCOVERY_FORENSICS"} for x in watch]
    pipeline={"flow":["MULTI_CHAIN_MARKET_SCAN","GLOBAL_ANOMALY_RADAR","QUALITY_GATE","PUMP_DUMP_RISK_GATE","WATCHLIST","HISTORICAL_DEEP_SCAN","WALLET_DISCOVERY_FORENSICS","OPERATOR_ELITE_SCORING","BEHAVIOR_LEARNING","SIGNAL_CORRELATION","OUTCOME_TRACKING","LIVE_DASHBOARD"],"current":{"MULTI_CHAIN_MARKET_SCAN":len(universe),"GLOBAL_ANOMALY_RADAR":len(anomalies),"QUALITY_GATE_QUALIFIED":len(qualified),"PUMP_DUMP_RISK":len(pump_dump),"QUALITY_GATE_REJECTED":len(rejected),"WATCHLIST":len(watch),"HISTORICAL_DEEP_SCAN":len(review),"OUTCOME_TRACKED":outcomes.get("tracked_tokens",0)},"discovery_health":state.get("last_run",{}),"unique_tokens_total":state.get("unique_tokens_total",0),"scan_runs_total":state.get("runs",0),"updated_at":now,"verified_only":True}

    _write(out/"market-universe.json",universe); _write(out/"market-snapshots.json",snapshots); _write(out/"anomaly-radar.json",anomalies)
    _write(out/"qualification-results.json",qualification); _write(out/"qualified-candidates.json",qualified); _write(out/"pump-dump-risk.json",pump_dump); _write(out/"rejected-candidates.json",rejected)
    _write(out/"watchlist.json",watch); _write(out/"historical-review-queue.json",review); _write(out/"pipeline-status.json",pipeline)
    result={"mode":"market-first","verified_only":True,"chains":market["chains"],"counts":market["counts"],"universe":len(universe),"snapshots":len(snapshots),"anomalies":len(anomalies),"qualified":len(qualified),"pump_dump_risk":len(pump_dump),"rejected":len(rejected),"watchlist":len(watch),"historical_review_queued":len(review),"outcome_tracked":outcomes.get("tracked_tokens",0),"manual_research_cases":len(manual_watch),"discovery":state.get("last_run",{}),"unique_tokens_total":state.get("unique_tokens_total",0),"scan_runs_total":state.get("runs",0),"updated_at":now}
    _write(out/"run-summary.json",result); return result

if __name__=="__main__": print(json.dumps(run(),indent=2))
