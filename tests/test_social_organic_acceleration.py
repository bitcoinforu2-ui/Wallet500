from datetime import datetime, timedelta, timezone

from wallet500.social_organic_acceleration import analyze_events, classify_event


NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
CA = "HD3JBABeFkdZwUgKwhwJYqjLNrPWXEaDVfH4uMqRpump"


def event(*, author, minutes_ago, text, source="x", **extra):
    return {
        "chain": "solana",
        "contract": CA,
        "source": source,
        "author": author,
        "published_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "first_seen_by_wallet500": NOW.isoformat(),
        "text": text,
        **extra,
    }


def token_result(events):
    rows = analyze_events(events, NOW)
    assert len(rows) == 1
    return rows[0]


def test_paid_and_project_owned_are_discounted_not_erased():
    paid = classify_event(event(author="promoter", minutes_ago=5, text="Sponsored paid promotion", paid=True))
    official = classify_event(event(author="official", minutes_ago=5, text="Official update", project_owned=True))
    assert paid["paid_or_incentivized"] is True
    assert paid["organic_weight"] <= 0.05
    assert official["project_owned"] is True
    assert official["organic_weight"] <= 0.15
    assert paid["organic_weight"] > 0
    assert official["organic_weight"] > 0


def test_many_copy_paste_shills_do_not_create_organic_acceleration():
    text = f"Raid this gem now and post to win rewards {CA}"
    rows = [event(author=f"shill{i}", minutes_ago=10 + i % 10, text=text) for i in range(100)]
    result = token_result(rows)
    assert result["current_1h"]["raw_mentions"] == 100
    assert result["current_1h"]["independent_authors"] == 0
    assert result["status"] == "NO_ORGANIC_SIGNAL"
    assert result["contamination_ratio_24h"] >= 0.99


def test_independent_cross_source_mentions_can_create_strong_acceleration():
    rows = []
    # Quiet prior baseline: one older independent observation.
    rows.append(event(author="old_user", minutes_ago=180, text=f"Watching this exact contract {CA}", source="reddit"))
    # Six independent current mentions across two platforms, all with unique text.
    for i in range(6):
        rows.append(event(
            author=f"organic{i}",
            minutes_ago=5 + i * 4,
            text=f"Independent observation number {i}: unusual revival flow on {CA}",
            source="x" if i % 2 == 0 else "reddit",
        ))
    result = token_result(rows)
    assert result["current_1h"]["independent_authors"] == 6
    assert result["current_1h"]["independent_sources"] == 2
    assert result["status"] == "STRONG_ORGANIC_ACCELERATION"
    assert result["organic_acceleration_score"] > 0


def test_same_author_burst_is_discounted():
    rows = [
        event(author="one_account", minutes_ago=5 + i, text=f"Different wording {i} around exact CA {CA}")
        for i in range(12)
    ]
    result = token_result(rows)
    # One loud account is not independent social discovery.
    assert result["current_1h"]["independent_authors"] <= 1
    assert result["status"] == "NO_ORGANIC_SIGNAL"


def test_name_or_ticker_only_noise_cannot_enter_exact_contract_layer():
    rows = [{
        "chain": "solana",
        "source": "x",
        "author": "noise",
        "published_at": (NOW - timedelta(minutes=5)).isoformat(),
        "text": "$USEFUL is trending but there is no exact contract attribution",
    }]
    assert analyze_events(rows, NOW) == []


def test_raw_mentions_never_promote_without_independent_authors():
    rows = [
        event(
            author="official_team",
            minutes_ago=2 + i,
            text=f"Official project post {i} about {CA}",
            project_owned=True,
        )
        for i in range(20)
    ]
    result = token_result(rows)
    assert result["current_1h"]["raw_mentions"] == 20
    assert result["status"] == "NO_ORGANIC_SIGNAL"
