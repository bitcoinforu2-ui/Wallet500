from dataclasses import dataclass, field
import os

from .policy import CANONICAL_MIN_EXECUTION_LIQUIDITY_USD


@dataclass(slots=True)
class Settings:
    solana_rpc_url: str = field(default_factory=lambda: os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"))
    seed_wallets: list[str] = field(default_factory=lambda: [x for x in os.getenv("WALLET500_SEEDS", "").split(",") if x])
    signatures_per_wallet: int = field(default_factory=lambda: int(os.getenv("WALLET500_SIGNATURES", "20")))
    anomaly_threshold: float = field(default_factory=lambda: float(os.getenv("WALLET500_ANOMALY_THRESHOLD", "60")))
    # Canonical veteran/revival execution floor. Configuration may make production
    # stricter, but can never relax the canonical fail-closed minimum.
    verified_min_liquidity_usd: float = field(default_factory=lambda: max(
        float(os.getenv("WALLET500_VERIFIED_MIN_LIQUIDITY_USD", str(CANONICAL_MIN_EXECUTION_LIQUIDITY_USD))),
        float(CANONICAL_MIN_EXECUTION_LIQUIDITY_USD),
    ))
    wallet_forensics_max_tokens: int = field(default_factory=lambda: int(os.getenv("WALLET500_FORENSICS_MAX_TOKENS", "5")))
    wallet_forensics_signatures: int = field(default_factory=lambda: int(os.getenv("WALLET500_FORENSICS_SIGNATURES", "12")))
    workflow_degraded_seconds: int = field(default_factory=lambda: int(os.getenv("WALLET500_WORKFLOW_DEGRADED_SECONDS", "600")))
    require_pair_survival_for_verified: bool = True
    require_liquidity_survival_for_verified: bool = True
    require_lp_cluster_verification_for_verified: bool = True
    output_dir: str = field(default_factory=lambda: os.getenv("WALLET500_OUTPUT_DIR", "data"))