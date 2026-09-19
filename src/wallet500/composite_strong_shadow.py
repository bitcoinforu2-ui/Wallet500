from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data")
MIN_SIGNAL = 60.0
MIN_LIQ = 50_000.0
REQUIRED_LANES = {"CEX_REVIVAL", "REVIVAL_MARKET_STRUCTURE", "WAKING_CONFIRMATION", "REVIVAL_PRECURSOR", "ACTIVE_PRODUCTION_GATE"}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _idx(rows):
    out = {}
    for r in rows or []:
        if isinstance(r, dict) and r.get("token_address"):
            out[str(r["token_address"]).lower()] = r
    return out


def evaluate_candidate(obs: dict, real: dict | None) -> dict:
    real = real or {}
    blockers = set(obs.get("blockers") or [])
    missing = set(obs.get("missing_gates") or [])
    lanes = set(real.get("source_lanes") or [])
    positive = set(obs.get("evidence_positive_lanes") or [])
    signal = float(obs.get("signal_score") or 0)
    liq = float(obs.get("execution_pool_liquidity_usd") or 0)

    base_truth = all([
        obs.get("exact_identity_verified") is True,
        obs.get("exact_pair_verified") is True,
        obs.get("market_age_verified") is True,
        obs.get("market_activity_verified") is True,
        liq >= MIN_LIQ,
    ])
    only_strong_missing = missing == {"STRONG_DECISION_LANE"}
    risk_clear = not any(x for x in blockers if x not in {"NO_STRONG_DECISION_LANE"})
    lane_count = int(real.get("source_lane_count") or obs.get("source_lane_count") or 0)
    strong_lane_mix = len(lanes & REQUIRED_LANES) >= 2 if lanes else lane_count >= 2
    has_live_positive = bool(positive)
    score_ok = signal >= MIN_SIGNAL

    shadow_pass = all([
        base_truth,
        only_strong_missing,
        risk_clear,
        lane_count >= 2,
        strong_lane_mix,
        has_live_positive,
        score_ok,
    ])
    return {
        "symbol": obs.get("symbol"),
        "token_address": obs.get("token_address"),
        "pair_address": obs.get("pair_address"),
        "current_tier": obs.get("radar_tier"),
        "signal_score": signal,
        "liquidity_usd": liq,
        "source_lane_count": lane_count,
        "source_lanes": sorted(lanes),
        "positive_lanes": sorted(positive),
        "missing_gates": sorted(missing),
        "blockers": sorted(blockers),
        "shadow_composite_pass": shadow_pass,
        "shadow_reason": "COMPOSITE_STRONG_DECISION" if shadow_pass else "NO_SHADOW_PROMOTION",
    }


def run() -> dict:
    obs = _load(DATA / "near-alert-observatory.json", {})
    real = _load(DATA / "real-alerts.json", {})
    real_rows = real.get("alerts") or real.get("candidates") or real.get("rows") or []
    real_index = _idx(real_rows)
    population = []
    seen = set()
    for key in ("near_alert_leaderboard", "closest_to_real_alert"):
        for row in obs.get(key) or []:
            token = str(row.get("token_address") or "").lower()
            if not token or token in seen:
                continue
            seen.add(token)
            population.append(evaluate_candidate(row, real_index.get(token)))

    promoted = [r for r in population if r["shadow_composite_pass"]]
    ray = next((r for r in population if str(r.get("symbol") or "").upper() == "RAY"), None)
    report = {
        "mode": "RESEARCH_ONLY_COMPOSITE_STRONG_DECISION_SHADOW_V1",
        "production_change": False,
        "automatic_buy": False,
        "rule": {
            "only_missing_gate": "STRONG_DECISION_LANE",
            "min_independent_lanes": 2,
            "min_signal_score": MIN_SIGNAL,
            "min_execution_liquidity_usd": MIN_LIQ,
            "requires_live_positive_evidence": True,
            "requires_exact_identity_pair_age_market_activity": True,
            "risk_blockers_may_not_be_bypassed": True,
        },
        "population_count": len(population),
        "shadow_promotions_count": len(promoted),
        "shadow_promotions": promoted,
        "ray": ray,
        "interpretation": "Shadow-only. Promotion means the composite rule would replace only the missing STRONG_DECISION_LANE; it does not create a buy or weaken risk gates.",
    }
    (DATA / "composite-strong-shadow-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
