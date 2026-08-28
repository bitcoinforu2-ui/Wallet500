from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _token_key(row: dict) -> str:
    chain=str(row.get('chain') or 'unknown').lower(); token=str(row.get('token') or row.get('mint') or row.get('token_address') or '')
    if chain in {'ethereum','bsc','bnb','eth'}: token=token.lower()
    return f'{chain}:{token}'


def _fmt_money(v) -> str:
    try: n=float(v)
    except Exception: return 'n/a'
    if abs(n)>=1_000_000: return f'${n/1_000_000:.2f}M'
    if abs(n)>=1_000: return f'${n/1_000:.1f}K'
    if abs(n)>=1: return f'${n:.2f}'
    if n==0: return '$0'
    return f'${n:.8f}'.rstrip('0').rstrip('.')


def _tier(row: dict) -> str | None:
    if row.get('qualification')!='QUALIFIED': return None
    if row.get('live_survival_gate')!='ACTIVE': return None
    if row.get('pump_dump_blocked'): return None
    if row.get('holder_cluster_production_status')!='PASS' or row.get('holder_cluster_verified') is not True: return None
    score=float(row.get('anomaly_score') or 0); liquidity=float(row.get('live_liquidity_usd') or row.get('liquidity_usd') or 0); volume=float(row.get('live_volume_h1') or row.get('volume_h1') or 0); activity=int(row.get('live_activity_h1') or 0); risk=str(row.get('pump_dump_risk_level') or '').upper()
    if liquidity<50_000 or volume<15_000 or activity<50: return None
    if risk in {'HIGH','CRITICAL'}: return None
    if score>=90 and volume>=30_000 and risk=='LOW': return 'HIGH_CONVICTION'
    return 'QUALIFIED'


def _message(row: dict, tier: str) -> str:
    chain=str(row.get('chain') or 'unknown').upper().replace('BSC','BNB'); token=str(row.get('token') or row.get('mint') or row.get('token_address') or 'unknown'); score=float(row.get('anomaly_score') or 0); risk=str(row.get('pump_dump_risk_level') or 'n/a').upper(); liquidity=row.get('live_liquidity_usd') or row.get('liquidity_usd'); volume=row.get('live_volume_h1') or row.get('volume_h1'); buys=int(row.get('buys_h1') or 0); sells=int(row.get('sells_h1') or 0); price=row.get('price_usd'); age=row.get('pair_age_minutes'); title='🔥 HIGH CONVICTION' if tier=='HIGH_CONVICTION' else '🚨 VERIFIED LIVE'; age_text=f'{float(age):.0f}m' if age is not None else 'n/a'; dex_url=row.get('url') or ''
    lines=[f'{title} — WALLET500',chain,f'Token: {token}',f'Score: {score:.0f}/100',f'Price: {_fmt_money(price)}',f'Liquidity: {_fmt_money(liquidity)} ✅ min $50K',f'Volume 1H: {_fmt_money(volume)}',f'Buys/Sells 1H: {buys}/{sells}',f'Age: {age_text}',f'Pump/Dump Risk: {risk}','Holder/Cluster: VERIFIED PASS','Discovery snapshot locked: YES','Verified Intelligence. The Pure Truth.']
    if dex_url: lines.append(f'DexScreener: {dex_url}')
    return '\n'.join(lines)


def _send(bot_token: str, chat_id: str, text: str) -> None:
    url=f'https://api.telegram.org/bot{bot_token}/sendMessage'; payload=urllib.parse.urlencode({'chat_id':chat_id,'text':text,'disable_web_page_preview':'true'}).encode('utf-8'); req=urllib.request.Request(url,data=payload,method='POST')
    with urllib.request.urlopen(req,timeout=15) as response:
        if response.status<200 or response.status>=300: raise RuntimeError(f'Telegram HTTP {response.status}')


def run() -> dict:
    out=Path(os.getenv('WALLET500_OUTPUT_DIR','data')); source_name=os.getenv('WALLET500_ALERT_INPUT','active-qualified-candidates.json'); candidates_path=out/source_name; state_path=out/'telegram-alert-state.json'; candidates=_load(candidates_path,[])
    if not isinstance(candidates,list): candidates=[]
    state=_load(state_path,{})
    if not isinstance(state,dict): state={}
    sent=state.get('sent') if isinstance(state.get('sent'),dict) else {}; bot_token=os.getenv('TELEGRAM_BOT_TOKEN','').strip(); chat_id=os.getenv('TELEGRAM_CHAT_ID','').strip(); configured=bool(bot_token and chat_id); now=datetime.now(timezone.utc).isoformat(); delivered=[]; eligible=[]; errors=[]
    for row in candidates:
        tier=_tier(row)
        if not tier: continue
        key=_token_key(row); fingerprint=f"{tier}:{row.get('qualified_at') or row.get('observed_at') or ''}"; eligible.append({'key':key,'tier':tier})
        if sent.get(key,{}).get('fingerprint')==fingerprint: continue
        if not configured: continue
        try:
            _send(bot_token,chat_id,_message(row,tier)); sent[key]={'fingerprint':fingerprint,'tier':tier,'sent_at':now}; delivered.append({'key':key,'tier':tier})
        except Exception as exc: errors.append({'key':key,'error':f'{type(exc).__name__}: {exc}'[:300]})
    if len(sent)>5000: sent=dict(sorted(sent.items(),key=lambda kv:kv[1].get('sent_at',''),reverse=True)[:5000])
    report={'version':3,'updated_at':now,'configured':configured,'candidate_count':len(candidates),'eligible_count':len(eligible),'delivered_count':len(delivered),'error_count':len(errors),'eligible':eligible,'delivered':delivered,'errors':errors,'policy':{'source':source_name,'requires':['qualification=QUALIFIED','live_survival_gate=ACTIVE','pump_dump_blocked=false','holder_cluster_production_status=PASS','holder_cluster_verified=true','liquidity>=50000','volume_h1>=15000','activity_h1>=50','risk not HIGH/CRITICAL'],'high_conviction':'score>=90, liquidity>=50000, volume_h1>=30000, risk=LOW','dedupe':'one alert per qualification fingerprint'}}
    _write(state_path,{'updated_at':now,'sent':sent}); _write(out/'telegram-alert-report.json',report); print(json.dumps(report,indent=2)); return report


if __name__=='__main__': run()
