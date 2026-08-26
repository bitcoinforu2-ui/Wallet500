import json
from pathlib import Path
from .config import Settings
from .market_pipeline import run_market_scan

def _write(path,payload): Path(path).write_text(json.dumps(payload,indent=2),encoding="utf-8")

def run():
    cfg=Settings(); out=Path(cfg.output_dir); out.mkdir(parents=True,exist_ok=True)
    market=run_market_scan(limit_per_chain=120,threshold=45.0)
    _write(out/"market-universe.json",market["universe"])
    _write(out/"market-snapshots.json",market["snapshots"])
    _write(out/"anomaly-radar.json",market["anomalies"])
    _write(out/"watchlist.json",market["anomalies"][:100])
    result={"mode":"market-first","chains":market["chains"],"counts":market["counts"],"universe":len(market["universe"]),"snapshots":len(market["snapshots"]),"anomalies":len(market["anomalies"]),"watchlist":min(100,len(market["anomalies"]))}
    _write(out/"run-summary.json",result)
    return result

if __name__=="__main__": print(json.dumps(run(),indent=2))
