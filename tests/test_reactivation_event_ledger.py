from __future__ import annotations

from datetime import datetime, timedelta, timezone

from wallet500.cex_reactivation_hold import evaluate_hold
from wallet500.reactivation_event_ledger import (
    build_confirmed_event,
    empty_ledger,
    event_needs_refresh,
    observe_event,
    record_confirmed_event,
)


UTC = timezone.utc


def _entry():
    return {
        "triggered_at": "2026-09-18T07:31:30+00:00",
        "pair_address": "0xPair",
        "trigger_price_usd": 0.03478,
        "chain": "bsc",
        "token_address": "0xToken",
        "symbol": "MUBARAKUSDT",
        "trigger_exchanges": ["binance", "gate", "kucoin"],
    }


def _metrics():
    return {
        "reactivation_hold_age_minutes": 13.6,
        "fresh_reactivation_exchanges": ["gate", "kucoin"],
        "current_price": 0.03488,
        "signal_score": 66,
        "signal_price": 0.03317,
        "signal_at": "2026-09-05T18:55:50+00:00",
        "signal_milestone": "first_alert",
        "since_discovery_pct": 5.2,
    }


def test_confirmed_at_is_stable_across_repeated_hold_evaluations():
    first = evaluate_hold(
        _entry(),
        now=datetime(2026, 9, 18, 7, 45, 7, tzinfo=UTC),
        pair_address="0xPair",
        current_pair_price=0.03485,
    )
    assert first["confirmed"] is True
    confirmed_at = first["entry"]["confirmed_at"]

    second = evaluate_hold(
        first["entry"],
        now=datetime(2026, 9, 18, 7, 46, 5, tzinfo=UTC),
        pair_address="0xPair",
        current_pair_price=0.03484,
    )
    assert second["confirmed"] is True
    assert second["entry"]["confirmed_at"] == confirmed_at


def test_duplicate_confirmed_event_never_overwrites_immutable_core():
    ledger = empty_ledger()
    event = build_confirmed_event(
        asset_key="bsc:0xtoken",
        entry=_entry(),
        metrics=_metrics(),
        snapshot={"pair_address": "0xPair", "price_usd": 0.03485, "liquidity_usd": 2_430_000},
        confirmed_at=datetime(2026, 9, 18, 7, 45, 7, tzinfo=UTC),
    )
    stored, created = record_confirmed_event(ledger, event)
    assert created is True
    assert stored["confirmation_price_usd"] == 0.03485

    changed = dict(event)
    changed["confirmation_price_usd"] = 9.99
    stored_again, created_again = record_confirmed_event(ledger, changed)
    assert created_again is False
    assert stored_again["confirmation_price_usd"] == 0.03485
    assert len(ledger["events"]) == 1


def test_sampled_outcomes_close_1h_6h_24h_72h_without_rewriting_event():
    event = build_confirmed_event(
        asset_key="bsc:0xtoken",
        entry=_entry(),
        metrics=_metrics(),
        snapshot={"pair_address": "0xPair", "price_usd": 0.03485, "liquidity_usd": 2_430_000},
        confirmed_at=datetime(2026, 9, 18, 7, 45, 7, tzinfo=UTC),
    )
    immutable = {
        "event_id": event["event_id"],
        "triggered_at": event["triggered_at"],
        "confirmed_at": event["confirmed_at"],
        "confirmation_price_usd": event["confirmation_price_usd"],
    }
    confirmed = datetime(2026, 9, 18, 7, 45, 7, tzinfo=UTC)

    observe_event(event, observed_at=confirmed + timedelta(hours=1, minutes=2), price_usd=0.036)
    observe_event(event, observed_at=confirmed + timedelta(hours=6, minutes=3), price_usd=0.033)
    observe_event(event, observed_at=confirmed + timedelta(hours=24, minutes=5), price_usd=0.045)
    observe_event(event, observed_at=confirmed + timedelta(hours=72, minutes=8), price_usd=0.053)

    horizons = event["outcome"]["horizons"]
    assert all(horizons[f"{h}h"]["closed"] is True for h in (1, 6, 24, 72))
    assert horizons["1h"]["checkpoint_price_usd"] == 0.036
    assert horizons["6h"]["checkpoint_price_usd"] == 0.033
    assert horizons["24h"]["checkpoint_price_usd"] == 0.045
    assert horizons["72h"]["checkpoint_price_usd"] == 0.053
    assert event["outcome"]["sampled_mfe_pct"] > 50
    assert event["outcome"]["sampled_mae_pct"] < 0
    assert event_needs_refresh(event) is False

    for key, value in immutable.items():
        assert event[key] == value


def test_late_first_sample_does_not_back_project_into_earlier_horizons():
    event = build_confirmed_event(
        asset_key="bsc:0xtoken",
        entry=_entry(),
        metrics=_metrics(),
        snapshot={"pair_address": "0xPair", "price_usd": 0.03485, "liquidity_usd": 2_430_000},
        confirmed_at=datetime(2026, 9, 18, 7, 45, 7, tzinfo=UTC),
    )
    confirmed = datetime(2026, 9, 18, 7, 45, 7, tzinfo=UTC)
    observe_event(event, observed_at=confirmed + timedelta(hours=30), price_usd=0.050)

    horizons = event["outcome"]["horizons"]
    assert horizons["1h"]["checkpoint_status"] == "MISSED_NO_TIMELY_SAMPLE"
    assert horizons["6h"]["checkpoint_status"] == "MISSED_NO_TIMELY_SAMPLE"
    assert horizons["24h"]["checkpoint_status"] == "MISSED_NO_TIMELY_SAMPLE"
    assert horizons["1h"]["sampled_mfe_pct"] == 0.0
    assert horizons["6h"]["sampled_mfe_pct"] == 0.0
    assert horizons["24h"]["sampled_mfe_pct"] == 0.0
    assert horizons["72h"]["checkpoint_status"] == "PENDING"
