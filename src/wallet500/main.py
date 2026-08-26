import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .market_pipeline import run_market_scan


def _write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return default


def _load_manual_watchlist(out: Path) -> list[dict]:
    data = _load_json(out / "manual-watchlist.json", [])
    return data if isinstance(data, list) else []


def _token_key(chain: str, token: str) -> str:
    token = token or ""
    if chain in {"ethereum", "bsc"}:
        token = token.lower()
    return f"{chain}:{token}"


def _update_discovery_state(out: Path, universe: list[dict], next_pages: dict, now: str):
    path = out / "discovery-state.json"
    state = _load_json(path, {})
    if not isinstance(state, dict):
        state = {}
    tokens = state.get("tokens") if isinstance(state.get("tokens"), dict) else {}
    new_count = 0
    revisited_count = 0
    by_chain = {"solana": {"new": 0, "revisited": 0}, "ethereum": {"new": 0, "revisited": 0}, "bsc": {"new": 0, "revisited": 0}}

    annotated = []
    for row in universe:
        chain = row.get("chain")
        token = row.get("token") or row.get("mint")
        key = _token_key(chain, token)
        prev = tokens.get(key)
        if prev:
            revisited_count += 1
            by_chain.setdefault(chain, {"new": 0, "revisited": 0})["revisited"] += 1
            first_seen = prev.get("first_seen", now)
            scan_count = int(prev.get("scan_count", 0)) + 1
            discovery_status = "REVISITED"
        else:
            new_count += 1
            by_chain.setdefault(chain, {"new": 0, "revisited": 0})["new"] += 1
            first_seen = now
            scan_count = 1
            discovery_status = "NEW"

        record = {
            "chain": chain,
            "token": token,
            "first_seen": first_seen,
            "last_seen": now,
            "scan_count": scan_count,
            "last_source": row.get("source"),
            "last_discovery_page": row.get("discovery_page"),
        }
        tokens[key] = record
        annotated.append({**row, "discovery_status": discovery_status, "first_seen": first_seen, "last_seen": now, "scan_count": scan_count})

    runs = int(state.get("runs", 0)) + 1
    state = {
        "version": 1,
        "runs": runs,
        "updated_at": now,
        "source_cursor": next_pages or state.get("source_cursor", {}),
        "unique_tokens_total": len(tokens),
        "last_run": {
            "discovered": len(universe),
            "new": new_count,
            "revisited": revisited_count,
            "new_ratio": round(new_count / len(universe), 4) if universe else 0.0,
            "by_chain": by_chain,
        },
        "tokens": tokens,
    }
    _write(path, state)
    return state, annotated


def run():
    cfg = Settings()
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    previous_state = _load_json(out / "discovery-state.json", {})
    start_pages = previous_state.get("source_cursor", {}) if isinstance(previous_state, dict) else {}

    # 01 MARKET SCAN — 120 is a per-run batch size, not a universe cap.
    market = run_market_scan(limit_per_chain=120, threshold=45.0, start_pages=start_pages)
    state, universe = _update_discovery_state(out, market["universe"], market.get("next_pages", {}), now)
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
        "discovery_health": state.get("last_run", {}),
        "unique_tokens_total": state.get("unique_tokens_total", 0),
        "scan_runs_total": state.get("runs", 0),
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
        "discovery": state.get("last_run", {}),
        "unique_tokens_total": state.get("unique_tokens_total", 0),
        "scan_runs_total": state.get("runs", 0),
        "updated_at": now,
    }
    _write(out / "run-summary.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
