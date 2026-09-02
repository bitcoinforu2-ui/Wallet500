from __future__ import annotations

import base64
from typing import Any


def sign_order_transaction(order: dict[str, Any], secret_b58: str, expected_pubkey: str) -> str:
    from solders.keypair import Keypair
    from solders.message import to_bytes_versioned
    from solders.signature import Signature
    from solders.transaction import VersionedTransaction

    raw = base64.b64decode(str(order.get("transaction") or ""))
    tx = VersionedTransaction.from_bytes(raw)
    kp = Keypair.from_base58_string(secret_b58)
    if str(kp.pubkey()) != expected_pubkey:
        raise RuntimeError("COPY_WALLET_SECRET_B58 does not match COPY_WALLET_PUBKEY")

    required = int(tx.message.header.num_required_signatures)
    account_keys = list(tx.message.account_keys)
    signer_index = next((i for i, key in enumerate(account_keys[:required]) if str(key) == expected_pubkey), None)
    if signer_index is None:
        raise RuntimeError("Jupiter transaction does not require the configured copy-wallet signature")

    signatures = list(tx.signatures)
    while len(signatures) < required:
        signatures.append(Signature.default())
    signatures[signer_index] = kp.sign_message(to_bytes_versioned(tx.message))
    signed = VersionedTransaction.populate(tx.message, signatures)
    signed.sanitize()
    checks = signed.verify_with_results()
    if signer_index >= len(checks) or not checks[signer_index]:
        raise RuntimeError("Local copy-wallet signature verification failed")
    return base64.b64encode(bytes(signed)).decode("ascii")
