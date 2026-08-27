from __future__ import annotations
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEX="https://api.dexscreener.com"
GECKO="https://api.geckoterminal.com/api/v2"
CHAINS=("solana","ethereum","bsc")
GECKO_NETWORK={"solana":"solana","ethereum":"eth","bsc":"bsc"}


def _get(url:str,timeout:int=20,retries:int=3):
    last=None
    for attempt in range(max(1,retries)):
        try:
            req=Request(url,headers={"Accept":"application/json;version=20230203","User-Agent":"Wallet500/0.6"})
            with urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last=e
            if attempt+1<retries:
                time.sleep(1.2*(attempt+1))
    raise last


def _key(chain:str,token:str):
    return (chain,token.lower() if chain in {"ethereum","bsc"} else token)


def _add(rows,seen,counts,chain,token,source,limit,**extra):
    if chain not in counts or counts[chain]>=limit or not token:
        return
    key=_key(chain,token)
    if key in seen:
        # Preserve multi-source confirmation without duplicating the candidate.
        for row in rows:
            if _key(row["chain"],row["token"])==key:
                sources=row.setdefault("sources",[row.get("source")])
                if source not in sources:
                    sources.append(source)
                row["source_confirmations"]=len(sources)
                break
        return
    seen.add(key)
    counts[chain]+=1
    rows.append({"chain":chain,"token":token,"source":source,"sources":[source],"source_confirmations":1,**extra})


def _dex_latest(wanted,limit,rows,seen,counts,errors):
    endpoints=(
        "/token-profiles/latest/v1",
        "/token-boosts/latest/v1",
        "/token-boosts/top/v1",
        "/community-takeovers/latest/v1",
    )
    for ep in endpoints:
        try:
            data=_get(DEX+ep)
        except Exception as e:
            errors.append({"source":"dexscreener","endpoint":ep,"error":repr(e)})
            continue
        if isinstance(data,dict):
            data=[data]
        for x in data or []:
            chain=str(x.get("chainId","")).lower()
            if chain in wanted:
                _add(rows,seen,counts,chain,x.get("tokenAddress"),"dexscreener:"+ep,limit,
                     url=x.get("url"),description=x.get("description"),links=x.get("links") or [],
                     boost_amount=x.get("amount"),boost_total=x.get("totalAmount"),claim_date=x.get("claimDate"))


def _extract_address(token_id,token_obj):
    attrs=(token_obj or {}).get("attributes") or {}
    address=attrs.get("address")
    if address:
        return address
    if token_id and "_" in token_id:
        return token_id.split("_",1)[1]
    return None


def _gecko_pool_page(chain,network,endpoint,page,limit,rows,seen,counts,source):
    query=urlencode({"page":page,"include":"base_token"})
    payload=_get(f"{GECKO}/networks/{network}/{endpoint}?{query}")
    included={x.get("id"):x for x in payload.get("included",[]) if isinstance(x,dict)}
    before=counts[chain]
    for pool in payload.get("data",[]) or []:
        rel=(pool.get("relationships") or {}).get("base_token",{}).get("data") or {}
        token_id=rel.get("id")
        address=_extract_address(token_id,included.get(token_id,{}))
        a=pool.get("attributes") or {}
        _add(rows,seen,counts,chain,address,source,limit,
             pool_address=a.get("address"),pool_created_at=a.get("pool_created_at"),name=a.get("name"),
             discovery_page=page,reserve_usd=a.get("reserve_in_usd"),volume_usd=a.get("volume_usd"),
             transactions=a.get("transactions"),price_change_percentage=a.get("price_change_percentage"))
        if counts[chain]>=limit:
            break
    return counts[chain]-before


def _gecko_discovery(wanted,limit,rows,seen,counts,start_pages=None,pages_per_run:int=3,max_page:int=12,errors=None):
    start_pages=start_pages or {}
    errors=errors if errors is not None else []
    next_pages={}
    for chain in sorted(wanted):
        network=GECKO_NETWORK.get(chain)
        if not network:
            errors.append({"source":"geckoterminal","chain":chain,"error":"NETWORK_MAPPING_MISSING"})
            continue
        start=max(1,int(start_pages.get(chain,1)))
        pages=[]; p=start
        for _ in range(max(1,pages_per_run)):
            pages.append(p); p=1 if p>=max_page else p+1
        next_pages[chain]=p
        # Rotate new-pool pages for breadth, then always sample trending/top pools for momentum/revival.
        for page in pages:
            if counts[chain]>=limit: break
            try:
                _gecko_pool_page(chain,network,"new_pools",page,limit,rows,seen,counts,"geckoterminal:new_pools")
            except Exception as e:
                errors.append({"source":"geckoterminal:new_pools","chain":chain,"page":page,"error":repr(e)})
        for endpoint,source in (("trending_pools","geckoterminal:trending_pools"),("pools","geckoterminal:top_pools")):
            if counts[chain]>=limit: break
            try:
                _gecko_pool_page(chain,network,endpoint,1,limit,rows,seen,counts,source)
            except Exception as e:
                errors.append({"source":source,"chain":chain,"page":1,"error":repr(e)})
    return next_pages


def discover_tokens(chains=CHAINS,limit_per_chain:int=120,start_pages=None,pages_per_run:int=3,max_page:int=12)->tuple[list[dict],dict]:
    wanted=set(chains)
    rows=[]; seen=set(); errors=[]
    counts={c:0 for c in wanted}
    _dex_latest(wanted,limit_per_chain,rows,seen,counts,errors)
    next_pages=_gecko_discovery(wanted,limit_per_chain,rows,seen,counts,start_pages,pages_per_run,max_page,errors)
    dead=[c for c in sorted(wanted) if counts.get(c,0)==0]
    if dead:
        detail=[e for e in errors if e.get("chain") in dead or e.get("source")=="dexscreener"][-12:]
        raise RuntimeError(f"Discovery health failure: zero tokens on {dead}; recent_errors={detail}")
    return rows,next_pages


def discover_solana_tokens(limit:int=120)->list[dict]:
    rows,_=discover_tokens(("solana",),limit)
    return [{"mint":x["token"],**x} for x in rows]
