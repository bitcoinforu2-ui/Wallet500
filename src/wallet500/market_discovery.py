from __future__ import annotations
import json
from urllib.request import Request, urlopen

DEX="https://api.dexscreener.com"
GECKO="https://api.geckoterminal.com/api/v2"
CHAINS=("solana","ethereum","bsc")
GECKO_NETWORK={"solana":"solana","ethereum":"eth","bsc":"bsc"}

def _get(url:str,timeout:int=20):
    req=Request(url,headers={"Accept":"application/json","User-Agent":"Wallet500/0.3"})
    with urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

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

def _dex_latest(wanted,limit,rows,seen,counts):
    for ep in ("/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1"):
        try:
            data=_get(DEX+ep)
        except Exception:
            continue
        if isinstance(data,dict):
            data=[data]
        for x in data or []:
            chain=str(x.get("chainId","")).lower()
            if chain in wanted:
                _add(rows,seen,counts,chain,x.get("tokenAddress"),"dexscreener:"+ep,limit,url=x.get("url"),description=x.get("description"),links=x.get("links") or [])

def _gecko_new_pools(wanted,limit,rows,seen,counts,start_pages=None,pages_per_run:int=3,max_page:int=12):
    start_pages=start_pages or {}
    next_pages={}
    for chain in wanted:
        network=GECKO_NETWORK.get(chain)
        if not network:
            continue
        start=max(1,int(start_pages.get(chain,1)))
        pages=[]
        p=start
        for _ in range(max(1,pages_per_run)):
            pages.append(p)
            p = 1 if p>=max_page else p+1
        next_pages[chain]=p
        for page in pages:
            if counts[chain]>=limit:
                break
            try:
                payload=_get(f"{GECKO}/networks/{network}/new_pools?page={page}")
            except Exception:
                continue
            included={x.get("id"):x for x in payload.get("included",[]) if isinstance(x,dict)}
            for pool in payload.get("data",[]) or []:
                rel=(pool.get("relationships") or {}).get("base_token",{}).get("data") or {}
                token_id=rel.get("id")
                token_obj=included.get(token_id,{})
                attrs=token_obj.get("attributes") or {}
                address=attrs.get("address")
                if not address and token_id and "_" in token_id:
                    address=token_id.split("_",1)[1]
                p_attrs=pool.get("attributes") or {}
                _add(rows,seen,counts,chain,address,"geckoterminal:new_pools",limit,pool_address=p_attrs.get("address"),pool_created_at=p_attrs.get("pool_created_at"),name=p_attrs.get("name"),discovery_page=page)
    return next_pages

def discover_tokens(chains=CHAINS,limit_per_chain:int=120,start_pages=None,pages_per_run:int=3,max_page:int=12)->tuple[list[dict],dict]:
    wanted=set(chains)
    rows=[]
    seen=set()
    counts={c:0 for c in wanted}
    _dex_latest(wanted,limit_per_chain,rows,seen,counts)
    next_pages=_gecko_new_pools(wanted,limit_per_chain,rows,seen,counts,start_pages,pages_per_run,max_page)
    return rows,next_pages

def discover_solana_tokens(limit:int=120)->list[dict]:
    rows,_=discover_tokens(("solana",),limit)
    return [{"mint":x["token"],**x} for x in rows]
