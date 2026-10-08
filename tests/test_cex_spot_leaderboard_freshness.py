from datetime import datetime, timedelta, timezone

from wallet500.cex_spot_leaderboard_bridge import _latest_market_rows, _timestamp_fresh


def test_timestamp_freshness_fail_closed():
    now = datetime(2026, 10, 8, 8, tzinfo=timezone.utc)
    assert _timestamp_fresh(now.isoformat(), now)
    assert not _timestamp_fresh(None, now)
    assert not _timestamp_fresh("bad", now)
    assert not _timestamp_fresh((now - timedelta(hours=2)).isoformat(), now)
    assert not _timestamp_fresh((now + timedelta(hours=1)).isoformat(), now)


def test_leaderboard_ignores_stale_and_missing_timestamps():
    now = datetime(2026, 10, 8, 8, tzinfo=timezone.utc)
    state = {"markets": {
        "spot:okx:METUSDT:MET/USDT": [{"observed_at": now.isoformat(), "change_24h_pct": 40}],
        "spot:gate:COOLUSDT:COOL/USDT": [{"observed_at": (now - timedelta(hours=2)).isoformat(), "change_24h_pct": 250}],
        "spot:gate:ZZZUSDT:ZZZ/USDT": [{"change_24h_pct": 50}],
    }}
    rows = _latest_market_rows(state, now)
    assert [row["symbol"] for row in rows] == ["METUSDT"]
