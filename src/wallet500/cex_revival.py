from __future__ import annotations
import gzip, json, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

UA={'User-Agent':'Wallet500/1.4','Accept':'application/json'}

def _get(url,timeout=12):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def _f(v):
    try:return float(v or 0)
    except:return 0.0

def _pct(cur,prev):
    try:
        cur=float(cur);prev=float(prev)
        if prev==0:return 0.0
        return (cur/prev-1.0)*100.0
    except:return 0.0

def _norm_symbol(sym):
    s=(sym or '').upper().strip().replace('-SWAP','').replace('-','').replace('_','')
    # KuCoin perpetual symbols commonly use USDTM while peers use USDT.
    # Normalize only the quote suffix; preserve the base symbol exactly.
    if s.endswith('USDTM'):s=s[:-1]
    return s

def _row(ex,sym,price=0,change=0,vol=0,fund=0,oi=0,contract=None):
    return {'exchange':ex,'symbol':_norm_symbol(sym),'contract':contract or sym,'price':_f(price),'change_24h_pct':_f(change),'volume_24h':_f(vol),'funding_rate':_f(fund),'open_interest':_f(oi)}

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
    xs=(_get('https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES').get('data') or [])
    return [_row('bitget',x['symbol'],x.get('lastPr'),_f(x.get('change24h'))*100,x.get('usdtVolume') or x.get('quoteVolume'),x.get('fundingRate'),x.get('holdingAmount')) for x in xs if x.get('symbol','').endswith('USDT')]

def mexc():
    xs=_get('https://contract.mexc.com/api/v1/contract/ticker').get('data',[]) or []
    return [_row('mexc',x['symbol'],x.get('lastPrice'),_f(x.get('riseFallRate'))*100,x.get('amount24'),x.get('fundingRate'),x.get('holdVol')) for x in xs if x.get('symbol','').endswith('_USDT')]

def kucoin():
    xs=_get('https://api-futures.kucoin.com/api/v1/contracts/active').get('data',[]) or [];out=[]
    for x in xs:
        s=x.get('symbol','')
        if 'USDT' not in s:continue
        out.append(_row('kucoin',s,x.get('lastTradePrice'),_f(x.get('priceChgPct'))*100,x.get('turnoverOf24h'),x.get('fundingFeeRate'),x.get('openInterest'),s))
    return out

def htx():
    xs=_get('https://api.hbdm.com/linear-swap-ex/market/detail/batch_merged?contract_code=all').get('ticks',[]) or [];out=[]
    for x in xs:
        s=x.get('contract_code') or x.get('symbol','')
        if 'USDT' not in s:continue
        op=_f(x.get('open'));close=_f(x.get('close'));ch=(close/op-1)*100 if op else 0
        out.append(_row('htx',s,close,ch,x.get('amount') or x.get('vol'),0,0,s))
    return out

def bingx():
    xs=_get('https://open-api.bingx.com/openApi/swap/v2/quote/ticker').get('data',[]) or []
    if isinstance(xs,dict):xs=[xs]
    return [_row('bingx',x['symbol'],x.get('lastPrice'),x.get('priceChangePercent'),x.get('quoteVolume'),0,0,x['symbol']) for x in xs if x.get('symbol','').endswith('-USDT')]

def coinex():
    xs=_get('https://api.coinex.com/v2/futures/ticker').get('data',[]) or []
    return [_row('coinex',x.get('market',''),x.get('last'),_f(x.get('open')) and ((_f(x.get('last'))/_f(x.get('open'))-1)*100),x.get('value'),x.get('funding_rate'),x.get('open_interest')) for x in xs if x.get('market','').endswith('USDT')]

def binance():
    xs=_get('https://fapi.binance.com/fapi/v1/ticker/24hr');prem={}
    try:prem={x.get('symbol'):x for x in _get('https://fapi.binance.com/fapi/v1/premiumIndex')}
    except Exception:pass
    return [_row('binance',x['symbol'],x.get('lastPrice'),x.get('priceChangePercent'),x.get('quoteVolume'),(prem.get(x['symbol']) or {}).get('lastFundingRate'),0) for x in xs if x.get('symbol','').endswith('USDT')]

SOURCES=[('gate',gate),('bybit',bybit),('okx',okx),('bitget',bitget),('mexc',mexc),('kucoin',kucoin),('htx',htx),('bingx',bingx),('coinex',coinex),('binance',binance)]

def _load(path,default):
    gz=Path(str(path)+'.gz')
    try:
        if gz.exists():
            with gzip.open(gz,'rt',encoding='utf-8') as f:return json.load(f)
        if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default
    return default

def _write_state_lossless(path,state):
    gz=Path(str(path)+'.gz')
    tmp=Path(str(gz)+'.tmp')
    with gzip.open(tmp,'wt',encoding='utf-8',compresslevel=6) as f:json.dump(state,f,separators=(',',':'))
    tmp.replace(gz)
    # cex-state is a rolling observation state, not a call ledger. Migration is
    # lossless: preserve every retained observation and remove only the redundant
    # uncompressed working-tree copy after the gzip file has been atomically written.
    if path.exists():path.unlink()

def _enrich_with_history(rows,state,now):
    histories=state.get('markets') if isinstance(state.get('markets'),dict) else {}
    enriched=[]
    for r in rows:
        key=f"{r['exchange']}:{r['symbol']}";hist=histories.get(key) if isinstance(histories.get(key),list) else []
        prev=hist[-1] if hist else {}
        e={**r,'price_delta_pct':round(_pct(r['price'],prev.get('price')),4) if prev else 0.0,'volume24_delta_pct':round(_pct(r['volume_24h'],prev.get('volume_24h')),4) if prev else 0.0,'oi_delta_pct':round(_pct(r['open_interest'],prev.get('open_interest')),4) if prev and r.get('open_interest') and prev.get('open_interest') else 0.0,'funding_delta':round(r.get('funding_rate',0)-_f(prev.get('funding_rate')),8) if prev else 0.0,'history_points':len(hist)}
        hist.append({'observed_at':now,'price':r['price'],'change_24h_pct':r['change_24h_pct'],'volume_24h':r['volume_24h'],'funding_rate':r['funding_rate'],'open_interest':r['open_interest']})
        histories[key]=hist[-96:]
        enriched.append(e)
    return enriched,{'version':4,'updated_at':now,'markets':histories,'signal_milestones':state.get('signal_milestones') if isinstance(state.get('signal_milestones'),dict) else {}}

def _classify(markets):
    funds=[m['funding_rate'] for m in markets if m.get('funding_rate')]
    max_pos=max(funds,default=0);min_neg=min(funds,default=0)
    price_acc=max([m.get('price_delta_pct',0) for m in markets],default=0)
    oi_acc=max([m.get('oi_delta_pct',0) for m in markets],default=0)
    if min_neg<=-0.003 and price_acc>0:return 'SHORT_SQUEEZE_REVIVAL'
    if max_pos>=0.001 and price_acc>0:return 'CROWDED_LONG_MOMENTUM'
    if abs(max_pos)<0.001 and abs(min_neg)<0.001 and price_acc>0:return 'NEUTRAL_FUNDING_BREAKOUT'
    if oi_acc>=8 and price_acc>=2:return 'OI_LED_BREAKOUT'
    return 'CEX_REVIVAL'

def _reference_market(markets):
    valid=[m for m in markets if _f(m.get('price'))>0]
    if not valid:return {}
    return max(valid,key=lambda m:(_f(m.get('volume_24h')),_f(m.get('open_interest'))))

def _market_signal(m):
    change=_f(m.get('change_24h_pct'));price_acc=_f(m.get('price_delta_pct'));vol_acc=_f(m.get('volume24_delta_pct'));oi_acc=_f(m.get('oi_delta_pct'));fund_abs=abs(_f(m.get('funding_rate')));vol=_f(m.get('volume_24h'))
    score=0;reasons=[];hits=[]
    if change>=8:score+=10;hits.append('MOMENTUM');reasons.append(f'24h momentum {change:.1f}%')
    if change>=20:score+=10
    if change>=50:score+=5
    if price_acc>=2:score+=15;hits.append('PRICE_ACCEL');reasons.append(f'price acceleration {price_acc:.2f}%/scan')
    if price_acc>=5:score+=10
    if vol_acc>=8:score+=12;hits.append('VOLUME_ACCEL');reasons.append(f'volume acceleration {vol_acc:.1f}%/scan')
    if vol_acc>=25:score+=8
    if oi_acc>=5:score+=15;hits.append('OI_ACCEL');reasons.append(f'OI acceleration {oi_acc:.1f}%/scan')
    if oi_acc>=15:score+=10
    if fund_abs>=0.0005:score+=8;hits.append('FUNDING_DIVERGENCE');reasons.append(f'funding divergence {fund_abs*100:.3f}%')
    if fund_abs>=0.003:score+=8
    if vol>=10_000_000:score+=5;reasons.append('large derivatives turnover')
    return {'exchange':m.get('exchange'),'score':score,'hits':hits,'hit_count':len(hits),'reasons':reasons,'change':change,'price_acc':price_acc,'vol_acc':vol_acc,'oi_acc':oi_acc,'fund_abs':fund_abs}

def _milestone(now,markets,score,conf,change,price_acc,vol_acc,oi_acc,fund_abs,kind,coherence=None):
    ref=_reference_market(markets);coherence=coherence or {}
    return {
        'kind':kind,'observed_at':now,'reference_exchange':ref.get('exchange'),
        'reference_price':_f(ref.get('price')),'reference_change_24h_pct':_f(ref.get('change_24h_pct')),
        'score':min(int(score),100),'confirmations':int(conf),'change_24h_max_pct':round(change,4),
        'price_acceleration_max_pct':round(price_acc,4),'volume_acceleration_max_pct':round(vol_acc,4),
        'oi_acceleration_max_pct':round(oi_acc,4),'funding_abs_max':fund_abs,
        'coherent_exchange':coherence.get('exchange'),'coherent_feature_hits':coherence.get('hit_count',0),
        'coherent_confirmations':coherence.get('confirmations',0),'dispersion_status':coherence.get('dispersion_status'),
    }

def _fetch_source(name,fn):
    got=fn()
    return name,got

def run_cex_revival(out:Path,now:str):
    rows=[];errors=[];health={}
    # Independent exchanges are I/O-bound: scan them concurrently so one slow
    # endpoint cannot serialize the entire Old-Coin Revival lane.
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures={pool.submit(_fetch_source,name,fn):name for name,fn in SOURCES}
        for fut in as_completed(futures):
            name=futures[fut]
            try:
                _,got=fut.result();rows.extend(got);health[name]={'ok':bool(got),'contracts':len(got)}
            except Exception as e:
                errors.append({'exchange':name,'error':str(e)[:300]});health[name]={'ok':False,'contracts':0}
    state_path=out/'cex-state.json';prev_state=_load(state_path,{})
    rows,state=_enrich_with_history(rows,prev_state,now)
    milestones=state['signal_milestones']
    groups={}
    for x in rows:
        if x['symbol'].endswith('USDT'):groups.setdefault(x['symbol'],[]).append(x)
    alerts=[]
    for sym,markets in groups.items():
        exs={m['exchange'] for m in markets};conf=len(exs)
        changes=[m['change_24h_pct'] for m in markets if m['change_24h_pct']]
        funds=[m['funding_rate'] for m in markets if m['funding_rate']]
        price_acc=max([m.get('price_delta_pct',0) for m in markets],default=0)
        vol_acc=max([m.get('volume24_delta_pct',0) for m in markets],default=0)
        oi_acc=max([m.get('oi_delta_pct',0) for m in markets],default=0)
        fund_abs=max([abs(x) for x in funds],default=0);change=max(changes,default=0)
        dispersion=(max(changes)-min(changes)) if len(changes)>=2 else 0

        local=[_market_signal(m) for m in markets]
        best=max(local,key=lambda x:(x['score'],x['hit_count']),default={'score':0,'hit_count':0,'reasons':[],'exchange':None})
        # Cross-exchange confirmation is earned only when another venue has a real
        # anomaly feature of its own. This prevents maxima from unrelated venues
        # being stitched into a synthetic "Frankenstein" signal.
        coherent=[x for x in local if x['hit_count']>0]
        coherent_conf=len({x['exchange'] for x in coherent if x.get('exchange')})
        score=int(best.get('score',0));reasons=list(best.get('reasons') or [])
        if coherent_conf>=2:score+=8;reasons.append(f'{coherent_conf} coherent exchange confirmation')
        if coherent_conf>=4:score+=8
        if coherent_conf>=6:score+=6

        if dispersion>=25:
            score-=8;dispersion_status='EXTREME_DISLOCATION_VERIFY';reasons.append(f'extreme cross-exchange dislocation {dispersion:.1f}pp')
        elif dispersion>=8:
            dispersion_status='ELEVATED_DISPERSION_VERIFY';reasons.append(f'elevated cross-exchange dispersion {dispersion:.1f}pp')
        else:
            dispersion_status='COHERENT_RANGE'
            if coherent_conf>=2 and len(changes)>=2:score+=3;reasons.append('cross-exchange momentum agreement')
        score=max(0,score)
        coherence={'exchange':best.get('exchange'),'hit_count':best.get('hit_count',0),'confirmations':coherent_conf,'dispersion_status':dispersion_status}

        ms=milestones.setdefault(sym,{})
        snapshot=_milestone(now,markets,score,conf,change,price_acc,vol_acc,oi_acc,fund_abs,'FIRST_SEEN',coherence)
        if 'first_seen' not in ms:ms['first_seen']=snapshot
        anomaly=bool(best.get('hit_count'))
        if anomaly and 'first_anomaly' not in ms:
            ms['first_anomaly']={**snapshot,'kind':'FIRST_ANOMALY'}
        if score>=35:
            if 'first_alert' not in ms:ms['first_alert']={**snapshot,'kind':'FIRST_ALERT'}
            alerts.append({'symbol':sym,'cex_revival_score':min(score,100),'archetype':_classify(markets),'reasons':reasons,'confirmations':conf,'coherent_confirmations':coherent_conf,'coherent_exchange':best.get('exchange'),'coherent_feature_hits':best.get('hits',[]),'dispersion_status':dispersion_status,'exchanges':sorted(exs),'change_24h_max_pct':round(change,4),'price_acceleration_max_pct':round(price_acc,4),'volume_acceleration_max_pct':round(vol_acc,4),'oi_acceleration_max_pct':round(oi_acc,4),'funding_abs_max':fund_abs,'momentum_dispersion_pp':round(dispersion,3),'milestones':ms,'markets':markets})
    _write_state_lossless(state_path,state)
    alerts.sort(key=lambda x:(x['cex_revival_score'],x['coherent_confirmations'],x['confirmations']),reverse=True)
    payload={'version':6,'generated_at':now,'requested_sources':[x[0] for x in SOURCES],'source_health':health,'healthy_sources':sum(1 for x in health.values() if x['ok']),'contracts_seen':len(rows),'symbols_seen':len(groups),'alerts_count':len(alerts),'scoring_method':'SINGLE_VENUE_FEATURE_COHERENCE_PLUS_REAL_CROSS_VENUE_CONFIRMATION','dispersion_policy':'NO_BONUS_FOR_DISPERSION;_GE25PP_PENALIZED_AND_FLAGGED_FOR_VERIFICATION','milestone_method':'IMMUTABLE_FIRST_SEEN_FIRST_FEATURE_ANOMALY_FIRST_SCORE35_ALERT','errors':errors,'alerts':alerts}
    (out/'cex-revival-radar.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    learning={'version':4,'updated_at':now,'purpose':'learn which early CEX revival features precede verified follow-through; case studies are not counted as Wallet500 calls','features':['same_exchange_feature_coherence','price_acceleration','volume24_acceleration','open_interest_acceleration','funding_divergence','real_cross_exchange_confirmation','momentum_dispersion_as_verification_risk'],'scoring_method':'SINGLE_VENUE_FEATURE_COHERENCE_PLUS_REAL_CROSS_VENUE_CONFIRMATION','milestone_method':'IMMUTABLE_FIRST_SEEN_FIRST_FEATURE_ANOMALY_FIRST_SCORE35_ALERT','top_candidates':[{'symbol':x['symbol'],'score':x['cex_revival_score'],'archetype':x['archetype'],'confirmations':x['confirmations'],'coherent_confirmations':x['coherent_confirmations'],'coherent_exchange':x['coherent_exchange'],'coherent_feature_hits':x['coherent_feature_hits'],'dispersion_status':x['dispersion_status'],'price_acceleration_max_pct':x['price_acceleration_max_pct'],'volume_acceleration_max_pct':x['volume_acceleration_max_pct'],'oi_acceleration_max_pct':x['oi_acceleration_max_pct'],'funding_abs_max':x['funding_abs_max'],'milestones':x.get('milestones',{})} for x in alerts[:50]]}
    (out/'cex-learning.json').write_text(json.dumps(learning,indent=2),encoding='utf-8')
    return payload
