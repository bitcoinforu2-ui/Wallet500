from __future__ import annotations

import os
from pathlib import Path

from . import cryptoyeezus_copy as engine
from .cryptoyeezus_signer import sign_order_transaction


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def main() -> None:
    if not _truthy("COPY_LIVE_ENABLED"):
        raise SystemExit("Refusing persistent executor start: COPY_LIVE_ENABLED is not true. Run the shadow lane first.")
    if not Path(engine.LEDGER_PATH).exists():
        raise SystemExit(
            "Refusing live execution without data/cryptoyeezus-copy-ledger.json. "
            "Run once in shadow mode on the same durable volume to establish the forward boundary."
        )
    missing = [name for name in ("COPY_WALLET_PUBKEY", "COPY_WALLET_SECRET_B58", "JUPITER_API_KEY", "SOLANA_RPC_URL") if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Refusing live execution; missing secrets: " + ", ".join(missing))

    # The live container explicitly injects the signer that uses Solana's canonical
    # versioned-message bytes and preserves any additional Jupiter/MM signatures.
    engine._sign_order_transaction = sign_order_transaction
    engine.serve()


if __name__ == "__main__":
    main()
