from wallet500.hyperliquid_copy_watch import (
    _close_fill_stats,
    _decision,
    _history_delta,
    _history_span_days,
    _max_drawdown_pct,
    _percentile,
)


def test_history_helpers():
    day = 86_400_000
    hist = [[0, "100"], [100 * day, "150"], [200 * day, "120"]]
    assert _history_span_days(hist) == 200
    assert _history_delta(hist) == 20
    assert round(_max_drawdown_pct(hist), 2) == 20.0


def test_close_fill_proxy_keeps_losses():
    now = 1_000_000_000_000
    fills = [
        {"time": now - 1000, "dir": "Close Long", "closedPnl": "10"},
        {"time": now - 2000, "dir": "Close Short", "closedPnl": "-4"},
        {"time": now - 3000, "dir": "Open Long", "closedPnl": "0"},
    ]
    s = _close_fill_stats(fills, now)
    assert s["closed_fill_events"] == 2
    assert s["wins"] == 1
    assert s["losses"] == 1
    assert s["close_win_rate_proxy_pct"] == 50.0


def test_decision_requires_forward_copyability_after_historical_pass():
    cfg = {
        "min_history_days": 180,
        "min_closed_fill_events": 200,
        "min_close_win_rate_proxy_pct": 60,
        "max_drawdown_pct": 20,
        "require_positive_month_pnl": True,
        "require_positive_all_time_pnl": True,
        "max_fills_per_day_30d": 50,
        "min_forward_observations_for_copyability": 20,
        "max_forward_median_abs_slippage_bps": 20,
        "max_forward_p95_abs_slippage_bps": 50,
    }
    row = {
        "history_span_days": 300,
        "closed_fill_events": 500,
        "close_win_rate_proxy_pct": 70,
        "max_drawdown_pct": 10,
        "month_pnl": 100,
        "all_time_pnl": 1000,
        "fills_per_day_30d": 8,
        "forward_copy_observations": 0,
        "forward_median_abs_slippage_bps": None,
        "forward_p95_abs_slippage_bps": None,
    }
    d, blockers = _decision(row, cfg)
    assert d == "HISTORICAL_SHORTLIST_FORWARD_VALIDATION"
    assert "NEED_MORE_FORWARD_COPY_OBSERVATIONS" in blockers

    row.update(
        forward_copy_observations=25,
        forward_median_abs_slippage_bps=8,
        forward_p95_abs_slippage_bps=22,
    )
    d, blockers = _decision(row, cfg)
    assert d == "COPYABLE_CANDIDATE"
    assert blockers == []


def test_decision_blocks_bad_drawdown_even_with_high_win_rate():
    cfg = {
        "min_history_days": 180,
        "min_closed_fill_events": 200,
        "min_close_win_rate_proxy_pct": 60,
        "max_drawdown_pct": 20,
        "require_positive_month_pnl": True,
        "require_positive_all_time_pnl": True,
        "max_fills_per_day_30d": 50,
    }
    row = {
        "history_span_days": 500,
        "closed_fill_events": 1000,
        "close_win_rate_proxy_pct": 95,
        "max_drawdown_pct": 55,
        "month_pnl": 1000,
        "all_time_pnl": 5000,
        "fills_per_day_30d": 10,
    }
    d, blockers = _decision(row, cfg)
    assert d == "WATCH"
    assert "DRAWDOWN_TOO_HIGH_OR_UNKNOWN" in blockers


def test_percentile():
    assert _percentile([], 0.95) is None
    assert _percentile([10], 0.95) == 10
    assert round(_percentile([1, 2, 3, 4, 5], 0.5), 2) == 3
