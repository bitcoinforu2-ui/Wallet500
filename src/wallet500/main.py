import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .market_pipeline import run_market_scan


def _write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_manual_watchlist(out: Path) -> list[dict]:
    path = out / "manual-watchlist.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def run():
    cfg = Settings()
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # 01 MARKET SCAN — real market discovery across SOL / ETH / BNB.
    market = run_market_scan(limit_per_chain=120, threshold=45.0)
    universe = market["universe"]
    snapshots = market["snapshots"]

    # 02 GLOBAL ANOMALY RADAR — rank only verified market snapshots.
    anomalies = market["anomalies"]

    # 03 WATCHLIST — anomaly-selected tokens plus explicit research cases.
    automatic_watch = [{**x, "watch_source": "ANOMALY_RADAR"} for x in anomalies[:100]]
    manual_watch = _load_manual_watchlist(out)
    seen = {(x.get("chain"), x.get("token") or x.get("mint")) for x in automatic_watch}
    watch = list(automatic_watch)
    for x in manual_watch:
        key = (x.get("chain"), x.get("token") or x.get("mint"))
        if key not in seen:
            watch.append({**x, "watch_source": "MANUAL_RESEARCH"})
            seen.add(key)

    # 04 HISTORICAL DEEP SCAN QUEUE — every watched token enters a visible stage.
    review = []
    for x in watch:
        review.append({
            **x,
            "stage": "HISTORICAL_DEEP_SCAN_QUEUED",
            "queued_at": now,
            "next_stage": "WALLET_DISCOVERY_FORENSICS",
        })

    # 05+ pipeline status is explicit so the dashboard reflects the agreed flow.
    pipeline = {
        "flow": [
            "MULTI_CHAIN_MARKET_SCAN",
            "GLOBAL_ANOMALY_RADAR",
            "WATCHLIST",
            "HISTORICAL_DEEP_SCAN",
            "WALLET_DISCOVERY_FORENSICS",
            "OPERATOR_ELITE_SCORING",
            "BEHAVIOR_LEARNING",
            "SIGNAL_CORRELATION",
            "OUTCOME_TRACKING",
            "LIVE_DASHBOARD",
        ],
        "current": {
            "MULTI_CHAIN_MARKET_SCAN": len(universe),
            "GLOBAL_ANOMALY_RADAR": len(anomalies),
            "WATCHLIST": len(watch),
            "HISTORICAL_DEEP_SCAN": len(review),
        },
        "updated_at": now,
        "verified_only": True,
    }

    _write(out / "market-universe.json", universe)
    _write(out / "market-snapshots.json", snapshots)
    _write(out / "anomaly-radar.json", anomalies)
    _write(out / "watchlist.json", watch)
    _write(out / "historical-review-queue.json", review)
    _write(out / "pipeline-status.json", pipeline)

    result = {
        "mode": "market-first",
        "verified_only": True,
        "chains": market["chains"],
        "counts": market["counts"],
        "universe": len(universe),
        "snapshots": len(snapshots),
        "anomalies": len(anomalies),
        "watchlist": len(watch),
        "historical_review_queued": len(review),
        "manual_research_cases": len(manual_watch),
        "updated_at": now,
    }
    _write(out / "run-summary.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
