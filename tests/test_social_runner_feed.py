from wallet500.social_runner_feed import build_native_snapshots


def _event(source, author, contract, ts, text="hello runner", **extra):
    row = {
        "source": source,
        "author": author,
        "chain": "solana",
        "contract": contract,
        "published_at": ts,
        "first_seen_by_wallet500": ts,
        "text": text,
    }
    row.update(extra)
    return row


def test_native_feed_rebuilds_windows_without_future_leakage():
    contract = "Mint111"
    ledger = {
        "updated_at": "2026-09-18T00:00:00Z",
        "events": [
            _event("telegram", "a", contract, "2026-09-17T20:00:00Z"),
            _event("twitter", "b", contract, "2026-09-17T22:30:00Z"),
            _event("reddit", "c", contract, "2026-09-17T23:30:00Z"),
        ],
    }
    rows = build_native_snapshots(ledger)
    assert len(rows) == 1
    row = rows[0]
    assert row["observed_at"].startswith("2026-09-17T23:30:00")
    assert row["windows"]["3h"]["mentions"] == 2
    assert row["windows"]["24h"]["mentions"] == 3
    assert row["platform_mentions"] == {"telegram": 1, "x": 1, "reddit": 1}


def test_project_owned_and_paid_events_receive_no_organic_credit():
    contract = "Mint222"
    ledger = {
        "updated_at": "2026-09-18T00:00:00Z",
        "events": [
            _event("telegram", "official", contract, "2026-09-17T22:00:00Z", project_owned=True),
            _event("twitter", "paid_kol", contract, "2026-09-17T22:30:00Z", paid=True),
            _event("reddit", "organic_user", contract, "2026-09-17T23:00:00Z"),
        ],
    }
    row = build_native_snapshots(ledger)[0]
    assert row["raw_mentions_24h"] == 3
    assert row["organic_mentions_24h"] == 1
    assert round(row["organic_share"], 4) == 0.3333


def test_first_time_communities_only_counts_new_community_arrivals():
    contract = "Mint333"
    ledger = {
        "updated_at": "2026-09-18T00:00:00Z",
        "events": [
            _event("telegram", "old", contract, "2026-09-10T12:00:00Z"),
            _event("telegram", "old", contract, "2026-09-17T23:00:00Z", text="new post from old community"),
            _event("twitter", "new", contract, "2026-09-17T23:30:00Z", text="first ever new community post"),
        ],
    }
    row = build_native_snapshots(ledger)[0]
    assert row["unique_communities"] == 2
    assert row["first_time_communities"] == 1


def test_token_without_recent_event_is_not_emitted():
    ledger = {
        "updated_at": "2026-09-18T00:00:00Z",
        "events": [_event("telegram", "a", "Mint444", "2026-09-17T10:00:00Z")],
    }
    assert build_native_snapshots(ledger) == []


def test_explicit_contamination_can_raise_coordination_penalty():
    contract = "Mint555"
    ledger = {
        "updated_at": "2026-09-18T00:00:00Z",
        "events": [
            _event("telegram", "a", contract, "2026-09-17T23:00:00Z", text="unique alpha post"),
            _event("twitter", "b", contract, "2026-09-17T23:30:00Z", text="another unique post"),
        ],
    }
    organic = {"tokens": [{"chain": "solana", "contract": contract, "contamination_ratio_24h": 0.8}]}
    row = build_native_snapshots(ledger, organic_acceleration=organic)[0]
    assert row["coordination_ratio"] == 0.8
