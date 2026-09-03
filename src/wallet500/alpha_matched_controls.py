from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

DATA = Path("data")
ALPHA_LEDGER = DATA / "alpha-proof-ledger.json"
STATE_PATH = DATA / "alpha-matched-control-state.json"
REPORT_PATH = DATA / "alpha-matched-controls.json"
MODE = "ALPHA_MATCHED_CONTROLS_DIAGNOSTIC_V1"
MAX_CONTROL_LAG_MINUTES = 180.0
MAX_LIQUIDITY_RATIO = 4.0


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dt(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _candidate_score(signal: dict[str, Any], control: dict[str, Any]) -> tuple[float, dict[str, Any]] | None:
    if str(signal.get("chain") or "").lower() != str(control.get("chain") or "").lower():
        return None
    se = _dt(signal.get("event_at"))
    ce = _dt(control.get("event_at"))
    sen = _dt(signal.get("enrolled_at"))
    cen = _dt(control.get("enrolled_at"))
    if se is None or ce is None or ce > se:
        return None
    # A control discovered only after the signal was enrolled is never back-filled.
    if sen is not None and cen is not None and cen > sen:
        return None
    lag = (se - ce).total_seconds() / 60.0
    if lag < 0 or lag > MAX_CONTROL_LAG_MINUTES:
        return None
    sl = _num(signal.get("entry_liquidity_usd"))
    cl = _num(control.get("entry_liquidity_usd"))
    if sl is None or cl is None or sl <= 0 or cl <= 0:
        return None
    ratio = max(sl, cl) / min(sl, cl)
    if ratio > MAX_LIQUIDITY_RATIO:
        return None
    liquidity_distance = abs(math.log(sl / cl))
    score = liquidity_distance + lag / MAX_CONTROL_LAG_MINUTES
    detail = {
        "same_chain": True,
        "control_precedes_or_equals_signal": True,
        "control_available_by_signal_enrollment": True,
        "event_lag_minutes": round(lag, 3),
        "signal_liquidity_usd": sl,
        "control_liquidity_usd": cl,
        "liquidity_ratio": round(ratio, 6),
        "match_score": round(score, 8),
    }
    return score, detail


def _assign_new_matches(state: dict[str, Any], signals: dict[str, Any], controls: dict[str, Any], now: datetime) -> None:
    matches = state.setdefault("matches", {})
    used_controls = {
        str(v.get("control_record_id"))
        for v in matches.values()
        if isinstance(v, dict) and v.get("status") == "MATCHED" and v.get("control_record_id")
    }
    ordered_signals = sorted(
        ((sid, s) for sid, s in signals.items() if isinstance(s, dict)),
        key=lambda item: (str(item[1].get("event_at") or ""), item[0]),
    )
    for signal_id, signal in ordered_signals:
        if signal_id in matches:
            continue
        candidates: list[tuple[float, str, dict[str, Any]]] = []
        for control_id, control in controls.items():
            if control_id in used_controls or not isinstance(control, dict):
                continue
            scored = _candidate_score(signal, control)
            if scored is None:
                continue
            score, detail = scored
            candidates.append((score, control_id, detail))
        if not candidates:
            matches[signal_id] = {
                "status": "NO_MATCH_AT_FIRST_EVALUATION",
                "signal_record_id": signal_id,
                "evaluated_at": now.isoformat(),
                "reason": "NO_SAME_CHAIN_PREEXISTING_CONTROL_WITHIN_TIME_AND_LIQUIDITY_BOUNDS",
            }
            continue
        candidates.sort(key=lambda x: (x[0], x[1]))
        _, control_id, detail = candidates[0]
        used_controls.add(control_id)
        matches[signal_id] = {
            "status": "MATCHED",
            "signal_record_id": signal_id,
            "control_record_id": control_id,
            "matched_at": now.isoformat(),
            "match_basis": detail,
        }


def _checkpoint_delta(signal: dict[str, Any], control: dict[str, Any], horizon: str) -> dict[str, Any] | None:
    scp = (signal.get("checkpoints") or {}).get(horizon)
    ccp = (control.get("checkpoints") or {}).get(horizon)
    if not isinstance(scp, dict) or not isinstance(ccp, dict):
        return None
    sg = _num(scp.get("gross_return_pct"))
    cg = _num(ccp.get("gross_return_pct"))
    sf = _num(scp.get("friction_adjusted_return_pct"))
    cf = _num(ccp.get("friction_adjusted_return_pct"))
    if sg is None or cg is None:
        return None
    return {
        "signal_gross_return_pct": sg,
        "control_gross_return_pct": cg,
        "matched_alpha_gross_pct": round(sg - cg, 6),
        "signal_friction_adjusted_return_pct": sf,
        "control_friction_adjusted_return_pct": cf,
        "matched_alpha_friction_adjusted_pct": round(sf - cf, 6) if sf is not None and cf is not None else None,
    }


def _summarize_horizon(rows: list[dict[str, Any]], horizon: str) -> dict[str, Any]:
    vals = []
    friction_vals = []
    for row in rows:
        delta = (row.get("horizons") or {}).get(horizon)
        if not isinstance(delta, dict):
            continue
        g = _num(delta.get("matched_alpha_gross_pct"))
        f = _num(delta.get("matched_alpha_friction_adjusted_pct"))
        if g is not None:
            vals.append(g)
        if f is not None:
            friction_vals.append(f)
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean_matched_alpha_gross_pct": round(mean(vals), 6),
        "median_matched_alpha_gross_pct": round(median(vals), 6),
        "positive_matched_alpha_rate_pct": round(sum(v > 0 for v in vals) / len(vals) * 100.0, 4),
        "mean_matched_alpha_friction_adjusted_pct": round(mean(friction_vals), 6) if friction_vals else None,
    }


def run(data_dir: str | Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    reference = now or datetime.now(timezone.utc)
    alpha = _load(data_dir / ALPHA_LEDGER.name, {})
    signals = alpha.get("signals") if isinstance(alpha, dict) and isinstance(alpha.get("signals"), dict) else {}
    controls = alpha.get("controls") if isinstance(alpha, dict) and isinstance(alpha.get("controls"), dict) else {}
    state_path = data_dir / STATE_PATH.name
    report_path = data_dir / REPORT_PATH.name
    state = _load(state_path, {})
    if not isinstance(state, dict) or state.get("mode") != MODE:
        state = {"version": 1, "mode": MODE, "created_at": reference.isoformat(), "matches": {}}

    _assign_new_matches(state, signals, controls, reference)
    state["updated_at"] = reference.isoformat()

    rows: list[dict[str, Any]] = []
    matched_count = 0
    for signal_id, signal in signals.items():
        if not isinstance(signal, dict):
            continue
        match = state.get("matches", {}).get(signal_id) or {}
        row = {
            "signal_record_id": signal_id,
            "lane": signal.get("lane"),
            "chain": signal.get("chain"),
            "token": signal.get("token"),
            "pair_address": signal.get("pair_address"),
            "event_at": signal.get("event_at"),
            "match_status": match.get("status") or "NOT_EVALUATED",
            "control_record_id": match.get("control_record_id"),
            "match_basis": match.get("match_basis"),
            "horizons": {},
        }
        control = controls.get(match.get("control_record_id")) if match.get("status") == "MATCHED" else None
        if isinstance(control, dict):
            matched_count += 1
            for horizon in ("5m", "15m", "1h", "6h", "24h", "7d"):
                delta = _checkpoint_delta(signal, control, horizon)
                if delta is not None:
                    row["horizons"][horizon] = delta
        rows.append(row)

    lanes = sorted({str(r.get("lane")) for r in rows if r.get("lane")})
    lane_reports = {}
    for lane in lanes:
        cohort = [r for r in rows if r.get("lane") == lane]
        lane_reports[lane] = {
            "signals": len(cohort),
            "matched": sum(r.get("match_status") == "MATCHED" for r in cohort),
            "unmatched": sum(r.get("match_status") != "MATCHED" for r in cohort),
            "horizons": {h: _summarize_horizon(cohort, h) for h in ("5m", "15m", "1h", "6h", "24h", "7d")},
        }

    report = {
        "version": 1,
        "mode": MODE,
        "updated_at": reference.isoformat(),
        "source_mode": alpha.get("mode") if isinstance(alpha, dict) else None,
        "formal_signal_count_unchanged": len(signals),
        "formal_control_pool_count_unchanged": len(controls),
        "matched_signal_count": matched_count,
        "unmatched_signal_count": max(0, len(signals) - matched_count),
        "safety_contract": {
            "secondary_diagnostic_only": True,
            "changes_signal_enrollment": False,
            "changes_candidate_qualification": False,
            "changes_production_gate": False,
            "can_block_or_drop_signal": False,
            "unmatched_signal_remains_in_primary_alpha_proof": True,
            "matched_result_changes_primary_proof_status": False,
        },
        "matching_policy": {
            "same_chain_required": True,
            "control_must_exist_no_later_than_signal_enrollment": True,
            "control_event_must_precede_or_equal_signal_event": True,
            "max_event_lag_minutes": MAX_CONTROL_LAG_MINUTES,
            "max_entry_liquidity_ratio": MAX_LIQUIDITY_RATIO,
            "one_control_per_signal": True,
            "control_reuse": False,
            "first_match_is_immutable": True,
            "no_match_is_frozen_at_first_evaluation": True,
        },
        "lanes": lane_reports,
        "rows": rows,
        "interpretation": "Matched controls are a harder secondary alpha diagnostic only. They never remove, downgrade, delay, or block a Wallet500 candidate or formal signal.",
    }
    _write(state_path, state)
    _write(report_path, report)
    print(json.dumps({
        "mode": MODE,
        "signals": len(signals),
        "matched": matched_count,
        "unmatched": max(0, len(signals) - matched_count),
        "production_impact": "NONE",
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
