from wallet500.decision_replay_lab import build as build_replay
from wallet500.decision_replay_path_metrics import build as build_path


def _source():
    return {
        "records": {
            "x": {
                "chain": "solana",
                "token_address": "TOKEN",
                "pair_address": "PAIR",
                "event_at": "2026-09-13T00:00:00+00:00",
                "decision_snapshot": {
                    "identity": {"chain": "solana", "token": "TOKEN", "pair_address": "PAIR"},
                    "entry": {
                        "observed_at": "2026-09-13T00:00:00+00:00",
                        "entry_price_usd": 1.0,
                        "verified_execution_liquidity_usd": 100000.0,
                    },
                },
                "checkpoint_history": [
                    {"captured_at": "2026-09-13T00:30:00+00:00", "price_usd": 1.20, "pair_address": "PAIR", "verified_execution_liquidity_usd": 90000.0, "source": "EXACT"},
                    {"captured_at": "2026-09-13T01:01:00+00:00", "price_usd": 1.50, "pair_address": "PAIR", "verified_execution_liquidity_usd": 80000.0, "source": "EXACT"},
                    {"captured_at": "2026-09-13T01:20:00+00:00", "price_usd": 0.70, "pair_address": "PAIR", "verified_execution_liquidity_usd": 50000.0, "source": "EXACT"},
                ],
            }
        }
    }


def test_path_metrics_use_only_observations_up_to_first_at_or_after_horizon():
    source = _source()
    ledger, _ = build_replay(source, {})
    report = build_path(source, ledger)
    rec = next(iter(report["records"].values()))
    h1 = rec["horizons"]["1h"]
    assert h1["observed_at"] == "2026-09-13T01:01:00+00:00"
    assert round(h1["observed_path_max_gain_pct"], 6) == 50.0
    assert round(h1["observed_path_max_drawdown_pct"], 6) == 0.0
    assert h1["observed_path_time_to_peak_minutes"] == 61.0
    assert h1["observed_path_min_exact_pair_liquidity_usd"] == 80000.0
    assert h1["neutral_gain_thresholds"]["gte_50pct"] is True
    assert h1["drawdown_semantics"] == "PEAK_TO_TROUGH_FROM_T0_THROUGH_SELECTED_HORIZON_OBSERVATION"


def test_future_crash_is_not_leaked_into_1h_path_metrics():
    source = _source()
    ledger, _ = build_replay(source, {})
    report = build_path(source, ledger)
    h1 = next(iter(report["records"].values()))["horizons"]["1h"]
    assert h1["observed_path_max_drawdown_pct"] == 0.0
    assert h1["observed_path_min_exact_pair_liquidity_usd"] == 80000.0


def test_peak_to_trough_drawdown_is_measured_after_peak_when_horizon_includes_crash():
    source = _source()
    source["records"]["x"]["checkpoint_history"].append({
        "captured_at": "2026-09-13T03:01:00+00:00",
        "price_usd": 0.80,
        "pair_address": "PAIR",
        "verified_execution_liquidity_usd": 45000.0,
        "source": "EXACT",
    })
    ledger, _ = build_replay(source, {})
    report = build_path(source, ledger)
    h3 = next(iter(report["records"].values()))["horizons"]["3h"]
    assert round(h3["observed_path_max_drawdown_pct"], 6) == round((0.70 / 1.50 - 1.0) * 100.0, 6)
    assert h3["neutral_drawdown_bands"]["lte_50pct"] is True


def test_wrong_pair_is_excluded_from_path():
    source = _source()
    source["records"]["x"]["checkpoint_history"].insert(1, {
        "captured_at": "2026-09-13T01:00:00+00:00",
        "price_usd": 99.0,
        "pair_address": "WRONG",
        "verified_execution_liquidity_usd": 1.0,
        "source": "BAD",
    })
    ledger, _ = build_replay(source, {})
    report = build_path(source, ledger)
    rec = next(iter(report["records"].values()))
    assert rec["horizons"]["1h"]["observed_path_max_gain_pct"] < 100.0
    assert any(e["type"] == "REJECTED_CHECKPOINT_IDENTITY_CONFLICT" for e in rec["checkpoint_integrity_events"])


def test_liquidity_coverage_is_explicit_when_missing():
    source = _source()
    for cp in source["records"]["x"]["checkpoint_history"]:
        cp.pop("verified_execution_liquidity_usd", None)
    ledger, _ = build_replay(source, {})
    report = build_path(source, ledger)
    h1 = next(iter(report["records"].values()))["horizons"]["1h"]
    assert h1["exact_pair_liquidity_coverage"] == "INSUFFICIENT_COVERAGE"
    assert h1["observed_path_min_exact_pair_liquidity_usd"] is None
