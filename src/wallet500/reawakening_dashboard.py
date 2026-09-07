"""Compact dashboard feed for False-Negative Recovery V2.

This module is presentation-only research plumbing. It reads the immutable
Reawakening V2 state and emits a small JSON payload suitable for the phone-first
dashboard. It never changes production gates, portfolio state, or BUY decisions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .reawakening_shadow import (
    MIN_CONFIRMATION_SPAN_MINUTES,
    MIN_LIQUIDITY_RETENTION,
    MIN_LIQUIDITY_USD,
    MIN_MARKET_AGE_DAYS,
    REQUIRED_CONSECUTIVE,
    observation_passes,
)

MODE = "RESEARCH_ONLY_REAWAKENING_DASHBOARD_V1"
OUTPUT_FILE = "reawakening-dashboard.json"
MAX_NEAR = 12


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _same_pair(chain: str, left: Any, right: Any) -> bool:
    left = str(left or "")
    right = str(right or "")
    if not left or not right:
        return False
    if str(chain).lower() in {"ethereum", "eth", "bsc", "bnb"}:
        return left.lower() == right.lower()
    return left == right


def _symbol(record: dict, token: str) -> str:
    snap = record.get("first_reject_snapshot")
    if not isinstance(snap, dict):
        snap = {}
    for key in ("symbol", "token_symbol", "base_symbol"):
        value = snap.get(key) or record.get(key)
        if value:
            return str(value)
    token = str(token or "")
    return token[:8] + ("…" if len(token) > 8 else "") if token else "TOKEN"


def _current_streak(
    observations: list[dict],
    reject_price: float,
    *,
    chain: str,
    expected_pair: str,
) -> tuple[int, float, dict, list[str]]:
    ordered = sorted(
        [row for row in observations if isinstance(row, dict)],
        key=lambda row: str(row.get("observed_at") or ""),
    )
    streak: list[tuple[dict, dict, list[str]]] = []
    for row in ordered:
        if not _same_pair(chain, row.get("pair_address"), expected_pair):
            streak = []
            continue
        passed, reasons, metrics = observation_passes(row, reject_price)
        if not passed:
            streak = []
            continue
        if streak:
            previous = streak[-1][0]
            if _f(row.get("price_usd")) < _f(previous.get("price_usd")):
                streak = []
            elif _f(row.get("liquidity_usd")) < _f(previous.get("liquidity_usd")) * MIN_LIQUIDITY_RETENTION:
                streak = []
        streak.append((row, metrics, reasons))

    if not streak:
        return 0, 0.0, {}, []
    first_at = _dt(streak[0][0].get("observed_at"))
    last_at = _dt(streak[-1][0].get("observed_at"))
    span = 0.0
    if first_at is not None and last_at is not None:
        span = max(0.0, (last_at - first_at).total_seconds() / 60.0)
    return len(streak), round(span, 2), streak[-1][1], streak[-1][2]


def build(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    shadow = _load(out / "reawakening-shadow.json", {})
    report = _load(out / "reawakening-forward-report.json", {})
    forward = _load(out / "reawakening-forward-state.json", {})
    ledger = _load(out / "rejected-candidate-ledger.json", {})

    shadow_counts = shadow.get("counts") if isinstance(shadow.get("counts"), dict) else {}
    candidates = forward.get("candidates") if isinstance(forward.get("candidates"), dict) else {}
    records = ledger.get("records") if isinstance(ledger.get("records"), dict) else {}
    raw_targets = shadow.get("targets") if isinstance(shadow.get("targets"), list) else []

    trigger_keys = {
        str(row.get("token_key") or "")
        for row in raw_targets
        if isinstance(row, dict) and row.get("token_key")
    }

    near_rows: list[dict] = []
    for key, candidate in candidates.items():
        if key in trigger_keys or not isinstance(candidate, dict):
            continue
        observations = candidate.get("hot_observations")
        if not isinstance(observations, list) or not observations:
            continue
        record = records.get(key)
        if not isinstance(record, dict):
            continue
        snap = record.get("first_reject_snapshot") if isinstance(record.get("first_reject_snapshot"), dict) else {}
        reject_price = _f(snap.get("price_usd"))
        if reject_price <= 0:
            continue

        ordered = sorted(
            [row for row in observations if isinstance(row, dict)],
            key=lambda row: str(row.get("observed_at") or ""),
        )
        if not ordered:
            continue
        latest = ordered[-1]
        passed_snapshot, reasons, metrics = observation_passes(latest, reject_price)
        chain = str(candidate.get("chain") or "")
        pair = str(candidate.get("pair_address") or "")
        streak_count, streak_span, streak_metrics, streak_reasons = _current_streak(
            ordered,
            reject_price,
            chain=chain,
            expected_pair=pair,
        )
        if streak_metrics:
            metrics = streak_metrics
            reasons = streak_reasons
            passed_snapshot = len(reasons) >= 6

        gate_passed = len(reasons)
        activity_passed = int(metrics.get("activity_checks_passed") or 0)
        activity_available = int(metrics.get("activity_checks_available") or 0)

        # Near-recovery is a positive recovery surface, not a list of every historical reject.
        # Fail closed on market age, current liquidity and actual returning activity.
        market_age_verified = snap.get("market_age_verified") is True or record.get("market_age_verified") is True
        market_age_days = _f(snap.get("market_age_min_days") or record.get("market_age_min_days"))
        liquidity_recovered_for_watch = _f(metrics.get("liquidity_usd")) >= MIN_LIQUIDITY_USD
        activity_returning = activity_passed >= 1
        if (
            not market_age_verified
            or market_age_days < MIN_MARKET_AGE_DAYS
            or not liquidity_recovered_for_watch
            or not activity_returning
        ):
            continue

        waiting_confirmation = (
            passed_snapshot
            and (
                streak_count < REQUIRED_CONSECUTIVE
                or streak_span < MIN_CONFIRMATION_SPAN_MINUTES
            )
        )
        near_rows.append(
            {
                "token_key": key,
                "symbol": _symbol(record, str(candidate.get("token") or "")),
                "chain": chain,
                "token_address": candidate.get("token"),
                "pair_address": pair,
                "observed_at": latest.get("observed_at"),
                "first_rejected_at": candidate.get("first_rejected_at"),
                "status": (
                    "SNAPSHOT_READY_WAITING_CONFIRMATION"
                    if waiting_confirmation
                    else "APPROACHING_RECOVERY"
                ),
                "snapshot_gates_passed": gate_passed,
                "snapshot_gates_total": 6,
                "confirmation_streak": streak_count,
                "confirmation_required": REQUIRED_CONSECUTIVE,
                "confirmation_span_minutes": streak_span,
                "confirmation_span_required_minutes": MIN_CONFIRMATION_SPAN_MINUTES,
                "metrics": metrics,
                "passed_reasons": reasons,
                "research_only": True,
            }
        )

    near_rows.sort(
        key=lambda row: (
            int(row.get("snapshot_gates_passed") or 0),
            int((row.get("metrics") or {}).get("activity_checks_passed") or 0),
            int(row.get("confirmation_streak") or 0),
            str(row.get("observed_at") or ""),
        ),
        reverse=True,
    )
    near_rows = near_rows[:MAX_NEAR]

    triggers: list[dict] = []
    for target in raw_targets:
        if not isinstance(target, dict):
            continue
        key = str(target.get("token_key") or "")
        record = records.get(key) if isinstance(records.get(key), dict) else {}
        token = str(target.get("token") or "")
        triggers.append(
            {
                **target,
                "symbol": _symbol(record, token),
                "token_address": token,
                "special_marker": "🔥 REAWAKENED",
                "research_only": True,
            }
        )

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 1,
        "mode": MODE,
        "generated_at": now,
        "source_generated_at": shadow.get("generated_at") or report.get("updated_at"),
        "production_portfolio_impact": "NONE",
        "production_gate_changed": False,
        "automatic_buy": False,
        "research_only": True,
        "counts": {
            "tracked_eligible": int(
                shadow_counts.get("eligible_liquidity_only_rejects")
                or report.get("eligible_rejects")
                or 0
            ),
            "forward_observations": int(
                shadow_counts.get("dedicated_forward_hot_rows")
                or report.get("state_hot_observations")
                or 0
            ),
            "exact_pair_successes_this_run": int(
                shadow_counts.get("dedicated_forward_exact_pair_successes_this_run")
                or report.get("exact_pair_successes")
                or 0
            ),
            "exact_pair_misses_this_run": int(
                shadow_counts.get("dedicated_forward_exact_pair_misses_this_run")
                or report.get("exact_pair_misses")
                or 0
            ),
            "observations_added_this_run": int(
                shadow_counts.get("dedicated_forward_observations_added_this_run")
                or report.get("observations_added_this_run")
                or 0
            ),
            "reawakening_triggers": len(triggers),
            "near_recovery_shown": len(near_rows),
        },
        "rule": {
            "liquidity_floor_usd": 15000,
            "exact_pair_locked": True,
            "confirmation_observations": REQUIRED_CONSECUTIVE,
            "confirmation_span_minutes": MIN_CONFIRMATION_SPAN_MINUTES,
            "marker_meaning": "All Reawakening V2 forward truth gates passed; research-only, not a BUY order.",
        },
        "triggers": triggers,
        "near_recovery": near_rows,
    }
    _write(out / OUTPUT_FILE, payload)
    return payload


if __name__ == "__main__":
    result = build()
    print(json.dumps({"mode": result.get("mode"), "counts": result.get("counts")}, ensure_ascii=False, indent=2))
