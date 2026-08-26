from __future__ import annotations
import json
from urllib.request import Request, urlopen

BASE="https://api.dexscreener.com"

def _get(path:str,timeout:int=20):
    req=Request(BASE+path,headers={"Accept":"application/json","User-Agent":"Wallet500/0.1"})
    with urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def discover_solana_tokens(limit:int=120)->list[dict]:
    rows=[]; seen=set()
    endpoints=["/token-profiles/latest/v1","/token-boosts/latest/v1","/token-boosts/top/v1"]
    for ep in endpoints:
        try: data=_get(ep)
        except Exception: continue
        if isinstance(data,dict): data=[data]
        for x in data or []:
            if str(x.get("chainId",""))!="solana": continue
            mint=x.get("tokenAddress")
            if not mint or mint in seen: continue
            seen.add(mint); rows.append({"mint":mint,"source":ep,"url":x.get("url"),"description":x.get("description"),"links":x.get("links") or []})
            if len(rows)>=limit: return rows
    return rows
