from collections import Counter, defaultdict
from .models import MarketEvent

STABLE_MINTS = {
    "So11111111111111111111111111111111111111112",  # WSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD8mK4uS5GehVwV5aYhKQ2",   # USDT legacy/common
}


def _mints_from_transaction(tx: dict) -> set[str]:
    meta = (tx or {}).get("meta") or {}
    mints: set[str] = set()
    for key in ("preTokenBalances", "postTokenBalances"):
        for bal in meta.get(key, []) or []:
            mint = bal.get("mint")
            if mint and mint not in STABLE_MINTS:
                mints.add(mint)
    return mints


def scan_wallet_activity(adapter, address: str, limit: int = 20) -> list[MarketEvent]:
    signatures = adapter.signatures_for_address(address, limit=limit)
    mint_hits: Counter[str] = Counter()
    successful = 0
    for item in signatures:
        if item.get("err") is not None or not item.get("signature"):
            continue
        tx = adapter.transaction(item["signature"])
        if not tx:
            continue
        successful += 1
        for mint in _mints_from_transaction(tx):
            mint_hits[mint] += 1
    events: list[MarketEvent] = []
    for mint, hits in mint_hits.items():
        score = min(100.0, hits * 22.0 + successful * 1.2)
        events.append(MarketEvent(chain="solana", token=mint, event_type="token_activity", score=score, metrics={"seed_wallet": address, "mint_hits": hits, "transactions_seen": successful}))
    return events


def scan_addresses(adapter, addresses: list[str], limit: int = 20) -> list[MarketEvent]:
    best: dict[str, MarketEvent] = {}
    seed_map: defaultdict[str, set[str]] = defaultdict(set)
    for address in addresses:
        for event in scan_wallet_activity(adapter, address, limit):
            seed_map[event.token].add(address)
            old = best.get(event.token)
            if old is None or event.score > old.score:
                best[event.token] = event
    for mint, event in best.items():
        n = len(seed_map[mint])
        event.metrics["seed_wallet_count"] = n
        event.metrics["seed_wallets"] = sorted(seed_map[mint])
        event.score = min(100.0, event.score + max(0, n - 1) * 25.0)
    return sorted(best.values(), key=lambda event: event.score, reverse=True)
