from wallet500.winner_separator import event_time, pre_t0_events
from datetime import datetime, timezone


def test_pre_t0_excludes_future_exact_token_event():
    row = {"chain": "solana", "token": "TokenA"}
    events = [
        {"chain": "solana", "contract": "TokenA", "first_seen_by_wallet500": "2026-09-01T09:00:00Z"},
        {"chain": "solana", "contract": "TokenA", "first_seen_by_wallet500": "2026-09-01T11:00:00Z"},
        {"chain": "solana", "contract": "Other", "first_seen_by_wallet500": "2026-09-01T08:00:00Z"},
    ]
    kept, post = pre_t0_events(events, row, datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc))
    assert len(kept) == 1
    assert post == 1


def test_first_seen_preferred_over_published_time():
    event = {
        "published_at": "2026-08-01T00:00:00Z",
        "first_seen_by_wallet500": "2026-09-01T00:00:00Z",
    }
    assert event_time(event) == datetime(2026, 9, 1, tzinfo=timezone.utc)
