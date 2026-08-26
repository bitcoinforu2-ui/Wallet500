from collections import Counter


def historical_profile(adapter, address: str, limit: int = 100) -> dict:
    signatures = adapter.signatures_for_address(address, limit=limit)
    ok = [s for s in signatures if s.get("err") is None]
    failed = len(signatures) - len(ok)
    slots = [s.get("slot") for s in ok if s.get("slot") is not None]
    return {
        "chain": "solana",
        "address": address,
        "transactions_seen": len(signatures),
        "successful": len(ok),
        "failed": failed,
        "success_rate": (len(ok) / len(signatures)) if signatures else 0.0,
        "first_slot": min(slots) if slots else None,
        "last_slot": max(slots) if slots else None,
    }
