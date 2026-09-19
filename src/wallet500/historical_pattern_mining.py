from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

from wallet500.decision_replay_lab import _dt, _num

DATA = Path("data")
REPLAY = "decision-replay-ledger.json"
OUTPUT = "historical-pattern-report.json"
MODE = "RESEARCH_ONLY_HISTORICAL_PATTERN_MINING_V1"

WIN_RETURN_PCT = 20.0
FAIL_RETURN_PCT = -20.0
FAIL_DRAWDOWN_PCT = -30.0
MIN_DISCOVERY_SUPPORT = 5
MIN_TERMINAL_RECORDS_FOR_REVIEW = 30
MIN_VALIDATION_WINDOW = 5
MAX_DISCOVERY_PATTERNS = 120
MAX_REPORTED_PATTERNS = 60


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _safe_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    cleaned = []
    for ch in text:
        if ch.isalnum() or ch in {"_", "-", ":", "."}:
            cleaned.append(ch)
        elif ch.isspace() or ch in {"/", "|"}:
            cleaned.append("_")
    return "".join(cleaned)[:96]


def _ratio(numerator: Any, denominator: Any) -> float | None:
    a = _num(numerator)
    b = _num(denominator)
    if a is None or b is None or b == 0:
        return None
    return a / b


def _active_features(record: dict) -> frozenset[str]:
    t0 = record.get("t0") if isinstance(record.get("t0"), dict) else {}
    features: set[str] = set()

    chain = _safe_name(record.get("chain"))
    if chain:
        features.add(f"chain:{chain}")

    actionable = t0.get("actionable")
    if actionable in (True, False):
        features.add("actionable:true" if actionable else "actionable:false")

    tradable = t0.get("verified_execution_tradable")
    if tradable in (True, False):
        features.add("tradable:true" if tradable else "tradable:false")

    score = _num(t0.get("signal_score"))
    if score is not None:
        if score >= 80:
            features.add("signal_score:gte80")
        elif score >= 70:
            features.add("signal_score:70_79")
        elif score >= 60:
            features.add("signal_score:60_69")
        else:
            features.add("signal_score:lt60")

    readiness = _ratio(t0.get("readiness_passed"), t0.get("readiness_total"))
    if readiness is not None:
        if readiness >= (6 / 7):
            features.add("readiness:gte6of7")
        elif readiness >= (4 / 7):
            features.add("readiness:4to5of7")
        else:
            features.add("readiness:lt4of7")

    turnover = _num(t0.get("turnover"))
    if turnover is not None:
        if turnover >= 2.0:
            features.add("turnover:gte2")
        elif turnover >= 1.0:
            features.add("turnover:1to2")
        elif turnover >= 0.5:
            features.add("turnover:0.5to1")
        else:
            features.add("turnover:lt0.5")

    liquidity = _num(t0.get("exact_pair_liquidity_usd"))
    if liquidity is not None:
        if liquidity >= 250000:
            features.add("liquidity:gte250k")
        elif liquidity >= 100000:
            features.add("liquidity:100k_250k")
        elif liquidity >= 50000:
            features.add("liquidity:50k_100k")
        elif liquidity >= 15000:
            features.add("liquidity:15k_50k")
        else:
            features.add("liquidity:lt15k")

    age = _num(t0.get("market_age_days"))
    if age is not None:
        if age <= 1:
            features.add("age:lte1d")
        elif age <= 7:
            features.add("age:1d_7d")
        elif age <= 30:
            features.add("age:7d_30d")
        elif age <= 90:
            features.add("age:30d_90d")
        else:
            features.add("age:gt90d")

    market_cap = _num(t0.get("market_cap_usd"))
    if market_cap is not None:
        if market_cap < 1_000_000:
            features.add("market_cap:lt1m")
        elif market_cap < 10_000_000:
            features.add("market_cap:1m_10m")
        elif market_cap < 100_000_000:
            features.add("market_cap:10m_100m")
        else:
            features.add("market_cap:gte100m")

    flow_ratio = _ratio(t0.get("buy_flow_usd"), t0.get("sell_flow_usd"))
    if flow_ratio is not None:
        if flow_ratio >= 2:
            features.add("buy_sell_ratio:gte2")
        elif flow_ratio >= 1.2:
            features.add("buy_sell_ratio:1.2to2")
        elif flow_ratio >= 1:
            features.add("buy_sell_ratio:1to1.2")
        else:
            features.add("buy_sell_ratio:lt1")

    lanes = _num(t0.get("source_lane_count"))
    if lanes is not None:
        features.add("source_lanes:gte3" if lanes >= 3 else ("source_lanes:2" if lanes >= 2 else "source_lanes:lt2"))

    evidence_count = _num(t0.get("evidence_positive_count"))
    if evidence_count is not None:
        if evidence_count >= 3:
            features.add("positive_evidence:gte3")
        elif evidence_count >= 2:
            features.add("positive_evidence:2")
        elif evidence_count >= 1:
            features.add("positive_evidence:1")
        else:
            features.add("positive_evidence:0")

    for lane in t0.get("evidence_positive_lanes") or []:
        lane_name = _safe_name(lane)
        if lane_name:
            features.add(f"evidence_lane:{lane_name}")

    blockers = t0.get("blockers") or []
    features.add("blockers:present" if blockers else "blockers:none")
    for blocker in blockers:
        blocker_name = _safe_name(blocker)
        if blocker_name:
            features.add(f"blocker:{blocker_name}")

    missing = t0.get("missing_gates") or []
    features.add("missing_gates:present" if missing else "missing_gates:none")
    for gate in missing:
        gate_name = _safe_name(gate)
        if gate_name:
            features.add(f"missing_gate:{gate_name}")

    label = _safe_name(t0.get("decision_label"))
    if label:
        features.add(f"decision_label:{label}")

    return frozenset(features)


def _outcome(record: dict, horizon: str) -> dict | None:
    outcome = ((record.get("outcomes") or {}).get(horizon) or {})
    if outcome.get("status") != "OBSERVED":
        return None
    ret = _num(outcome.get("friction_adjusted_return_pct"))
    if ret is None:
        return None
    drawdown = _num(outcome.get("observed_drawdown_pct"))
    if ret >= WIN_RETURN_PCT:
        outcome_class = "WIN"
    elif ret <= FAIL_RETURN_PCT or (drawdown is not None and drawdown <= FAIL_DRAWDOWN_PCT):
        outcome_class = "FAILURE"
    else:
        outcome_class = "NEUTRAL"
    actionable = ((record.get("t0") or {}).get("actionable"))
    subtype = "NEAR_MISS_WIN" if outcome_class == "WIN" and actionable is False else None
    return {
        "return_pct": ret,
        "drawdown_pct": drawdown,
        "class": outcome_class,
        "subtype": subtype,
        "observed_at": outcome.get("observed_at"),
    }


def _rows(replay: dict, horizon: str) -> list[dict]:
    records = replay.get("records") if isinstance(replay.get("records"), dict) else {}
    rows: list[dict] = []
    for key, record in records.items():
        if not isinstance(record, dict):
            continue
        outcome = _outcome(record, horizon)
        first = _dt(record.get("first_decision_at"))
        if outcome is None or first is None:
            continue
        rows.append(
            {
                "key": key,
                "first_dt": first,
                "first_decision_at": first.isoformat(),
                "features": _active_features(record),
                "outcome": outcome,
            }
        )
    rows.sort(key=lambda row: (row["first_dt"], str(row["key"])))
    return rows


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    phat = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (phat + z2 / (2 * total)) / denom
    margin = z * math.sqrt((phat * (1 - phat) / total) + (z2 / (4 * total * total))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _baseline(rows: list[dict]) -> dict:
    total = len(rows)
    wins = sum(1 for row in rows if row["outcome"]["class"] == "WIN")
    failures = sum(1 for row in rows if row["outcome"]["class"] == "FAILURE")
    neutrals = total - wins - failures
    near_misses = sum(1 for row in rows if row["outcome"].get("subtype") == "NEAR_MISS_WIN")
    returns = [row["outcome"]["return_pct"] for row in rows]
    return {
        "records": total,
        "wins": wins,
        "failures": failures,
        "neutral": neutrals,
        "near_miss_wins": near_misses,
        "win_rate": wins / total if total else None,
        "failure_rate": failures / total if total else None,
        "median_return_pct": median(returns) if returns else None,
    }


def _pattern_metrics(pattern: tuple[str, ...], rows: list[dict], baseline: dict) -> dict:
    matched = [row for row in rows if all(feature in row["features"] for feature in pattern)]
    support = len(matched)
    wins = sum(1 for row in matched if row["outcome"]["class"] == "WIN")
    failures = sum(1 for row in matched if row["outcome"]["class"] == "FAILURE")
    neutrals = support - wins - failures
    returns = [row["outcome"]["return_pct"] for row in matched]
    win_rate = wins / support if support else None
    failure_rate = failures / support if support else None
    base_win = baseline.get("win_rate")
    base_fail = baseline.get("failure_rate")
    low, high = _wilson(wins, support)
    return {
        "features": list(pattern),
        "support": support,
        "support_ratio": support / len(rows) if rows else 0.0,
        "wins": wins,
        "failures": failures,
        "neutral": neutrals,
        "win_rate": win_rate,
        "failure_rate": failure_rate,
        "win_lift": (win_rate / base_win) if win_rate is not None and base_win not in (None, 0) else None,
        "failure_lift": (failure_rate / base_fail) if failure_rate is not None and base_fail not in (None, 0) else None,
        "win_rate_wilson_95_low": low,
        "win_rate_wilson_95_high": high,
        "mean_return_pct": (sum(returns) / len(returns)) if returns else None,
        "median_return_pct": median(returns) if returns else None,
    }


def _candidate_patterns(rows: list[dict], min_support: int) -> list[tuple[str, ...]]:
    support: dict[tuple[str, ...], int] = {}
    for row in rows:
        features = sorted(row["features"])
        for feature in features:
            key = (feature,)
            support[key] = support.get(key, 0) + 1
        for pair in itertools.combinations(features, 2):
            support[pair] = support.get(pair, 0) + 1
    candidates = [pattern for pattern, count in support.items() if count >= min_support]
    candidates.sort(key=lambda pattern: (-support[pattern], len(pattern), pattern))
    return candidates


def _discovery(rows: list[dict], max_patterns: int = MAX_DISCOVERY_PATTERNS) -> list[dict]:
    if not rows:
        return []
    baseline = _baseline(rows)
    min_support = max(MIN_DISCOVERY_SUPPORT, math.ceil(len(rows) * 0.05))
    patterns = _candidate_patterns(rows, min_support)
    metrics = [_pattern_metrics(pattern, rows, baseline) for pattern in patterns]
    metrics = [m for m in metrics if m["support"] < len(rows)]
    metrics.sort(
        key=lambda m: (
            -max(abs((m.get("win_lift") or 1.0) - 1.0), abs((m.get("failure_lift") or 1.0) - 1.0)),
            -m["support"],
            tuple(m["features"]),
        )
    )
    return metrics[:max_patterns]


def _direction(metric: dict) -> str:
    win_lift = metric.get("win_lift")
    failure_lift = metric.get("failure_lift")
    win_delta = abs((win_lift or 1.0) - 1.0)
    fail_delta = abs((failure_lift or 1.0) - 1.0)
    if win_delta >= fail_delta:
        if win_lift is None:
            return "UNRESOLVED"
        return "WIN_ENRICHED" if win_lift > 1.0 else "WIN_DEPLETED"
    if failure_lift is None:
        return "UNRESOLVED"
    return "FAILURE_ENRICHED" if failure_lift > 1.0 else "FAILURE_DEPLETED"


def _window_metrics(pattern: tuple[str, ...], rows: list[dict]) -> dict:
    baseline = _baseline(rows)
    metric = _pattern_metrics(pattern, rows, baseline)
    metric["baseline"] = baseline
    metric["direction"] = _direction(metric)
    return metric


def _walk_forward(rows: list[dict]) -> dict:
    n = len(rows)
    if n < MIN_TERMINAL_RECORDS_FOR_REVIEW:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "records": n,
            "minimum_records": MIN_TERMINAL_RECORDS_FOR_REVIEW,
            "validation_windows": [],
            "stable_patterns": [],
        }

    train_end = max(MIN_VALIDATION_WINDOW, int(n * 0.60))
    remaining = n - train_end
    if remaining < 2 * MIN_VALIDATION_WINDOW:
        train_end = n - 2 * MIN_VALIDATION_WINDOW
    val1_end = train_end + (n - train_end) // 2

    train = rows[:train_end]
    val1 = rows[train_end:val1_end]
    val2 = rows[val1_end:]
    if len(train) < MIN_DISCOVERY_SUPPORT or len(val1) < MIN_VALIDATION_WINDOW or len(val2) < MIN_VALIDATION_WINDOW:
        return {
            "status": "INSUFFICIENT_WINDOWS",
            "records": n,
            "minimum_records": MIN_TERMINAL_RECORDS_FOR_REVIEW,
            "validation_windows": [],
            "stable_patterns": [],
        }

    discovered = _discovery(train)
    stable: list[dict] = []
    for candidate in discovered:
        pattern = tuple(candidate["features"])
        train_metric = _window_metrics(pattern, train)
        v1 = _window_metrics(pattern, val1)
        v2 = _window_metrics(pattern, val2)
        directions = [train_metric["direction"], v1["direction"], v2["direction"]]
        sufficient_support = all(m["support"] >= 2 for m in (v1, v2))
        stable_direction = directions[0] != "UNRESOLVED" and directions.count(directions[0]) == 3
        if not (sufficient_support and stable_direction):
            continue
        stable.append(
            {
                "features": list(pattern),
                "direction": directions[0],
                "train": train_metric,
                "validation_1": v1,
                "validation_2": v2,
            }
        )

    stable.sort(
        key=lambda item: (
            -min(item["validation_1"]["support"], item["validation_2"]["support"]),
            tuple(item["features"]),
        )
    )
    return {
        "status": "VALIDATED" if stable else "NO_STABLE_PATTERN_YET",
        "records": n,
        "train_records": len(train),
        "validation_windows": [
            {
                "name": "validation_1",
                "records": len(val1),
                "start_at": val1[0]["first_decision_at"],
                "end_at": val1[-1]["first_decision_at"],
            },
            {
                "name": "validation_2",
                "records": len(val2),
                "start_at": val2[0]["first_decision_at"],
                "end_at": val2[-1]["first_decision_at"],
            },
        ],
        "stable_patterns": stable[:MAX_REPORTED_PATTERNS],
    }


def _cohort_report(replay: dict, horizon: str) -> dict:
    rows = _rows(replay, horizon)
    baseline = _baseline(rows)
    discovery = _discovery(rows)[:MAX_REPORTED_PATTERNS]
    walk_forward = _walk_forward(rows)
    return {
        "horizon": horizon,
        "baseline": baseline,
        "discovery_patterns": discovery,
        "walk_forward": walk_forward,
        "label_contract": {
            "winner": f"friction_adjusted_return_pct >= {WIN_RETURN_PCT}",
            "failure": f"friction_adjusted_return_pct <= {FAIL_RETURN_PCT} OR observed_drawdown_pct <= {FAIL_DRAWDOWN_PCT}",
            "neutral": "otherwise",
            "near_miss": "T0 actionable=false AND outcome=WIN",
        },
    }


def build(replay: dict) -> dict:
    report_24h = _cohort_report(replay, "24h")
    report_7d = _cohort_report(replay, "7d")
    terminal_walk = report_7d["walk_forward"]
    stable = terminal_walk.get("stable_patterns") or []
    terminal_records = report_7d["baseline"]["records"]
    ready = terminal_records >= MIN_TERMINAL_RECORDS_FOR_REVIEW and len(terminal_walk.get("validation_windows") or []) >= 2 and bool(stable)
    return {
        "version": 1,
        "mode": MODE,
        "research_only": True,
        "production_effect": False,
        "production_thresholds_modified": False,
        "source_replay": REPLAY,
        "feature_contract": "T0_ONLY_NO_FUTURE_FEATURES",
        "pattern_contract": "UNIVARIATE_AND_PAIRWISE_T0_INTERACTIONS",
        "cohorts": {
            "24h_exploratory": report_24h,
            "7d_terminal": report_7d,
        },
        "promotion_gate": {
            "status": "READY_FOR_RESEARCH_REVIEW" if ready else "NOT_READY_FOR_RESEARCH_REVIEW",
            "minimum_terminal_records": MIN_TERMINAL_RECORDS_FOR_REVIEW,
            "terminal_records": terminal_records,
            "minimum_non_overlapping_validation_windows": 2,
            "validation_windows": len(terminal_walk.get("validation_windows") or []),
            "stable_terminal_patterns": len(stable),
            "automatic_production_promotion": False,
            "requires_manual_review": True,
        },
        "guardrails": {
            "t0_features_only": True,
            "future_outcomes_used_as_labels_only": True,
            "chronological_walk_forward": True,
            "non_overlapping_validation_windows": True,
            "no_automatic_buy": True,
            "no_production_threshold_change": True,
            "no_telegram_change": True,
        },
    }


def main() -> None:
    replay = _load(DATA / REPLAY, {})
    report = build(replay)
    (DATA / OUTPUT).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "HISTORICAL_PATTERN_MINING_OK",
        {
            "24h": report["cohorts"]["24h_exploratory"]["baseline"],
            "7d": report["cohorts"]["7d_terminal"]["baseline"],
            "gate": report["promotion_gate"],
        },
    )


if __name__ == "__main__":
    main()
