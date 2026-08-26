from __future__ import annotations
import json
from urllib.request import Request, urlopen
from urllib.parse import quote

BASE="https://api.dexscreener.com"

def _get(path:str,timeout:int=20):
    req=Request(BASE+path,headers={"Accept":"application/json","User-Agent":"Wallet500/0.1"})
    with urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def token_pairs(mint:str)->list[dict]:
    try: data=_get("/token-pairs/v1/solana/"+quote(mint,safe=""))
    except Exception: return []
    return data if isinstance(data,list) else []

def snapshot(mint:str)->dict|None:
    pairs=token_pairs(mint)
    if not pairs: return None
    p=max(pairs,key=lambda x: float((x.get("liquidity") or {}).get("usd") or 0))
    tx=p.get("txns") or {}; vol=p.get("volume") or {}; ch=p.get("priceChange") or {}; liq=p.get("liquidity") or {}
    h1=tx.get("h1") or {}; h24=tx.get("h24") or {}
    return {"mint":mint,"pair_address":p.get("pairAddress"),"dex":p.get("dexId"),"url":p.get("url"),"price_usd":float(p.get("priceUsd") or 0),"liquidity_usd":float(liq.get("usd") or 0),"fdv":float(p.get("fdv") or 0),"market_cap":float(p.get("marketCap") or 0),"volume_m5":float(vol.get("m5") or 0),"volume_h1":float(vol.get("h1") or 0),"volume_h6":float(vol.get("h6") or 0),"volume_h24":float(vol.get("h24") or 0),"price_change_m5":float(ch.get("m5") or 0),"price_change_h1":float(ch.get("h1") or 0),"price_change_h6":float(ch.get("h6") or 0),"price_change_h24":float(ch.get("h24") or 0),"buys_h1":int(h1.get("buys") or 0),"sells_h1":int(h1.get("sells") or 0),"buys_h24":int(h24.get("buys") or 0),"sells_h24":int(h24.get("sells") or 0),"pair_created_at":p.get("pairCreatedAt")}
