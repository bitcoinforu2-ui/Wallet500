from __future__ import annotations
import json
from urllib.request import Request, urlopen

BASE="https://api.dexscreener.com"
CHAINS=("solana","ethereum","bsc")

def _get(path:str,timeout:int=20):
    req=Request(BASE+path,headers={"Accept":"application/json","User-Agent":"Wallet500/0.1"})
    with urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def discover_tokens(chains=CHAINS,limit_per_chain:int=120)->list[dict]:
    wanted=set(chains); rows=[]; seen=set(); counts={c:0 for c in wanted}
    endpoints=["/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1"]
    for ep in endpoints:
        try: data=_get(ep)
        except Exception: continue
        if isinstance(data,dict): data=[data]
        for x in data or []:
            chain=str(x.get("chainId","")).lower()
            if chain not in wanted or counts[chain]>=limit_per_chain: continue
            token=x.get("tokenAddress")
            key=(chain,token)
            if not token or key in seen: continue
            seen.add(key); counts[chain]+=1
            rows.append({"chain":chain,"token":token,"source":ep,"url":x.get("url"),"description":x.get("description"),"links":x.get("links") or []})
    return rows

def discover_solana_tokens(limit:int=120)->list[dict]:
    return [{"mint":x["token"],**x} for x in discover_tokens(("solana",),limit)]
