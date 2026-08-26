import json
from pathlib import Path
from .adapters.solana import SolanaAdapter
from .config import Settings
from .scanner import scan_addresses
from .watchlist import Watchlist
from .historical import historical_profile
from .forensics import wallet_forensics
from .discovery import discover_wallet_candidates
from .wallet_scorer import score_wallet, rank_wallets
from .live_monitor import monitor_ranked
from .trade_intelligence import build_signals

def _write(path,payload): Path(path).write_text(json.dumps(payload,indent=2),encoding="utf-8")

def run():
    cfg=Settings(); adapter=SolanaAdapter(cfg.solana_rpc_url); out=Path(cfg.output_dir); out.mkdir(parents=True,exist_ok=True)
    events=scan_addresses(adapter,cfg.seed_wallets,cfg.signatures_per_wallet)
    watch_rows=Watchlist(str(out/"watchlist.json")).save_events(events,cfg.anomaly_threshold)
    candidates=discover_wallet_candidates(adapter,[x["token"] for x in watch_rows[:25]])
    _write(out/"wallet-candidates.json",candidates[:500])
    scored=[]
    for row in candidates[:100]:
        p=wallet_forensics(historical_profile(adapter,row["address"],limit=100)); p["balance_sol"]=adapter.balance(row["address"]); scored.append(score_wallet(p,row))
    ranked=rank_wallets(scored); _write(out/"wallet-quality.json",ranked); _write(out/"elite-wallets.json",[x for x in ranked if x["tier"]=="ELITE"])
    live_pool=[x for x in ranked if x["tier"] in {"ELITE","STRONG","WATCH"}]; live=monitor_ranked(adapter,live_pool,50); _write(out/"live-wallets.json",live)
    activity,signals=build_signals(adapter,ranked,30,20); _write(out/"trade-activity.json",activity); _write(out/"token-signals.json",signals)
    tiers={n:sum(1 for x in ranked if x["tier"]==n) for n in ("ELITE","STRONG","WATCH","LOW")}
    result={"chain":"solana","seeds":len(cfg.seed_wallets),"events":len(events),"watchlist":len(watch_rows),"wallet_candidates":len(candidates),"wallets_scored":len(ranked),"tiers":tiers,"live_monitored":len(live),"trade_events":len(activity),"token_signals":len(signals)}; _write(out/"run-summary.json",result); return result

if __name__=="__main__": print(json.dumps(run(),indent=2))
