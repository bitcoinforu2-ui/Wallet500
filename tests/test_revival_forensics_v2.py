from datetime import datetime, timezone

from wallet500.revival_forensics_v2 import (
    MIN_AGE_DAYS,
    _qualifies_t0,
    build_t0,
    exact_pair,
    holder_evidence,
    pct,
    sha256,
    update_event,
)


def test_pct():
    assert pct(1, 2) == 100.0
    assert pct(100, 50) == -50.0
    assert pct(0, 2) is None


def test_revival_forensics_age_pair_gate_is_90d_and_fail_closed():
    assert MIN_AGE_DAYS == 90

    valid = {
        "watch_status": "WAKING_MARKET_ONLY",
        "market_age_verified": True,
        "market_age_min_days": 90,
        "dex_pair_address": "pair",
    }
    assert _qualifies_t0(valid) is True
    assert exact_pair(valid) == "pair"

    too_young = dict(valid, market_age_min_days=89)
    assert _qualifies_t0(too_young) is False

    age_unverified = dict(valid, market_age_verified=False)
    assert _qualifies_t0(age_unverified) is False

    no_pair = dict(valid, dex_pair_address="")
    assert _qualifies_t0(no_pair) is False

    wrong_lane = dict(valid, watch_status="OTHER")
    assert _qualifies_t0(wrong_lane) is False


def test_hash_stable():
    assert sha256({"a": 1, "b": 2}) == sha256({"b": 2, "a": 1})


def test_runner_compatibility_helpers_preserve_t0_exact_pair_and_no_hindsight_inputs():
    coin = {
        "token_address": "mint",
        "symbol": "T",
        "market_age_verified": True,
        "market_age_min_days": 90,
        "dex_pair_address": "pair-A",
        "price_usd": 1.0,
        "dex_pair_liquidity_usd": 15000.0,
    }
    t0 = build_t0(coin, {"confirmation_status": "WAKING"}, "2026-09-10T10:00:00+00:00", "2026-09-10T10:00:01+00:00")
    assert t0["pair_address"] == "pair-A"
    assert t0["market_age_min_days"] == 90
    assert t0["blockers"] == []
    assert t0["evidence_sha256"] == sha256({k: v for k, v in t0.items() if k != "evidence_sha256"})

    holder = holder_evidence({}, {}, "mint")
    event = {"t0": t0, "horizons": {}, "observations": []}
    update_event(event, [{"pair_address": "pair-B", "observed_at": "2026-09-10T10:10:00+00:00", "price_usd": 99}], holder, datetime(2026, 9, 10, 10, 20, tzinfo=timezone.utc))
    assert event["peak_return_pct"] == 0.0
    assert event["horizons"]["5m"]["available"] is False
    assert event["horizons"]["15m"]["available"] is False
