from __future__ import annotations

import os
from pathlib import Path

from .cryptoyeezus_copy import LEDGER_PATH, serve


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def main() -> None:
    if not _truthy("COPY_LIVE_ENABLED"):
        raise SystemExit("Refusing persistent executor start: COPY_LIVE_ENABLED is not true. Run the shadow lane first.")
    if not Path(LEDGER_PATH).exists():
        raise SystemExit(
            "Refusing live execution without data/cryptoyeezus-copy-ledger.json. "
            "Run once in shadow mode on the same durable volume to establish the forward boundary."
        )
    missing = [name for name in ("COPY_WALLET_PUBKEY", "COPY_WALLET_SECRET_B58", "JUPITER_API_KEY", "SOLANA_RPC_URL") if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Refusing live execution; missing secrets: " + ", ".join(missing))
    serve()


if __name__ == "__main__":
    main()
