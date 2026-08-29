from __future__ import annotations
import json, os, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATA=Path('data')
EVM_API='https://api.0x.org/swap/allowance-holder/quote'
SOLANA_API='https://api.0x.org/solana/swap-instructions'
KEY=os.getenv('ZEROX_API_KEY','').strip()
CHAIN_IDS={'ETH':1,'ETHEREUM':1,'BSC':56,'BNB':56}
STABLE={
    1:('0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',6,'USDC'),
    56:('0x55d398326f99059fF775485246999027B3197955',18,'USDT'),
}
EVM_RPC={
    1:os.getenv('ETH_RPC_URL','https://ethereum-rpc.publicnode.com').strip(),
    56:os.getenv('BSC_RPC_URL','https://bsc-rpc.publicnode.com').strip(),
}
SOLANA_RPC_URL=os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com').strip()
SOLANA_USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
SOLANA_USDC_DECIMALS=6
EVM_TAKER=os.getenv('EVM_QUOTE_TAKER','0x0000000000000000000000000000000000000001').strip()
SOLANA_TAKER=os.getenv('SOLANA_QUOTE_TAKER','ZeroEx1111111111111111111111111111111111111').strip()
DECIMALS_SELECTOR='0x313ce567'
_decimals_cache={}

def load(p,d):
    try:return json.loads(p.read_text())
    except Exception:return d

def write(p,x):p.write_text(json.dumps(x,indent=2))

def _post_json(url,payload,headers=None,timeout=20):
    body=json.dumps(payload).encode()
    h={'Content-Type':'application/json','Accept':'application/json','User-Agent':'Wallet500/0.2'}
    if headers:h.update(headers)
    req=urllib.request.Request(url,data=body,headers=h,method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read())

def _http_error(prefix,e):
    try: body=e.read().decode()[:500]
    except Exception: body=''
    return f'{prefix}_HTTP_{e.code}:{body}'

def evm_token_decimals(chain,token):
    cid=CHAIN_IDS.get(str(chain).upper())
    key=('evm',cid,str(token).lower())
    if key in _decimals_cache:return _decimals_cache[key]
    rpc=EVM_RPC.get(cid)
    if not cid or not rpc or not token:return None,'EVM_DECIMALS_RPC_UNAVAILABLE'
    payload={'jsonrpc':'2.0','id':1,'method':'eth_call','params':[{'to':token,'data':DECIMALS_SELECTOR},'latest']}
    try:
        d=_post_json(rpc,payload)
        raw=d.get('result') if isinstance(d,dict) else None
        if not raw or raw=='0x':return None,'EVM_DECIMALS_EMPTY'
        dec=int(raw,16)
        if not 0<=dec<=36:return None,'EVM_DECIMALS_OUT_OF_RANGE'
        _decimals_cache[key]=dec
        return dec,None
    except urllib.error.HTTPError as e:return None,_http_error('EVM_DECIMALS',e)
    except Exception as e:return None,'EVM_DECIMALS_ERROR:'+type(e).__name__

def solana_token_decimals(token):
    key=('solana',str(token))
    if key in _decimals_cache:return _decimals_cache[key]
    if not SOLANA_RPC_URL or not token:return None,'SOLANA_DECIMALS_RPC_UNAVAILABLE'
    payload={'jsonrpc':'2.0','id':1,'method':'getTokenSupply','params':[token,{'commitment':'confirmed'}]}
    try:
        d=_post_json(SOLANA_RPC_URL,payload)
        value=((d or {}).get('result') or {}).get('value') if isinstance(d,dict) else None
        dec=value.get('decimals') if isinstance(value,dict) else None
        if dec is None:return None,'SOLANA_DECIMALS_EMPTY'
        dec=int(dec)
        if not 0<=dec<=30:return None,'SOLANA_DECIMALS_OUT_OF_RANGE'
        _decimals_cache[key]=dec
        return dec,None
    except urllib.error.HTTPError as e:return None,_http_error('SOLANA_DECIMALS',e)
    except Exception as e:return None,'SOLANA_DECIMALS_ERROR:'+type(e).__name__

def _position_base_units(entry,decimals):
    try:
        p=Decimal(str(entry))
        if p<=0:return None
        units=(Decimal('1')/p)*(Decimal(10)**int(decimals))
        return max(1,int(units))
    except (InvalidOperation,ValueError,TypeError,OverflowError):
        return None

def evm_quote(chain,token,amount):
    cid=CHAIN_IDS.get(str(chain).upper())
    if not cid:return None,'CHAIN_NOT_SUPPORTED_BY_EVM_QUOTER'
    if not KEY:return None,'ZEROX_API_KEY_MISSING'
    stable,stable_decimals,stable_symbol=STABLE[cid]
    q=urllib.parse.urlencode({'chainId':cid,'sellToken':token,'buyToken':stable,'sellAmount':str(amount),'taker':EVM_TAKER})
    req=urllib.request.Request(EVM_API+'?'+q,headers={'0x-api-key':KEY,'0x-version':'v2','Accept':'application/json','User-Agent':'Wallet500/0.2'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return {'quote':json.loads(r.read()),'stable_decimals':stable_decimals,'stable_symbol':stable_symbol},None
    except urllib.error.HTTPError as e:return None,_http_error('QUOTE',e)
    except Exception as e:return None,'QUOTE_ERROR:'+type(e).__name__

def solana_quote(token,amount):
    if not KEY:return None,'ZEROX_API_KEY_MISSING'
    payload={'token_in':token,'token_out':SOLANA_USDC,'amount_in':int(amount),'taker':SOLANA_TAKER,'slippage_bps':50}
    try:
        q=_post_json(SOLANA_API,payload,{'0x-api-key':KEY})
        amount_out=int(q.get('amount_out') or 0)
        if amount_out<=0:return None,'SOLANA_QUOTE_ZERO_OUTPUT'
        return {'quote':q,'stable_decimals':SOLANA_USDC_DECIMALS,'stable_symbol':'USDC'},None
    except urllib.error.HTTPError as e:return None,_http_error('SOLANA_QUOTE',e)
    except Exception as e:return None,'SOLANA_QUOTE_ERROR:'+type(e).__name__

def run():
    src=load(DATA/'realizable-performance.json',{})
    rows=src.get('plausible_rows') or []
    now=datetime.now(timezone.utc).isoformat(); out=[]
    for r in rows:
        chain=str(r.get('chain') or '').upper(); token=r.get('token')
        try: entry=float(r.get('entry_price_usd') or 0)
        except Exception: entry=0.0
        if not token or entry<=0:
            out.append({**r,'cash_status':'QUOTE_UNAVAILABLE','cash_reason':'TOKEN_OR_ENTRY_INVALID','quote_checked_at':now}); continue

        source_dec=r.get('token_decimals')
        if source_dec is not None:
            try: dec=int(source_dec); dec_err=None
            except Exception: dec=None; dec_err='SOURCE_TOKEN_DECIMALS_INVALID'
        elif chain in ('SOL','SOLANA'):
            dec,dec_err=solana_token_decimals(token)
        else:
            dec,dec_err=evm_token_decimals(chain,token)

        if dec is None:
            out.append({**r,'cash_status':'QUOTE_UNAVAILABLE','cash_reason':dec_err or 'TOKEN_DECIMALS_NOT_VERIFIED','quote_checked_at':now}); continue
        amount=_position_base_units(entry,dec)
        if amount is None:
            out.append({**r,'cash_status':'QUOTE_UNAVAILABLE','cash_reason':'POSITION_BASE_UNITS_INVALID','quote_checked_at':now,'token_decimals_verified':dec}); continue

        result,err=(solana_quote(token,amount) if chain in ('SOL','SOLANA') else evm_quote(chain,token,amount))
        if err:
            out.append({**r,'cash_status':'QUOTE_UNAVAILABLE','cash_reason':err,'quote_checked_at':now,'token_decimals_verified':dec,'sell_amount_base_units':amount}); continue

        q=result['quote']; stable_decimals=int(result['stable_decimals'])
        raw_out=int(q.get('amount_out') or 0) if chain in ('SOL','SOLANA') else int(q.get('buyAmount') or 0)
        net=Decimal(raw_out)/(Decimal(10)**stable_decimals)
        out.append({
            **r,'cash_status':'EXIT_QUOTE_VERIFIED','cash_reason':None,'quote_checked_at':now,
            'token_decimals_verified':dec,'sell_amount_base_units':amount,
            'quote_stable_symbol':result['stable_symbol'],'quote_stable_decimals':stable_decimals,
            'quoted_usd_value':round(float(net),6),
            'quote_liquidity_available':q.get('liquidityAvailable') if isinstance(q,dict) else None,
            'quote_issues':q.get('issues') if isinstance(q,dict) else None,
            'quote_route':q.get('route') if chain not in ('SOL','SOLANA') else q.get('route_plan'),
            'proof_level':'0X_EXIT_FIRM_QUOTE_NOT_EXECUTED_NOT_ENTRY_PROOF'
        })
    verified=[x for x in out if x.get('cash_status')=='EXIT_QUOTE_VERIFIED']
    invested=len(verified); value=sum(float(x.get('quoted_usd_value') or 0) for x in verified)
    profit=value-invested
    roi=((value/invested)-1)*100 if invested else 0.0
    payload={
        'updated_at':now,'method':'CASH_EXIT_QUOTE_VERIFIED_V2_0X',
        'source_market_eligible_count':len(rows),'cash_quote_verified_count':len(verified),
        'exit_quote_verified_count':len(verified),'quote_unavailable_count':len(out)-len(verified),
        'cash_verified_investment_usd':float(invested),'cash_verified_quoted_value_usd':round(value,6),
        'cash_verified_profit_usd':round(profit,6),'cash_verified_roi_pct':round(roi,4),
        'hypothetical_entry_cost_usd':float(invested),'quoted_exit_value_usd':round(value,6),
        'quoted_exit_profit_vs_hypothetical_entry_usd':round(profit,6),
        'quoted_exit_roi_vs_hypothetical_entry_pct':round(roi,4),
        'truth_note':'A verified row proves a current 0x exit quote for the token quantity implied by a historical $1 entry price. It does NOT prove that the historical buy was executable or executed.',
        'important_limit':'FIRM EXIT QUOTE VERIFIED, NOT TRADE EXECUTED AND NOT HISTORICAL ENTRY-EXECUTION PROOF.',
        'rows':out
    }
    write(DATA/'cash-verified-performance.json',payload)
    write(DATA/'cash-verified-summary.json',{k:v for k,v in payload.items() if k!='rows'})
    print(json.dumps(load(DATA/'cash-verified-summary.json',{}),indent=2)); return payload

if __name__=='__main__':run()
