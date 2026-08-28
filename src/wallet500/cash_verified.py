from __future__ import annotations
import json, os, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

DATA=Path('data')
API='https://api.0x.org/swap/allowance-holder/quote'
KEY=os.getenv('ZEROX_API_KEY','').strip()
CHAIN_IDS={'ETH':1,'ETHEREUM':1,'BSC':56,'BNB':56}
STABLE={1:'0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',56:'0x55d398326f99059fF775485246999027B3197955'}
TAKER='0x0000000000000000000000000000000000000001'

def load(p,d):
    try:return json.loads(p.read_text())
    except Exception:return d

def write(p,x):p.write_text(json.dumps(x,indent=2))

def quote(chain,token,amount):
    cid=CHAIN_IDS.get(str(chain).upper())
    if not cid:return None,'CHAIN_NOT_SUPPORTED_BY_EVM_QUOTER'
    if not KEY:return None,'ZEROX_API_KEY_MISSING'
    q=urllib.parse.urlencode({'chainId':cid,'sellToken':token,'buyToken':STABLE[cid],'sellAmount':str(amount),'taker':TAKER})
    req=urllib.request.Request(API+'?'+q,headers={'0x-api-key':KEY,'0x-version':'v2'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read()),None
    except urllib.error.HTTPError as e:
        try: body=e.read().decode()[:500]
        except Exception: body=''
        return None,f'QUOTE_HTTP_{e.code}:{body}'
    except Exception as e:return None,'QUOTE_ERROR:'+type(e).__name__

def run():
    src=load(DATA/'realizable-performance.json',{})
    rows=src.get('plausible_rows') or []
    now=datetime.now(timezone.utc).isoformat(); out=[]
    for r in rows:
        chain=str(r.get('chain') or '').upper(); token=r.get('token'); entry=float(r.get('entry_price_usd') or 0)
        # Exact token base units require decimals. Do not invent them: quote only when source carries decimals.
        dec=r.get('token_decimals')
        if chain in ('SOL','SOLANA'):
            out.append({**r,'cash_status':'QUOTE_UNAVAILABLE','cash_reason':'SOLANA_QUOTER_NOT_IMPLEMENTED_YET','quote_checked_at':now}); continue
        if not token or entry<=0 or dec is None:
            out.append({**r,'cash_status':'QUOTE_UNAVAILABLE','cash_reason':'TOKEN_DECIMALS_NOT_VERIFIED','quote_checked_at':now}); continue
        amount=max(1,int((1.0/entry)*(10**int(dec))))
        q,err=quote(chain,token,amount)
        if err:
            out.append({**r,'cash_status':'QUOTE_UNAVAILABLE','cash_reason':err,'quote_checked_at':now}); continue
        buy=int(q.get('buyAmount') or 0); net=buy/1_000_000
        out.append({**r,'cash_status':'CASH_QUOTE_VERIFIED','cash_reason':None,'quote_checked_at':now,'sell_amount_base_units':amount,'quoted_usd_value':round(net,6),'quote_liquidity_available':q.get('liquidityAvailable'),'quote_issues':q.get('issues'),'quote_route':q.get('route'),'proof_level':'0X_FIRM_QUOTE_NOT_EXECUTED'})
    verified=[x for x in out if x.get('cash_status')=='CASH_QUOTE_VERIFIED']; invested=len(verified); value=sum(float(x.get('quoted_usd_value') or 0) for x in verified)
    payload={'updated_at':now,'method':'CASH_VERIFIED_V1_0X_FIRM_QUOTE','source_market_eligible_count':len(rows),'cash_quote_verified_count':len(verified),'quote_unavailable_count':len(out)-len(verified),'cash_verified_investment_usd':float(invested),'cash_verified_quoted_value_usd':round(value,6),'cash_verified_profit_usd':round(value-invested,6),'cash_verified_roi_pct':round(((value/invested)-1)*100,4) if invested else 0.0,'important_limit':'FIRM QUOTE VERIFIED, NOT TRADE EXECUTED. Solana remains separate until its quote path is implemented.','rows':out}
    write(DATA/'cash-verified-performance.json',payload)
    write(DATA/'cash-verified-summary.json',{k:v for k,v in payload.items() if k!='rows'})
    print(json.dumps(load(DATA/'cash-verified-summary.json',{}),indent=2)); return payload

if __name__=='__main__':run()
