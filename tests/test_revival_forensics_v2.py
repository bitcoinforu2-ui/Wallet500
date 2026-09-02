from datetime import datetime, timedelta, timezone

from wallet500.revival_forensics_v2 import (
    MIN_AGE_DAYS,
    build_t0,
    pct,
    select_exact_pair_observation,
    sha256,
)


def test_pct():
    assert pct(1, 2) == 100.0
    assert pct(100, 50) == -50.0
    assert pct(0, 2) is None


def test_build_t0_locks_age_pair_and_hash():
    coin = {
        "token_address": "mint",
        "symbol": "OLD",
        "watch_status": "WAKING_MARKET_ONLY",
        "market_age_verified": True,
        "market_age_min_days": MIN_AGE_DAYS,
        "market_age_evidence_at": "2025-01-01T00:00:00+00:00",
        "market_age_evidence_source": "TEST",
        "dex_pair_address": "pair",
        "price_usd": 1.0,
        "dex_pair_liquidity_usd": 100000,
        "market_cap_usd": 1000000,
        "revival_score_verified": 80,
    }
    target = {"confirmation_status": "UNCONFIRMED_RESEARCH", "confirmation_score": 50}
    t0 = build_t0(coin, target, "2026-09-02T12:00:00+00:00", "2026-09-02T12:05:00+00:00")
    assert t0["market_age_min_days"] == 180
    assert t0["pair_address"] == "pair"
    assert t0["blockers"] == []
    assert len(t0["evidence_sha256"]) == 64


def test_build_t0_fails_closed_under_180():
    coin = {
        "token_address": "mint",
        "market_age_verified": True,
        "market_age_min_days": 179,
        "dex_pair_address": "pair",
        "price_usd": 1,
        "dex_pair_liquidity_usd": 100000,
    }
    t0 = build_t0(coin, {}, "2026-09-02T12:00:00+00:00", "2026-09-02T12:00:01+00:00")
    assert "AGE_NOT_VERIFIED_180D_PLUS" in t0["blockers"]


def test_exact_pair_forward_only_horizon_selection():
    t0 = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    history = [
        {"at": (t0 + timedelta(minutes=4)).isoformat(), "pair_address": "pair", "price_usd": 1.01},
        {"at": (t0 + timedelta(minutes=5)).isoformat(), "pair_address": "other", "price_usd": 9},
        {"at": (t0 + timedelta(minutes=6)).isoformat(), "pair_address": "pair", "price_usd": 1.05},
    ]
    row = select_exact_pair_observation(history, "pair", t0 + timedelta(minutes=5), 8)
    assert row["price_usd"] == 1.05
    assert row["pair_address"] == "pair"


def test_hash_stable():
    assert sha256({"a": 1, "b": 2}) == sha256({"b": 2, "a": 1})
