from __future__ import annotations

import json

from wallet500 import cryptoyeezus_copy as base


_SWAP_LOG_MARKERS = (
    "instruction: swap",
    "instruction: buy",
    "instruction: sell",
    "program log: swap",
    "program log: buy",
    "program log: sell",
)


def has_explicit_swap_evidence(tx: dict) -> bool:
    """Fail closed unless the confirmed transaction logs explicitly identify trade execution.

    Wallet-level balance deltas alone are not sufficient: a signer can receive a token while
    spending SOL on fees/rent, which can otherwise resemble a SOL->token buy. Requiring an
    explicit Swap/Buy/Sell program log prevents plain transfers, airdrops and ATA/rent flows
    from entering the CryptoYeezus research cohort as verified swaps.
    """
    if not isinstance(tx, dict):
        return False
    meta = tx.get("meta") if isinstance(tx.get("meta"), dict) else {}
    if meta.get("err") is not None:
        return False
    logs = meta.get("logMessages") if isinstance(meta.get("logMessages"), list) else []
    text = "\n".join(str(x).lower() for x in logs if x is not None)
    return any(marker in text for marker in _SWAP_LOG_MARKERS)


_original_parse_wallet_swap = base.parse_wallet_swap


def verified_parse_wallet_swap(tx: dict, wallet: str = base.SOURCE_WALLET):
    if not has_explicit_swap_evidence(tx):
        return None
    return _original_parse_wallet_swap(tx, wallet)


def run_once():
    # Patch only this process. The underlying parser remains available for unit-level
    # balance-delta tests, while the live research lane is strictly fail-closed.
    base.parse_wallet_swap = verified_parse_wallet_swap
    return base.run_once()


if __name__ == "__main__":
    print(json.dumps(run_once(), indent=2, ensure_ascii=False))
