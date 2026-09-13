from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
EVM_CHAINS = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "polygon", "optimism", "avalanche"}
HORIZONS = ((5, "5m"), (60, "1h"), (240, "4h"), (1440, "24h"))
MIN_TOTAL = 12
MIN_ARM = 4
MAX_RANK_ADJUSTMENT = 3


def _load(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _atomic_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(path)


def _dt(value: Any) -> datetime | None:
    try:
        x = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _norm(chain: Any, value: Any) -> str:
    chain = str(chain or "").lower()
    value = str(value or "").strip()
    return value.lower() if chain in EVM_CHAINS else value


def exact_key(chain: Any, token: Any, pair: Any) -> str:
    c = str(chain or "").lower().strip()
    return f"{c}:{_norm(c, token)}:{_norm(c, pair)}"


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def feature_flags(candidate: dict) -> dict[str, bool]:
    adaptive = candidate.get("adaptive_discovery") if isinstance(candidate.get("adaptive_discovery"), dict) else {}
    coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
    market = candidate.get("market") if isinstance(candidate.get("market"), dict) else {}
    flags: dict[str, bool] = {}
    for signal in adaptive.get("signals") or []:
        if signal:
            flags[f"signal:{signal}"] = True
    for lane in coverage.get("positive_independent_lanes") or []:
        if lane:
            flags[f"lane:{lane}"] = True
    tier = str(candidate.get("discovery_tier") or "")
    if tier:
        flags[f"tier:{tier}"] = True
    anomaly = _num(adaptive.get("anomaly_score"))
    velocity = _num(adaptive.get("velocity_score"))
    persistence = _num(adaptive.get("persistence_score"))
    revival = _num(market.get("revival_score_verified"))
    liquidity = _num(market.get("liquidity_usd"))
    if anomaly is not None:
        flags["bucket:anomaly_ge_45"] = anomaly >= 45
    if velocity is not None:
        flags["bucket:velocity_ge_35"] = velocity >= 35
    if persistence is not None:
        flags["bucket:persistence_ge_55"] = persistence >= 55
    if revival is not None:
        flags["bucket:revival_ge_65"] = revival >= 65
    if liquidity is not None:
        flags["bucket:liquidity_ge_50k"] = liquidity >= 50000
    return flags


def _immutable_features(candidate: dict) -> dict:
    adaptive = candidate.get("adaptive_discovery") if isinstance(candidate.get("adaptive_discovery"), dict) else {}
    coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
    market = candidate.get("market") if isinstance(candidate.get("market"), dict) else {}
    truth = candidate.get("truth") if isinstance(candidate.get("truth"), dict) else {}
    return {
        "status": candidate.get("status"),
        "discovery_tier": candidate.get("discovery_tier"),
        "market": {
            "revival_score_verified": market.get("revival_score_verified"),
            "price_usd": market.get("price_usd"),
            "liquidity_usd": market.get("liquidity_usd"),
            "volume_24h_usd": market.get("volume_24h_usd"),
            "change_24h_pct": market.get("change_24h_pct"),
            "change_7d_pct": market.get("change_7d_pct"),
            "liquidity_change_pct": market.get("liquidity_change_pct"),
            "pair_volume_change_pct": market.get("pair_volume_change_pct"),
        },
        "adaptive": {
            "anomaly_score": adaptive.get("anomaly_score"),
            "velocity_score": adaptive.get("velocity_score"),
            "persistence_score": adaptive.get("persistence_score"),
            "signal_family_count": adaptive.get("signal_family_count"),
            "signals": sorted(str(x) for x in adaptive.get("signals") or []),
        },
        "coverage": {
            "verified_independent_count": coverage.get("verified_independent_count"),
            "positive_independent_count": coverage.get("positive_independent_count"),
            "positive_independent_lanes": sorted(str(x) for x in coverage.get("positive_independent_lanes") or []),
        },
        "truth": {
            "exact_identity_verified": truth.get("exact_identity_verified"),
            "exact_pair_verified": truth.get("exact_pair_verified"),
            "market_age_days": truth.get("market_age_days"),
            "execution_pool_liquidity_usd": truth.get("execution_pool_liquidity_usd"),
        },
        "feature_flags": feature_flags(candidate),
    }


def _records_by_exact_pair(tracker: dict) -> dict[str, dict]:
    records = tracker.get("tokens") if isinstance(tracker, dict) else {}
    out: dict[str, dict] = {}
    if not isinstance(records, dict):
        return out
    for rec in records.values():
        if not isinstance(rec, dict):
            continue
        chain, token, pair = rec.get("chain"), rec.get("token"), rec.get("entry_pair_address")
        if not chain or not token or not pair:
            continue
        out[exact_key(chain, token, pair)] = rec
    return out


def _forward_outcomes(observation: dict, record: dict | None) -> dict[str, dict]:
    result = {label: {"status": "UNRESOLVED", "return_pct": None, "captured_at": None} for _, label in HORIZONS}
    if not record:
        return result
    observed_at = _dt(observation.get("observed_at"))
    entry_price = _num((observation.get("features") or {}).get("market", {}).get("price_usd"))
    if observed_at is None or entry_price is None or entry_price <= 0:
        return result
    chain = observation.get("chain")
    expected_pair = observation.get("pair_address")
    history = record.get("history") if isinstance(record.get("history"), list) else []
    eligible: list[tuple[datetime, dict]] = []
    for row in history:
        if not isinstance(row, dict) or row.get("measurement_eligible") is not True or row.get("token_identity_verified") is not True:
            continue
        if row.get("price_identity_contract_version") != 2:
            continue
        when = _dt(row.get("observed_at"))
        price = _num(row.get("price_usd"))
        pair = row.get("pair_address")
        if when is None or when <= observed_at or price is None or price <= 0 or not pair:
            continue
        if _norm(chain, pair) != _norm(chain, expected_pair):
            continue
        eligible.append((when, row))
    eligible.sort(key=lambda x: x[0])
    for minutes, label in HORIZONS:
        threshold = observed_at.timestamp() + minutes * 60
        hit = next(((when, row) for when, row in eligible if when.timestamp() >= threshold), None)
        if not hit:
            continue
        when, row = hit
        price = float(row["price_usd"])
        result[label] = {
            "status": "RESOLVED_EXACT_PAIR_FORWARD",
            "return_pct": round((price / entry_price - 1.0) * 100.0, 6),
            "captured_at": when.isoformat(),
        }
    return result


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "hit_rate_10pct": None, "positive_rate": None, "median_return_pct": None}
    return {
        "n": len(values),
        "hit_rate_10pct": round(100.0 * sum(v >= 10.0 for v in values) / len(values), 2),
        "positive_rate": round(100.0 * sum(v > 0.0 for v in values) / len(values), 2),
        "median_return_pct": round(float(statistics.median(values)), 4),
    }


def _attribution(observations: list[dict], outcomes: dict[str, dict]) -> tuple[dict, dict]:
    attribution: dict[str, Any] = {}
    recommendations: list[dict] = []
    all_features = sorted({name for obs in observations for name in ((obs.get("features") or {}).get("feature_flags") or {})})
    for _, horizon in HORIZONS:
        resolved = []
        for obs in observations:
            outcome = (outcomes.get(obs["observation_id"]) or {}).get(horizon) or {}
            value = _num(outcome.get("return_pct")) if outcome.get("status") == "RESOLVED_EXACT_PAIR_FORWARD" else None
            if value is not None:
                resolved.append((obs, value))
        horizon_rows = []
        for feature in all_features:
            present = [ret for obs, ret in resolved if ((obs.get("features") or {}).get("feature_flags") or {}).get(feature) is True]
            absent = [ret for obs, ret in resolved if ((obs.get("features") or {}).get("feature_flags") or {}).get(feature) is not True]
            ps, as_ = _stats(present), _stats(absent)
            eligible = len(resolved) >= MIN_TOTAL and len(present) >= MIN_ARM and len(absent) >= MIN_ARM
            hit_uplift = None if not eligible else round(float(ps["hit_rate_10pct"]) - float(as_["hit_rate_10pct"]), 2)
            med_uplift = None if not eligible else round(float(ps["median_return_pct"]) - float(as_["median_return_pct"]), 4)
            delta = 0
            if eligible and hit_uplift >= 10 and med_uplift >= 3:
                delta = 1
            elif eligible and hit_uplift <= -10 and med_uplift <= -3:
                delta = -1
            horizon_rows.append({"feature": feature, "present": ps, "absent": as_, "eligible": eligible, "hit_rate_uplift_pp": hit_uplift, "median_return_uplift_pct": med_uplift})
            if horizon in {"4h", "24h"}:
                recommendations.append({
                    "feature": feature,
                    "horizon": horizon,
                    "sample_total": len(resolved),
                    "present_n": len(present),
                    "absent_n": len(absent),
                    "recommended_rank_delta": delta,
                    "status": "EVIDENCE_READY" if eligible else "INSUFFICIENT_EVIDENCE",
                    "hit_rate_uplift_pp": hit_uplift,
                    "median_return_uplift_pct": med_uplift,
                    "production_change": False,
                })
        attribution[horizon] = {"resolved_n": len(resolved), "unresolved_n": len(observations) - len(resolved), "features": horizon_rows}
    candidate_payload = {
        "version": 1,
        "mode": "RESEARCH_ONLY_BOUNDED_RANK_WEIGHT_CANDIDATES_V1",
        "production_change": False,
        "automatic_promotion": False,
        "max_rank_delta_per_feature": 1,
        "max_total_rank_adjustment": MAX_RANK_ADJUSTMENT,
        "minimum_total_sample": MIN_TOTAL,
        "minimum_arm_sample": MIN_ARM,
        "recommendations": recommendations,
    }
    return attribution, candidate_payload


def apply_research_rank_overlay(candidates: list[dict], weight_payload: dict) -> list[dict]:
    """Bounded, prospective ranking only. Never changes status, tier or production gates."""
    recommendations = weight_payload.get("recommendations") if isinstance(weight_payload, dict) else []
    active: dict[str, int] = {}
    if isinstance(recommendations, list):
        # Prefer 24h evidence; fall back to 4h only when 24h has no evidence-ready row.
        for horizon in ("24h", "4h"):
            for row in recommendations:
                if not isinstance(row, dict) or row.get("horizon") != horizon or row.get("status") != "EVIDENCE_READY":
                    continue
                feature = str(row.get("feature") or "")
                if feature and feature not in active:
                    delta = int(row.get("recommended_rank_delta") or 0)
                    active[feature] = max(-1, min(1, delta))
    for candidate in candidates:
        flags = feature_flags(candidate)
        matched = sorted(f for f, enabled in flags.items() if enabled and f in active and active[f] != 0)
        raw = sum(active[f] for f in matched)
        bounded = max(-MAX_RANK_ADJUSTMENT, min(MAX_RANK_ADJUSTMENT, raw))
        adaptive = candidate.get("adaptive_discovery") if isinstance(candidate.get("adaptive_discovery"), dict) else {}
        base = _num(adaptive.get("anomaly_score")) or 0.0
        candidate["learning_rank"] = {
            "research_only": True,
            "prospective": True,
            "base_anomaly_score": base,
            "rank_adjustment": bounded,
            "rank_score": round(base + bounded, 2),
            "matched_evidence_features": matched,
            "may_change_status_or_tier": False,
            "may_bypass_truth_gate": False,
        }
    return candidates


def run(data_dir: Path = DATA) -> dict:
    now = datetime.now(timezone.utc)
    envelope = _load(data_dir / "candidate-evidence-envelope.json", {})
    tracker = _load(data_dir / "outcome-tracker.json", {})
    generation = _load(data_dir / "decision-generation.json", {})
    ledger = _load(data_dir / "learning-observations.json", {})
    if envelope.get("production_change") is not False or (envelope.get("truth_contract") or {}).get("no_hindsight") is not True:
        raise SystemExit("LEARNING_FAIL_CLOSED: candidate evidence truth contract invalid")
    candidates = envelope.get("candidates") if isinstance(envelope.get("candidates"), list) else []
    observations = ledger.get("observations") if isinstance(ledger, dict) and isinstance(ledger.get("observations"), list) else []
    existing = {str(x.get("observation_id")): x for x in observations if isinstance(x, dict) and x.get("observation_id")}
    generation_id = generation.get("generation_id")
    added = 0
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("status") == "BLOCKED_TRUTH":
            continue
        truth = candidate.get("truth") if isinstance(candidate.get("truth"), dict) else {}
        chain = candidate.get("chain") or candidate.get("network")
        token, pair = candidate.get("token_address"), candidate.get("pair_address")
        if truth.get("exact_identity_verified") is not True or truth.get("exact_pair_verified") is not True or not chain or not token or not pair:
            continue
        price = _num((candidate.get("market") or {}).get("price_usd"))
        if price is None or price <= 0:
            continue
        tier = str(candidate.get("discovery_tier") or candidate.get("status") or "UNKNOWN")
        oid = hashlib.sha256(f"{exact_key(chain, token, pair)}|{tier}".encode("utf-8")).hexdigest()
        features = _immutable_features(candidate)
        feature_hash = _canonical_hash(features)
        if oid in existing:
            old_hash = existing[oid].get("feature_hash")
            if old_hash != feature_hash:
                # The first observation is immutable. A later changing live snapshot is expected;
                # it must never rewrite the original feature vector.
                continue
            continue
        obs = {
            "observation_id": oid,
            "observed_at": envelope.get("generated_at") or now.isoformat(),
            "generation_id": generation_id,
            "chain": str(chain).lower(),
            "token_address": token,
            "pair_address": pair,
            "exact_pair_key": exact_key(chain, token, pair),
            "decision_status": candidate.get("status"),
            "decision_tier": tier,
            "feature_hash": feature_hash,
            "features": features,
            "truth": {"exact_pair": True, "no_hindsight": True, "immutable_first_observation": True, "research_only": True},
        }
        observations.append(obs)
        existing[oid] = obs
        added += 1
    observations.sort(key=lambda x: (str(x.get("observed_at") or ""), str(x.get("observation_id") or "")))
    obs_payload = {
        "version": 1,
        "mode": "IMMUTABLE_FIRST_DECISION_EVIDENCE_V1",
        "updated_at": now.isoformat(),
        "production_change": False,
        "no_hindsight": True,
        "exact_pair_required": True,
        "observations": observations,
    }
    records = _records_by_exact_pair(tracker)
    outcome_map = {obs["observation_id"]: _forward_outcomes(obs, records.get(obs["exact_pair_key"])) for obs in observations}
    attribution, weights = _attribution(observations, outcome_map)
    outcome_payload = {
        "version": 1,
        "mode": "EXACT_PAIR_FORWARD_OUTCOME_ATTRIBUTION_V1",
        "generated_at": now.isoformat(),
        "production_change": False,
        "no_hindsight": True,
        "observation_count": len(observations),
        "outcomes": outcome_map,
        "attribution": attribution,
    }
    weights["generated_at"] = now.isoformat()
    weights["truth_contract"] = {
        "research_rank_only": True,
        "never_auto_promotes": True,
        "never_changes_liquidity_gate": True,
        "exact_pair_required": True,
        "forward_observations_only": True,
        "missing_outcomes_are_unknown_not_zero": True,
    }
    ranked = apply_research_rank_overlay([dict(x) for x in candidates], weights)
    ranked.sort(key=lambda x: (
        {"EVIDENCE_READY": 0, "VERIFIED_WATCH": 1, "DEEP_WATCH": 2, "BLOCKED_TRUTH": 3}.get(x.get("status"), 9),
        -float((x.get("learning_rank") or {}).get("rank_score") or 0),
        str(x.get("exact_pair_key") or x.get("key") or ""),
    ))
    ranked_payload = {
        "version": 1,
        "mode": "RESEARCH_ONLY_PROSPECTIVE_LEARNING_RANK_V1",
        "generated_at": now.isoformat(),
        "production_change": False,
        "automatic_promotion": False,
        "status_and_tier_unchanged": True,
        "candidate_count": len(ranked),
        "candidates": ranked,
    }
    _atomic_write(data_dir / "learning-observations.json", obs_payload)
    _atomic_write(data_dir / "feature-attribution.json", outcome_payload)
    _atomic_write(data_dir / "weight-update-candidates.json", weights)
    _atomic_write(data_dir / "learning-ranked-candidates.json", ranked_payload)
    return {"observations": len(observations), "added": added, "recommendations": len(weights["recommendations"]), "ranked": len(ranked)}


def main() -> None:
    print(json.dumps(run(), sort_keys=True))


if __name__ == "__main__":
    main()
