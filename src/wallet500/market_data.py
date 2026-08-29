from __future__ import annotations
import json
import time
from urllib.request import Request, urlopen
from urllib.parse import quote

BASE="https://api.dexscreener.com"

def _get(path:str,timeout:int=20):
    req=Request(BASE+path,headers={"Accept":"application/json","User-Agent":"Wallet500/0.1"})
    with urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def token_pairs(chain:str,token:str)->list[dict]:
    # Token lookup is the broad discovery path. Retry transient misses so a
    # momentary API failure does not unnecessarily quarantine a good pair.
    for attempt in range(3):
        try:
            data=_get(f"/token-pairs/v1/{quote(chain,safe='')}/{quote(token,safe='')}")
            if isinstance(data,list) and data:
                return data
        except Exception:
            pass
        if attempt < 2:
            time.sleep(0.6 * (attempt + 1))
    return []

def pair_lookup(chain:str,pair_address:str)->dict|None:
    """Direct exact-pair fallback used only for immutable pair revalidation."""
    if not chain or not pair_address:
        return None
    for attempt in range(3):
        try:
            data=_get(f"/latest/dex/pairs/{quote(chain,safe='')}/{quote(pair_address,safe='')}")
            pairs=(data or {}).get("pairs") if isinstance(data,dict) else None
            if isinstance(pairs,list):
                wanted=str(pair_address).lower()
                for p in pairs:
                    if str((p or {}).get("pairAddress") or "").lower()==wanted:
                        return p
        except Exception:
            pass
        if attempt < 2:
            time.sleep(0.6 * (attempt + 1))
    return None

def _pair_to_snapshot(chain:str,token:str,p:dict)->dict:
    tx=p.get("txns") or {}; vol=p.get("volume") or {}; ch=p.get("priceChange") or {}; liq=p.get("liquidity") or {}
    h1=tx.get("h1") or {}; h24=tx.get("h24") or {}; base=p.get("baseToken") or {}; qtok=p.get("quoteToken") or {}
    liq_usd=float(liq.get("usd") or 0); liq_base=float(liq.get("base") or 0); liq_quote=float(liq.get("quote") or 0)
    return {"chain":chain,"token":token,"pair_address":p.get("pairAddress"),"dex":p.get("dexId"),"url":p.get("url"),"price_usd":float(p.get("priceUsd") or 0),"liquidity_usd":liq_usd,"liquidity_base":liq_base,"liquidity_quote":liq_quote,"base_token_address":base.get("address"),"base_token_symbol":base.get("symbol"),"quote_token_address":qtok.get("address"),"quote_token_symbol":qtok.get("symbol"),"liquidity_composition_present":bool(liq_usd>0 and liq_base>0 and liq_quote>0),"fdv":float(p.get("fdv") or 0),"market_cap":float(p.get("marketCap") or 0),"volume_m5":float(vol.get("m5") or 0),"volume_h1":float(vol.get("h1") or 0),"volume_h6":float(vol.get("h6") or 0),"volume_h24":float(vol.get("h24") or 0),"price_change_m5":float(ch.get("m5") or 0),"price_change_h1":float(ch.get("h1") or 0),"price_change_h6":float(ch.get("h6") or 0),"price_change_h24":float(ch.get("h24") or 0),"buys_h1":int(h1.get("buys") or 0),"sells_h1":int(h1.get("sells") or 0),"buys_h24":int(h24.get("buys") or 0),"sells_h24":int(h24.get("sells") or 0),"pair_created_at":p.get("pairCreatedAt")}

def _compact_pool(chain:str,token:str,p:dict)->dict:
    s=_pair_to_snapshot(chain,token,p)
    return {k:s.get(k) for k in ("chain","token","pair_address","dex","url","price_usd","liquidity_usd","liquidity_base","liquidity_quote","quote_token_symbol","liquidity_composition_present","volume_m5","volume_h1","buys_h1","sells_h1","pair_created_at")}

def snapshot(chain:str,token:str,pair_address:str|None=None)->dict|None:
    pairs=token_pairs(chain,token)
    if pair_address:
        wanted=pair_address.lower()
        for p in pairs:
            if str(p.get("pairAddress") or "").lower()==wanted:
                return _pair_to_snapshot(chain,token,p)
        # Critical bottleneck fix: token-pairs can transiently omit a known
        # immutable pair. Verify that exact address directly before PENDING.
        direct=pair_lookup(chain,pair_address)
        return _pair_to_snapshot(chain,token,direct) if direct else None
    if not pairs: return None
    p=max(pairs,key=lambda x: float((x.get("liquidity") or {}).get("usd") or 0))
    out=_pair_to_snapshot(chain,token,p)
    ranked=sorted(pairs,key=lambda x: float((x.get("liquidity") or {}).get("usd") or 0),reverse=True)[:8]
    out["pools"]=[_compact_pool(chain,token,x) for x in ranked if x.get("pairAddress")]
    return out
