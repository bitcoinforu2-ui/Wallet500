import json
from pathlib import Path
from .adapters.solana import SolanaAdapter
from .config import Settings
from .scanner import scan_addresses
from .watchlist import Watchlist
from .historical import historical_profile
from .forensics import wallet_forensics
from .discovery import discover_wallet_candidates


def run() -> dict:
    cfg = Settings()
    adapter = SolanaAdapter(cfg.solana_rpc_url)
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    events = scan_addresses(adapter, cfg.seed_wallets, cfg.signatures_per_wallet)
    watch = Watchlist(str(out / "watchlist.json"))
    watch_rows = watch.save_events(events, cfg.anomaly_threshold)

    token_mints = [row["token"] for row in watch_rows[:25]]
    candidates = discover_wallet_candidates(adapter, token_mints)
    (out / "wallet-candidates.json").write_text(json.dumps(candidates[:500], indent=2), encoding="utf-8")

    profiles = []
    for row in candidates[:50]:
        profile = historical_profile(adapter, row["address"], limit=100)
        profile["discovery_score"] = row["score"]
        profile["token_count"] = row["token_count"]
        profiles.append(wallet_forensics(profile))
    (out / "wallet-profiles.json").write_text(json.dumps(profiles, indent=2), encoding="utf-8")

    result = {
        "chain": "solana",
        "seeds": len(cfg.seed_wallets),
        "events": len(events),
        "watchlist": len(watch_rows),
        "wallet_candidates": len(candidates),
        "profiles": len(profiles),
    }
    (out / "run-summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
