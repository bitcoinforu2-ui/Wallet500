from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone

IGNORED_MINTS={"So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","Es9vMFrzaCERmJfrF4H2FYD8mK4uS5GehVwV5aYhKQ2"}

def _balances(meta,key,address):
    out=defaultdict(float)
    for b in (meta.get(key) or []):
        if b.get("owner")!=address: continue
        mint=b.get("mint")
        if not mint or mint in IGNORED_MINTS: continue
        ui=(b.get("uiTokenAmount") or {}).get("uiAmount")
        out[mint]+=float(ui or 0)
    return out

def wallet_token_activity(adapter,wallet,limit=20):
    rows=[]
    for s in adapter.signatures_for_address(wallet,limit=limit):
        if s.get("err") is not None: continue
        sig=s.get("signature")
        tx=adapter.transaction(sig) if sig else None
        if not tx: continue
        meta=tx.get("meta") or {}
        pre=_balances(meta,"preTokenBalances",wallet); post=_balances(meta,"postTokenBalances",wallet)
        for mint in set(pre)|set(post):
            delta=post[mint]-pre[mint]
            if abs(delta)<1e-12: continue
            rows.append({"wallet":wallet,"mint":mint,"side":"BUY" if delta>0 else "SELL","token_delta":delta,"signature":sig,"slot":s.get("slot"),"block_time":s.get("blockTime")})
    return rows

def build_signals(adapter,ranked,max_wallets=30,tx_limit=20):
    activity=[]
    scores={x["address"]:x for x in ranked}
    for w in ranked[:max_wallets]: activity.extend(wallet_token_activity(adapter,w["address"],tx_limit))
    grouped=defaultdict(list)
    for row in activity: grouped[(row["mint"],row["side"])].append(row)
    signals=[]
    for (mint,side),rows in grouped.items():
        wallets=sorted(set(x["wallet"] for x in rows))
        elite=sum(1 for w in wallets if scores.get(w,{}).get("tier")=="ELITE")
        strong=sum(1 for w in wallets if scores.get(w,{}).get("tier")=="STRONG")
        score=min(100,25*len(wallets)+15*elite+8*strong+min(20,len(rows)*2))
        signals.append({"mint":mint,"side":side,"signal_score":score,"wallet_count":len(wallets),"elite_wallets":elite,"strong_wallets":strong,"events":len(rows),"wallets":wallets,"observed_at":datetime.now(timezone.utc).isoformat()})
    signals.sort(key=lambda x:(x["signal_score"],x["wallet_count"]),reverse=True)
    return activity,signals
