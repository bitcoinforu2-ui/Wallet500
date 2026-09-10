"""Selective Catalyst alerts with exact-market and minimum-activity guards."""
from __future__ import annotations
import json, math, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .market_data import snapshot as market_snapshot

DATA=Path(os.getenv("WALLET500_OUTPUT_DIR","data")); WIRE=DATA/"catalyst-wire-live.json"; LEDGER=DATA/"catalyst-wire-ledger.json"; STATE=DATA/"catalyst-focus-state.json"; OUT=DATA/"catalyst-focus-live.json"
MIN_LIQ=15_000.0; FOCUS_SCORE=76.0; DROP_SCORE=64.0
EXCEPTIONAL_SCORE=88.0; EXCEPTIONAL_READINESS=85.0; EXCEPTIONAL_MAX_RISK=20.0; EXCEPTIONAL_MIN_LIQ=250_000.0
PENDING_RECHECK_MIN=15; FOCUS_COOLDOWN_MIN=30; UNKNOWN_MAX_H=72; MAX_PENDING=120
# A buy/sell ratio from a tiny sample is not evidence. These guards apply both to
# readiness scoring and to BUY/SELL_PRESSURE_SURGE Telegram updates.
MIN_FLOW_TXNS_H1=10; MIN_FLOW_BUYS_H1=3; MIN_FLOW_VOLUME_H1_USD=1_000.0
PRIORS={"binance":(100,96,"S"),"coinbase":(96,94,"S"),"okx":(91,84,"A"),"bybit":(87,78,"A"),"kraken":(83,84,"A"),"upbit":(82,88,"A"),"bithumb":(72,82,"A"),"bitget":(78,66,"B"),"gate":(74,58,"B"),"kucoin":(72,62,"B"),"crypto.com":(70,72,"B"),"mexc":(64,30,"C"),"htx":(60,48,"C"),"coinex":(48,45,"C"),"lbank":(44,35,"C"),"bingx":(46,38,"C"),"bitmart":(42,34,"C"),"weex":(34,28,"D")}

def nowdt(): return datetime.now(timezone.utc)
def load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d
    except Exception:return d
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def num(v,d=0.0):
    try:x=float(v);return x if math.isfinite(x) else d
    except Exception:return d
def clamp(v):return max(0.0,min(100.0,v))
def pct(n,o):return None if not o else (n/o-1)*100
def parseiso(v):
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc) if v else None
    except Exception:return None
def prior(o):
    r,s,t=PRIORS.get(str(o or "").lower(),(45,40,"C"));return {"reach":r,"scarcity":s,"tier":t}
def liqscore(v):
    if v<MIN_LIQ:return 0
    if v<100_000:return 45+25*(v-50_000)/50_000
    if v<250_000:return 70+15*(v-100_000)/150_000
    if v<1_000_000:return 85+15*(v-250_000)/750_000
    return 100
def flowscore(b,s):
    r=(b+1)/(s+1);q=10 if r<.6 else 35 if r<.85 else 55 if r<1.05 else 70 if r<1.3 else 86 if r<1.75 else 96 if r<2.5 else 90;return q,r
def flow_coverage(m):
    b=int(m.get("buys_h1") or 0);s=int(m.get("sells_h1") or 0);v=num(m.get("volume_h1"));tx=b+s
    ok=tx>=MIN_FLOW_TXNS_H1 and b>=MIN_FLOW_BUYS_H1 and v>=MIN_FLOW_VOLUME_H1_USD
    missing=[]
    if tx<MIN_FLOW_TXNS_H1:missing.append("TXNS_H1")
    if b<MIN_FLOW_BUYS_H1:missing.append("BUYS_H1")
    if v<MIN_FLOW_VOLUME_H1_USD:missing.append("VOLUME_H1_USD")
    return ok,{"status":"SUFFICIENT_ACTIVITY" if ok else "INSUFFICIENT_ACTIVITY","txns_h1":tx,"buys_h1":b,"sells_h1":s,"volume_h1_usd":round(v,2),"minimums":{"txns_h1":MIN_FLOW_TXNS_H1,"buys_h1":MIN_FLOW_BUYS_H1,"volume_h1_usd":MIN_FLOW_VOLUME_H1_USD},"missing":missing}
def turnoverscore(v,l):
    r=v/l if l else 0;q=20 if r<.05 else 45 if r<.2 else 65 if r<.5 else 85 if r<1.5 else 100 if r<4 else 78 if r<8 else 58;return q,r
def headroom(h1,h24):
    if h1>=80 or h24>=220:return 15
    if h1>=50 or h24>=140:return 35
    if h1>=25 or h24>=80:return 55
    if h1>=12 or h24>=45:return 72
    if max(h1,h24)>=0:return 90
    if max(h1,h24)>=-15:return 78
    return 58
def grade(s):return "A+" if s>=88 else "A" if s>=82 else "B+" if s>=76 else "B" if s>=68 else "C" if s>=58 else "D"
def risk(m):
    q=0;rs=[];l=num(m.get("liquidity_usd"));cap=num(m.get("market_cap")) or num(m.get("fdv"));b=int(m.get("buys_h1") or 0);s=int(m.get("sells_h1") or 0);h1=num(m.get("price_change_h1"));h24=num(m.get("price_change_h24"))
    if l<MIN_LIQ:q+=60;rs.append("LIQUIDITY_BELOW_15K")
    if cap>0:
        d=l/cap
        if d<.01:q+=25;rs.append("LIQUIDITY_LT_1PCT_MCAP")
        elif d<.03:q+=15;rs.append("LIQUIDITY_LT_3PCT_MCAP")
        elif d<.05:q+=7;rs.append("LIQUIDITY_LT_5PCT_MCAP")
    if s>max(10,b*1.45):q+=18;rs.append("SELL_PRESSURE")
    if h1>=80 or h24>=220:q+=22;rs.append("ALREADY_OVEREXTENDED")
    if m.get("token_identity_verified") is not True:q+=50;rs.append("TOKEN_IDENTITY_UNVERIFIED")
    if not m.get("pair_address"):q+=50;rs.append("PAIR_UNRESOLVED")
    return clamp(q),rs
def listing_start(e):
    v=(e.get("machine_state") or {}).get("start") or e.get("listing_start")
    if v in (None,"",0,"0"):return None
    try:
        if isinstance(v,(int,float)) or str(v).isdigit():x=float(v);x=x/1000 if x>10_000_000_000 else x;return datetime.fromtimestamp(x,tz=timezone.utc).isoformat()
        return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:return None

def score_event(e):
    o=dict(e);c=str(e.get("chain") or "").lower();t=str(e.get("contract") or "").strip();m=None
    if c and t:
        try:m=market_snapshot(c,t)
        except Exception as x:o["market_error"]=f"{type(x).__name__}: {x}"[:160]
    if not m:o.update(decision_score=0.0,grade="D",focus_eligible=False,decision="WATCH_SILENT_NO_EXACT_MARKET",market=None,blockers=["EXACT_MARKET_UNAVAILABLE"]);return o
    ep=prior(e.get("source_owner"));es=.64*ep["reach"]+.36*ep["scarcity"];l=num(m.get("liquidity_usd"));ls=liqscore(l);b=int(m.get("buys_h1") or 0);s=int(m.get("sells_h1") or 0);fs,fr=flowscore(b,s);flow_ok,flow_cov=flow_coverage(m)
    # Neutralize flow contribution when the sample is too small; never infer pressure from 1-3 trades.
    if not flow_ok:fs=50.0
    ts,tr=turnoverscore(num(m.get("volume_h1")),l);room=headroom(num(m.get("price_change_h1")),num(m.get("price_change_h24")));ready=.45*ls+.30*fs+.25*ts;rq,rr=risk(m);raw=.24*clamp(num(e.get("impact_score")))+.27*es+.27*ready+.22*room;score=clamp(raw-.35*rq);bl=[]
    if e.get("preliminary_filter_pass") is not True:bl.append("PRELIMINARY_FILTER_FAIL")
    if not e.get("source_url"):bl.append("OFFICIAL_SOURCE_MISSING")
    if l<MIN_LIQ:bl.append("LIQUIDITY_BELOW_15K")
    if m.get("token_identity_verified") is not True or not m.get("pair_address"):bl.append("EXACT_PAIR_NOT_VERIFIED")
    if rq>=55:bl.append("RISK_TOO_HIGH")
    if es<50:bl.append("EXCHANGE_IMPACT_TOO_LOW")
    st=listing_start(e);sd=parseiso(st)
    if sd and sd<=nowdt():bl.append("LISTING_ALREADY_STARTED")
    eligible=bool(score>=FOCUS_SCORE and not bl)
    reasons=[f"EXCHANGE_{str(e.get('source_owner') or 'unknown').upper()}_{ep['tier']}",f"TURNOVER_H1_{tr:.2f}",*rr]
    reasons.insert(1,f"FLOW_RATIO_{fr:.2f}" if flow_ok else "FLOW_INSUFFICIENT_ACTIVITY")
    o.update(market=m,dex_url=m.get("url") or e.get("dex_url"),listing_start=st,exchange_prior=ep,exchange_score=round(es,2),market_readiness_score=round(ready,2),headroom_score=round(room,2),risk_score=round(rq,2),decision_score=round(score,2),grade=grade(score),focus_eligible=eligible,decision="FOCUS_UNTIL_LISTING" if eligible else "WATCH_SILENT",blockers=bl,flow_activity=flow_cov,decision_reasons=reasons);return o

def focus_key(e):return f"{e.get('chain')}:{str(e.get('contract') or '').lower()}:{str(e.get('source_owner') or '').lower()}"
def identity_key(e):return f"{str(e.get('chain') or '').lower()}:{str(e.get('contract') or '').lower()}"
def listing_exchanges(e,l):
    target=identity_key(e);owners=set();records=l.get("events") if isinstance(l.get("events"),dict) else {}
    for r in records.values():
        x=(r or {}).get("event") if isinstance(r,dict) else None
        if not isinstance(x,dict) or identity_key(x)!=target:continue
        ow=str(x.get("source_owner") or "").strip().lower()
        if ow and x.get("source_url"):owners.add(ow)
    return sorted(owners)
def telegram_gate(s,l):
    ex=listing_exchanges(s,l);multi=len(ex)>=2;m=s.get("market") or {};exceptional=bool(s.get("focus_eligible") and num(s.get("decision_score"))>=EXCEPTIONAL_SCORE and num(s.get("market_readiness_score"))>=EXCEPTIONAL_READINESS and num(s.get("risk_score"))<=EXCEPTIONAL_MAX_RISK and num(m.get("liquidity_usd"))>=EXCEPTIONAL_MIN_LIQ and m.get("token_identity_verified") is True and m.get("pair_address"));return multi or exceptional,{"telegram_relevant":multi or exceptional,"reason":"MULTI_EXCHANGE_LISTING" if multi else "EXCEPTIONAL_SETUP" if exceptional else "ROUTINE_LISTING_SILENT","exchange_count":len(ex),"exchanges":ex,"exceptional":exceptional}
def _current_forward(w):
    o={}
    for e in w.get("events") or []:
        if isinstance(e,dict) and e.get("forward_new") and str(e.get("event_id") or ""):o[str(e.get("event_id"))]=e
    return o
def discover_unseen(w,l,state,seen):
    records=l.get("events") if isinstance(l.get("events"),dict) else {};forward=_current_forward(w)
    if not bool(state.get("ledger_baseline_complete")):
        for i,r in records.items():
            if i not in forward:seen[i]=(r or {}).get("first_seen_at") or nowdt().isoformat()
        state["ledger_baseline_complete"]=True;state["ledger_baseline_at"]=nowdt().isoformat()
    c={}
    for i,r in records.items():
        if i not in seen and isinstance(r,dict) and isinstance(r.get("event"),dict):c[i]=r["event"]
    for i,e in forward.items():
        if i not in seen:c[i]=e
    return c

def send(text):
    tok=os.getenv("TELEGRAM_BOT_TOKEN","").strip();cid=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not tok or not cid:return False,"TELEGRAM_SECRETS_MISSING"
    body=urllib.parse.urlencode({"chat_id":cid,"text":text,"disable_web_page_preview":"true"}).encode();req=urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",data=body,method="POST")
    try:
        with urllib.request.urlopen(req,timeout=15) as r:p=json.loads(r.read().decode("utf-8"))
        return bool(p.get("ok")),"OK" if p.get("ok") else "API_OK_FALSE"
    except Exception as x:return False,f"{type(x).__name__}: {x}"[:180]
def money(v):
    x=num(v);return f"${x/1e6:.2f}M" if x>=1e6 else f"${x/1e3:.1f}K" if x>=1e3 else f"${x:.2f}" if x>0 else "—"
def price(v):x=num(v);return f"${x:.8g}" if x>0 else "—"
def activity_line(e):
    a=e.get("flow_activity") or {};return "Flow activity: INSUFFICIENT — pressure ratio ignored" if a.get("status")=="INSUFFICIENT_ACTIVITY" else "Flow activity: sufficient"
def startmsg(e):
    m=e.get("market") or {};g=e.get("telegram_gate") or {};badge="🔥 DOUBLE LISTING" if g.get("reason")=="MULTI_EXCHANGE_LISTING" else "💎 EXCEPTIONAL LISTING SETUP";lines=[f"{badge} · WALLET500",f"{e.get('symbol')} · {str(e.get('source_owner') or '').upper()} · {e.get('event_type')}",f"Decision {e.get('decision_score')}/100 · Grade {e.get('grade')} (ranking, not probability)",f"Exchange {e.get('exchange_score')}/100 · Readiness {e.get('market_readiness_score')}/100 · Risk {e.get('risk_score')}/100",f"Price {price(m.get('price_usd'))} · Liq {money(m.get('liquidity_usd'))} · MCap {money(m.get('market_cap') or m.get('fdv'))}",f"1h {num(m.get('price_change_h1')):+.1f}% · Vol {money(m.get('volume_h1'))} · Buys/Sells {m.get('buys_h1',0)}/{m.get('sells_h1',0)}",activity_line(e)]
    if g.get("exchange_count",0)>=2:lines.append("Exchanges: "+", ".join(str(x).upper() for x in g.get("exchanges") or []))
    if e.get("listing_start"):lines.append("Listing UTC: "+e["listing_start"])
    if e.get("dex_url"):lines.append("📈 DEX: "+e["dex_url"])
    if e.get("source_url"):lines.append("🔗 Official: "+e["source_url"])
    return "\n".join(lines)
def updatemsg(e,r,p):
    m=e.get("market") or {};o=p.get("market") or {};pd=pct(num(m.get("price_usd")),num(o.get("price_usd")));ld=pct(num(m.get("liquidity_usd")),num(o.get("liquidity_usd")));return "\n".join(["⚡ WALLET500 · FOCUS UPDATE",f"{e.get('symbol')} · {str(e.get('source_owner') or '').upper()} · {r}",f"Score {e.get('decision_score')}/100 · Grade {e.get('grade')} · Risk {e.get('risk_score')}/100",f"Price {price(m.get('price_usd'))}"+(f" ({pd:+.1f}%)" if pd is not None else ""),f"Liquidity {money(m.get('liquidity_usd'))}"+(f" ({ld:+.1f}%)" if ld is not None else ""),activity_line(e),f"📈 DEX: {e.get('dex_url') or 'unresolved'}"])
def finalmsg(e,r):m=e.get("market") or {};return "\n".join(["🏁 WALLET500 · FOCUS CLOSED",f"{e.get('symbol')} · {r}",f"Final score {e.get('decision_score')}/100 · Risk {e.get('risk_score')}/100",f"Price {price(m.get('price_usd'))} · Liq {money(m.get('liquidity_usd'))}"])
def material_change(c,p):
    cm=c.get("market") or {};om=p.get("market") or {}
    if num(cm.get("liquidity_usd"))<MIN_LIQ:return "LIQUIDITY_BROKE_15K",True
    if num(c.get("decision_score"))<DROP_SCORE:return "SCORE_COLLAPSED",True
    sd=num(c.get("decision_score"))-num(p.get("decision_score"))
    if abs(sd)>=8:return f"SCORE_CHANGE_{sd:+.0f}",False
    pd=pct(num(cm.get("price_usd")),num(om.get("price_usd")))
    if pd is not None and abs(pd)>=10:return f"PRICE_MOVE_{pd:+.1f}PCT",False
    ld=pct(num(cm.get("liquidity_usd")),num(om.get("liquidity_usd")))
    if ld is not None and abs(ld)>=20:return f"LIQUIDITY_MOVE_{ld:+.1f}PCT",False
    cur_ok,_=flow_coverage(cm);prev_ok,_=flow_coverage(om)
    # Never emit pressure-surge semantics from an under-sampled market.
    if not cur_ok:return None,False
    _,cr=flowscore(int(cm.get("buys_h1") or 0),int(cm.get("sells_h1") or 0));_,pr=flowscore(int(om.get("buys_h1") or 0),int(om.get("sells_h1") or 0)) if prev_ok else (50.0,1.0)
    if cr>=1.6 and pr<1.6:return "BUY_PRESSURE_SURGE",False
    if cr<=.7 and pr>.7:return "SELL_PRESSURE_SURGE",True
    return None,False
def _listing_close_reason(e,first,now):
    l=parseiso(e.get("listing_start"));return "LISTING_TIME_REACHED" if l and now>=l else "72H_NO_LISTING_TIME" if not l and now-first>=timedelta(hours=UNKNOWN_MAX_H) else None
def _due(last,mins,now):l=parseiso(last);return l is None or now-l>=timedelta(minutes=mins)
def _send_record(text,delivered,errors,payload):
    ok,detail=send(text)
    if ok:delivered.append(payload)
    elif detail!="TELEGRAM_SECRETS_MISSING":errors.append({"key":payload.get("key"),"error":detail})
    return ok

def run():
    wire=load(WIRE,{});ledger=load(LEDGER,{"events":{}});state=load(STATE,{"version":4,"focus":{},"pending":{},"seen_event_ids":{},"ledger_baseline_complete":False});state=state if isinstance(state,dict) else {};focus=state.get("focus") if isinstance(state.get("focus"),dict) else {};pending=state.get("pending") if isinstance(state.get("pending"),dict) else {};seen=state.get("seen_event_ids") if isinstance(state.get("seen_event_ids"),dict) else {};now=nowdt();delivered=[];errors=[];evaluated=[]
    for i,e in discover_unseen(wire,ledger,state,seen).items():seen[i]=now.isoformat();pending.setdefault(i,{"status":"WATCHING_SILENT","first_seen_at":now.isoformat(),"event":e,"last_check_at":None})
    for i,r in list(pending.items()):
        if r.get("status")!="WATCHING_SILENT" or not _due(r.get("last_check_at"),PENDING_RECHECK_MIN,now):continue
        first=parseiso(r.get("first_seen_at")) or now;s=score_event(dict(r.get("event") or {}));r["last_check_at"]=now.isoformat();r["last_snapshot"]=s;evaluated.append(s);close=_listing_close_reason(s,first,now)
        if close:r.update(status="CLOSED_SILENT",closed_at=now.isoformat(),close_reason=close);continue
        if not s.get("focus_eligible"):continue
        notify,g=telegram_gate(s,ledger);s["telegram_gate"]=g;r["telegram_gate"]=g
        if not notify:continue
        k=focus_key(s)
        if k in focus and focus[k].get("status")=="TRACKING":r.update(status="MERGED_INTO_FOCUS",promoted_at=now.isoformat(),focus_key=k);continue
        focus[k]={"status":"TRACKING","selected_at":now.isoformat(),"event":s,"last_alert_at":None,"last_alert_snapshot":s,"last_snapshot":s,"start_alert_delivered":False,"updates_sent":0};r.update(status="PROMOTED",promoted_at=now.isoformat(),focus_key=k)
    for k,r in list(focus.items()):
        if r.get("status")!="TRACKING":continue
        c=score_event(dict(r.get("event") or {}));c["telegram_gate"]=(r.get("event") or {}).get("telegram_gate") or {};r["last_check_at"]=now.isoformat()
        if not c.get("market"):continue
        sel=parseiso(r.get("selected_at")) or now;close=_listing_close_reason(c,sel,now)
        if close:
            if r.get("start_alert_delivered"):_send_record(finalmsg(c,close),delivered,errors,{"key":k,"type":"FOCUS_CLOSED","symbol":c.get("symbol"),"reason":close})
            r.update(status="LISTING_REACHED" if close=="LISTING_TIME_REACHED" else "TIMEOUT",closed_at=now.isoformat(),last_snapshot=c);continue
        if not r.get("start_alert_delivered"):
            ok=_send_record(startmsg(c),delivered,errors,{"key":k,"type":"FOCUS_START","symbol":c.get("symbol"),"telegram_gate":c.get("telegram_gate")})
            if ok:r.update(start_alert_delivered=True,last_alert_at=now.isoformat(),last_alert_snapshot=c)
            r["last_snapshot"]=c;continue
        p=r.get("last_alert_snapshot") or r.get("event") or {};reason,critical=material_change(c,p);cool=critical or _due(r.get("last_alert_at"),FOCUS_COOLDOWN_MIN,now)
        if reason and cool:
            text=finalmsg(c,reason) if critical else updatemsg(c,reason,p)
            if _send_record(text,delivered,errors,{"key":k,"type":"FOCUS_CRITICAL" if critical else "FOCUS_UPDATE","symbol":c.get("symbol"),"reason":reason}):r.update(last_alert_at=now.isoformat(),last_alert_snapshot=c,updates_sent=int(r.get("updates_sent") or 0)+1);r.update(status="DROPPED",closed_at=now.isoformat()) if critical else None
        r["last_snapshot"]=c
    ap=[(i,r) for i,r in pending.items() if r.get("status")=="WATCHING_SILENT"];ap.sort(key=lambda x:x[1].get("first_seen_at") or "",reverse=True)
    for i,r in ap[MAX_PENDING:]:r.update(status="EVICTED_SILENT_CAP",closed_at=now.isoformat())
    if len(seen)>20_000:seen=dict(list(seen.items())[-20_000:])
    af=[dict(r,key=k) for k,r in focus.items() if r.get("status")=="TRACKING"]
    out={"version":4,"updated_at":now.isoformat(),"mode":"TELEGRAM_MULTI_EXCHANGE_OR_EXCEPTIONAL_ONLY","policy":{"raw_listing_telegram":False,"routine_listing_telegram":False,"multi_exchange_listing_telegram":True,"exceptional_listing_telegram":True,"focus_threshold":FOCUS_SCORE,"hard_liquidity_floor_usd":MIN_LIQ,"flow_min_txns_h1":MIN_FLOW_TXNS_H1,"flow_min_buys_h1":MIN_FLOW_BUYS_H1,"flow_min_volume_h1_usd":MIN_FLOW_VOLUME_H1_USD,"automatic_trade":False},"counts":{"raw_events":len(wire.get("events") or []),"silent_pending":sum(1 for r in pending.values() if r.get("status")=="WATCHING_SILENT"),"evaluated_this_run":len(evaluated),"active_focus":len(af),"telegram_delivered_this_run":len(delivered)},"active_focus":af[:50],"new_evaluations":evaluated[:100],"telegram":{"delivered":delivered,"errors":errors}}
    write(OUT,out);state.update(version=4,updated_at=now.isoformat(),focus=focus,pending=pending,seen_event_ids=seen);write(STATE,state);print("CATALYST_FOCUS",json.dumps(out["counts"],separators=(",",":")));return out
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))