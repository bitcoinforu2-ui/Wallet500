import json
from pathlib import Path
from .adapters.solana import SolanaAdapter
from .config import Settings
from .scanner import scan_addresses
from .watchlist import Watchlist
from .historical import historical_profile
from .forensics import wallet_forensics


def run() -> dict:
    cfg = Settings()
    adapter = SolanaAdapter(cfg.solana_rpc_url)
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    events = scan_addresses(adapter, cfg.seed_wallets, cfg.signatures_per_wallet)
    watch = Watchlist(str(out / "watchlist.json"))
    watch_rows = watch.save_events(events, cfg.anomaly_threshold)
    profiles = []
    for row in watch_rows[:25]:
        profiles.append(wallet_forensics(historical_profile(adapter, row["token"], limit=100)))
    (out / "wallet-profiles.json").write_text(json.dumps(profiles, indent=2), encoding="utf-8")
    result = {"chain": "solana", "seeds": len(cfg.seed_wallets), "events": len(events), "watchlist": len(watch_rows), "profiles": len(profiles)}
    (out / "run-summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
