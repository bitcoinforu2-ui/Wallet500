from .models import MarketEvent


def scan_wallet_activity(adapter, address: str, limit: int = 20) -> list[MarketEvent]:
    signatures = adapter.signatures_for_address(address, limit=limit)
    score = min(100.0, len(signatures) * 5.0)
    if not signatures:
        return []
    return [MarketEvent(chain="solana", token=address, event_type="wallet_activity", score=score, metrics={"transactions_seen": len(signatures)})]


def scan_addresses(adapter, addresses: list[str], limit: int = 20) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    for address in addresses:
        events.extend(scan_wallet_activity(adapter, address, limit))
    return sorted(events, key=lambda event: event.score, reverse=True)
