from datetime import datetime, timezone

from wallet500.experiment_v1 import (
    checkpoint_once,
    classify_survival,
    history_features,
    merge_immutable,
    percentile,
    summarize,
)


def test_survivor_first_requires_50k_and_90pct_retention():
    ok = classify_survival({"entry_liquidity_usd": 100000, "current_liquidity_usd": 95000})
    bad = classify_survival({"entry_liquidity_usd": 100000, "current_liquidity_usd": 80000})
    below = classify_survival({"entry_liquidity_usd": 49000, "current_liquidity_usd": 49000})
    assert ok["survivor_first_pass"] is True
    assert ok["verified_tradable"] is True
    assert bad["survivor_first_pass"] is False
    assert below["verified_tradable"] is False


def test_failed_survival_marks_liquidity_floor_break():
    z = classify_survival({"entry_liquidity_usd": 60000, "current_liquidity_usd": 40000})
    assert z["failed_survival"] is True
    assert z["verified_tradable"] is False


def test_summary_uses_only_observed_checkpoints():
    rows = [
        {"return_pct": -50, "verified_tradable": False, "failed_survival": True, "checkpoint_1h": {"survived": False}, "max_drawdown_pct": -70},
        {"return_pct": 10, "verified_tradable": True, "failed_survival": False, "checkpoint_1h": {"survived": True}, "max_drawdown_pct": -10},
        {"return_pct": 30, "verified_tradable": True, "failed_survival": False, "max_drawdown_pct": -5},
    ]
    z = summarize(rows)
    assert z["n"] == 3
    assert z["survival_1h_observed_n"] == 2
    assert z["survival_1h_pct"] == 50.0
    assert z["median_roi_pct"] == 10
    assert z["p25_roi_pct"] == -20
    assert z["verified_tradable_pct"] == 66.67
    assert z["max_drawdown_pct"] == -70


def test_immutable_entry_fields_never_rewrite_and_conflict_is_audited():
    prev = {"chain": "bsc", "token": "0x1", "pair_address": "pairA", "entry_price_usd": 1.0, "entry_liquidity_usd": 60000}
    row = {"chain": "bsc", "token": "0x1", "pair_address": "pairB", "entry_price_usd": 2.0, "entry_liquidity_usd": 70000, "current_price_usd": 3.0}
    z = merge_immutable(prev, row)
    assert z["pair_address"] == "pairA"
    assert z["entry_price_usd"] == 1.0
    assert z["entry_liquidity_usd"] == 60000
    assert z["current_price_usd"] == 3.0
    assert {c["field"] for c in z["immutability_conflicts"]} >= {"pair_address", "entry_price_usd", "entry_liquidity_usd"}


def test_checkpoint_is_first_observation_and_never_rewritten():
    rec = {}
    now = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
    checkpoint_once(rec, "1h", 1.2, {"current_liquidity_usd": 55000}, now)
    first = dict(rec["checkpoint_1h"])
    checkpoint_once(rec, "1h", 2.5, {"current_liquidity_usd": 1000}, now)
    assert rec["checkpoint_1h"] == first
    assert rec["checkpoint_1h"]["survived"] is True


def test_five_minute_fallback_is_unverified():
    z = history_features({"history": [{"price_usd": 1, "liquidity_usd": 60000}, {"price_usd": 2, "liquidity_usd": 60000}]})
    assert z["provenance"] == "FALLBACK_UNVERIFIED"


def test_five_minute_timestamped_history_is_verified():
    z = history_features({
        "discovered_at": "2026-08-30T20:00:00+00:00",
        "history": [
            {"at": "2026-08-30T20:01:00+00:00", "price_usd": 1, "liquidity_usd": 60000},
            {"at": "2026-08-30T20:05:00+00:00", "price_usd": 1.1, "liquidity_usd": 62000},
        ],
    })
    assert z["provenance"] == "TIMESTAMP_VERIFIED_5M"
    assert z["marks_5m"] == 2


def test_percentile_empty_is_none():
    assert percentile([], .25) is None
