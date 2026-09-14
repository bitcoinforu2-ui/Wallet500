from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wallet500.decision_replay_lab import (
    HORIZON_MINUTES,
    _dt,
    _identity,
    _immutable_key,
    _num,
    _reliable_candidates,
)

DATA = Path("data")
SOURCE = "research-sample-ledger.json"
LEDGER = "decision-replay-ledger.json"
OUTPUT = "decision-replay-path-metrics.json"
MODE = "RESEARCH_ONLY_DECISION_REPLAY_PATH_METRICS_V1"
NEUTRAL_THRESHOLDS_PCT = (25.0, 50.0, 100.0, 200.0)
DRAWDOWN_BANDS_PCT = (-10.0, -20.0, -30.0, -50.0)


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _pct(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base <= 0:
        return None
    return (current / base - 1.0) * 100.0


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def _path_metrics(row: dict, replay_record: dict) -> dict:
    identity = _identity(row)
    if identity is None:
        return {"status": "INSUFFICIENT_COVERAGE", "reason": "INVALID_EXACT_IDENTITY"}
    first_dt = _dt(identity[3])
    if first_dt is None:
        return {"status": "INSUFFICIENT_COVERAGE", "reason": "INVALID_T0_TIMESTAMP"}
    t0 = replay_record.get("t0") if isinstance(replay_record.get("t0"), dict) else {}
    entry_price = _num(t0.get("price_usd"))
    t0_liq = _num(t0.get("exact_pair_liquidity_usd"))
    candidates, events = _reliable_candidates(row, identity)
    horizons: dict[str, dict] = {}

    for horizon, minutes in HORIZON_MINUTES.items():
        target = first_dt.timestamp() + minutes * 60
        selected = next((c for c in candidates if c["observed_dt"].timestamp() >= target), None)
        if selected is None:
            horizons[horizon] = {
                "status": "NOT_MATURED_OR_INSUFFICIENT_COVERAGE",
                "selection_rule": "FIRST_RELIABLE_EXACT_PAIR_OBSERVATION_AT_OR_AFTER_TARGET",
            }
            continue

        path = [c for c in candidates if first_dt <= c["observed_dt"] <= selected["observed_dt"]]
        price_points = [c for c in path if _num(c.get("price_usd")) is not None]
        returns = [(_pct(_num(c.get("price_usd")), entry_price), c) for c in price_points]
        returns = [(ret, c) for ret, c in returns if ret is not None]
        max_gain = max((ret for ret, _ in returns), default=None)
        max_drawdown = min((ret for ret, _ in returns), default=None)
        peak = max(returns, key=lambda x: x[0]) if returns else None
        time_to_peak = None
        if peak is not None:
            time_to_peak = (peak[1]["observed_dt"] - first_dt).total_seconds() / 60.0

        exact_liqs = [_num(c.get("exact_pair_liquidity_usd")) for c in path]
        exact_liqs = [x for x in exact_liqs if x is not None]
        min_liq = min(exact_liqs) if exact_liqs else None
        selected_liq = _num(selected.get("exact_pair_liquidity_usd"))
        liquidity_survival_ratio = None
        if min_liq is not None and t0_liq is not None and t0_liq > 0:
            liquidity_survival_ratio = min_liq / t0_liq

        selected_return = _pct(_num(selected.get("price_usd")), entry_price)
        horizons[horizon] = {
            "status": "OBSERVED",
            "observed_at": selected.get("observed_at"),
            "selected_return_pct": selected_return,
            "observed_path_max_gain_pct": max_gain,
            "observed_path_max_drawdown_pct": max_drawdown,
            "observed_path_time_to_peak_minutes": time_to_peak,
            "observed_path_points": len(path),
            "exact_pair_survival": True,
            "exact_pair_liquidity_at_horizon_usd": selected_liq,
            "observed_path_min_exact_pair_liquidity_usd": min_liq,
            "observed_path_min_liquidity_vs_t0_ratio": liquidity_survival_ratio,
            "exact_pair_liquidity_coverage": "SUFFICIENT" if exact_liqs else "INSUFFICIENT_COVERAGE",
            "neutral_gain_thresholds": {
                f"gte_{int(threshold)}pct": (max_gain is not None and max_gain >= threshold)
                for threshold in NEUTRAL_THRESHOLDS_PCT
            },
            "neutral_drawdown_bands": {
                f"lte_{abs(int(band))}pct": (max_drawdown is not None and max_drawdown <= band)
                for band in DRAWDOWN_BANDS_PCT
            },
            "volume_turnover_evolution": "INSUFFICIENT_COVERAGE",
            "notes": "Path metrics use only reliable exact-pair observations available up to the selected horizon observation; they are not continuous intraperiod extrema.",
        }

    return {
        "status": "OK",
        "key": replay_record.get("key"),
        "chain": replay_record.get("chain"),
        "token_address": replay_record.get("token_address"),
        "pair_address": replay_record.get("pair_address"),
        "first_decision_at": replay_record.get("first_decision_at"),
        "entry_price_usd": entry_price,
        "t0_exact_pair_liquidity_usd": t0_liq,
        "horizons": horizons,
        "checkpoint_integrity_events": events,
    }


def build(source: dict, ledger: dict) -> dict:
    source_rows = source.get("records") if isinstance(source.get("records"), dict) else {}
    source_rows = list(source_rows.values()) if isinstance(source_rows, dict) else list(source_rows or [])
    replay_records = ledger.get("records") if isinstance(ledger.get("records"), dict) else {}
    results: dict[str, dict] = {}
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        identity = _identity(row)
        if identity is None:
            continue
        key = _immutable_key(identity)
        rec = replay_records.get(key)
        if not isinstance(rec, dict):
            continue
        results[key] = _path_metrics(row, rec)

    horizon_summary: dict[str, dict] = {}
    for horizon in HORIZON_MINUTES:
        observed = [r["horizons"][horizon] for r in results.values() if r.get("status") == "OK" and r["horizons"][horizon].get("status") == "OBSERVED"]
        gains = [_num(x.get("observed_path_max_gain_pct")) for x in observed]
        gains = [x for x in gains if x is not None]
        drawdowns = [_num(x.get("observed_path_max_drawdown_pct")) for x in observed]
        drawdowns = [x for x in drawdowns if x is not None]
        survival = [x for x in observed if x.get("exact_pair_survival") is True]
        liq_cov = [x for x in observed if x.get("exact_pair_liquidity_coverage") == "SUFFICIENT"]
        horizon_summary[horizon] = {
            "records": len(results),
            "matured_observed": len(observed),
            "median_observed_path_max_gain_pct": _median(gains),
            "median_observed_path_max_drawdown_pct": _median(drawdowns),
            "exact_pair_survival_rate": (len(survival) / len(observed)) if observed else None,
            "exact_pair_liquidity_coverage_rate": (len(liq_cov) / len(observed)) if observed else None,
            "status": "OK" if observed else "INSUFFICIENT_COVERAGE",
        }

    return {
        "version": 1,
        "mode": MODE,
        "research_only": True,
        "production_effect": False,
        "production_thresholds_modified": False,
        "source_ledger": SOURCE,
        "replay_ledger": LEDGER,
        "selection_contract": "FIRST_RELIABLE_EXACT_PAIR_OBSERVATION_AT_OR_AFTER_TARGET",
        "path_extrema_semantics": "OBSERVED_EXACT_PAIR_PATH_ONLY_NOT_CONTINUOUS_INTRAPERIOD_HIGH_LOW",
        "records": results,
        "horizon_summary": horizon_summary,
        "guardrails": {
            "exact_pair_required": True,
            "no_future_observation_before_horizon_selection": True,
            "no_t0_mutation": True,
            "production_changes": False,
            "telegram_changes": False,
        },
    }


def main() -> None:
    source = _load(DATA / SOURCE, {})
    ledger = _load(DATA / LEDGER, {})
    report = build(source, ledger)
    (DATA / OUTPUT).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DECISION_REPLAY_PATH_METRICS_OK", {k: v["matured_observed"] for k, v in report["horizon_summary"].items()})


if __name__ == "__main__":
    main()
