"""Wallet500 Listing Opportunity Router.

Routes official future-listing events into a lane that is deliberately separate
from the >=90d Revival engine. Exact identity remains fail-closed: symbol-only
announcements may be tracked as IDENTITY_PENDING but can never become actionable.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

DATA=Path("data"); WIRE=DATA/"catalyst-wire-live.json"; LEDGER=DATA/"catalyst-wire-ledger.json"; OUT=DATA/"listing-opportunity-live.json"

def _dt(v):
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc) if v else None
    except Exception:return None

def _start(e):
    v=(e.get("machine_state") or {}).get("start") or e.get("listing_start")
    if not v:return None
    try:
        if isinstance(v,(int,float)) or str(v).isdigit():
            x=float(v);x=x/1000 if x>10_000_000_000 else x;return datetime.fromtimestamp(x,tz=timezone.utc)
        return _dt(v)
    except Exception:return None

def _identity(e):return bool(e.get("chain") and (e.get("contract") or e.get("token") or e.get("mint")))
def _key(e):return f"{str(e.get('chain') or 'unknown').lower()}:{str(e.get('contract') or e.get('token') or e.get('mint') or e.get('symbol') or '').lower()}"
def _owners(key,events):
    out=set()
    for x in events:
        if _key(x)==key and x.get("source_owner") and x.get("source_url"):out.add(str(x["source_owner"]).lower())
    return sorted(out)
def run(now=None):
    now=now or datetime.now(timezone.utc)
    try:w=json.loads(WIRE.read_text())
    except Exception:w={}
    try:l=json.loads(LEDGER.read_text())
    except Exception:l={}
    events=[x for x in (w.get("events") or []) if isinstance(x,dict)]
    records=l.get("events") if isinstance(l.get("events"),dict) else {}
    for r in records.values():
        e=(r or {}).get("event") if isinstance(r,dict) else None
        if isinstance(e,dict):events.append(e)
    uniq={str(e.get("event_id") or f"{_key(e)}:{e.get('source_owner')}:{e.get('source_url')}"):e for e in events}
    rows=[]
    for e in uniq.values():
        et=str(e.get("event_type") or "").upper(); st=_start(e)
        if "LIST" not in et and not st:continue
        exact=_identity(e); key=_key(e); owners=_owners(key,list(uniq.values())) if exact else []
        future=bool(st and st>now)
        if not exact:lane="IDENTITY_PENDING"
        elif len(owners)>=2:lane="MULTI_CEX_PRE_LISTING" if future else "MULTI_CEX_LISTING_LIVE"
        elif future:lane="PRE_LISTING_EXISTING_OR_NEW"
        else:lane="LISTING_LIVE_RESEARCH"
        rows.append({"asset_key":key,"symbol":e.get("symbol"),"chain":e.get("chain"),"contract":e.get("contract") or e.get("token") or e.get("mint"),"lane":lane,"exact_identity_verified":exact,"listing_start":st.isoformat() if st else None,"minutes_to_listing":round((st-now).total_seconds()/60,1) if st else None,"exchange_count":len(owners),"exchanges":owners,"source_owner":e.get("source_owner"),"source_url":e.get("source_url"),"event_type":e.get("event_type"),"forward_new":e.get("forward_new") is True,"tracking_required":True,"revival_age_gate_applies":False,"automatic_buy":False,"telegram_candidate":bool(exact and (future or len(owners)>=2))})
    rows.sort(key=lambda x:(x["lane"]=="IDENTITY_PENDING", x["minutes_to_listing"] if x["minutes_to_listing"] is not None else 10**12))
    payload={"version":1,"mode":"LISTING_OPPORTUNITY_ROUTER","generated_at":now.isoformat(),"policy":{"separate_from_revival_90d":True,"symbol_only_never_actionable":True,"exact_identity_required_for_market_tracking":True,"multi_exchange_priority":True,"future_listing_starts_immediate_tracking":True,"automatic_buy":False},"counts":{"total":len(rows),"telegram_candidates":sum(x["telegram_candidate"] for x in rows),"identity_pending":sum(x["lane"]=="IDENTITY_PENDING" for x in rows),"multi_cex":sum(x["exchange_count"]>=2 for x in rows)},"opportunities":rows[:250]}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");return payload
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
