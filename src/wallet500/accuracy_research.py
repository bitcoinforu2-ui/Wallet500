from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

DATA = Path("data")
OUTPUT = "accuracy-research.json"
MODE = "RESEARCH_ONLY_ACCURACY_LAB_V1"
WINNER_RETURN_PCT = 20.0
PEAK_TARGETS = (25.0, 50.0, 100.0)


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _med(values: list[float]) -> float | None:
    return round(median(values), 6) if values else None


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 4) if denominator else None


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _records(payload: dict) -> list[dict]:
    rows = payload.get("records") if isinstance(payload, dict) else None
    if isinstance(rows, dict):
        return [x for x in rows.values() if isinstance(x, dict)]
    if isinstance(rows, list):
        return [x for x in rows if isinstance(x, dict)]
    return []


def _positions(payload: dict) -> list[dict]:
    rows = payload.get("positions") if isinstance(payload, dict) else None
    return [x for x in rows or [] if isinstance(x, dict)]


def _mature_24h_rows(sample_ledger: dict) -> list[dict]:
    out: list[dict] = []
    for row in _records(sample_ledger):
        cp = (row.get("checkpoints") or {}).get("24h")
        if not isinstance(cp, dict):
            continue
        ret = _num(cp.get("friction_adjusted_return_pct"))
        if ret is None:
            continue
        out.append({"row": row, "return_pct": ret})
    return out


def _gate_distance(mature: list[dict]) -> dict:
    winner_gaps: list[float] = []
    neutral_gaps: list[float] = []
    winner_source_deficits: list[float] = []
    neutral_source_deficits: list[float] = []
    winner_missing_counts: list[float] = []
    neutral_missing_counts: list[float] = []
    one_gate_short_winners = 0
    one_gate_short_total = 0

    for item in mature:
        row = item["row"]
        entry = (row.get("decision_snapshot") or {}).get("entry") or {}
        passed = _num(entry.get("readiness_passed"), 0.0) or 0.0
        total = _num(entry.get("readiness_total"), 0.0) or 0.0
        gap = max(0.0, total - passed) if total else 0.0
        source_lanes = _num(entry.get("source_lane_count"), 0.0) or 0.0
        source_deficit = max(0.0, 2.0 - source_lanes)
        missing_count = float(len(entry.get("missing_gates") or []))
        winner = item["return_pct"] >= WINNER_RETURN_PCT
        target_gaps = winner_gaps if winner else neutral_gaps
        target_src = winner_source_deficits if winner else neutral_source_deficits
        target_miss = winner_missing_counts if winner else neutral_missing_counts
        target_gaps.append(gap)
        target_src.append(source_deficit)
        target_miss.append(missing_count)
        if gap == 1:
            one_gate_short_total += 1
            if winner:
                one_gate_short_winners += 1

    return {
        "definition": "distance_to_current_production_readiness_without_changing_any_gate",
        "winner_threshold_24h_friction_adjusted_pct": WINNER_RETURN_PCT,
        "winner_mean_readiness_gap": _avg(winner_gaps),
        "nonwinner_mean_readiness_gap": _avg(neutral_gaps),
        "winner_mean_source_lane_deficit": _avg(winner_source_deficits),
        "nonwinner_mean_source_lane_deficit": _avg(neutral_source_deficits),
        "winner_mean_missing_gate_count": _avg(winner_missing_counts),
        "nonwinner_mean_missing_gate_count": _avg(neutral_missing_counts),
        "one_gate_short": {
            "n": one_gate_short_total,
            "winner_count": one_gate_short_winners,
            "winner_rate_pct": _pct(one_gate_short_winners, one_gate_short_total),
        },
        "research_only": True,
    }


def _coverage_and_timing(real_ledger: dict) -> tuple[dict, dict, dict]:
    rows = _positions(real_ledger)
    coverages: list[float] = []
    winner_cov: list[float] = []
    other_cov: list[float] = []
    delays: list[float] = []
    winner_delays: list[float] = []
    other_delays: list[float] = []
    low_coverage_count = 0
    target_counts = {str(int(t)): 0 for t in PEAK_TARGETS}
    stop_touch_count = 0
    with_peak = 0
    with_trough = 0

    for row in rows:
        dna = row.get("entry_signal_dna") if isinstance(row.get("entry_signal_dna"), dict) else {}
        cov = _num(dna.get("feature_coverage_ratio"))
        peak = _num(row.get("peak_return_pct"))
        trough = _num(row.get("trough_return_pct"))
        if peak is not None:
            with_peak += 1
            for target in PEAK_TARGETS:
                if peak >= target:
                    target_counts[str(int(target))] += 1
        if trough is not None:
            with_trough += 1
            if trough <= -8.0:
                stop_touch_count += 1
        winner = peak is not None and peak >= 25.0
        if cov is not None:
            pct = cov * 100.0 if cov <= 1.0 else cov
            coverages.append(pct)
            (winner_cov if winner else other_cov).append(pct)
            if pct < 50.0:
                low_coverage_count += 1
        t0 = _parse_dt(row.get("original_signal_t0"))
        entry = _parse_dt(row.get("entry_time"))
        if t0 and entry and entry >= t0:
            delay = (entry - t0).total_seconds() / 3600.0
            delays.append(delay)
            (winner_delays if winner else other_delays).append(delay)

    coverage = {
        "real_alert_position_count": len(rows),
        "measured_count": len(coverages),
        "mean_feature_coverage_pct": _avg(coverages),
        "median_feature_coverage_pct": _med(coverages),
        "low_coverage_under_50pct_count": low_coverage_count,
        "peak_25plus_mean_coverage_pct": _avg(winner_cov),
        "sub_25_peak_mean_coverage_pct": _avg(other_cov),
        "finding": "MISSING_FEATURES_ARE_A_MEASUREMENT_GAP_NOT_ZERO_ALPHA",
        "research_only": True,
    }
    timing = {
        "measured_count": len(delays),
        "mean_signal_to_entry_hours": _avg(delays),
        "median_signal_to_entry_hours": _med(delays),
        "peak_25plus_mean_signal_to_entry_hours": _avg(winner_delays),
        "sub_25_peak_mean_signal_to_entry_hours": _avg(other_delays),
        "purpose": "SEPARATE_TOKEN_QUALITY_FROM_ENTRY_TIMING_AND_ANTI_CHASE",
        "production_anti_chase_changed": False,
        "research_only": True,
    }
    barrier = {
        "ordered_path_status": "COLLECTING_ORDERED_PATHS",
        "note": "Peak/trough alone cannot prove whether a gain target happened before an -8% stop. Current values are descriptive attainment only.",
        "positions_with_peak": with_peak,
        "observed_peak_attainment": {
            f"plus_{int(t)}pct": {
                "count": target_counts[str(int(t))],
                "rate_pct": _pct(target_counts[str(int(t))], with_peak),
            }
            for t in PEAK_TARGETS
        },
        "positions_with_trough": with_trough,
        "observed_minus_8pct_touch_count": stop_touch_count,
        "observed_minus_8pct_touch_rate_pct": _pct(stop_touch_count, with_trough),
        "target_probabilities": ["P(+25% before -8%)", "P(+50% before -8%)", "P(+100% before -8%)"],
        "probabilities_publishable": False,
    }
    return coverage, timing, barrier


def _persistence_breadth(mature: list[dict]) -> dict:
    win_sources: list[float] = []
    other_sources: list[float] = []
    win_evidence: list[float] = []
    other_evidence: list[float] = []
    for item in mature:
        entry = ((item["row"].get("decision_snapshot") or {}).get("entry") or {})
        sources = _num(entry.get("source_lane_count"), 0.0) or 0.0
        evidence = _num(entry.get("evidence_positive_count"), 0.0) or 0.0
        winner = item["return_pct"] >= WINNER_RETURN_PCT
        (win_sources if winner else other_sources).append(sources)
        (win_evidence if winner else other_evidence).append(evidence)
    return {
        "winner_mean_source_lane_count": _avg(win_sources),
        "nonwinner_mean_source_lane_count": _avg(other_sources),
        "winner_mean_positive_evidence_count": _avg(win_evidence),
        "nonwinner_mean_positive_evidence_count": _avg(other_evidence),
        "next_probe": "wallet_independence_repeat_buyers_and_multi_scan_persistence",
        "status": "PARTIAL_CURRENT_DATA_MORE_PROSPECTIVE_BREADTH_NEEDED",
        "research_only": True,
    }


def build(data_dir: Path = DATA) -> dict:
    report = _load(data_dir / "research-sample-report.json", {})
    sample_ledger = _load(data_dir / "research-sample-ledger.json", {})
    real_ledger = _load(data_dir / "real-alert-10usd-ledger.json", {})
    decision_only = _load(data_dir / "decision-only-shadow.json", {})

    mature = _mature_24h_rows(sample_ledger)
    sample = report.get("sample_acceleration") if isinstance(report.get("sample_acceleration"), dict) else {}
    verified_24h = ((report.get("horizons") or {}).get("24h") or {}).get("verified_execution_subset") or {}
    gate_rows = report.get("gate_attribution_24h") or []
    independent = next((x for x in gate_rows if x.get("gate_or_blocker") == "INDEPENDENT_CONFIRMATION_LT_2"), {})
    strong = (decision_only.get("horizons") or {}).get("24h") or {}

    coverage, timing, barrier = _coverage_and_timing(real_ledger)
    gate_distance = _gate_distance(mature)
    breadth = _persistence_breadth(mature)

    mature_count = int(sample.get("mature_24h_count") or len(mature))
    strong_target = int(sample.get("strong_target") or 50)
    deep_target = int(sample.get("deep_target") or 100)
    winner_rate = _num(verified_24h.get("winner_rate_pct"))

    findings = [
        {
            "id": "INDEPENDENT_CONFIRMATION_FALSE_NEGATIVE",
            "priority": 1,
            "status": "PRIMARY_RESEARCH_CANDIDATE_KEEP_PRODUCTION_GATE",
            "n": int(independent.get("n") or 0),
            "winner_count": int(independent.get("winner_count") or 0),
            "big_winner_count": int(independent.get("big_winner_count") or 0),
            "winner_rate_pct": _num(independent.get("winner_rate_pct")),
            "mean_friction_adjusted_return_pct": _num(independent.get("mean_friction_adjusted_return_pct")),
            "production_action": "NO_CHANGE_KEEP_GATE_COLLECT_MORE_FORWARD_EVIDENCE",
        },
        {
            "id": "STRONG_DECISION_LANE_CLEAN_SHADOW",
            "priority": 2,
            "status": "NO_RELAXATION_EVIDENCE_YET",
            "n_24h": int(strong.get("n") or 0),
            "winner_count_24h": int(strong.get("winner_count") or 0),
            "winner_rate_pct_24h": _num(strong.get("winner_rate_pct")),
            "mean_friction_adjusted_return_pct_24h": _num(strong.get("mean_friction_adjusted_return_pct")),
            "production_action": "NO_CHANGE_KEEP_GATE",
        },
        {
            "id": "T0_EVIDENCE_COVERAGE",
            "priority": 3,
            "status": "MEASUREMENT_COVERAGE_IS_A_PRIMARY_LIMITATION",
            "mean_feature_coverage_pct": coverage.get("mean_feature_coverage_pct"),
            "low_coverage_under_50pct_count": coverage.get("low_coverage_under_50pct_count"),
            "production_action": "IMPROVE_OBSERVABILITY_NOT_THRESHOLDS",
        },
    ]

    return {
        "version": 1,
        "mode": MODE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "production_thresholds_modified": False,
        "headline": {
            "title": "ACCURACY LAB",
            "primary_finding": "INDEPENDENT_CONFIRMATION_IS_THE_LEADING_FALSE_NEGATIVE_RESEARCH_CANDIDATE",
            "primary_constraint": "T0_EVIDENCE_COVERAGE_AND_FRESHNESS",
            "production_recommendation": "KEEP_ALL_PRODUCTION_GATES_UNCHANGED",
            "verified_24h_winner_rate_pct": winner_rate,
        },
        "sample": {
            "records": int(report.get("record_count") or 0),
            "verified_execution_records": int(report.get("verified_execution_record_count") or 0),
            "mature_24h": mature_count,
            "strong_target": strong_target,
            "deep_target": deep_target,
            "strong_progress_pct": _pct(mature_count, strong_target),
            "deep_progress_pct": _pct(mature_count, deep_target),
            "next_strong_sample_remaining": max(0, strong_target - mature_count),
        },
        "findings": findings,
        "t0_coverage_freshness": coverage,
        "gate_distance": gate_distance,
        "confirmation_velocity": {
            "status": "COLLECTING_PROSPECTIVE_TRANSITIONS",
            "historical_backfill_allowed": False,
            "metric_plan": [
                "minutes_first_evidence_to_second_independent_confirmation",
                "source_lane_growth_15m_30m_60m",
                "readiness_velocity_15m_30m_60m",
            ],
            "production_effect": False,
        },
        "quality_vs_entry_timing": timing,
        "persistence_breadth": breadth,
        "barrier_probabilities": barrier,
        "research_priority": [
            "T0_COVERAGE_FRESHNESS",
            "GATE_DISTANCE",
            "CONFIRMATION_VELOCITY",
            "QUALITY_VS_ENTRY_TIMING",
            "PERSISTENCE_BREADTH",
        ],
        "guardrails": {
            "forward_or_immutable_t0_only": True,
            "no_hindsight_threshold_tuning": True,
            "no_automatic_weight_mutation": True,
            "real_alert_gate_changed": False,
            "telegram_alerts_changed": False,
            "automatic_buy": False,
        },
    }


def main() -> None:
    payload = build(DATA)
    path = DATA / OUTPUT
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "ACCURACY_RESEARCH_OK",
        {
            "mature_24h": (payload.get("sample") or {}).get("mature_24h"),
            "winner_rate": (payload.get("headline") or {}).get("verified_24h_winner_rate_pct"),
            "primary": (payload.get("headline") or {}).get("primary_finding"),
        },
    )


if __name__ == "__main__":
    main()
