from __future__ import annotations
import gzip, json, math
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone


def _load(p,default):
    gz=Path(str(p)+'.gz')
    try:
        if gz.exists():
            with gzip.open(gz,'rt',encoding='utf-8') as f:return json.load(f)
        if p.exists():return json.loads(p.read_text(encoding='utf-8'))
    except:return default
    return default

def _median(xs):
    xs=sorted(float(x) for x in xs if x is not None)
    if not xs:return 0.0
    n=len(xs);return xs[n//2] if n%2 else (xs[n//2-1]+xs[n//2])/2

def _pct(cur,base):
    try:return (float(cur)/float(base)-1)*100 if float(base) else 0.0
    except:return 0.0

def _consensus_profiles(profiles):
    grouped=defaultdict(list)
    for p in profiles: grouped[p['symbol']].append(p)
    out=[]
    for sym,rows in grouped.items():
        n=len(rows); feature_counts=Counter()
        for r in rows:
            feature_counts.update(set(r.get('pattern') or []))
        consensus_features=[]
        for feature,count in feature_counts.most_common():
            support_pct=round(count/max(1,n)*100,2)
            if count>=2 or n==1 or support_pct>=50:
                consensus_features.append({'feature':feature,'supporting_markets':count,'support_pct':support_pct})
        scores=[r.get('dna_score',0) for r in rows]
        price_devs=[(r.get('current_deviation') or {}).get('price_pct',0) for r in rows]
        volume_devs=[(r.get('current_deviation') or {}).get('volume_pct',0) for r in rows]
        oi_devs=[(r.get('current_deviation') or {}).get('oi_pct',0) for r in rows]
        exchanges=sorted({r.get('exchange') for r in rows if r.get('exchange')})
        agreement=sum(1 for x in consensus_features if x['support_pct']>=50)
        out.append({
            'symbol':sym,
            'markets_count':n,
            'exchanges':exchanges,
            'consensus_dna_score_median':round(_median(scores),3),
            'consensus_feature_count':agreement,
            'consensus_features':consensus_features,
            'cross_exchange_deviation_median':{
                'price_pct':round(_median(price_devs),3),
                'volume_pct':round(_median(volume_devs),3),
                'oi_pct':round(_median(oi_devs),3),
            },
            'market_profiles':rows,
        })
    out.sort(key=lambda x:(x['consensus_dna_score_median'],x['consensus_feature_count'],x['markets_count']),reverse=True)
    return out

def run_catalyst_dna(out:Path,now:str|None=None):
    now=now or datetime.now(timezone.utc).isoformat()
    state=_load(out/'cex-state.json',{})
    markets=state.get('markets',{}) if isinstance(state,dict) else {}
    profiles=[];source_stats={};archetypes={}
    for key,hist in markets.items():
        if not isinstance(hist,list) or len(hist)<3:continue
        ex,sym=key.split(':',1)
        prices=[x.get('price',0) for x in hist if x.get('price')]
        if not prices:continue
        recent=hist[-1];base_hist=hist[:-1][-24:]
        bp=_median([x.get('price',0) for x in base_hist if x.get('price')]);bv=_median([x.get('volume_24h',0) for x in base_hist if x.get('volume_24h')]);bo=_median([x.get('open_interest',0) for x in base_hist if x.get('open_interest')]);bf=_median([x.get('funding_rate',0) for x in base_hist if x.get('funding_rate') is not None])
        pdev=_pct(recent.get('price',0),bp);vdev=_pct(recent.get('volume_24h',0),bv);odev=_pct(recent.get('open_interest',0),bo) if bo else 0;fdev=float(recent.get('funding_rate',0) or 0)-bf
        quiet=sum(abs(_pct(base_hist[i].get('price',0),base_hist[i-1].get('price',0)))<2 for i in range(1,len(base_hist))) / max(1,len(base_hist)-1)
        pattern=[];score=0
        if quiet>=.65:pattern.append('QUIET_BASELINE');score+=10
        if pdev>=3:pattern.append('PRICE_BREAKOUT');score+=15
        if vdev>=25:pattern.append('VOLUME_EXPANSION');score+=20
        if odev>=8:pattern.append('OI_EXPANSION');score+=20
        if abs(fdev)>=.0005:pattern.append('FUNDING_DIVERGENCE');score+=10
        if recent.get('funding_rate',0)<-.003 and pdev>0:pattern.append('SHORT_SQUEEZE_STRUCTURE');score+=15
        if recent.get('funding_rate',0)>.001 and pdev>0:pattern.append('CROWDED_LONG_STRUCTURE');score+=8
        source_stats.setdefault(ex,{'observations':0,'early_pattern_hits':0});source_stats[ex]['observations']+=1
        if score>=35:source_stats[ex]['early_pattern_hits']+=1
        dna='>'.join(pattern) if pattern else 'NO_CLEAR_PATTERN';archetypes[dna]=archetypes.get(dna,0)+1
        profiles.append({'symbol':sym,'exchange':ex,'history_points':len(hist),'dna_score':min(score,100),'pattern':pattern,'baseline':{'price_median':bp,'volume24_median':bv,'oi_median':bo,'funding_median':bf,'quiet_ratio':round(quiet,3)},'current_deviation':{'price_pct':round(pdev,3),'volume_pct':round(vdev,3),'oi_pct':round(odev,3),'funding_delta':round(fdev,8)}})
    profiles.sort(key=lambda x:x['dna_score'],reverse=True)
    for v in source_stats.values():v['early_pattern_hit_rate']=round(v['early_pattern_hits']/max(1,v['observations']),4)
    consensus=_consensus_profiles(profiles)
    payload={'version':2,'generated_at':now,'purpose':'learn established-market catalyst DNA at both market and unique-symbol levels without hindsight leakage','history_rule':'only observations already collected by Wallet500 are used; unavailable historical catalysts are never invented','profiles_count':len(profiles),'market_profiles_count':len(profiles),'unique_symbols_count':len(consensus),'counting_rule':'market_profiles are exchange:symbol observations; unique_symbols_count is the deduplicated symbol universe','consensus_method':'symbol-level aggregation across exchanges; consensus features require >=50% support or >=2 markets, with single-market symbols retained transparently','source_attribution':source_stats,'archetype_frequency':dict(sorted(archetypes.items(),key=lambda x:x[1],reverse=True)[:50]),'top_profiles':profiles[:200],'top_consensus_symbols':consensus[:200],'future_catalyst_sources':[{'source':'CoinMarketCal','features':['historical/upcoming project events','event categories','impact score'],'requires_key':True},{'source':'Messari Token Unlocks','features':['unlock events','vesting','allocation/supply catalysts'],'requires_key':True},{'source':'CoinGecko','features':['historical price/volume','exchange/derivatives','onchain trades/holders'],'requires_key_for_full_history':True},{'source':'CoinGlass','features':['historical OI','funding','liquidations','long-short','spot flows/order flow'],'requires_key':True},{'source':'CoinMarketCap','features':['cross-exchange derivatives','funding/OI','market context'],'requires_key_for_full_catalog':True}], 'profiles':profiles,'consensus_profiles':consensus}
    (out/'catalyst-dna.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return payload
