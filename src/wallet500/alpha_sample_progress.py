from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EARLY_TARGET_SIGNAL_24H = 20
EARLY_TARGET_CONTROL_24H = 20
STRONG_TARGET_SIGNAL_24H = 50
STRONG_TARGET_CONTROL_24H = 50
PROVEN_TARGET_SIGNAL_24H = 100
PROVEN_TARGET_CONTROL_24H = 100


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _n(stats: object) -> int:
    if not isinstance(stats, dict):
        return 0
    try:
        return max(0, int(stats.get("n") or 0))
    except Exception:
        return 0


def enrich(report: dict[str, Any]) -> dict[str, Any]:
    lane = (report.get("lanes") or {}).get("PRECURSOR_REAWAKENING") or {}
    horizons = lane.get("horizons") if isinstance(lane, dict) else {}
    h24 = horizons.get("24h") if isinstance(horizons, dict) else {}
    signal_24h = _n((h24 or {}).get("signal"))
    control_24h = _n((h24 or {}).get("control"))
    early_progress = min(1.0, signal_24h / EARLY_TARGET_SIGNAL_24H, control_24h / EARLY_TARGET_CONTROL_24H)
    strong_progress = min(1.0, signal_24h / STRONG_TARGET_SIGNAL_24H, control_24h / STRONG_TARGET_CONTROL_24H)
    proven_progress = min(1.0, signal_24h / PROVEN_TARGET_SIGNAL_24H, control_24h / PROVEN_TARGET_CONTROL_24H)
    report["sample_maturity"] = {
        "status": "SUFFICIENT_EARLY_SAMPLE" if signal_24h >= EARLY_TARGET_SIGNAL_24H and control_24h >= EARLY_TARGET_CONTROL_24H else "INSUFFICIENT_SAMPLE",
        "primary_lane": "PRECURSOR_REAWAKENING",
        "mature_24h_signal_count": signal_24h,
        "mature_24h_control_count": control_24h,
        "early_target": {"signal": EARLY_TARGET_SIGNAL_24H, "control": EARLY_TARGET_CONTROL_24H},
        "early_remaining": {"signal": max(0, EARLY_TARGET_SIGNAL_24H - signal_24h), "control": max(0, EARLY_TARGET_CONTROL_24H - control_24h)},
        "early_progress_pct": round(early_progress * 100, 1),
        "strong_progress_pct": round(strong_progress * 100, 1),
        "proven_progress_pct": round(proven_progress * 100, 1),
        "calibrated_probability_allowed": False,
        "reason": "Forward-only exact-pair cohorts must mature naturally; sample enrollment and production gates are never loosened to accelerate proof.",
    }
    return report


def run(data_dir: str | Path = "data") -> dict[str, Any]:
    path = Path(data_dir) / "alpha-proof-report.json"
    report = _load(path)
    if report.get("mode") != "FORWARD_ONLY_ALPHA_PROOF_V1":
        raise SystemExit("ALPHA_PROOF_REPORT_MISSING_OR_INVALID")
    enrich(report)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["sample_maturity"], indent=2))
    return report


if __name__ == "__main__":
    run()
