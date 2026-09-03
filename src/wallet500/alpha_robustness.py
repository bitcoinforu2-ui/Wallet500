from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

DATA = Path("data")
ALPHA_LEDGER = DATA / "alpha-proof-ledger.json"
MATCHED_REPORT = DATA / "alpha-matched-controls.json"
REPORT_PATH = DATA / "alpha-robustness-audit.json"
MODE = "ALPHA_ROBUSTNESS_AUDIT_V1"
HORIZONS = {"5m": 5, "15m": 15, "1h": 60, "6h": 360, "24h": 1440, "7d": 10080}


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


def _checkpoint_value(row: dict[str, Any], horizon: str) -> float | None:
    cp = (row.get("checkpoints") or {}).get(horizon)
    return _num(cp.get("friction_adjusted_return_pct")) if isinstance(cp, dict) else None


def _matured(rows: list[dict[str, Any]], horizon: str, now: datetime) -> list[dict[str, Any]]:
    minutes = HORIZONS[horizon]
    out = []
    for row in rows:
        event = _dt(row.get("event_at"))
        if event is None:
            continue
        age = (now - event).total_seconds() / 60.0
        if age >= minutes:
            out.append(row)
    return out


def _coverage(rows: list[dict[str, Any]], horizon: str, now: datetime) -> dict[str, Any]:
    mature = _matured(rows, horizon, now)
    values = [v for r in mature if (v := _checkpoint_value(r, horizon)) is not None]
    return {
        "matured_expected": len(mature),
        "checkpoint_n": len(values),
        "coverage_pct": round(len(values) / len(mature) * 100.0, 4) if mature else None,
        "values": values,
    }


def _leave_one_out_alpha(signal: list[float], control: list[float]) -> dict[str, Any] | None:
    if len(signal) < 2 or len(control) < 2:
        return None
    vals: list[float] = []
    for i in range(len(signal)):
        s = signal[:i] + signal[i + 1 :]
        vals.append(mean(s) - mean(control))
    for i in range(len(control)):
        c = control[:i] + control[i + 1 :]
        vals.append(mean(signal) - mean(c))
    return {
        "worst_case_alpha_pct": round(min(vals), 6),
        "best_case_alpha_pct": round(max(vals), 6),
        "all_single_deletions_positive": min(vals) > 0,
        "deletions_tested": len(vals),
    }


def _summary(signal_rows: list[dict[str, Any]], control_rows: list[dict[str, Any]], horizon: str, now: datetime) -> dict[str, Any]:
    s = _coverage(signal_rows, horizon, now)
    c = _coverage(control_rows, horizon, now)
    sv = s.pop("values")
    cv = c.pop("values")
    out: dict[str, Any] = {"signal": s, "control": c}
    if sv:
        out["signal_mean_pct"] = round(mean(sv), 6)
        out["signal_median_pct"] = round(median(sv), 6)
    if cv:
        out["control_mean_pct"] = round(mean(cv), 6)
        out["control_median_pct"] = round(median(cv), 6)
    if sv and cv:
        out["mean_alpha_pct"] = round(mean(sv) - mean(cv), 6)
        out["median_alpha_pct"] = round(median(sv) - median(cv), 6)
        out["leave_one_out"] = _leave_one_out_alpha(sv, cv)
        if len(sv) >= 3:
            best = max(sv)
            without_best = [x for x in sv if x is not best]
            # Remove one occurrence only, deterministically.
            tmp = list(sv)
            tmp.remove(best)
            out["alpha_without_best_signal_pct"] = round(mean(tmp) - mean(cv), 6) if tmp else None
    return out


def _matched_context(payload: Any, lane: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"available": False}
    lanes = payload.get("lanes") if isinstance(payload.get("lanes"), dict) else {}
    data = lanes.get(lane) if isinstance(lanes.get(lane), dict) else None
    if not data:
        return {"available": False}
    h24 = ((data.get("horizons") or {}).get("24h") or {}) if isinstance(data.get("horizons"), dict) else {}
    h7 = ((data.get("horizons") or {}).get("7d") or {}) if isinstance(data.get("horizons"), dict) else {}
    return {
        "available": True,
        "matched": data.get("matched"),
        "unmatched": data.get("unmatched"),
        "matched_24h": h24,
        "matched_7d": h7,
    }


def _robustness_status(h24: dict[str, Any], h7: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    s24 = h24.get("signal") or {}
    c24 = h24.get("control") or {}
    if int(s24.get("matured_expected") or 0) < 20 or int(c24.get("matured_expected") or 0) < 20:
        return "COLLECTING_FORWARD_SAMPLE", ["NEED_20_MATURED_SIGNAL_AND_CONTROL_AT_24H"]
    if float(s24.get("coverage_pct") or 0) < 90 or float(c24.get("coverage_pct") or 0) < 90:
        reasons.append("CHECKPOINT_COVERAGE_BELOW_90_PCT")
    if (h24.get("mean_alpha_pct") or 0) <= 0:
        reasons.append("MEAN_ALPHA_24H_NOT_POSITIVE")
    if (h24.get("median_alpha_pct") or 0) <= 0:
        reasons.append("MEDIAN_ALPHA_24H_NOT_POSITIVE")
    loo = h24.get("leave_one_out") or {}
    if loo and loo.get("all_single_deletions_positive") is not True:
        reasons.append("SINGLE_OBSERVATION_CAN_FLIP_ALPHA")
    if h24.get("alpha_without_best_signal_pct") is not None and h24.get("alpha_without_best_signal_pct") <= 0:
        reasons.append("BEST_SIGNAL_DOMINATES_ALPHA")
    if reasons:
        return "FRAGILE_FORWARD_ALPHA", reasons

    s7 = h7.get("signal") or {}
    c7 = h7.get("control") or {}
    if int(s7.get("matured_expected") or 0) < 30 or int(c7.get("matured_expected") or 0) < 30:
        return "ROBUST_24H_AWAITING_7D", ["NEED_30_MATURED_SIGNAL_AND_CONTROL_AT_7D"]
    if float(s7.get("coverage_pct") or 0) < 90 or float(c7.get("coverage_pct") or 0) < 90:
        return "FRAGILE_7D_COVERAGE", ["7D_CHECKPOINT_COVERAGE_BELOW_90_PCT"]
    if (h7.get("mean_alpha_pct") or 0) <= 0 or (h7.get("median_alpha_pct") or 0) <= 0:
        return "FRAGILE_7D_PERSISTENCE", ["7D_ALPHA_NOT_POSITIVE_ON_BOTH_MEAN_AND_MEDIAN"]
    loo7 = h7.get("leave_one_out") or {}
    if loo7 and loo7.get("all_single_deletions_positive") is not True:
        return "FRAGILE_7D_INFLUENCE", ["7D_SINGLE_OBSERVATION_CAN_FLIP_ALPHA"]
    return "ROBUST_FORWARD_ALPHA_AUDIT_PASS", []


def run(data_dir: str | Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    reference = now or datetime.now(timezone.utc)
    ledger = _load(data_dir / ALPHA_LEDGER.name, {})
    matched = _load(data_dir / MATCHED_REPORT.name, {})
    signals = ledger.get("signals") if isinstance(ledger, dict) and isinstance(ledger.get("signals"), dict) else {}
    controls = ledger.get("controls") if isinstance(ledger, dict) and isinstance(ledger.get("controls"), dict) else {}
    signal_rows = [x for x in signals.values() if isinstance(x, dict)]
    control_rows = [x for x in controls.values() if isinstance(x, dict)]
    lanes = sorted({str(x.get("lane")) for x in signal_rows if x.get("lane")})

    lane_reports: dict[str, Any] = {}
    for lane in lanes:
        cohort = [x for x in signal_rows if x.get("lane") == lane]
        horizons = {h: _summary(cohort, control_rows, h, reference) for h in HORIZONS}
        status, reasons = _robustness_status(horizons["24h"], horizons["7d"])
        lane_reports[lane] = {
            "signal_count_unchanged": len(cohort),
            "control_pool_count_unchanged": len(control_rows),
            "robustness_status": status,
            "robustness_reasons": reasons,
            "horizons": horizons,
            "matched_control_context": _matched_context(matched, lane),
        }

    primary = lane_reports.get("PRECURSOR_REAWAKENING") or {
        "robustness_status": "COLLECTING_FORWARD_SAMPLE",
        "robustness_reasons": ["NO_FORMAL_PRECURSOR_SIGNAL_YET"],
    }
    report = {
        "version": 1,
        "mode": MODE,
        "updated_at": reference.isoformat(),
        "source_mode": ledger.get("mode") if isinstance(ledger, dict) else None,
        "primary_lane": "PRECURSOR_REAWAKENING",
        "primary_robustness_status": primary.get("robustness_status"),
        "primary_robustness_reasons": primary.get("robustness_reasons"),
        "formal_signal_count_unchanged": len(signal_rows),
        "formal_control_count_unchanged": len(control_rows),
        "safety_contract": {
            "proof_audit_only": True,
            "changes_discovery_funnel": False,
            "changes_signal_enrollment": False,
            "changes_candidate_qualification": False,
            "changes_production_gate": False,
            "changes_telegram_alerts": False,
            "can_block_or_drop_candidate": False,
            "can_block_or_drop_signal": False,
            "changes_primary_alpha_proof_status": False,
        },
        "audit_rules": {
            "maturity_adjusted_checkpoint_coverage": True,
            "minimum_checkpoint_coverage_pct": 90,
            "requires_positive_mean_and_median_alpha_24h": True,
            "single_observation_leave_one_out_sensitivity": True,
            "best_signal_dependency_test": True,
            "requires_7d_persistence_for_full_robustness": True,
            "matched_controls_are_supporting_secondary_context_only": True,
        },
        "lanes": lane_reports,
        "interpretation": "This audit hardens only the evidence standard. It cannot remove, delay, downgrade, or block any Wallet500 candidate, signal, production qualification, or Telegram alert.",
    }
    _write(data_dir / REPORT_PATH.name, report)
    print(json.dumps({
        "mode": MODE,
        "signals": len(signal_rows),
        "controls": len(control_rows),
        "primary_robustness_status": report["primary_robustness_status"],
        "discovery_impact": "NONE",
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
