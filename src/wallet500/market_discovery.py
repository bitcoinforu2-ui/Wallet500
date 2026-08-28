from __future__ import annotations
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEX="https://api.dexscreener.com"
GECKO="https://api.geckoterminal.com/api/v2"
MOONSHOT="https://api.moonshot.cc"
CHAINS=("solana","ethereum","bsc")
GECKO_NETWORK={"solana":"solana","ethereum":"eth","bsc":"bsc"}

# Base assets/stables are noise for Wallet500 discovery and are rejected before
# snapshot/anomaly work. EVM addresses are normalized to lowercase.
BLOCKED_BASE_TOKENS={
    "solana":{
        "So11111111111111111111111111111111111111112",  # WSOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD9iG6vGvL5JZtJm6Gq5tQ",  # USDT legacy/common mint
    },
    "ethereum":{
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
        "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
        "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
        "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC
    },
    "bsc":{
        "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
        "0x55d398326f99059ff775485246999027b3197955",  # USDT
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
        "0xc5f0f7b66764f6ec8c8dff7ba683102295e16409",  # FDUSD
    },
}

_LAST_DIAGNOSTICS={}
_LAST_GECKO_CALL=0.0


def _get(url:str,timeout:int=20,retries:int=3):
    last=None
    for attempt in range(max(1,retries)):
        try:
            req=Request(url,headers={"Accept":"application/json","User-Agent":"Wallet500/0.8"})
            with urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode())
        except Exception as e:
            last=e
            if attempt+1<retries:time.sleep(1.5*(attempt+1))
    raise last


def _gecko_get(url:str):
    # Public GeckoTerminal is rate-limited. Pace discovery calls so one busy
    # source cannot silently collapse Ethereum/BSC coverage.
    global _LAST_GECKO_CALL
    wait=1.15-(time.monotonic()-_LAST_GECKO_CALL)
    if wait>0:time.sleep(wait)
    try:return _get(url)
    finally:_LAST_GECKO_CALL=time.monotonic()


def _key(chain:str,token:str):return (chain,token.lower() if chain in {"ethereum","bsc"} else token)

def _blocked(chain:str,token:str)->bool:
    if not token:return True
    norm=token.lower() if chain in {"ethereum","bsc"} else token
    return norm in BLOCKED_BASE_TOKENS.get(chain,set())


def _add(rows,seen,counts,filtered,chain,token,source,limit,**extra):
    if chain not in counts or not token:return
    if _blocked(chain,token):
        filtered[chain]=filtered.get(chain,0)+1
        return
    key=_key(chain,token)
    if key in seen:
        for row in rows:
            if _key(row["chain"],row["token"])==key:
                sources=row.setdefault("sources",[row.get("source")])
                if source not in sources:sources.append(source)
                row["source_confirmations"]=len(sources);row.update({k:v for k,v in extra.items() if v is not None})
                break
        return
    if counts[chain]>=limit:return
    seen.add(key);counts[chain]+=1
    rows.append({"chain":chain,"token":token,"source":source,"sources":[source],"source_confirmations":1,**extra})


def _moonshot(wanted,limit,rows,seen,counts,filtered,errors):
    if "solana" not in wanted:return
    for view in ("rising","trending","top","finalized","new"):
        try:data=_get(f"{MOONSHOT}/tokens/v1/{view}/solana")
        except Exception as e:errors.append({"source":"moonshot","view":view,"error":repr(e)});continue
        if isinstance(data,dict):data=data.get("data") or data.get("tokens") or [data]
        for x in data or []:
            token=x.get("tokenId") or x.get("tokenAddress") or x.get("mint") or x.get("address")
            _add(rows,seen,counts,filtered,"solana",token,"moonshot:"+view,limit,moonshot_view=view,
                 moonshot_pair=x.get("pairId") or x.get("pairAddress"),moonshot_price=x.get("priceUsd") or x.get("price"),
                 moonshot_volume=x.get("volumeUsd") or x.get("volume"),moonshot_marketcap=x.get("marketCap") or x.get("marketCapUsd"))


def _dex_latest(wanted,limit,rows,seen,counts,filtered,errors):
    for ep in ("/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1","/community-takeovers/latest/v1"):
        try:data=_get(DEX+ep)
        except Exception as e:errors.append({"source":"dexscreener","endpoint":ep,"error":repr(e)});continue
        if isinstance(data,dict):data=[data]
        for x in data or []:
            chain=str(x.get("chainId","")).lower()
            if chain in wanted:_add(rows,seen,counts,filtered,chain,x.get("tokenAddress"),"dexscreener:"+ep,limit,url=x.get("url"),boost_amount=x.get("amount"),boost_total=x.get("totalAmount"))


def _extract_address(token_id,token_obj):
    attrs=(token_obj or {}).get("attributes") or {};address=attrs.get("address")
    return address or (token_id.split("_",1)[1] if token_id and "_" in token_id else None)


def _gecko_pool_page(chain,network,endpoint,page,limit,rows,seen,counts,filtered,source):
    payload=_gecko_get(f"{GECKO}/networks/{network}/{endpoint}?{urlencode({'page':page,'include':'base_token'})}")
    included={x.get("id"):x for x in payload.get("included",[]) if isinstance(x,dict)};before=counts[chain]
    for pool in payload.get("data",[]) or []:
        rel=(pool.get("relationships") or {}).get("base_token",{}).get("data") or {};tid=rel.get("id");a=pool.get("attributes") or {}
        token_obj=included.get(tid,{}) or {};ta=token_obj.get("attributes") or {}
        _add(rows,seen,counts,filtered,chain,_extract_address(tid,token_obj),source,limit,pool_address=a.get("address"),pool_created_at=a.get("pool_created_at"),name=a.get("name"),symbol=ta.get("symbol"),token_name=ta.get("name"),discovery_page=page,reserve_usd=a.get("reserve_in_usd"),volume_usd=a.get("volume_usd"),transactions=a.get("transactions"),price_change_percentage=a.get("price_change_percentage"))
    return counts[chain]-before


def _gecko_fresh_lane(wanted,limit,rows,seen,counts,filtered,errors=None,fresh_pages:int=3):
    """Always rescan newest pool pages so scheduler cadence/API lag cannot create discovery gaps."""
    errors=errors if errors is not None else [];pages_used={}
    for chain in sorted(wanted):
        network=GECKO_NETWORK.get(chain)
        if not network:continue
        pages=list(range(1,max(1,fresh_pages)+1));pages_used[chain]=pages
        for page in pages:
            try:_gecko_pool_page(chain,network,"new_pools",page,limit,rows,seen,counts,filtered,"geckoterminal:new_pools:fresh")
            except Exception as e:errors.append({"source":"geckoterminal:new_pools:fresh","chain":chain,"page":page,"error":repr(e)})
    return pages_used


def _gecko_deep_lane(wanted,limit,rows,seen,counts,filtered,start_pages=None,pages_per_run:int=3,max_page:int=12,errors=None,fresh_pages:int=3):
    """Rotate through older new-pool pages independently from the always-on fresh overlap lane."""
    start_pages=start_pages or {};errors=errors if errors is not None else [];next_pages={};pages_used={}
    deep_first=max(2,fresh_pages+1);max_page=max(deep_first,max_page)
    for chain in sorted(wanted):
        network=GECKO_NETWORK.get(chain)
        if not network:continue
        raw=int(start_pages.get(chain,deep_first));start=raw if deep_first<=raw<=max_page else deep_first
        pages=[];p=start
        for _ in range(max(1,pages_per_run)):
            pages.append(p);p=deep_first if p>=max_page else p+1
        next_pages[chain]=p;pages_used[chain]=pages
        for page in pages:
            try:_gecko_pool_page(chain,network,"new_pools",page,limit,rows,seen,counts,filtered,"geckoterminal:new_pools:deep")
            except Exception as e:errors.append({"source":"geckoterminal:new_pools:deep","chain":chain,"page":page,"error":repr(e)})
        for endpoint,source in (("trending_pools","geckoterminal:trending_pools"),("pools","geckoterminal:top_pools")):
            try:_gecko_pool_page(chain,network,endpoint,1,limit,rows,seen,counts,filtered,source)
            except Exception as e:errors.append({"source":source,"chain":chain,"error":repr(e)})
    return next_pages,pages_used


def discovery_diagnostics()->dict:return dict(_LAST_DIAGNOSTICS)


def discover_tokens(chains=CHAINS,limit_per_chain:int=120,start_pages=None,pages_per_run:int=3,max_page:int=12)->tuple[list[dict],dict]:
    global _LAST_DIAGNOSTICS
    wanted=set(chains);rows=[];seen=set();errors=[];counts={c:0 for c in wanted};filtered={c:0 for c in wanted}

    # Fresh overlap is first-class: pages 1-3 are rescanned every run. This is
    # intentionally independent from the deep cursor so a token born just after
    # the previous 15-minute scan remains discoverable on the next run.
    fresh_pages_used=_gecko_fresh_lane(wanted,limit_per_chain,rows,seen,counts,filtered,errors,fresh_pages=3)

    # Independent latest/trending sources enrich/confirm the same candidates.
    # _add still records confirmations even after a chain reaches its new-token cap.
    _moonshot(wanted,limit_per_chain,rows,seen,counts,filtered,errors)
    _dex_latest(wanted,limit_per_chain,rows,seen,counts,filtered,errors)

    # Deep coverage rotates pages 4-12 and never replaces the fresh overlap lane.
    next_pages,deep_pages_used=_gecko_deep_lane(wanted,limit_per_chain,rows,seen,counts,filtered,start_pages,pages_per_run,max_page,errors,fresh_pages=3)
    dead=[c for c in sorted(wanted) if counts.get(c,0)==0]
    health={c:("FAILED" if counts.get(c,0)==0 else "DEGRADED" if counts.get(c,0)<10 else "HEALTHY") for c in sorted(wanted)}
    _LAST_DIAGNOSTICS={
        "counts":dict(counts),"health":health,"filtered_base_assets":dict(filtered),
        "cursor_in":dict(start_pages or {}),"cursor_out":dict(next_pages),
        "fresh_overlap_pages":fresh_pages_used,"deep_pages_scanned":deep_pages_used,
        "fresh_overlap_enabled":True,"fresh_overlap_page_count":3,
        "errors_count":len(errors),"recent_errors":errors[-20:]
    }
    if dead:raise RuntimeError(f"Discovery health failure: zero tokens on {dead}; recent_errors={errors[-12:]}")
    return rows,next_pages


def discover_solana_tokens(limit:int=120)->list[dict]:
    rows,_=discover_tokens(("solana",),limit);return [{"mint":x["token"],**x} for x in rows]
