import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .market_pipeline import run_market_scan
from .revival_radar import run_revival_scan
from .market_data import snapshot as market_snapshot


def _write(path,payload): Path(path).write_text(json.dumps(payload,indent=2),encoding="utf-8")
def _load_json(path,default):
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception: return default
def _token_key(chain,token): return f"{chain}:{(token or '').lower() if chain in {'ethereum','bsc'} else (token or '')}"
def _snapshot_map(rows): return {_token_key(x.get('chain'),x.get('token') or x.get('mint')):x for x in rows or [] if x.get('chain') and (x.get('token') or x.get('mint'))}
def _merge_snapshots(*groups):
    rows={}
    for group in groups:
        rows.update(_snapshot_map(group))
    return list(rows.values())
def _pct(cur,base):
    try:
        cur=float(cur);base=float(base);return round((cur/base-1)*100,4) if base>0 else None
    except Exception:return None


def _update_discovery_state(out,universe,snapshots,next_pages,now):
    path=out/'discovery-state.json';state=_load_json(path,{})
    if not isinstance(state,dict):state={}
    tokens=state.get('tokens') if isinstance(state.get('tokens'),dict) else {};snap=_snapshot_map(snapshots);new=revisited=0
    by_chain={c:{'new':0,'revisited':0} for c in ('solana','ethereum','bsc')};annotated=[]
    for row in universe:
        chain=row.get('chain');token=row.get('token') or row.get('mint');key=_token_key(chain,token);prev=tokens.get(key);sx=snap.get(key) or {};price=sx.get('price_usd');pair=sx.get('pair_address');dex=sx.get('dex')
        if prev:
            revisited+=1;by_chain.setdefault(chain,{'new':0,'revisited':0})['revisited']+=1;first=prev.get('first_seen',now);count=int(prev.get('scan_count',0))+1;status='REVISITED';entry=prev.get('entry_price_usd');started=prev.get('tracking_started_at');legacy=bool(prev.get('legacy_price_tracking',False));entry_pair=prev.get('entry_pair_address');entry_dex=prev.get('entry_dex')
            if entry is None and price not in (None,0,0.0):entry=price;started=now;legacy=True;entry_pair=pair;entry_dex=dex
            elif entry is not None and not entry_pair and pair:entry_pair=pair;entry_dex=entry_dex or dex
        else:
            new+=1;by_chain.setdefault(chain,{'new':0,'revisited':0})['new']+=1;first=now;count=1;status='NEW';entry=price if price not in (None,0,0.0) else None;started=now if entry is not None else None;legacy=False;entry_pair=pair if entry is not None else None;entry_dex=dex if entry is not None else None
        tokens[key]={'chain':chain,'token':token,'first_seen':first,'last_seen':now,'scan_count':count,'last_source':row.get('source'),'last_discovery_page':row.get('discovery_page'),'entry_price_usd':entry,'tracking_started_at':started,'legacy_price_tracking':legacy,'entry_pair_address':entry_pair,'entry_dex':entry_dex}
        annotated.append({**row,'discovery_status':status,'first_seen':first,'last_seen':now,'scan_count':count,'entry_price_usd':entry,'tracking_started_at':started,'legacy_price_tracking':legacy,'entry_pair_address':entry_pair,'entry_dex':entry_dex})
    runs=int(state.get('runs',0))+1;state={'version':3,'runs':runs,'updated_at':now,'source_cursor':next_pages or state.get('source_cursor',{}),'unique_tokens_total':len(tokens),'last_run':{'discovered':len(universe),'new':new,'revisited':revisited,'new_ratio':round(new/len(universe),4) if universe else 0.0,'by_chain':by_chain},'tokens':tokens};_write(path,state);return state,annotated


def _ensure_revival_tracking(out,state,snapshots,now):
    tokens=state.get('tokens') if isinstance(state.get('tokens'),dict) else {};changed=False
    for s in snapshots or []:
        chain=s.get('chain');token=s.get('token') or s.get('mint')
        if not chain or not token:continue
        key=_token_key(chain,token);price=s.get('price_usd');rec=tokens.get(key);pair=s.get('pair_address');dex=s.get('dex')
        if rec:
            if rec.get('entry_price_usd') in (None,0,0.0) and price not in (None,0,0.0):rec.update({'entry_price_usd':price,'tracking_started_at':now,'legacy_price_tracking':True,'entry_pair_address':pair,'entry_dex':dex});changed=True
            elif rec.get('entry_price_usd') not in (None,0,0.0) and not rec.get('entry_pair_address') and pair:rec['entry_pair_address']=pair;rec['entry_dex']=dex;changed=True
        else:tokens[key]={'chain':chain,'token':token,'first_seen':now,'last_seen':now,'scan_count':0,'last_source':'REVIVAL_RADAR','last_discovery_page':None,'entry_price_usd':price if price not in (None,0,0.0) else None,'tracking_started_at':now if price not in (None,0,0.0) else None,'legacy_price_tracking':True,'entry_pair_address':pair if price not in (None,0,0.0) else None,'entry_dex':dex if price not in (None,0,0.0) else None};changed=True
    if changed:state['tokens']=tokens;state['unique_tokens_total']=len(tokens);state['updated_at']=now;_write(out/'discovery-state.json',state)
    return state


def _update_outcomes(out,state,snapshots,now):
    path=out/'outcome-tracker.json';tracker=_load_json(path,{})
    if not isinstance(tracker,dict):tracker={}
    records=tracker.get('tokens') if isinstance(tracker.get('tokens'),dict) else {};snap=_snapshot_map(snapshots);horizons=((5,'5m'),(15,'15m'),(30,'30m'),(60,'1h'),(240,'4h'),(720,'12h'),(1440,'24h'));now_dt=datetime.fromisoformat(now.replace('Z','+00:00'));updated=refetched=unavailable=0
    for key,s in list(snap.items()):
        meta=(state.get('tokens') or {}).get(key) or {};entry=meta.get('entry_price_usd');entry_pair=meta.get('entry_pair_address')
        if entry in (None,0,0.0):continue
        current_pair=s.get('pair_address')
        if entry_pair and (not current_pair or str(entry_pair).lower()!=str(current_pair).lower()):
            locked=market_snapshot(meta.get('chain') or s.get('chain'),meta.get('token') or s.get('token') or s.get('mint'),entry_pair)
            if not locked or locked.get('price_usd') in (None,0,0.0):unavailable+=1;continue
            s=locked;current_pair=s.get('pair_address');refetched+=1
        current=s.get('price_usd')
        if current in (None,0,0.0):continue
        rec=records.get(key) if isinstance(records.get(key),dict) else {};started=meta.get('tracking_started_at') or rec.get('tracking_started_at') or now
        try:start_dt=datetime.fromisoformat(started.replace('Z','+00:00'))
        except Exception:start_dt=now_dt
        age=max(0,(now_dt-start_dt).total_seconds()/60);peak=max(float(rec.get('peak_price_usd') or current),float(current));low=min(float(rec.get('low_price_usd') or current),float(current));checkpoints=rec.get('checkpoints') if isinstance(rec.get('checkpoints'),dict) else {}
        for mins,label in horizons:
            if age>=mins and label not in checkpoints:checkpoints[label]={'price_usd':current,'return_pct':_pct(current,entry),'captured_at':now,'pair_address':current_pair}
        history=rec.get('history') if isinstance(rec.get('history'),list) else [];history.append({'observed_at':now,'price_usd':current,'return_pct':_pct(current,entry),'pair_address':current_pair,'dex':s.get('dex'),'liquidity_usd':s.get('liquidity_usd'),'volume_h1':s.get('volume_h1'),'buys_h1':s.get('buys_h1'),'sells_h1':s.get('sells_h1')});history=history[-200:]
        records[key]={'chain':meta.get('chain') or s.get('chain'),'token':meta.get('token') or s.get('token') or s.get('mint'),'first_seen':meta.get('first_seen'),'tracking_started_at':started,'legacy_price_tracking':bool(meta.get('legacy_price_tracking',False)),'entry_price_usd':entry,'entry_pair_address':entry_pair or current_pair,'entry_dex':meta.get('entry_dex') or s.get('dex'),'current_pair_address':current_pair,'current_price_usd':current,'current_return_pct':_pct(current,entry),'peak_price_usd':peak,'peak_return_pct':_pct(peak,entry),'low_price_usd':low,'low_return_pct':_pct(low,entry),'age_minutes':round(age,2),'checkpoints':checkpoints,'history':history,'updated_at':now};updated+=1
    tracker={'version':2,'method':'VERIFIED_POST_DISCOVERY_PRICE_TRACKING_PAIR_LOCKED','note':'Verified ROI is always measured on the immutable discovery pair. If general market discovery selects a different pool, Wallet500 re-fetches the original pair; if that pair is unavailable, the verified record is not updated.','updated_at':now,'tracked_tokens':len(records),'updated_this_run':updated,'pair_mismatch_refetched':refetched,'pair_unavailable':unavailable,'tokens':records};_write(path,tracker);_write(out/'signal-outcomes.json',list(records.values()));return tracker


def _pump_dump_risk(x,outcomes):
    key=_token_key(x.get('chain'),x.get('token') or x.get('mint'));rec=((outcomes or {}).get('tokens') or {}).get(key) or {};liq=float(x.get('liquidity_usd') or 0);vol=float(x.get('volume_h1') or 0);buys=int(x.get('buys_h1') or 0);sells=int(x.get('sells_h1') or 0);tx=buys+sells;h1=float(x.get('price_change_h1') or 0);m5=float(x.get('price_change_m5') or 0);turnover=vol/max(liq,1) if vol>0 else 0;ratio=buys/max(sells,1) if tx else 0;score=0;reasons=[];critical=[]
    if liq<=0:score+=100;critical.append('ZERO_LIQUIDITY')
    elif liq<10000:score+=35;reasons.append('VERY_LOW_LIQUIDITY')
    elif liq<20000:score+=15;reasons.append('LOW_LIQUIDITY')
    if turnover>=25:score+=30;reasons.append('EXTREME_VOLUME_TO_LIQUIDITY')
    elif turnover>=12:score+=18;reasons.append('HIGH_VOLUME_TO_LIQUIDITY')
    if h1>=1000 and (liq<50000 or turnover>=8):score+=35;reasons.append('EXTREME_1H_PUMP_WITH_FRAGILE_STRUCTURE')
    elif h1>=400 and (liq<30000 or turnover>=12):score+=22;reasons.append('PARABOLIC_1H_MOVE')
    if h1>150 and m5<=-12:score+=28;reasons.append('PUMP_THEN_5M_REVERSAL')
    if sells>=80 and ratio<.70:score+=25;reasons.append('SELL_PRESSURE_DOMINANT')
    if tx>=100 and ratio<.50:score+=20;reasons.append('SEVERE_BUYER_EXHAUSTION')
    entry=float(rec.get('entry_price_usd') or 0);cur=float(rec.get('current_price_usd') or 0);peak=float(rec.get('peak_price_usd') or 0)
    if peak>0 and cur>0:
        dd=(cur/peak-1)*100
        if dd<=-60:score+=55;critical.append('POST_DISCOVERY_CRASH_GT_60PCT')
        elif dd<=-40:score+=35;reasons.append('POST_DISCOVERY_DRAWDOWN_GT_40PCT')
        elif dd<=-25:score+=18;reasons.append('POST_DISCOVERY_DRAWDOWN_GT_25PCT')
    if entry>0 and cur>0 and (_pct(cur,entry) or 0)<=-50:score+=30;reasons.append('LOSS_FROM_VERIFIED_ENTRY_GT_50PCT')
    history=rec.get('history') if isinstance(rec.get('history'),list) else []
    if len(history)>=2:
        prev=history[-2];prev_liq=float(prev.get('liquidity_usd') or 0);prev_buys=int(prev.get('buys_h1') or 0)
        if prev_liq>=20000 and liq>0 and liq/prev_liq<=.55:score+=45;critical.append('LIQUIDITY_REMOVAL_GT_45PCT')
        if prev_buys>=100 and buys/prev_buys<=.35 and sells>buys:score+=25;reasons.append('BUYER_ACTIVITY_COLLAPSE')
    score=min(100,int(score));blocked=score>=70 or bool(critical);level='CRITICAL' if critical or score>=85 else 'HIGH' if score>=70 else 'MEDIUM' if score>=40 else 'LOW';return {'pump_dump_risk_score':score,'pump_dump_risk_level':level,'pump_dump_blocked':blocked,'pump_dump_reasons':critical+reasons,'pump_dump_critical':critical}


def _qualify(x,now,outcomes):
    cfg=Settings();score=float(x.get('anomaly_score') or 0);liq=float(x.get('liquidity_usd') or 0);vol=float(x.get('volume_h1') or 0);tx=int(x.get('buys_h1') or 0)+int(x.get('sells_h1') or 0);risk=_pump_dump_risk(x,outcomes);failed=[]
    if score<80:failed.append('ANOMALY_SCORE_LT_80')
    if liq<cfg.verified_min_liquidity_usd:failed.append(f'LIQUIDITY_LT_{int(cfg.verified_min_liquidity_usd/1000)}K')
    if vol<15000:failed.append('VOLUME_1H_LT_15K')
    if tx<50:failed.append('ACTIVITY_LT_50_TX_1H')
    if risk['pump_dump_blocked']:failed.append('PUMP_DUMP_RISK_GATE')
    status='PUMP_DUMP_RISK' if risk['pump_dump_blocked'] else ('QUALIFIED' if not failed else 'REJECTED');return {**x,**risk,'qualification':status,'qualification_reasons':failed or ['PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION'],'qualified_at':now if status=='QUALIFIED' else None,'evaluated_at':now}


def _qualify_revival(x,now,outcomes):
    cfg=Settings();score=float(x.get('revival_score') or 0);liq=float(x.get('liquidity_usd') or 0);vol=float(x.get('volume_h1') or 0);tx=int(x.get('buys_h1') or 0)+int(x.get('sells_h1') or 0);risk=_pump_dump_risk(x,outcomes);failed=[]
    if score<65:failed.append('REVIVAL_SCORE_LT_65')
    if liq<cfg.verified_min_liquidity_usd:failed.append(f'LIQUIDITY_LT_{int(cfg.verified_min_liquidity_usd/1000)}K')
    if vol<15000:failed.append('VOLUME_1H_LT_15K')
    if tx<50:failed.append('ACTIVITY_LT_50_TX_1H')
    if risk['pump_dump_blocked']:failed.append('PUMP_DUMP_RISK_GATE')
    status='PUMP_DUMP_RISK' if risk['pump_dump_blocked'] else ('REVIVAL_QUALIFIED' if not failed else 'REVIVAL_WATCH');return {**x,**risk,'qualification':status,'qualification_reasons':failed or ['PASSED_REVIVAL_BASELINE_ACTIVITY_LIQUIDITY_MANIPULATION'],'qualified_at':now if status=='REVIVAL_QUALIFIED' else None,'evaluated_at':now}


def run():
    cfg=Settings();out=Path(cfg.output_dir);out.mkdir(parents=True,exist_ok=True);now=datetime.now(timezone.utc).isoformat();market=run_market_scan(cfg);universe=market.get('universe',[]);snapshots=market.get('snapshots',[]);state,annotated=_update_discovery_state(out,universe,snapshots,market.get('next_pages',{}),now);revival=run_revival_scan(cfg,annotated);revival_snapshots=revival.get('snapshots',[]) if isinstance(revival,dict) else [];state=_ensure_revival_tracking(out,state,revival_snapshots,now);outcomes=_update_outcomes(out,state,_merge_snapshots(snapshots,revival_snapshots),now);qualified=[];rejected=[];risks=[]
    for x in market.get('radar',[]):
        q=_qualify(x,now,outcomes);(risks if q.get('pump_dump_blocked') else qualified if q.get('qualification')=='QUALIFIED' else rejected).append(q)
    revival_qualified=[];revival_watch=[]
    for x in (revival.get('radar',[]) if isinstance(revival,dict) else []):
        q=_qualify_revival(x,now,outcomes);(risks if q.get('pump_dump_blocked') else revival_qualified if q.get('qualification')=='REVIVAL_QUALIFIED' else revival_watch).append(q)
    for name,payload in [('market-universe.json',annotated),('market-snapshots.json',snapshots),('anomaly-radar.json',market.get('radar',[])),('qualified-candidates.json',qualified),('rejected-candidates.json',rejected),('pump-dump-risk.json',risks),('revival-radar.json',revival.get('radar',[]) if isinstance(revival,dict) else []),('revival-snapshots.json',revival_snapshots),('revival-qualified.json',revival_qualified),('revival-watch.json',revival_watch)]:_write(out/name,payload)
    summary={'updated_at':now,'market_scan':len(universe),'qualified':len(qualified),'rejected':len(rejected),'pump_dump_risk':len(risks),'revival_qualified':len(revival_qualified),'revival_watch':len(revival_watch),'outcomes_updated':outcomes.get('updated_this_run',0),'pair_mismatch_refetched':outcomes.get('pair_mismatch_refetched',0),'pair_unavailable':outcomes.get('pair_unavailable',0),'qualification_min_liquidity_usd':cfg.verified_min_liquidity_usd};_write(out/'run-summary.json',summary);return summary


if __name__=='__main__':print(json.dumps(run(),indent=2))
