from dataclasses import dataclass, field
import os


@dataclass(slots=True)
class Settings:
    solana_rpc_url: str = field(default_factory=lambda: os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"))
    seed_wallets: list[str] = field(default_factory=lambda: [x for x in os.getenv("WALLET500_SEEDS", "").split(",") if x])
    signatures_per_wallet: int = field(default_factory=lambda: int(os.getenv("WALLET500_SIGNATURES", "20")))
    anomaly_threshold: float = field(default_factory=lambda: float(os.getenv("WALLET500_ANOMALY_THRESHOLD", "60")))
    output_dir: str = field(default_factory=lambda: os.getenv("WALLET500_OUTPUT_DIR", "data"))
