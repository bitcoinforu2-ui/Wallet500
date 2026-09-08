from wallet500.revival_forensics_v2 import (
    MIN_AGE_DAYS,
    _qualifies_t0,
    exact_pair,
    pct,
    sha256,
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