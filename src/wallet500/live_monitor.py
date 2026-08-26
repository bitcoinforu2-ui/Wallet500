from __future__ import annotations
from datetime import datetime, timezone


def monitor_wallet(adapter, address: str, limit: int = 10) -> dict:
    signatures = adapter.signatures_for_address(address, limit=limit)
    ok = [x for x in signatures if x.get("err") is None]
    newest = ok[0] if ok else None
    return {"address": address, "transactions_seen": len(signatures), "successful": len(ok), "latest_signature": newest.get("signature") if newest else None, "latest_slot": newest.get("slot") if newest else None, "checked_at": datetime.now(timezone.utc).isoformat()}


def monitor_ranked(adapter, wallets: list[dict], max_wallets: int = 50) -> list[dict]:
    rows = []
    for wallet in wallets[:max_wallets]:
        row = monitor_wallet(adapter, wallet["address"])
        row["tier"] = wallet.get("tier")
        row["wallet_score"] = wallet.get("wallet_score")
        rows.append(row)
    return rows
