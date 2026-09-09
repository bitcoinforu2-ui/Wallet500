from __future__ import annotations

import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .telegram_alerts import _fmt_israel_time, _fmt_money, _load, _send, _write

MODE="RESEARCH_ONLY_REVIVAL_90D_15K_TELEGRAM_V1"; SOURCE="revival-radar.json"; STATE="revival-90d-telegram-state.json"; REPORT="revival-90d-telegram-report.json"
MIN_AGE_DAYS=90.0; MIN_LIQUIDITY_USD=15_000.0; MIN_REVIVAL_SCORE=65.0; MIN_VOLUME_H1_USD=15_000.0; MIN_TXNS_H1=30

def _f(v:Any,d:float=0.0)->float:
    try:return float(v)
    except (TypeError,ValueError):return d

def _i(v:Any,d:int=0)->int:
    try:return int(float(v))
    except (TypeError,ValueError):return d

def _norm_chain(v:Any)->str:
    c=str(v or '').lower()
    return 'ethereum' if c in {'eth','ethereum'} else 'bsc' if c in {'bnb','bsc'} else 'solana' if c in {'sol','solana'} else c

def _same_identity(chain:str,a:Any,b:Any)->bool:
    a,b=str(a or ''),str(b or '')
    return bool(a and b and (a.lower()==b.lower() if chain in {'ethereum','bsc','arbitrum','base'} else a==b))

def _created_at(row:dict)->datetime|None:
    try:
        x=float(row.get('pair_created_at')); x=x/1000.0 if x>10_000_000_000 else x
        return datetime.fromtimestamp(x,tz=timezone.utc)
    except (TypeError,ValueError,OSError,OverflowError):return None

def _eligibility(row:object,now:datetime)->tuple[bool,dict[str,Any]]:
    if not isinstance(row,dict):return False,{'blockers':['ROW_INVALID']}
    chain=_norm_chain(row.get('chain')); token=str(row.get('token') or row.get('token_address') or ''); base=str(row.get('base_token_address') or ''); pair=str(row.get('pair_address') or '')
    created=_created_at(row); age=(now-created).total_seconds()/86400.0 if created else 0.0; liq=_f(row.get('liquidity_usd')); score=_f(row.get('revival_score')); vol=_f(row.get('volume_h1')); tx=_i(row.get('buys_h1'))+_i(row.get('sells_h1'))
    blockers=[]
    if not chain or not token or not pair:blockers.append('IDENTITY_OR_PAIR_MISSING')
    if not _same_identity(chain,token,base):blockers.append('BASE_TOKEN_IDENTITY_NOT_VERIFIED')
    if created is None or age<MIN_AGE_DAYS:blockers.append('PAIR_AGE_LT_90D_OR_UNKNOWN')
    if liq<MIN_LIQUIDITY_USD:blockers.append('LIQUIDITY_LT_15K')
    if score<MIN_REVIVAL_SCORE:blockers.append('REVIVAL_SCORE_LT_65')
    if vol<MIN_VOLUME_H1_USD:blockers.append('VOLUME_H1_LT_15K')
    if tx<MIN_TXNS_H1:blockers.append('TXNS_H1_LT_30')
    if str(row.get('pump_dump_risk_level') or row.get('risk_level') or '').upper() in {'HIGH','CRITICAL'}:blockers.append('HIGH_OR_CRITICAL_RISK')
    return not blockers,{'chain':chain,'token_address':token,'pair_address':pair,'market_age_days':round(age,2),'liquidity_usd':liq,'revival_score':score,'volume_h1_usd':vol,'txns_h1':tx,'blockers':blockers}

def _key(m:dict[str,Any])->str:
    c=str(m.get('chain') or ''); t=str(m.get('token_address') or ''); p=str(m.get('pair_address') or '')
    if c in {'ethereum','bsc','arbitrum','base'}:t,p=t.lower(),p.lower()
    return f'{c}:{t}:{p}'

def _event_id(k:str,ts:str)->str:return 'R90-'+hashlib.sha256(f'{k}|{ts}'.encode()).hexdigest()[:12].upper()

def _message(row:dict,m:dict[str,Any],ts:str,eid:str)->str:
    symbol=str(row.get('base_token_symbol') or row.get('symbol') or 'UNKNOWN'); url=str(row.get('url') or row.get('dex_url') or '')
    lines=['🔥🔥🔥 REVIVAL 90D / 15K — WALLET500','🆕 התעוררות חדשה במסלול המורחב',f'📅 זמן התראה (ישראל): {_fmt_israel_time(ts)}',f'🧾 Alert ID: {eid}','⚠️ RESEARCH ONLY — MANUAL DECISION — NO AUTOMATIC TRADE',f'Token: {symbol}',f"Chain: {str(m['chain']).upper().replace('BSC','BNB')}",f"Contract: {m['token_address']}",f"Pair: {m['pair_address']}",'Exact token identity: VERIFIED ✅','Exact pair: LOCKED ✅',f"Market age: {m['market_age_days']:.1f}d ✅ min 90d",f"Liquidity: {_fmt_money(m['liquidity_usd'])} ✅ min $15K",f"Revival score: {m['revival_score']:.1f}/100 ✅ min 65",f"Volume H1: {_fmt_money(m['volume_h1_usd'])} ✅ min $15K",f"Activity H1: {m['txns_h1']} tx ✅ min 30",'Canonical Revival gate: 90d / $15K ✅','Verified Intelligence. The Pure Truth.']
    if url:lines.append(f'🔗 OPEN DEX: {url}')
    return '\n'.join(lines)

def run(output_dir:str|None=None,now:datetime|None=None)->dict:
    out=Path(output_dir or os.getenv('WALLET500_OUTPUT_DIR','data')); now_dt=now or datetime.now(timezone.utc); now_iso=now_dt.isoformat(); src=_load(out/SOURCE,[]); rows=[x for x in src if isinstance(x,dict)] if isinstance(src,list) else []
    eligible=[]
    for row in rows:
        ok,m=_eligibility(row,now_dt)
        if ok:eligible.append((row,m))
    active={_key(m) for _,m in eligible}; state_exists=(out/STATE).exists(); state=_load(out/STATE,{}) if state_exists else {}; sent=state.get('sent') if isinstance(state,dict) and isinstance(state.get('sent'),dict) else {}
    token=os.getenv('TELEGRAM_BOT_TOKEN','').strip(); chat=os.getenv('TELEGRAM_CHAT_ID','').strip(); configured=bool(token and chat); delivered=[]; errors=[]; baseline_count=0
    if configured and not state_exists:
        for row,m in eligible:
            k=_key(m); sent[k]={'active':True,'baseline_at':now_iso,'symbol':row.get('base_token_symbol') or row.get('symbol'),'pair_address':m['pair_address'],'source':'FORWARD_ONLY_BASELINE_NO_SEND'}; baseline_count+=1
        _write(out/STATE,{'version':1,'updated_at':now_iso,'forward_started_at':now_iso,'sent':sent})
    elif configured:
        for row,m in eligible:
            k=_key(m); prev=sent.get(k) if isinstance(sent.get(k),dict) else {}
            if prev.get('active') is True:continue
            eid=_event_id(k,now_iso)
            try:
                mid,attempts=_send(token,chat,_message(row,m,now_iso,eid)); info={'active':True,'sent_at':now_iso,'event_id':eid,'telegram_message_id':mid,'attempts':attempts,'symbol':row.get('base_token_symbol') or row.get('symbol'),'pair_address':m['pair_address']}; sent[k]=info; delivered.append({'key':k,**info})
            except Exception as exc:errors.append({'key':k,'error':f'{type(exc).__name__}: {exc}'[:300]})
        for k,info in list(sent.items()):
            if isinstance(info,dict) and info.get('active') is True and k not in active:info['active']=False; info['cleared_at']=now_iso; sent[k]=info
        _write(out/STATE,{'version':1,'updated_at':now_iso,'forward_started_at':state.get('forward_started_at') or now_iso,'sent':sent})
    report={'version':1,'mode':MODE,'updated_at':now_iso,'configured':configured,'source':SOURCE,'source_rows':len(rows),'eligible_count':len(eligible),'baseline_count':baseline_count,'delivered_count':len(delivered),'error_count':len(errors),'delivered':delivered,'errors':errors,'truth_contract':{'research_only':True,'production_portfolio_impact':'NONE','production_gate_changed':False,'automatic_buy':False,'minimum_pair_age_days':MIN_AGE_DAYS,'minimum_liquidity_usd':MIN_LIQUIDITY_USD,'minimum_revival_score':MIN_REVIVAL_SCORE,'minimum_volume_h1_usd':MIN_VOLUME_H1_USD,'minimum_txns_h1':MIN_TXNS_H1,'exact_pair_required':True,'exact_base_token_identity_required':True,'notification_marker':'🔥🔥🔥','dedupe':'one alert per exact chain+token+pair active transition; re-arm after leaving eligibility','no_historical_backfill':True,'no_hindsight':True}}
    _write(out/REPORT,report); print(json.dumps(report,ensure_ascii=False,indent=2)); return report

if __name__=='__main__':run()
