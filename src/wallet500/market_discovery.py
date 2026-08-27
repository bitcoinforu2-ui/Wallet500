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
            req=Request(url,headers={"Accept":"application/json","User-Agent":"Wallet500/0.5"})
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
        return
    seen.add(key)
    counts[chain]+=1
    rows.append({"chain":chain,"token":token,"source":source,**extra})


def _dex_latest(wanted,limit,rows,seen,counts,errors):
    for ep in ("/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1"):
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
                _add(rows,seen,counts,chain,x.get("tokenAddress"),"dexscreener:"+ep,limit,url=x.get("url"),description=x.get("description"),links=x.get("links") or [])


def _extract_address(token_id, token_obj):
    attrs=(token_obj or {}).get("attributes") or {}
    address=attrs.get("address")
    if address:
        return address
    if token_id and "_" in token_id:
        return token_id.split("_",1)[1]
    return None


def _gecko_page(chain,network,page,limit,rows,seen,counts,source="geckoterminal:new_pools"):
    # include=base_token is critical: without it some networks return only relationship IDs,
    # which previously caused silent zero-token discovery on Ethereum.
    query=urlencode({"page":page,"include":"base_token"})
    payload=_get(f"{GECKO}/networks/{network}/new_pools?{query}")
    included={x.get("id"):x for x in payload.get("included",[]) if isinstance(x,dict)}
    before=counts[chain]
    for pool in payload.get("data",[]) or []:
        rel=(pool.get("relationships") or {}).get("base_token",{}).get("data") or {}
        token_id=rel.get("id")
        address=_extract_address(token_id,included.get(token_id,{}))
        p_attrs=pool.get("attributes") or {}
        _add(rows,seen,counts,chain,address,source,limit,pool_address=p_attrs.get("address"),pool_created_at=p_attrs.get("pool_created_at"),name=p_attrs.get("name"),discovery_page=page)
        if counts[chain]>=limit:
            break
    return counts[chain]-before


def _gecko_new_pools(wanted,limit,rows,seen,counts,start_pages=None,pages_per_run:int=3,max_page:int=12,errors=None):
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
            pages.append(p)
            p=1 if p>=max_page else p+1
        next_pages[chain]=p
        before_chain=counts[chain]
        for page in pages:
            if counts[chain]>=limit:
                break
            try:
                _gecko_page(chain,network,page,limit,rows,seen,counts)
            except Exception as e:
                errors.append({"source":"geckoterminal","chain":chain,"page":page,"error":repr(e)})
        if counts[chain]==before_chain:
            for page in (1,2,3):
                if counts[chain]>=limit:
                    break
                try:
                    _gecko_page(chain,network,page,limit,rows,seen,counts,"geckoterminal:fallback_new_pools")
                except Exception as e:
                    errors.append({"source":"geckoterminal:fallback","chain":chain,"page":page,"error":repr(e)})
    return next_pages


def discover_tokens(chains=CHAINS,limit_per_chain:int=120,start_pages=None,pages_per_run:int=3,max_page:int=12)->tuple[list[dict],dict]:
    wanted=set(chains)
    rows=[]; seen=set(); errors=[]
    counts={c:0 for c in wanted}
    _dex_latest(wanted,limit_per_chain,rows,seen,counts,errors)
    next_pages=_gecko_new_pools(wanted,limit_per_chain,rows,seen,counts,start_pages,pages_per_run,max_page,errors)

    dead=[c for c in sorted(wanted) if counts.get(c,0)==0]
    if dead:
        detail=[e for e in errors if e.get("chain") in dead or e.get("source")=="dexscreener"][-12:]
        raise RuntimeError(f"Discovery health failure: zero tokens on {dead}; recent_errors={detail}")

    return rows,next_pages


def discover_solana_tokens(limit:int=120)->list[dict]:
    rows,_=discover_tokens(("solana",),limit)
    return [{"mint":x["token"],**x} for x in rows]
