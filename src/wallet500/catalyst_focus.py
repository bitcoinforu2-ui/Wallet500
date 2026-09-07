"""Selective Catalyst alerts: raw listings stay silent; only high-interest listings
are promoted to Telegram and monitored until listing. Scores are rankings, not
probabilities of future return.
"""
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from .market_data import snapshot as market_snapshot

DATA=Path(os.getenv('WALLET500_OUTPUT_DIR','data'))
WIRE=DATA/'catalyst-wire-live.json'; STATE=DATA/'catalyst-focus-state.json'; OUT=DATA/'catalyst-focus-live.json'
MIN_LIQ=50_000.0; FOCUS_SCORE=76.0; DROP_SCORE=64.0; COOLDOWN_MIN=30; UNKNOWN_MAX_H=72
PRIORS={
 'binance':(100,96,'S'),'coinbase':(96,94,'S'),'okx':(91,84,'A'),'bybit':(87,78,'A'),
 'kraken':(83,84,'A'),'upbit':(82,88,'A'),'bithumb':(72,82,'A'),'bitget':(78,66,'B'),
 'gate':(74,58,'B'),'kucoin':(72,62,'B'),'crypto.com':(70,72,'B'),'mexc':(64,30,'C'),
 'htx':(60,48,'C'),'coinex':(48,45,'C'),'lbank':(44,35,'C'),'bingx':(46,38,'C'),
 'bitmart':(42,34,'C'),'weex':(34,28,'D')}

def nowdt(): return datetime.now(timezone.utc)
def load(p,d):
 try: return json.loads(p.read_text()) if p.exists() else d
 except Exception: return d
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2))
def num(v,d=0.0):
 try:
  x=float(v); return x if math.isfinite(x) else d
 except Exception: return d
def clamp(x): return max(0.0,min(100.0,x))
def pct(a,b): return None if not b else (a/b-1)*100

def prior(owner):
 r,s,t=PRIORS.get(str(owner or '').lower(),(45,40,'C')); return {'reach':r,'scarcity':s,'tier':t}
def liqscore(x):
 if x<MIN_LIQ:return 0
 if x<100_000:return 45+25*(x-50_000)/50_000
 if x<250_000:return 70+15*(x-100_000)/150_000
 if x<1_000_000:return 85+15*(x-250_000)/750_000
 return 100
def flowscore(b,s):
 r=(b+1)/(s+1)
 score=10 if r<.6 else 35 if r<.85 else 55 if r<1.05 else 70 if r<1.3 else 86 if r<1.75 else 96 if r<2.5 else 90
 return score,r
def turnoverscore(v,l):
 r=v/l if l else 0
 score=20 if r<.05 else 45 if r<.2 else 65 if r<.5 else 85 if r<1.5 else 100 if r<4 else 78 if r<8 else 58
 return score,r
def headroom(h1,h24):
 if h1>=80 or h24>=220:return 15
 if h1>=50 or h24>=140:return 35
 if h1>=25 or h24>=80:return 55
 if h1>=12 or h24>=45:return 72
 if max(h1,h24)>=0:return 90
 if max(h1,h24)>=-15:return 78
 return 58
def grade(s): return 'A+' if s>=88 else 'A' if s>=82 else 'B+' if s>=76 else 'B' if s>=68 else 'C' if s>=58 else 'D'

def risk(m):
 r=0; reasons=[]; l=num(m.get('liquidity_usd')); cap=num(m.get('market_cap')) or num(m.get('fdv'))
 b,s=int(m.get('buys_h1') or 0),int(m.get('sells_h1') or 0); h1,h24=num(m.get('price_change_h1')),num(m.get('price_change_h24'))
 if l<MIN_LIQ:r+=60;reasons.append('LIQUIDITY_BELOW_50K')
 if cap>0:
  d=l/cap
  if d<.01:r+=25;reasons.append('LIQUIDITY_LT_1PCT_MCAP')
  elif d<.03:r+=15;reasons.append('LIQUIDITY_LT_3PCT_MCAP')
  elif d<.05:r+=7;reasons.append('LIQUIDITY_LT_5PCT_MCAP')
 if s>max(10,b*1.45):r+=18;reasons.append('SELL_PRESSURE')
 if h1>=80 or h24>=220:r+=22;reasons.append('ALREADY_OVEREXTENDED')
 if m.get('token_identity_verified') is not True:r+=50;reasons.append('TOKEN_IDENTITY_UNVERIFIED')
 if not m.get('pair_address'):r+=50;reasons.append('PAIR_UNRESOLVED')
 return clamp(r),reasons

def listing_start(e):
 v=(e.get('machine_state') or {}).get('start')
 if v in (None,'',0,'0'):return None
 try:
  if isinstance(v,(int,float)) or str(v).isdigit():
   x=float(v); x=x/1000 if x>10_000_000_000 else x; return datetime.fromtimestamp(x,tz=timezone.utc).isoformat()
  return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
 except Exception:return None

def score_event(e):
 o=dict(e); chain=str(e.get('chain') or '').lower(); token=str(e.get('contract') or '').strip(); m=None
 if chain and token:
  try:m=market_snapshot(chain,token)
  except Exception as ex:o['market_error']=f'{type(ex).__name__}: {ex}'[:160]
 if not m:
  o.update(decision_score=0.0,grade='D',focus_eligible=False,decision='IGNORE_NO_EXACT_MARKET',market=None,blockers=['EXACT_MARKET_UNAVAILABLE']);return o
 p=prior(e.get('source_owner')); ex=.64*p['reach']+.36*p['scarcity']; l=num(m.get('liquidity_usd')); ls=liqscore(l)
 fs,fr=flowscore(int(m.get('buys_h1') or 0),int(m.get('sells_h1') or 0)); ts,tr=turnoverscore(num(m.get('volume_h1')),l)
 hr=headroom(num(m.get('price_change_h1')),num(m.get('price_change_h24'))); mr=.45*ls+.30*fs+.25*ts; rr,rrs=risk(m)
 raw=.24*clamp(num(e.get('impact_score')))+.27*ex+.27*mr+.22*hr; sc=clamp(raw-.35*rr)
 blockers=[]
 if e.get('preliminary_filter_pass') is not True:blockers.append('PRELIMINARY_FILTER_FAIL')
 if not e.get('source_url'):blockers.append('OFFICIAL_SOURCE_MISSING')
 if l<MIN_LIQ:blockers.append('LIQUIDITY_BELOW_50K')
 if m.get('token_identity_verified') is not True or not m.get('pair_address'):blockers.append('EXACT_PAIR_NOT_VERIFIED')
 if rr>=55:blockers.append('RISK_TOO_HIGH')
 eligible=bool(sc>=FOCUS_SCORE and not blockers)
 o.update(market=m,dex_url=m.get('url') or e.get('dex_url'),listing_start=listing_start(e),exchange_prior=p,exchange_score=round(ex,2),
  market_readiness_score=round(mr,2),headroom_score=round(hr,2),risk_score=round(rr,2),decision_score=round(sc,2),grade=grade(sc),
  focus_eligible=eligible,decision='FOCUS_UNTIL_LISTING' if eligible else 'IGNORE_RAW_EVENT',blockers=blockers,
  decision_reasons=[f'EXCHANGE_{str(e.get("source_owner") or "unknown").upper()}_{p["tier"]}',f'FLOW_RATIO_{fr:.2f}',f'TURNOVER_H1_{tr:.2f}',*rrs])
 return o

def key(e):return f"{e.get('chain')}:{str(e.get('contract') or '').lower()}:{str(e.get('source_owner') or '').lower()}"
def parseiso(v):
 try:return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc) if v else None
 except Exception:return None

def send(text):
 tok,cid=os.getenv('TELEGRAM_BOT_TOKEN','').strip(),os.getenv('TELEGRAM_CHAT_ID','').strip()
 if not tok or not cid:return False,'TELEGRAM_SECRETS_MISSING'
 body=urllib.parse.urlencode({'chat_id':cid,'text':text,'disable_web_page_preview':'true'}).encode(); req=urllib.request.Request(f'https://api.telegram.org/bot{tok}/sendMessage',data=body,method='POST')
 try:
  with urllib.request.urlopen(req,timeout=15) as r:x=json.loads(r.read().decode())
  return bool(x.get('ok')),'OK' if x.get('ok') else 'API_OK_FALSE'
 except Exception as ex:return False,f'{type(ex).__name__}: {ex}'[:180]
def money(v):
 x=num(v); return f'${x/1e6:.2f}M' if x>=1e6 else f'${x/1e3:.1f}K' if x>=1e3 else f'${x:.2f}' if x>0 else '—'
def price(v):x=num(v);return f'${x:.8g}' if x>0 else '—'
def startmsg(e):
 m=e.get('market') or {}; lines=['🚨 WALLET500 · FOCUS LISTING ALERT',f"{e.get('symbol')} · {str(e.get('source_owner') or '').upper()} · {e.get('event_type')}",
  f"Decision {e.get('decision_score')}/100 · Grade {e.get('grade')} (ranking, not probability)",f"Exchange {e.get('exchange_score')}/100 · Readiness {e.get('market_readiness_score')}/100 · Risk {e.get('risk_score')}/100",
  f"Price {price(m.get('price_usd'))} · Liq {money(m.get('liquidity_usd'))} · MCap {money(m.get('market_cap') or m.get('fdv'))}",f"1h {num(m.get('price_change_h1')):+.1f}% · Vol {money(m.get('volume_h1'))} · Buys/Sells {m.get('buys_h1',0)}/{m.get('sells_h1',0)}",'🎯 FOCUS UNTIL LISTING — only material changes will be sent']
 if e.get('listing_start'):lines.append('Listing UTC: '+e['listing_start'])
 if e.get('dex_url'):lines.append('📈 DEX: '+e['dex_url'])
 if e.get('source_url'):lines.append('🔗 Official: '+e['source_url'])
 return '\n'.join(lines)
def updatemsg(e,reason,prev):
 m=e.get('market') or {}; pm=prev.get('market') or {}; pd=pct(num(m.get('price_usd')),num(pm.get('price_usd'))); ld=pct(num(m.get('liquidity_usd')),num(pm.get('liquidity_usd')))
 return '\n'.join(['⚡ WALLET500 · FOCUS UPDATE',f"{e.get('symbol')} · {str(e.get('source_owner') or '').upper()} · {reason}",f"Score {e.get('decision_score')}/100 · Grade {e.get('grade')} · Risk {e.get('risk_score')}/100",f"Price {price(m.get('price_usd'))}"+(f' ({pd:+.1f}%)' if pd is not None else ''),f"Liquidity {money(m.get('liquidity_usd'))}"+(f' ({ld:+.1f}%)' if ld is not None else ''),f"1h {num(m.get('price_change_h1')):+.1f}% · Buys/Sells {m.get('buys_h1',0)}/{m.get('sells_h1',0)}",f"📈 DEX: {e.get('dex_url') or 'unresolved'}"])
def finalmsg(e,reason):
 m=e.get('market') or {}; return '\n'.join(['🏁 WALLET500 · FOCUS CLOSED',f"{e.get('symbol')} · {str(e.get('source_owner') or '').upper()} · {reason}",f"Final score {e.get('decision_score')}/100 · Risk {e.get('risk_score')}/100",f"Price {price(m.get('price_usd'))} · Liq {money(m.get('liquidity_usd'))}",f"📈 DEX: {e.get('dex_url') or 'unresolved'}"])
def change(cur,prev):
 cm,pm=cur.get('market') or {},prev.get('market') or {}
 if num(cm.get('liquidity_usd'))<MIN_LIQ:return 'LIQUIDITY_BROKE_50K',True
 if num(cur.get('decision_score'))<DROP_SCORE:return 'SCORE_COLLAPSED',True
 sd=num(cur.get('decision_score'))-num(prev.get('decision_score'))
 if abs(sd)>=8:return f'SCORE_CHANGE_{sd:+.0f}',False
 pd=pct(num(cm.get('price_usd')),num(pm.get('price_usd')))
 if pd is not None and abs(pd)>=10:return f'PRICE_MOVE_{pd:+.1f}PCT',False
 ld=pct(num(cm.get('liquidity_usd')),num(pm.get('liquidity_usd')))
 if ld is not None and abs(ld)>=20:return f'LIQUIDITY_MOVE_{ld:+.1f}PCT',False
 _,cr=flowscore(int(cm.get('buys_h1') or 0),int(cm.get('sells_h1') or 0)); _,pr=flowscore(int(pm.get('buys_h1') or 0),int(pm.get('sells_h1') or 0))
 if cr>=1.6 and pr<1.6:return 'BUY_PRESSURE_SURGE',False
 if cr<=.7 and pr>.7:return 'SELL_PRESSURE_SURGE',True
 return None,False

def run():
 wire=load(WIRE,{}); st=load(STATE,{'version':1,'focus':{},'seen_event_ids':{}}); focus=st.get('focus') if isinstance(st.get('focus'),dict) else {}; seen=st.get('seen_event_ids') if isinstance(st.get('seen_event_ids'),dict) else {}; now=nowdt(); evaluated=[]; delivered=[]; errors=[]
 for e in wire.get('events') or []:
  if not isinstance(e,dict) or not e.get('forward_new'):continue
  eid=str(e.get('event_id') or '')
  if not eid or eid in seen:continue
  seen[eid]=now.isoformat(); s=score_event(e); evaluated.append(s)
  if not s.get('focus_eligible'):continue
  k=key(s)
  if k in focus and focus[k].get('status')=='TRACKING':continue
  rec={'status':'TRACKING','selected_at':now.isoformat(),'event':s,'last_alert_at':now.isoformat(),'last_alert_snapshot':s,'last_snapshot':s,'updates_sent':0}; ok,detail=send(startmsg(s))
  if ok:delivered.append({'key':k,'type':'FOCUS_START','symbol':s.get('symbol')})
  elif detail!='TELEGRAM_SECRETS_MISSING':errors.append({'key':k,'error':detail})
  focus[k]=rec
 for k,rec in list(focus.items()):
  if rec.get('status')!='TRACKING':continue
  cur=score_event(dict(rec.get('event') or {})); rec['last_check_at']=now.isoformat()
  if not cur.get('market'):rec['last_check_error']=cur.get('market_error') or 'EXACT_MARKET_UNAVAILABLE';continue
  selected=parseiso(rec.get('selected_at')) or now; listing=parseiso(cur.get('listing_start') or (rec.get('event') or {}).get('listing_start'))
  close_reason='LISTING_TIME_REACHED' if listing and now>=listing else '72H_NO_LISTING_TIME' if not listing and now-selected>=timedelta(hours=UNKNOWN_MAX_H) else None
  if close_reason:
   ok,detail=send(finalmsg(cur,close_reason)); rec.update(status='LISTING_REACHED' if listing else 'TIMEOUT',closed_at=now.isoformat(),last_snapshot=cur)
   if ok:delivered.append({'key':k,'type':'FOCUS_CLOSED','symbol':cur.get('symbol'),'reason':close_reason})
   elif detail!='TELEGRAM_SECRETS_MISSING':errors.append({'key':k,'error':detail})
   continue
  prev=rec.get('last_alert_snapshot') or rec.get('event') or {}; reason,critical=change(cur,prev); la=parseiso(rec.get('last_alert_at')); cooldown=critical or la is None or now-la>=timedelta(minutes=COOLDOWN_MIN)
  if reason and cooldown:
   ok,detail=send(finalmsg(cur,reason) if critical else updatemsg(cur,reason,prev))
   if ok:
    delivered.append({'key':k,'type':'FOCUS_CRITICAL' if critical else 'FOCUS_UPDATE','symbol':cur.get('symbol'),'reason':reason}); rec.update(last_alert_at=now.isoformat(),last_alert_snapshot=cur,updates_sent=int(rec.get('updates_sent') or 0)+1)
    if critical:rec.update(status='DROPPED',closed_at=now.isoformat())
   elif detail!='TELEGRAM_SECRETS_MISSING':errors.append({'key':k,'error':detail})
  rec['last_snapshot']=cur
 if len(seen)>20_000:seen=dict(list(seen.items())[-20_000:])
 active=[dict(v,key=k) for k,v in focus.items() if v.get('status')=='TRACKING']; active.sort(key=lambda x:num((x.get('last_snapshot') or {}).get('decision_score')),reverse=True)
 out={'version':1,'updated_at':now.isoformat(),'mode':'SELECTIVE_LISTING_FOCUS_ONLY','policy':{'raw_listing_telegram':False,'focus_threshold':FOCUS_SCORE,'hard_liquidity_floor_usd':MIN_LIQ,'focus_score_is_probability':False,'selected_candidates_monitored_until_listing':True,'unknown_listing_time_fallback_hours':UNKNOWN_MAX_H,'followup_only_on_material_change':True,'automatic_trade':False,'exchange_priors_status':'BOOTSTRAP_PRIORS_PENDING_EMPIRICAL_EXCHANGE_LISTING_DNA_CALIBRATION'},'counts':{'raw_events':len(wire.get('events') or []),'new_evaluated':len(evaluated),'new_focus_selected':sum(1 for x in evaluated if x.get('focus_eligible')),'active_focus':len(active),'telegram_delivered_this_run':len(delivered)},'active_focus':active[:50],'new_evaluations':evaluated[:100],'telegram':{'delivered':delivered,'errors':errors}}
 write(OUT,out); st.update(version=1,updated_at=now.isoformat(),focus=focus,seen_event_ids=seen); write(STATE,st); print('CATALYST_FOCUS',json.dumps(out['counts'],separators=(',',':'))); return out

if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False,indent=2))
