from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from wallet500.cex_verified_arbitrage import run


def _send(text: str) -> tuple[bool, str | None]:
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:
        return False,"TELEGRAM_SECRETS_MISSING"
    body=urllib.parse.urlencode({"chat_id":chat,"text":text,"disable_web_page_preview":"true"}).encode()
    try:
        req=urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",data=body)
        with urllib.request.urlopen(req,timeout=10) as r:
            ok=json.loads(r.read().decode()).get("ok") is True
        return ok,None if ok else "TELEGRAM_SEND_REJECTED"
    except Exception as e:
        return False,f"TELEGRAM_SEND_FAILED:{type(e).__name__}"


def main(data_dir: Path=Path("data")) -> dict:
    payload=run(data_dir)
    state_path=data_dir/"cex-verified-arbitrage-alert-state.json"
    try: state=json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception: state={}
    prior=set(state.get("sent_signatures") or []); sent=list(prior); deliveries=[]
    for row in payload.get("results") or []:
        if row.get("verified_arbitrage") is not True: continue
        sig="|".join([str(row.get("symbol")),str(row.get("buy_exchange")),str(row.get("sell_exchange")),str(row.get("network")),str(round(float(row.get("net_profit_pct") or 0),1))])
        if sig in prior: continue
        text=("💰 Wallet500 VERIFIED ARBITRAGE\n"+f"{row.get('symbol')}\n"+f"BUY {str(row.get('buy_exchange')).upper()} @ VWAP ${row.get('buy_execution',{}).get('vwap')}\n"+f"SELL {str(row.get('sell_exchange')).upper()} @ VWAP ${row.get('sell_execution',{}).get('vwap')}\n"+f"Size: ${row.get('target_quote_usd')}\n"+f"Network: {row.get('network')}\n"+f"Net: +{row.get('net_profit_pct')}% / ${row.get('net_profit_usd')}\n"+"Route + depth + fees + transfer-time checks passed. Manual decision only.")
        ok,blocker=_send(text); deliveries.append({"signature":sig,"sent":ok,"blocker":blocker})
        if ok: sent.append(sig)
    state_out={"version":1,"mode":"FORWARD_ONLY_VERIFIED_ARBITRAGE_ALERT_STATE_V1","sent_signatures":sorted(set(sent))[-500:],"last_deliveries":deliveries,"automatic_trade":False}
    state_path.write_text(json.dumps(state_out,indent=2),encoding="utf-8")
    return {"verified_count":payload.get("verified_count",0),"deliveries":deliveries}


if __name__=="__main__":
    print(json.dumps(main(),indent=2))
