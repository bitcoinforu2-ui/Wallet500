from datetime import datetime, timezone

from wallet500.paid_attention_watch import _fresh_paid_groups, classify_watch, timing_class


TOKEN = "9NMQjV8PVxx8rDxym1fG3Dbc8D2YFwWUZKYQ9VU6pump"
PAIR = "5bqPJzqqYsuPVcScosTKHQzRMFjiBZNDU9Yom95uDhn1"


def ledger(events):
    return {
        "mode": "RESEARCH_ONLY_PAID_VISIBILITY_LAB_V1",
        "contract": "PAID_VISIBILITY_LAB_V1",
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "events": events,
    }


def event(kind="BOOST", h24=8, h6=12, boost=500, pair_locked=True):
    return {
        "provider": "dexscreener",
        "promotion_type": kind,
        "chain": "solana",
        "token_address": TOKEN,
        "pair_address": PAIR,
        "pair_identity_locked": pair_locked,
        "first_seen_at": "2026-09-01T01:00:00+00:00",
        "last_seen_at": "2026-09-01T02:00:00+00:00",
        "boost_amount_latest": boost if kind == "BOOST" else None,
        "boost_total_amount_latest": boost if kind == "BOOST" else None,
        "t0": {
            "pair_address": PAIR,
            "price_change_h1_pct": 2,
            "price_change_h6_pct": h6,
            "price_change_h24_pct": h24,
            "liquidity_usd": 80_000,
        },
        "observations": [],
        "production_portfolio_impact": "NONE",
    }


def test_boost_and_ad_merge_into_one_exact_pair_research_group():
    ref = datetime(2026, 9, 1, 3, tzinfo=timezone.utc)
    groups = _fresh_paid_groups(ledger([event("BOOST"), event("AD")]), ref)
    assert len(groups) == 1
    g = groups[0]
    assert g["token_address"] == TOKEN
    assert g["pair_address"] == PAIR
    assert g["boost_total_amount"] == 500
    assert g["ad_and_boost"] is True
    assert set(g["promotion_types"]) == {"AD", "BOOST"}


def test_unlocked_pair_never_enters_research_watch():
    ref = datetime(2026, 9, 1, 3, tzinfo=timezone.utc)
    groups = _fresh_paid_groups(ledger([event(pair_locked=False)]), ref)
    assert groups == []


def test_stale_paid_event_is_not_active_trigger():
    old = event()
    old["last_seen_at"] = "2026-08-28T01:00:00+00:00"
    ref = datetime(2026, 9, 1, 3, tzinfo=timezone.utc)
    assert _fresh_paid_groups(ledger([old]), ref) == []


def test_timing_uses_t0_and_separates_early_from_late():
    ref = datetime(2026, 9, 1, 3, tzinfo=timezone.utc)
    early = _fresh_paid_groups(ledger([event(h24=7, h6=12)]), ref)[0]
    late = _fresh_paid_groups(ledger([event(h24=140, h6=95)]), ref)[0]
    assert timing_class(early) == "PROMOTION_PRE_BREAKOUT_WINDOW"
    assert timing_class(late) == "PROMOTION_AFTER_BREAKOUT"


def test_paid_trigger_alone_stays_research_watch():
    assert classify_watch(
        "PROMOTION_PRE_BREAKOUT_WINDOW",
        "WAKING_UNCONFIRMED_RESEARCH",
        None,
    ) == "PAID_ATTENTION_RESEARCH_WATCH"


def test_early_status_requires_independent_waking_confirmation():
    assert classify_watch(
        "PROMOTION_PRE_BREAKOUT_WINDOW",
        "WAKING_CONFIRMED_RESEARCH",
        None,
    ) == "PAID_ATTENTION_EARLY_CONFIRMING"


def test_late_promotion_never_becomes_early_confirming():
    assert classify_watch(
        "PROMOTION_AFTER_BREAKOUT",
        "WAKING_STRONG_RESEARCH",
        None,
    ) == "PAID_ATTENTION_LATE_MOVE"


def test_distribution_risk_overrides_early_confirmation():
    assert classify_watch(
        "PROMOTION_PRE_BREAKOUT_WINDOW",
        "WAKING_STRONG_RESEARCH",
        {"risk_score": 75},
    ) == "PAID_ATTENTION_RISK_RESEARCH"
