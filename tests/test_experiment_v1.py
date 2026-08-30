from wallet500.experiment_v1 import classify_survival, percentile, summarize


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


def test_summary_uses_median_p25_and_verified_rate():
    rows = [
        {"return_pct": -50, "verified_tradable": False, "failed_survival": True, "survived_1h": False, "max_drawdown_pct": -70},
        {"return_pct": 10, "verified_tradable": True, "failed_survival": False, "survived_1h": True, "max_drawdown_pct": -10},
        {"return_pct": 30, "verified_tradable": True, "failed_survival": False, "survived_1h": True, "max_drawdown_pct": -5},
    ]
    z = summarize(rows)
    assert z["n"] == 3
    assert z["median_roi_pct"] == 10
    assert z["p25_roi_pct"] == -20
    assert z["verified_tradable_pct"] == 66.67
    assert z["max_drawdown_pct"] == -70


def test_percentile_empty_is_none():
    assert percentile([], .25) is None
