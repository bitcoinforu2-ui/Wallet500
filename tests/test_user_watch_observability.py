"""Truth accounting: evaluating a WATCH row is not fresh market coverage."""
from scripts.user_watch_final_buy import coverage_observability


def test_report_distinguishes_evaluated_and_observable():
    rows = [
        {"observable": True, "blockers": []},
        {"observable": False, "blockers": ["MARKET_SNAPSHOT_STALE_OR_UNTIMED"]},
        {"blockers": ["UPSTREAM_PARTIAL_SNAPSHOT_NOT_FRESH"]},
        {"observable": True, "blockers": []},
    ]
    report = coverage_observability(rows, 4)
    assert report["evaluated_target_count"] == 3
    assert report["decision_coverage_pct"] == 75
    assert report["observable_target_count"] == 2
    assert report["observable_coverage_pct"] == 50
    assert report["unobservable_target_count"] == 2


def test_zero_targets_is_no_work_not_an_outage():
    r = coverage_observability([], 0)
    assert r["decision_coverage_pct"] == 100
    assert r["observable_coverage_pct"] == 100
    assert r["observable_target_count"] == 0


def test_observable_never_inflates_from_stale_watch_rows():
    rows = [{"observable": False, "blockers": ["STALE"]} for _ in range(100)]
    r = coverage_observability(rows, 100)
    assert r["decision_coverage_pct"] == 100
    assert r["observable_coverage_pct"] == 0
