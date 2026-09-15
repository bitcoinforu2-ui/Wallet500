from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
MODE = "RESEARCH_ONLY_LEARNING_ENGINE_V2"
STATE_FILE = "prewave-learning-state.json"
PREWAVE_FILE = "prewave-learning-v2.json"
MISSED_FILE = "missed-winner-miner.json"
WEIGHTS_FILE = "adaptive-learned-weights.json"
SCAN_FILE = "adaptive-scan-plan.json"

MIN_POLICY_EVALUATED = 10
MIN_MATURED_FOR_WEIGHT_REVIEW = 30
MAX_HISTORY = 12

DEFAULT_WEIGHTS: dict[str, float] = {
    "wallet_alpha": 22.0,
    "market_microstructure": 18.0,
    "execution_copyability": 14.0,
    "holder_growth": 8.0,
    "funding_cluster_independence": 5.0,
    "social_narrative": 9.0,
    "official_catalyst": 8.0,
    "independent_confirmation": 7.0,
    "cex_acceleration": 4.0,
    "price_anti_chase": 5.0,
}

POLICY_TO_LANES: dict[str, dict[str, float]] = {
    "B_ACCELERATION_TURNOVER": {
        "market_microstructure": 0.70,
        "price_anti_chase": 0.30,
    },
    "D_WALLET_CAPITAL_SOCIAL": {
        "wallet_alpha": 0.50,
        "social_narrative": 0.30,
        "independent_confirmation": 0.20,
    },
    "E_WINNER_DNA_PERSISTENCE": {
        "wallet_alpha": 0.25,
        "market_microstructure": 0.25,
        "holder_growth": 0.25,
        "independent_confirmation": 0.25,
    },
}


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        n = float(value)
        return n if math.isfinite(n) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        out = datetime.fromisoformat(text)
    except ValueError:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def _norm_chain(value: Any) -> str:
    chain = str(value or "").strip().lower()
    return {"eth": "ethereum", "bnb": "bsc", "arbitrum-one": "arbitrum"}.get(chain, chain)


def _norm_addr(chain: str, value: Any) -> str:
    text = str(value or "").strip()
    return text.lower() if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "linea", "scroll"} else text


def _identity(row: dict[str, Any]) -> tuple[str, str, str]:
    chain = _norm_chain(row.get("chain") or row.get("network"))
    token = _norm_addr(chain, row.get("token_address") or row.get("token") or row.get("mint") or row.get("contract"))
    pair = _norm_addr(chain, row.get("pair_address") or row.get("entry_pair_address") or row.get("dex_pair_address"))
    return chain, token, pair


def _key(row: dict[str, Any]) -> str:
    chain, token, pair = _identity(row)
    return f"{chain}|{token}|{pair}" if chain and token and pair else ""


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw = payload.get("records")
        if isinstance(raw, dict):
            return [x for x in raw.values() if isinstance(x, dict)]
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    return []


def _checkpoint_return(record: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    best: tuple[float | None, str | None, str | None] = (None, None, None)
    checkpoints = record.get("checkpoints") if isinstance(record.get("checkpoints"), dict) else {}
    for horizon, cp in checkpoints.items():
        if not isinstance(cp, dict):
            continue
        ret = _num(cp.get("gross_return_pct"))
        if ret is None:
            entry = _num(record.get("entry_price_usd"))
            px = _num(cp.get("price_usd"))
            if entry and px is not None:
                ret = (px / entry - 1.0) * 100.0
        if ret is None:
            continue
        if best[0] is None or ret > best[0]:
            best = (ret, str(horizon), cp.get("captured_at") or cp.get("observed_at"))
    return best


def build_missed_winners(data_dir: Path, now: datetime) -> dict[str, Any]:
    source = _load(data_dir / "research-sample-ledger.json", {})
    missed: list[dict[str, Any]] = []
    blocker_counts: Counter[str] = Counter()
    threshold_counts = {"gte_50": 0, "gte_100": 0, "gte_200": 0}
    matured = 0

    for row in _records(source):
        decision = row.get("decision_snapshot") if isinstance(row.get("decision_snapshot"), dict) else {}
        entry = decision.get("entry") if isinstance(decision.get("entry"), dict) else {}
        best_ret, horizon, observed_at = _checkpoint_return(row)
        if best_ret is None:
            continue
        matured += 1
        status = str(entry.get("status") or row.get("status") or "")
        actionable = entry.get("actionable") is True or row.get("actionable") is True
        production_alert = actionable or "REAL_ALERT" in status
        if production_alert or best_ret < 50.0:
            continue
        if best_ret >= 50:
            threshold_counts["gte_50"] += 1
        if best_ret >= 100:
            threshold_counts["gte_100"] += 1
        if best_ret >= 200:
            threshold_counts["gte_200"] += 1
        blockers = [str(x) for x in (entry.get("blockers") or row.get("blockers") or []) if str(x)]
        missing = [str(x) for x in (entry.get("missing_gates") or []) if str(x)]
        blocker_counts.update(blockers)
        chain, token, pair = _identity(row)
        missed.append({
            "chain": chain,
            "token_address": token,
            "pair_address": pair,
            "symbol": row.get("symbol"),
            "first_decision_at": row.get("event_at") or entry.get("observed_at"),
            "entry_price_usd": _num(row.get("entry_price_usd") or entry.get("entry_price_usd")),
            "best_forward_return_pct": round(best_ret, 4),
            "best_horizon": horizon,
            "best_observed_at": observed_at,
            "t0_status": status,
            "t0_signal_score": _num(entry.get("signal_score")),
            "t0_readiness": [entry.get("readiness_passed"), entry.get("readiness_total")],
            "t0_blockers": blockers,
            "t0_missing_gates": missing,
            "source_lane_count": entry.get("source_lane_count"),
            "evidence_positive_lanes": entry.get("evidence_positive_lanes") or [],
            "lesson_scope": "RESEARCH_ONLY_NO_RETROACTIVE_T0_MUTATION",
        })

    missed.sort(key=lambda x: x["best_forward_return_pct"], reverse=True)
    return {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": "RESEARCH_ONLY_MISSED_WINNER_MINER_V1",
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "winner_thresholds_pct": [50, 100, 200],
        "source": "research-sample-ledger.json",
        "counts": {"records_with_forward_observation": matured, "missed_winners": len(missed), **threshold_counts},
        "top_blockers_on_missed_winners": [{"blocker": k, "count": v} for k, v in blocker_counts.most_common(20)],
        "missed_winners": missed[:100],
        "truth_contract": {
            "t0_is_immutable": True,
            "future_outcome_used_only_for_research_labels": True,
            "no_retroactive_alert_creation": True,
            "exact_identity_preserved": True,
        },
    }


def _prior_weights(confluence: dict[str, Any]) -> dict[str, float]:
    raw = ((confluence.get("weight_contract") or {}).get("weights") or {}) if isinstance(confluence, dict) else {}
    out = {k: float(raw.get(k, v)) for k, v in DEFAULT_WEIGHTS.items()}
    if abs(sum(out.values()) - 100.0) > 0.01:
        return dict(DEFAULT_WEIGHTS)
    return out


def _policy_quality(metric: dict[str, Any]) -> tuple[float | None, int]:
    evaluated = int(_num(metric.get("evaluated"), 0) or 0)
    if evaluated < MIN_POLICY_EVALUATED:
        return None, evaluated
    precision = _num(metric.get("precision"))
    recall = _num(metric.get("recall"))
    vals = [x for x in (precision, recall) if x is not None]
    if not vals:
        return None, evaluated
    quality = sum(vals) / len(vals)
    if quality > 1.0:
        quality /= 100.0
    ret = _num(metric.get("mean_7d_return_pct_when_positive"), 0.0) or 0.0
    quality = _clamp(quality * 100.0 + max(-20.0, min(50.0, ret)) * 0.25) / 100.0
    return quality, evaluated


def build_adaptive_weights(data_dir: Path, now: datetime) -> dict[str, Any]:
    confluence = _load(data_dir / "confluence-matrix.json", {})
    replay = _load(data_dir / "decision-replay-report.json", {})
    prior = _prior_weights(confluence)
    metrics = ((replay.get("walk_forward") or {}).get("policy_metrics") or {})
    if not any(int(_num(v.get("evaluated"), 0) or 0) for v in metrics.values() if isinstance(v, dict)):
        metrics = replay.get("policies") or {}

    lane_signal: dict[str, list[tuple[float, int, float]]] = {k: [] for k in prior}
    total_evaluated = 0
    usable_policies = 0
    policy_evidence: dict[str, Any] = {}
    for policy, mapping in POLICY_TO_LANES.items():
        metric = metrics.get(policy) if isinstance(metrics.get(policy), dict) else {}
        quality, evaluated = _policy_quality(metric)
        total_evaluated += evaluated
        policy_evidence[policy] = {"evaluated": evaluated, "quality": None if quality is None else round(quality, 4)}
        if quality is None:
            continue
        usable_policies += 1
        raw_multiplier = max(0.70, min(1.30, 0.70 + 0.60 * quality))
        for lane, share in mapping.items():
            lane_signal[lane].append((raw_multiplier, evaluated, share))

    learned = dict(prior)
    shrink = min(0.35, total_evaluated / 100.0 * 0.35) if total_evaluated else 0.0
    for lane, signals in lane_signal.items():
        if not signals:
            continue
        denom = sum(n * share for _, n, share in signals)
        if denom <= 0:
            continue
        raw_mult = sum(mult * n * share for mult, n, share in signals) / denom
        mult = 1.0 + (raw_mult - 1.0) * shrink
        mult = max(0.80, min(1.20, mult))
        learned[lane] = prior[lane] * mult

    # Execution is copyability, not predictive alpha: keep it fixed and normalise the rest around it.
    execution = prior["execution_copyability"]
    predictive_target = 100.0 - execution
    pred_names = [k for k in learned if k != "execution_copyability"]
    pred_sum = sum(learned[k] for k in pred_names) or predictive_target
    for lane in pred_names:
        learned[lane] = learned[lane] / pred_sum * predictive_target
    learned["execution_copyability"] = execution
    learned = {k: round(v, 4) for k, v in learned.items()}

    gate = replay.get("promotion_gate") if isinstance(replay.get("promotion_gate"), dict) else {}
    replay_ready = gate.get("status") == "READY_FOR_REVIEW"
    eligible = bool(replay_ready and total_evaluated >= MIN_MATURED_FOR_WEIGHT_REVIEW and usable_policies >= 2)
    status = "READY_FOR_SHADOW_RANKING_REVIEW" if eligible else "STATIC_PRIOR_WAITING_FOR_FORWARD_VALIDATION"
    return {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": "RESEARCH_ONLY_ADAPTIVE_WEIGHTS_V1",
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "status": status,
        "eligible_for_shadow_ranking_review": eligible,
        "eligible_for_production": False,
        "prior_weights": prior,
        "learned_weights": learned,
        "weight_sum": round(sum(learned.values()), 6),
        "shrinkage_factor": round(shrink, 4),
        "total_policy_evaluations": total_evaluated,
        "usable_policies": usable_policies,
        "policy_evidence": policy_evidence,
        "replay_promotion_gate": gate,
        "truth_contract": {
            "forward_only_labels": True,
            "minimum_policy_evaluated": MIN_POLICY_EVALUATED,
            "execution_copyability_weight_is_not_learned_alpha": True,
            "hard_gates_never_weakened": True,
            "production_weights_never_modified_automatically": True,
        },
    }


def _lane_score(row: dict[str, Any], name: str) -> float | None:
    lanes = row.get("lanes") if isinstance(row.get("lanes"), dict) else {}
    lane = lanes.get(name) if isinstance(lanes.get(name), dict) else {}
    if lane.get("available") is not True:
        return None
    return _num(lane.get("score"))


def _regime(row: dict[str, Any]) -> str:
    cex = _lane_score(row, "cex_acceleration") or 0.0
    catalyst = _lane_score(row, "official_catalyst") or 0.0
    market = _lane_score(row, "market_microstructure") or 0.0
    source = " ".join(str(row.get(k) or "") for k in ("source_status", "discovery_tier", "confluence_status")).upper()
    if cex >= 60 or catalyst >= 70:
        return "CEX_CATALYST"
    if "REVIVAL" in source:
        return "VETERAN_REVIVAL"
    if market >= 72 and _num(row.get("priority_score"), 0.0) >= 60:
        return "BREAKOUT"
    return "NEW_WAVE"


def _median_mad(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    med = statistics.median(values)
    mad = statistics.median(abs(x - med) for x in values)
    return med, mad


def _robust_z(value: float, values: list[float]) -> float:
    med, mad = _median_mad(values)
    if mad <= 1e-9:
        return 0.0
    return max(-4.0, min(4.0, 0.6745 * (value - med) / mad))


def _confidence(row: dict[str, Any], source_health_ratio: float) -> tuple[float, dict[str, Any]]:
    lanes = row.get("lanes") if isinstance(row.get("lanes"), dict) else {}
    available = [x for x in lanes.values() if isinstance(x, dict) and x.get("available") is True]
    coverage = len(available) / max(1, len(DEFAULT_WEIGHTS))
    strong_independent = sum(1 for x in available if (_num(x.get("score"), 0.0) or 0.0) >= 60)
    independence = min(1.0, strong_independent / 4.0)
    base = (_num(row.get("confidence_pct"), 0.0) or 0.0) / 100.0
    score = 100.0 * (0.40 * base + 0.25 * coverage + 0.20 * source_health_ratio + 0.15 * independence)
    blockers = [str(x) for x in (row.get("hard_blockers") or []) if str(x)]
    if blockers:
        score = min(score, 25.0)
    score = _clamp(score)
    return score, {
        "base_confluence_confidence_pct": round(base * 100.0, 2),
        "lane_coverage_pct": round(coverage * 100.0, 2),
        "fresh_source_ratio_pct": round(source_health_ratio * 100.0, 2),
        "strong_independent_lanes": strong_independent,
        "hard_blocker_cap_applied": bool(blockers),
    }


def _observation(row: dict[str, Any], at: str) -> dict[str, Any]:
    change = row.get("source_change") if isinstance(row.get("source_change"), dict) else {}
    return {
        "at": at,
        "priority": _num(row.get("priority_score"), 0.0) or 0.0,
        "alpha": _num(row.get("signal_alpha_score"), 0.0) or 0.0,
        "confidence": _num(row.get("confidence_pct"), 0.0) or 0.0,
        "market": _lane_score(row, "market_microstructure"),
        "holders": _lane_score(row, "holder_growth"),
        "wallet": _lane_score(row, "wallet_alpha"),
        "social": _lane_score(row, "social_narrative"),
        "volume_change_pct": _num(change.get("pair_volume_change_pct")),
        "liquidity_change_pct": _num(change.get("liquidity_change_pct")),
        "holder_growth_pct": _num(change.get("holder_growth_24h_pct")),
        "social_acceleration": _num(change.get("social_acceleration_vs_6h")),
    }


def _slope(history: list[dict[str, Any]], field: str) -> float | None:
    vals = [_num(x.get(field)) for x in history[-3:]]
    vals = [x for x in vals if x is not None]
    if len(vals) < 2:
        return None
    return (vals[-1] - vals[0]) / max(1, len(vals) - 1)


def _acceleration(history: list[dict[str, Any]], field: str) -> float | None:
    vals = [_num(x.get(field)) for x in history[-3:]]
    if len(vals) < 3 or any(x is None for x in vals):
        return None
    a, b, c = (float(x) for x in vals)
    return (c - b) - (b - a)


def _shadow_weighted_score(row: dict[str, Any], weights: dict[str, float]) -> float | None:
    total = 0.0
    denom = 0.0
    lanes = row.get("lanes") if isinstance(row.get("lanes"), dict) else {}
    for name, weight in weights.items():
        if name == "execution_copyability":
            continue
        lane = lanes.get(name) if isinstance(lanes.get(name), dict) else {}
        if lane.get("available") is not True:
            continue
        score = _num(lane.get("score"))
        cf = _num(lane.get("coverage_factor"), 1.0) or 0.0
        if score is None or cf <= 0:
            continue
        ew = weight * min(1.0, max(0.0, cf))
        total += score * ew
        denom += ew
    return total / denom if denom else None


def build_prewave(data_dir: Path, now: datetime, adaptive: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    confluence = _load(data_dir / "confluence-matrix.json", {})
    old_state = _load(data_dir / STATE_FILE, {})
    histories = old_state.get("histories") if isinstance(old_state.get("histories"), dict) else {}
    rows = [x for x in (confluence.get("tokens") or []) if isinstance(x, dict)]
    at = now.isoformat()

    source_health = confluence.get("source_health_summary") if isinstance(confluence.get("source_health_summary"), dict) else {}
    fresh = float(_num(source_health.get("fresh"), 0) or 0)
    total = float(_num(source_health.get("total"), 0) or 0)
    fresh_ratio = fresh / total if total > 0 else 0.0
    priorities = [float(_num(x.get("priority_score"), 0.0) or 0.0) for x in rows]
    alphas = [float(_num(x.get("signal_alpha_score"), 0.0) or 0.0) for x in rows]

    out: list[dict[str, Any]] = []
    next_histories: dict[str, list[dict[str, Any]]] = {}
    weights = adaptive.get("learned_weights") if isinstance(adaptive.get("learned_weights"), dict) else DEFAULT_WEIGHTS
    use_learned = adaptive.get("eligible_for_shadow_ranking_review") is True

    for row in rows:
        k = _key(row)
        if not k:
            continue
        history = list(histories.get(k) or [])[-(MAX_HISTORY - 1):]
        # Same generated snapshot can be processed more than once; do not fabricate acceleration.
        current = _observation(row, at)
        if not history or history[-1].get("source_generated_at") != confluence.get("generated_at"):
            current["source_generated_at"] = confluence.get("generated_at")
            history.append(current)
        next_histories[k] = history[-MAX_HISTORY:]

        p = float(_num(row.get("priority_score"), 0.0) or 0.0)
        a = float(_num(row.get("signal_alpha_score"), 0.0) or 0.0)
        pz = _robust_z(p, priorities)
        az = _robust_z(a, alphas)
        priority_slope = _slope(history, "priority")
        market_slope = _slope(history, "market")
        holder_slope = _slope(history, "holders")
        volume_slope = _slope(history, "volume_change_pct")
        priority_accel = _acceleration(history, "priority")

        temporal_bonus = 0.0
        temporal_bonus += max(-8.0, min(16.0, (priority_slope or 0.0) * 0.9))
        temporal_bonus += max(-6.0, min(12.0, (market_slope or 0.0) * 0.55))
        temporal_bonus += max(-4.0, min(9.0, (holder_slope or 0.0) * 0.35))
        temporal_bonus += max(-4.0, min(8.0, (volume_slope or 0.0) * 0.05))
        temporal_bonus += max(-4.0, min(8.0, (priority_accel or 0.0) * 0.5))
        peer_bonus = max(-8.0, min(12.0, 3.0 * pz + 2.0 * az))
        prewave = _clamp(0.72 * p + 0.18 * a + temporal_bonus + peer_bonus)
        conf, conf_detail = _confidence(row, fresh_ratio)
        if row.get("hard_blockers"):
            prewave = min(prewave, 25.0)

        regime = _regime(row)
        if prewave >= 80 and conf >= 65:
            tier = "HOT_PREWAVE"
            interval = 120
        elif prewave >= 65 and conf >= 50:
            tier = "WARM_PREWAVE"
            interval = 300
        elif prewave >= 50:
            tier = "WATCH_PREWAVE"
            interval = 600
        else:
            tier = "COLD"
            interval = 1800

        learned_score = _shadow_weighted_score(row, weights)
        out.append({
            "chain": row.get("chain"),
            "token_address": row.get("token_address"),
            "pair_address": row.get("pair_address"),
            "symbol": row.get("symbol"),
            "regime": regime,
            "prewave_score": round(prewave, 2),
            "confidence_score": round(conf, 2),
            "confidence_components": conf_detail,
            "tier": tier,
            "recommended_scan_interval_seconds": interval,
            "observations_in_state": len(history),
            "temporal": {
                "priority_slope": None if priority_slope is None else round(priority_slope, 4),
                "priority_acceleration": None if priority_accel is None else round(priority_accel, 4),
                "market_slope": None if market_slope is None else round(market_slope, 4),
                "holder_slope": None if holder_slope is None else round(holder_slope, 4),
                "volume_change_slope": None if volume_slope is None else round(volume_slope, 4),
            },
            "peer_baseline": {"priority_robust_z": round(pz, 4), "alpha_robust_z": round(az, 4)},
            "canonical_priority_score": round(p, 2),
            "canonical_alpha_score": round(a, 2),
            "experimental_adaptive_alpha_score": None if learned_score is None else round(learned_score, 2),
            "adaptive_weight_status": adaptive.get("status"),
            "adaptive_weights_used_for_tier": bool(use_learned),
            "hard_blockers": row.get("hard_blockers") or [],
            "production_effect": False,
            "automatic_buy": False,
        })

    out.sort(key=lambda x: (x["tier"] != "COLD", x["prewave_score"], x["confidence_score"]), reverse=True)
    counts = {name: sum(x["tier"] == name for x in out) for name in ("HOT_PREWAVE", "WARM_PREWAVE", "WATCH_PREWAVE", "COLD")}
    payload = {
        "version": 2,
        "generated_at": at,
        "mode": "RESEARCH_ONLY_PREWAVE_LEARNING_V2",
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "regimes": ["NEW_WAVE", "VETERAN_REVIVAL", "CEX_CATALYST", "BREAKOUT"],
        "counts": {"tokens": len(out), **counts},
        "source_generated_at": confluence.get("generated_at"),
        "tokens": out,
        "truth_contract": {
            "temporal_features_use_only_prior_and_current_snapshots": True,
            "duplicate_source_snapshot_does_not_create_fake_acceleration": True,
            "peer_baseline_is_point_in_time": True,
            "confidence_is_separate_from_score": True,
            "hard_blockers_cap_score": True,
            "learned_weights_do_not_change_production": True,
        },
    }
    state = {
        "version": 1,
        "updated_at": at,
        "mode": "RESEARCH_ONLY_PREWAVE_STATE_V1",
        "max_history_per_identity": MAX_HISTORY,
        "histories": next_histories,
    }
    return payload, state


def build_scan_plan(prewave: dict[str, Any], now: datetime) -> dict[str, Any]:
    rows = [x for x in (prewave.get("tokens") or []) if isinstance(x, dict)]
    hot = [x for x in rows if x.get("tier") == "HOT_PREWAVE"]
    warm = [x for x in rows if x.get("tier") == "WARM_PREWAVE"]
    return {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": "RESEARCH_ONLY_ADAPTIVE_SCAN_PLAN_V1",
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
        "scheduler_execution_cap_seconds": 300,
        "recommended_cadence_seconds": {"HOT_PREWAVE": 120, "WARM_PREWAVE": 300, "WATCH_PREWAVE": 600, "COLD": 1800},
        "counts": {"hot": len(hot), "warm": len(warm), "total": len(rows)},
        "priority_identities": [
            {k: x.get(k) for k in ("chain", "token_address", "pair_address", "symbol", "tier", "prewave_score", "confidence_score", "recommended_scan_interval_seconds")}
            for x in rows[:50]
        ],
        "truth_contract": {
            "plan_does_not_dispatch_weaker_scan": True,
            "hot_120s_is_recommendation_until_scheduler_support_is_validated": True,
            "github_schedule_floor_respected": True,
            "no_duplicate_truth_publisher": True,
        },
    }


def run(data_dir: Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    missed = build_missed_winners(data_dir, now)
    adaptive = build_adaptive_weights(data_dir, now)
    prewave, state = build_prewave(data_dir, now, adaptive)
    scan = build_scan_plan(prewave, now)

    _write(data_dir / MISSED_FILE, missed)
    _write(data_dir / WEIGHTS_FILE, adaptive)
    _write(data_dir / PREWAVE_FILE, prewave)
    _write(data_dir / STATE_FILE, state)
    _write(data_dir / SCAN_FILE, scan)

    summary = {
        "mode": MODE,
        "missed_winners": missed["counts"]["missed_winners"],
        "adaptive_weight_status": adaptive["status"],
        "prewave_counts": prewave["counts"],
        "scan_counts": scan["counts"],
        "production_effect": False,
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
