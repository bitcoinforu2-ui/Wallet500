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


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> dict:
    cfg = Settings()
    adapter = SolanaAdapter(cfg.solana_rpc_url)
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    events = scan_addresses(adapter, cfg.seed_wallets, cfg.signatures_per_wallet)
    watch_rows = Watchlist(str(out / "watchlist.json")).save_events(events, cfg.anomaly_threshold)

    token_mints = [row["token"] for row in watch_rows[:25]]
    candidates = discover_wallet_candidates(adapter, token_mints)
    _write(out / "wallet-candidates.json", candidates[:500])

    scored = []
    for row in candidates[:100]:
        profile = wallet_forensics(historical_profile(adapter, row["address"], limit=100))
        scored.append(score_wallet(profile, row))
    ranked = rank_wallets(scored)
    _write(out / "wallet-quality.json", ranked)
    _write(out / "elite-wallets.json", [x for x in ranked if x["tier"] == "ELITE"])

    live_pool = [x for x in ranked if x["tier"] in {"ELITE", "STRONG", "WATCH"}]
    live = monitor_ranked(adapter, live_pool, max_wallets=50)
    _write(out / "live-wallets.json", live)

    tiers = {name: sum(1 for x in ranked if x["tier"] == name) for name in ("ELITE", "STRONG", "WATCH", "LOW")}
    result = {"chain": "solana", "seeds": len(cfg.seed_wallets), "events": len(events), "watchlist": len(watch_rows), "wallet_candidates": len(candidates), "wallets_scored": len(ranked), "tiers": tiers, "live_monitored": len(live)}
    _write(out / "run-summary.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
