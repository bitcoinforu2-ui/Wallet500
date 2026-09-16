from __future__ import annotations
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'data/unified-watch-config.json'
EVENTS=ROOT/'data/close-watch-events.json'
STATE=ROOT/'data/derivatives-intelligence-state.json'

def now(): return datetime.now(timezone.utc).isoformat()
def get(url):
    req=urllib.request.Request(url,headers={'accept':'application/json','user-agent':'Wallet500-Derivatives/1.0'})
    return json.load(urllib.request.urlopen(req,timeout=15))
def post(url,payload):
    data=json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,headers={'content-type':'application/json','user-agent':'Wallet500-Derivatives/1.0'},method='POST')
    return json.load(urllib.request.urlopen(req,timeout=15))
def pct(a,b): return ((a/b)-1)*100 if b else None
def ev(symbol,kind,direction,strength,confidence,source,subject,**extra):
    x={'symbol':symbol,'family':'derivatives','kind':kind,'direction':direction,'strength':max(0,min(100,strength)),'confidence':max(0,min(100,confidence)),'source':source,'subject':subject,'canonical_event_id':f'{source}:{symbol}:{kind}:{subject}','event_time':now(),'observed_at':now(),'free_source':True}
    x.update(extra); return x

def binance_snapshot(symbol):
    s=symbol.upper()+'USDT'; base='https://fapi.binance.com'
    oi=float(get(base+'/fapi/v1/openInterest?'+urllib.parse.urlencode({'symbol':s}))['openInterest'])
    mark=get(base+'/fapi/v1/premiumIndex?'+urllib.parse.urlencode({'symbol':s}))
    px=float(mark['markPrice']); funding=float(mark.get('lastFundingRate') or 0)*100
    return {'oi_units':oi,'oi_usd':oi*px,'mark_price':px,'funding_pct':funding}

def hyper_user(address):
    perp=post('https://api.hyperliquid.xyz/info',{'type':'clearinghouseState','user':address})
    spot=post('https://api.hyperliquid.xyz/info',{'type':'spotClearinghouseState','user':address})
    positions=[]
    for row in perp.get('assetPositions') or []:
        p=row.get('position') or {}; sz=float(p.get('szi') or 0)
        if sz: positions.append({'coin':p.get('coin'),'signed_size':sz,'side':'LONG' if sz>0 else 'SHORT','entry_px':p.get('entryPx'),'position_value':p.get('positionValue'),'liquidation_px':p.get('liquidationPx'),'unrealized_pnl':p.get('unrealizedPnl')})
    balances={str(x.get('coin')):float(x.get('total') or 0) for x in (spot.get('balances') or [])}
    return {'positions':positions,'spot_balances':balances}

def main():
    cfg=json.loads(CONFIG.read_text()); doc=json.loads(EVENTS.read_text()) if EVENTS.exists() else {'version':2,'events':[]}; state=json.loads(STATE.read_text()) if STATE.exists() else {'version':1,'tokens':{}}
    out=[]
    for t in cfg.get('tokens') or []:
        sym=str(t.get('symbol') or '').upper(); prev=(state.get('tokens') or {}).get(sym) or {}; snap=None
        try: snap=binance_snapshot(sym)
        except Exception as e: snap={'status':'UNAVAILABLE','reason':type(e).__name__}
        if snap.get('oi_usd'):
            old=float(prev.get('oi_usd') or 0); d=pct(snap['oi_usd'],old)
            if d is not None and abs(d)>=5:
                direction=1 if d>0 else -1; out.append(ev(sym,'open_interest_change',direction,min(100,abs(d)*3),85,'Binance Futures',f'OI {d:+.2f}% vs prior verified snapshot',oi_usd=snap['oi_usd'],delta_pct=round(d,3),funding_pct=snap['funding_pct']))
            if abs(snap['funding_pct'])>=0.05:
                # Crowding is risk evidence, not automatically bullish/bearish.
                out.append(ev(sym,'funding_extreme',-1,min(100,abs(snap['funding_pct'])*1000),80,'Binance Futures',f'funding {snap["funding_pct"]:+.4f}%',contradicts_bullish=snap['funding_pct']>0))
            state.setdefault('tokens',{})[sym]={**snap,'observed_at':now()}
        # Same-address spot/perp correlation is accepted only where account state is public.
        for w in t.get('tracked_perp_wallets') or []:
            address=str(w.get('address') if isinstance(w,dict) else w)
            provider=str(w.get('provider','hyperliquid') if isinstance(w,dict) else 'hyperliquid').lower()
            if provider!='hyperliquid' or not address: continue
            try: u=hyper_user(address)
            except Exception: continue
            pos=next((p for p in u['positions'] if str(p.get('coin','')).upper()==sym),None)
            spot=float(u['spot_balances'].get(sym,0));
            if not pos: continue
            pv=abs(float(pos.get('position_value') or 0)); side=pos['side']; spx=float(snap.get('mark_price') or 0) if snap else 0; spot_usd=spot*spx if spx else None
            hedge_ratio=(pv/spot_usd) if spot_usd and spot_usd>0 and side=='SHORT' else None
            direction=1 if side=='LONG' else -1
            strength=min(100,35+(min(2.0,hedge_ratio or 0)*25))
            out.append(ev(sym,'verified_same_wallet_perp_exposure',direction,strength,92,'Hyperliquid public account state',address, wallet_address=address,side=side,perp_notional_usd=pv,spot_units=spot,spot_usd=spot_usd,hedge_ratio=hedge_ratio,entry_px=pos.get('entry_px'),liquidation_px=pos.get('liquidation_px')))
            # A short against a material spot holding is classified as hedge/distribution risk, never as manipulation proof.
            if side=='SHORT' and spot>0:
                out.append(ev(sym,'spot_holder_short_hedge',-1,min(100,45+(min(2.0,hedge_ratio or 0)*20)),90,'Hyperliquid public account state',address,contradicts_bullish=True,wallet_address=address,hedge_ratio=hedge_ratio,interpretation='HEDGE_OR_DISTRIBUTION_RISK_NOT_MANIPULATION_PROOF'))
    merged=(doc.get('events') or [])+out
    # Keep recent bounded evidence; fusion handles canonical dedup and freshness.
    doc={'version':2,'generated_at':now(),'events':merged[-5000:]}; EVENTS.write_text(json.dumps(doc,indent=2,ensure_ascii=False)+'\n')
    state['updated_at']=now(); STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':'OK','new_events':len(out),'tokens':len(cfg.get('tokens') or [])},ensure_ascii=False))
if __name__=='__main__': raise SystemExit(main())
