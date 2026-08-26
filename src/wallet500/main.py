import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .market_pipeline import run_market_scan

def _write(path,payload): Path(path).write_text(json.dumps(payload,indent=2),encoding="utf-8")

def run():
    cfg=Settings(); out=Path(cfg.output_dir); out.mkdir(parents=True,exist_ok=True)
    market=run_market_scan(limit_per_chain=120,threshold=45.0)
    anomalies=market["anomalies"]
    watch=anomalies[:100]
    review=[{**x,"stage":"HISTORICAL_REVIEW_QUEUED","queued_at":datetime.now(timezone.utc).isoformat()} for x in watch]
    _write(out/"market-universe.json",market["universe"])
    _write(out/"market-snapshots.json",market["snapshots"])
    _write(out/"anomaly-radar.json",anomalies)
    _write(out/"watchlist.json",watch)
    _write(out/"historical-review-queue.json",review)
    result={"mode":"market-first","verified_only":True,"chains":market["chains"],"counts":market["counts"],"universe":len(market["universe"]),"snapshots":len(market["snapshots"]),"anomalies":len(anomalies),"watchlist":len(watch),"historical_review_queued":len(review),"updated_at":datetime.now(timezone.utc).isoformat()}
    _write(out/"run-summary.json",result)
    return result

if __name__=="__main__": print(json.dumps(run(),indent=2))
