from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

DATA = Path("data")
NEAR = DATA / "near-alert-observatory.json"
LEDGER = DATA / "research-sample-ledger.json"
OUT = DATA / "decision-only-shadow.json"
MODE = "RESEARCH_ONLY_DECISION_ONLY_6OF7_SHADOW_V1"
MIN_EXECUTION_LIQUIDITY_USD = 50_000.0
MIN_SOURCE_LANES = 2
WINNER_PCT = 20.0
BIG_WINNER_PCT = 100.0
LOSER_PCT = -20.0
HORIZONS = ("1h", "6h", "24h", "7d")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _entry(rec: dict[str, Any]) -> dict[str, Any]:
    snap = rec.get("decision_snapshot") if isinstance(rec.get("decision_snapshot"), dict) else {}
    value = snap.get("entry") if isinstance(snap.get("entry"), dict) else {}
    return value


def _decision_only_entry(entry: dict[str, Any]) -> bool:
    missing = [str(x) for x in (entry.get("missing_gates") or []) if x]
    blockers = {str(x) for x in (entry.get("blockers") or []) if x}
    return bool(
        int(entry.get("readiness_passed") or 0) == 6
        and int(entry.get("readiness_total") or 7) == 7
        and missing == ["STRONG_DECISION_LANE"]
        and blockers == {"NO_STRONG_DECISION_LANE"}
        and entry.get("verified_execution_tradable") is True
        and _num(entry.get("verified_execution_liquidity_usd")) >= MIN_EXECUTION_LIQUIDITY_USD
        and int(entry.get("source_lane_count") or 0) >= MIN_SOURCE_LANES
    )


def _current_candidate(row: dict[str, Any]) -> bool:
    missing = [str(x) for x in (row.get("missing_gates") or []) if x]
    blockers = {str(x) for x in (row.get("blockers") or []) if x}
    return bool(
        int(row.get("readiness_passed") or 0) == 6
        and int(row.get("readiness_total") or 7) == 7
        and missing == ["STRONG_DECISION_LANE"]
        and blockers == {"NO_STRONG_DECISION_LANE"}
        and row.get("exact_identity_verified") is True
        and row.get("exact_pair_verified") is True
        and row.get("market_age_verified") is True
        and row.get("market_activity_verified") is True
        and _num(row.get("execution_pool_liquidity_usd")) >= MIN_EXECUTION_LIQUIDITY_USD
        and int(row.get("source_lane_count") or 0) >= MIN_SOURCE_LANES
    )


def _metrics(records: list[dict[str, Any]], horizon: str) -> dict[str, Any]:
    vals: list[float] = []
    classes: Counter[str] = Counter()
    for rec in records:
        cp = (rec.get("checkpoints") or {}).get(horizon)
        if not isinstance(cp, dict) or cp.get("friction_adjusted_return_pct") is None:
            continue
        value = _num(cp.get("friction_adjusted_return_pct"))
        vals.append(value)
        if value >= BIG_WINNER_PCT:
            classes["BIG_WINNER"] += 1
        elif value >= WINNER_PCT:
            classes["WINNER"] += 1
        elif value <= LOSER_PCT:
            classes["LOSER"] += 1
        else:
            classes["NEUTRAL"] += 1
    n = len(vals)
    return {
        "n": n,
        "mean_friction_adjusted_return_pct": round(mean(vals), 6) if vals else None,
        "median_friction_adjusted_return_pct": round(median(vals), 6) if vals else None,
        "winner_count": sum(v >= WINNER_PCT for v in vals),
        "winner_rate_pct": round(sum(v >= WINNER_PCT for v in vals) / n * 100.0, 4) if n else None,
        "big_winner_count": sum(v >= BIG_WINNER_PCT for v in vals),
        "loser_count": sum(v <= LOSER_PCT for v in vals),
        "loser_rate_pct": round(sum(v <= LOSER_PCT for v in vals) / n * 100.0, 4) if n else None,
        "class_counts": dict(classes),
    }


def build(near: dict[str, Any], ledger: dict[str, Any], observed_at: str | None = None) -> dict[str, Any]:
    now = observed_at or datetime.now(timezone.utc).isoformat()
    records = [
        rec for rec in (ledger.get("records") or {}).values()
        if isinstance(rec, dict) and _decision_only_entry(_entry(rec))
    ] if isinstance(ledger, dict) else []

    rows = near.get("near_alert_leaderboard") if isinstance(near, dict) else []
    current = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not _current_candidate(row):
            continue
        current.append({
            "symbol": row.get("symbol"),
            "chain": row.get("chain"),
            "token_address": row.get("token_address"),
            "pair_address": row.get("pair_address"),
            "readiness": "6/7",
            "missing_gate": "STRONG_DECISION_LANE",
            "blockers": ["NO_STRONG_DECISION_LANE"],
            "source_lane_count": int(row.get("source_lane_count") or 0),
            "evidence_positive_count": int(row.get("evidence_positive_count") or 0),
            "evidence_positive_lanes": list(row.get("evidence_positive_lanes") or []),
            "execution_pool_liquidity_usd": round(_num(row.get("execution_pool_liquidity_usd")), 2),
            "signal_score": row.get("signal_score"),
            "dex_volume_h1": row.get("dex_volume_h1"),
            "turnover_h1": row.get("turnover_h1"),
            "watch_added_at": row.get("watch_added_at"),
            "research_state": "SHADOW_TEST_ACTIVE",
            "production_effect": False,
            "automatic_promotion": False,
            "automatic_buy": False,
        })

    horizons = {label: _metrics(records, label) for label in HORIZONS}
    h24 = horizons["24h"]
    mature24 = int(h24.get("n") or 0)
    winner_rate = h24.get("winner_rate_pct")
    loser_rate = h24.get("loser_rate_pct")
    evidence_stage = "COLLECTING"
    if mature24 >= 10:
        evidence_stage = "USABLE_SHADOW_SAMPLE"
    if mature24 >= 30:
        evidence_stage = "STRONG_SHADOW_SAMPLE"

    review_signal = bool(
        mature24 >= 10
        and winner_rate is not None and winner_rate >= 10.0
        and loser_rate is not None and loser_rate <= 10.0
    )

    return {
        "version": 1,
        "mode": MODE,
        "generated_at": now,
        "production_change_allowed": False,
        "production_thresholds_modified": False,
        "automatic_promotion": False,
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "exact_identity_required": True,
            "exact_pair_required": True,
            "market_age_verified_required": True,
            "market_activity_verified_required_for_current_candidates": True,
            "minimum_execution_liquidity_usd": MIN_EXECUTION_LIQUIDITY_USD,
            "minimum_source_lanes": MIN_SOURCE_LANES,
            "only_missing_gate": "STRONG_DECISION_LANE",
            "only_allowed_blocker": "NO_STRONG_DECISION_LANE",
            "forward_only_outcomes": True,
            "friction_adjusted_outcomes": True,
            "real_alert_gate_unchanged": True,
        },
        "current_shadow_candidates": current,
        "current_shadow_candidate_count": len(current),
        "historical_decision_only_records": len(records),
        "horizons": horizons,
        "evidence_stage": evidence_stage,
        "research_review_signal": review_signal,
        "research_review_reason": (
            "Decision-only 6/7 cohort has enough 24h forward evidence for human review in shadow."
            if review_signal else
            "Keep collecting forward outcomes; no production threshold change is justified yet."
        ),
        "next_discussion": "Compare decision-only 6/7 lift and downside against current REAL_ALERT and broader verified-watch cohorts before considering any production tuning.",
    }


def run(data_dir: str | Path = DATA, observed_at: str | None = None) -> dict[str, Any]:
    data = Path(data_dir)
    payload = build(
        _load(data / NEAR.name, {}),
        _load(data / LEDGER.name, {}),
        observed_at=observed_at,
    )
    _write(data / OUT.name, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
