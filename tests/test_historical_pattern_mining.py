from copy import deepcopy
from datetime import datetime, timedelta, timezone

from wallet500.historical_pattern_mining import _active_features, build


def _record(index: int, *, high_signal: bool, winner: bool, actionable: bool | None = None) -> dict:
    first = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(hours=index)
    ret = 40.0 if winner else -30.0
    drawdown = -5.0 if winner else -35.0
    if actionable is None:
        actionable = high_signal
    t0 = {
        "actionable": actionable,
        "verified_execution_tradable": True,
        "signal_score": 90.0 if high_signal else 40.0,
        "readiness_passed": 7 if high_signal else 3,
        "readiness_total": 7,
        "turnover": 1.5 if high_signal else 0.2,
        "exact_pair_liquidity_usd": 120000.0,
        "market_age_days": 5.0,
        "market_cap_usd": 5_000_000.0,
        "buy_flow_usd": 30000.0 if high_signal else 9000.0,
        "sell_flow_usd": 10000.0,
        "source_lane_count": 3,
        "evidence_positive_count": 3 if high_signal else 1,
        "evidence_positive_lanes": ["wallet", "capital", "social"] if high_signal else ["social"],
        "blockers": [] if high_signal else ["weak_wallet_confirmation"],
        "missing_gates": [] if high_signal else ["wallet"],
        "decision_label": "REAL_ALERT" if high_signal else "WATCH",
    }
    return {
        "key": f"k{index}",
        "chain": "solana",
        "token_address": f"TOKEN{index}",
        "pair_address": f"PAIR{index}",
        "first_decision_at": first.isoformat(),
        "t0": t0,
        "outcomes": {
            "24h": {
                "status": "OBSERVED",
                "observed_at": (first + timedelta(hours=24)).isoformat(),
                "friction_adjusted_return_pct": ret,
                "observed_drawdown_pct": drawdown,
            },
            "7d": {
                "status": "OBSERVED",
                "observed_at": (first + timedelta(days=7)).isoformat(),
                "friction_adjusted_return_pct": ret,
                "observed_drawdown_pct": drawdown,
            },
        },
    }


def _replay(count: int) -> dict:
    records = {}
    for index in range(count):
        high = (index % 6) < 3
        records[f"k{index}"] = _record(index, high_signal=high, winner=high)
    return {"records": records}


def test_future_outcomes_never_enter_t0_feature_vector():
    record = _record(0, high_signal=True, winner=True)
    before = _active_features(record)
    changed = deepcopy(record)
    changed["outcomes"]["7d"]["friction_adjusted_return_pct"] = -99.0
    changed["outcomes"]["7d"]["observed_drawdown_pct"] = -99.0
    changed["outcomes"]["24h"]["friction_adjusted_return_pct"] = -99.0
    assert _active_features(changed) == before


def test_recurring_pattern_must_survive_two_non_overlapping_future_windows():
    report = build(_replay(30))
    terminal = report["cohorts"]["7d_terminal"]
    walk = terminal["walk_forward"]

    assert terminal["baseline"]["records"] == 30
    assert len(walk["validation_windows"]) == 2
    assert walk["status"] == "VALIDATED"
    assert any("signal_score:gte80" in item["features"] for item in walk["stable_patterns"])
    assert report["promotion_gate"]["status"] == "READY_FOR_RESEARCH_REVIEW"
    assert report["promotion_gate"]["automatic_production_promotion"] is False
    assert report["production_effect"] is False


def test_review_gate_stays_closed_below_terminal_sample_requirement():
    report = build(_replay(18))
    assert report["cohorts"]["7d_terminal"]["walk_forward"]["status"] == "INSUFFICIENT_SAMPLE"
    assert report["promotion_gate"]["status"] == "NOT_READY_FOR_RESEARCH_REVIEW"
    assert report["promotion_gate"]["validation_windows"] == 0


def test_near_miss_winner_is_preserved_as_a_separate_count():
    replay = _replay(10)
    replay["records"]["k0"] = _record(0, high_signal=True, winner=True, actionable=False)
    report = build(replay)
    assert report["cohorts"]["24h_exploratory"]["baseline"]["near_miss_wins"] >= 1
    assert report["cohorts"]["7d_terminal"]["baseline"]["near_miss_wins"] >= 1
