from __future__ import annotations
import json
from pathlib import Path
from .config import Settings
from .market_discovery import discover_tokens, discovery_diagnostics
from .market_data import snapshot
from .anomaly_radar import rank_anomalies

CHAINS=("solana","ethereum","bsc")

def run_market_scan(limit_per_chain:int=120,threshold:float=45.0,start_pages=None)->dict:
    universe,next_pages=discover_tokens(CHAINS,limit_per_chain,start_pages=start_pages)
    diagnostics=discovery_diagnostics()
    out=Path(Settings().output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"discovery-health.json").write_text(json.dumps(diagnostics,indent=2),encoding="utf-8")
    snapshots=[]
    for row in universe:
        s=snapshot(row["chain"],row["token"])
        if s:
            snapshots.append(s)
    anomalies=rank_anomalies(snapshots,threshold)
    counts={c:{"discovered":0,"snapshots":0,"anomalies":0} for c in CHAINS}
    for x in universe:
        counts[x["chain"]]["discovered"]+=1
    for x in snapshots:
        counts[x["chain"]]["snapshots"]+=1
    for x in anomalies:
        counts[x["chain"]]["anomalies"]+=1
    return {"chains":list(CHAINS),"universe":universe,"snapshots":snapshots,"anomalies":anomalies,"counts":counts,"next_pages":next_pages,"discovery_diagnostics":diagnostics}
