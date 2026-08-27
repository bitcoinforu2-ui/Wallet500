from __future__ import annotations
import json, urllib.request
from pathlib import Path

UA={'User-Agent':'Wallet500/1.2','Accept':'application/json'}
def _get(url,timeout=20):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode())
def _f(v):
    try:return float(v or 0)
    except:return 0.0
def _row(ex,sym,price=0,change=0,vol=0,fund=0,oi=0,contract=None):
    return {'exchange':ex,'symbol':sym.replace('-','').replace('_',''),'contract':contract or sym,'price':_f(price),'change_24h_pct':_f(change),'volume_24h':_f(vol),'funding_rate':_f(fund),'open_interest':_f(oi)}

def gate():
    return [_row('gate',x['contract'],x.get('last'),x.get('change_percentage'),x.get('volume_24h_quote') or x.get('volume_24h'),x.get('funding_rate'),x.get('total_size'),x['contract']) for x in _get('https://api.gateio.ws/api/v4/futures/usdt/tickers') if x.get('contract','').endswith('_USDT')]
def bybit():
    xs=(_get('https://api.bybit.com/v5/market/tickers?category=linear').get('result') or {}).get('list',[])
    return [_row('bybit',x['symbol'],x.get('lastPrice'),_f(x.get('price24hPcnt'))*100,x.get('turnover24h'),x.get('fundingRate'),x.get('openInterestValue') or x.get('openInterest')) for x in xs if x.get('symbol','').endswith('USDT')]
def okx():
    xs=_get('https://www.okx.com/api/v5/market/tickers?instType=SWAP').get('data',[]);out=[]
    for x in xs:
        s=x.get('instId','')
        if not s.endswith('-USDT-SWAP'):continue
        op=_f(x.get('open24h'));last=_f(x.get('last'));ch=(last/op-1)*100 if op else 0
        out.append(_row('okx',s.replace('-SWAP',''),last,ch,x.get('volCcy24h'),0,0,s))
    return out
def bitget():
    d=_get('https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES');xs=d.get('data',[]) or []
    return [_row('bitget',x['symbol'],x.get('lastPr'),_f(x.get('change24h'))*100,x.get('usdtVolume') or x.get('quoteVolume'),x.get('fundingRate'),x.get('holdingAmount')) for x in xs if x.get('symbol','').endswith('USDT')]
def mexc():
    xs=_get('https://contract.mexc.com/api/v1/contract/ticker').get('data',[]) or []
    return [_row('mexc',x['symbol'],x.get('lastPrice'),_f(x.get('riseFallRate'))*100,x.get('amount24'),x.get('fundingRate'),x.get('holdVol')) for x in xs if x.get('symbol','').endswith('_USDT')]
def kucoin():
    xs=_get('https://api-futures.kucoin.com/api/v1/contracts/active').get('data',[]) or []
    out=[]
    for x in xs:
        s=x.get('symbol','')
        if 'USDT' not in s:continue
        out.append(_row('kucoin',s,x.get('lastTradePrice'),_f(x.get('priceChgPct'))*100,x.get('turnoverOf24h'),x.get('fundingFeeRate'),x.get('openInterest'),s))
    return out
def htx():
    xs=_get('https://api.hbdm.com/linear-swap-ex/market/detail/batch_merged?contract_code=all').get('ticks',[]) or []
    out=[]
    for x in xs:
        s=x.get('contract_code') or x.get('symbol','')
        if 'USDT' not in s:continue
        op=_f(x.get('open'));close=_f(x.get('close'));ch=(close/op-1)*100 if op else 0
        out.append(_row('htx',s,close,ch,x.get('amount') or x.get('vol'),0,0,s))
    return out
def bingx():
    d=_get('https://open-api.bingx.com/openApi/swap/v2/quote/ticker');xs=d.get('data',[]) or []
    if isinstance(xs,dict):xs=[xs]
    return [_row('bingx',x['symbol'],x.get('lastPrice'),x.get('priceChangePercent'),x.get('quoteVolume'),0,0,x['symbol']) for x in xs if x.get('symbol','').endswith('-USDT')]
def coinex():
    d=_get('https://api.coinex.com/v2/futures/ticker');xs=d.get('data',[]) or []
    return [_row('coinex',x.get('market',''),x.get('last'),_f(x.get('open')) and ((_f(x.get('last'))/_f(x.get('open'))-1)*100),x.get('value'),x.get('funding_rate'),x.get('open_interest')) for x in xs if x.get('market','').endswith('USDT')]
def binance():
    # Binance is strategically important, but endpoint accessibility varies by runner/region.
    xs=_get('https://fapi.binance.com/fapi/v1/ticker/24hr');prem={}
    try:prem={x.get('symbol'):x for x in _get('https://fapi.binance.com/fapi/v1/premiumIndex')}
    except Exception:pass
    return [_row('binance',x['symbol'],x.get('lastPrice'),x.get('priceChangePercent'),x.get('quoteVolume'),(prem.get(x['symbol']) or {}).get('lastFundingRate'),0) for x in xs if x.get('symbol','').endswith('USDT')]

SOURCES=[('gate',gate),('bybit',bybit),('okx',okx),('bitget',bitget),('mexc',mexc),('kucoin',kucoin),('htx',htx),('bingx',bingx),('coinex',coinex),('binance',binance)]

def run_cex_revival(out:Path,now:str):
    rows=[];errors=[];health={}
    for name,fn in SOURCES:
        try:
            got=fn();rows.extend(got);health[name]={'ok':bool(got),'contracts':len(got)}
        except Exception as e:errors.append({'exchange':name,'error':str(e)[:300]});health[name]={'ok':False,'contracts':0}
    groups={}
    for x in rows:
        if x['symbol'].endswith('USDT'):groups.setdefault(x['symbol'],[]).append(x)
    alerts=[]
    for sym,markets in groups.items():
        exs={m['exchange'] for m in markets};conf=len(exs);changes=[m['change_24h_pct'] for m in markets if m['change_24h_pct']]
        funds=[m['funding_rate'] for m in markets if m['funding_rate']];vols=[m['volume_24h'] for m in markets if m['volume_24h']]
        change=max(changes,default=0);absfund=max([abs(x) for x in funds],default=0);score=0;reasons=[]
        if change>=8:score+=15;reasons.append(f'momentum {change:.1f}%')
        if change>=20:score+=15
        if change>=50:score+=10
        if absfund>=0.0005:score+=10;reasons.append(f'funding divergence {absfund*100:.3f}%')
        if absfund>=0.003:score+=15
        if conf>=2:score+=10;reasons.append(f'{conf} exchange confirmation')
        if conf>=4:score+=10
        if conf>=6:score+=10
        if max(vols,default=0)>=1_000_000:score+=5
        if max(vols,default=0)>=10_000_000:score+=5;reasons.append('large derivatives turnover')
        # dispersion flags exchange-specific dislocation instead of blindly averaging it away.
        dispersion=(max(changes)-min(changes)) if len(changes)>=2 else 0
        if dispersion>=8:score+=5;reasons.append(f'cross-exchange price momentum dispersion {dispersion:.1f}pp')
        if score>=40:alerts.append({'symbol':sym,'cex_revival_score':min(score,100),'reasons':reasons,'confirmations':conf,'exchanges':sorted(exs),'change_24h_max_pct':change,'funding_abs_max':absfund,'momentum_dispersion_pp':round(dispersion,3),'markets':markets})
    alerts.sort(key=lambda x:(x['cex_revival_score'],x['confirmations']),reverse=True)
    payload={'version':2,'generated_at':now,'requested_sources':[x[0] for x in SOURCES],'source_health':health,'healthy_sources':sum(1 for x in health.values() if x['ok']),'contracts_seen':len(rows),'symbols_seen':len(groups),'alerts_count':len(alerts),'errors':errors,'alerts':alerts}
    (out/'cex-revival-radar.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return payload
