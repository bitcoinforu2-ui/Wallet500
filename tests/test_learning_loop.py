from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wallet500.learning_loop import apply_research_rank_overlay, exact_key, run


def _write(root: Path, name: str, payload) -> None:
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _candidate(now: datetime) -> dict:
    return {
        "key": "solana:TOKEN:PAIR",
        "chain": "solana",
        "network": "solana",
        "token_address": "TOKEN",
        "pair_address": "PAIR",
        "status": "VERIFIED_WATCH",
        "discovery_tier": "ANOMALY_WATCH",
        "production_effect": False,
        "truth": {
            "exact_identity_verified": True,
            "exact_pair_verified": True,
            "market_age_days": 200,
            "execution_pool_liquidity_usd": 60000,
        },
        "market": {
            "revival_score_verified": 70,
            "price_usd": 1.0,
            "liquidity_usd": 60000,
            "volume_24h_usd": 100000,
            "change_24h_pct": 5,
            "change_7d_pct": 8,
            "liquidity_change_pct": 10,
            "pair_volume_change_pct": 50,
        },
        "adaptive_discovery": {
            "anomaly_score": 55,
            "velocity_score": 50,
            "persistence_score": 60,
            "signal_family_count": 3,
            "signals": ["PAIR_VOLUME_VELOCITY_GE_50PCT", "LIQUIDITY_STABLE_OR_RISING"],
        },
        "coverage": {
            "verified_independent_count": 3,
            "positive_independent_count": 1,
            "positive_independent_lanes": ["WALLET_ACCUMULATION"],
        },
    }


def test_learning_loop_uses_only_forward_exact_pair_marks(tmp_path: Path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    candidate = _candidate(now)
    envelope = {
        "generated_at": now.isoformat(),
        "production_change": False,
        "truth_contract": {"no_hindsight": True},
        "candidates": [candidate],
    }
    history = [
        {
            "observed_at": (now - timedelta(minutes=10)).isoformat(),
            "price_usd": 99.0,
            "pair_address": "PAIR",
            "measurement_eligible": True,
            "token_identity_verified": True,
            "price_identity_contract_version": 2,
        },
        {
            "observed_at": (now + timedelta(minutes=6)).isoformat(),
            "price_usd": 1.1,
            "pair_address": "OTHER_PAIR",
            "measurement_eligible": True,
            "token_identity_verified": True,
            "price_identity_contract_version": 2,
        },
        {
            "observed_at": (now + timedelta(minutes=7)).isoformat(),
            "price_usd": 1.2,
            "pair_address": "PAIR",
            "measurement_eligible": True,
            "token_identity_verified": True,
            "price_identity_contract_version": 2,
        },
    ]
    tracker = {"tokens": {"x": {"chain": "solana", "token": "TOKEN", "entry_pair_address": "PAIR", "history": history}}}
    _write(tmp_path, "candidate-evidence-envelope.json", envelope)
    _write(tmp_path, "outcome-tracker.json", tracker)
    _write(tmp_path, "decision-generation.json", {"generation_id": "g1"})

    summary = run(tmp_path)
    assert summary["added"] == 1
    obs = json.loads((tmp_path / "learning-observations.json").read_text())["observations"][0]
    outcomes = json.loads((tmp_path / "feature-attribution.json").read_text())["outcomes"][obs["observation_id"]]
    assert outcomes["5m"]["status"] == "RESOLVED_EXACT_PAIR_FORWARD"
    assert outcomes["5m"]["return_pct"] == 20.0
    assert outcomes["1h"]["status"] == "UNRESOLVED"
    assert obs["exact_pair_key"] == exact_key("solana", "TOKEN", "PAIR")


def test_first_observation_is_immutable_when_live_features_change(tmp_path: Path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    candidate = _candidate(now)
    _write(tmp_path, "candidate-evidence-envelope.json", {"generated_at": now.isoformat(), "production_change": False, "truth_contract": {"no_hindsight": True}, "candidates": [candidate]})
    _write(tmp_path, "outcome-tracker.json", {"tokens": {}})
    _write(tmp_path, "decision-generation.json", {"generation_id": "g1"})
    run(tmp_path)
    first = json.loads((tmp_path / "learning-observations.json").read_text())["observations"][0]

    candidate["adaptive_discovery"]["anomaly_score"] = 99
    _write(tmp_path, "candidate-evidence-envelope.json", {"generated_at": (now + timedelta(minutes=5)).isoformat(), "production_change": False, "truth_contract": {"no_hindsight": True}, "candidates": [candidate]})
    run(tmp_path)
    second = json.loads((tmp_path / "learning-observations.json").read_text())["observations"][0]
    assert first["feature_hash"] == second["feature_hash"]
    assert second["features"]["adaptive"]["anomaly_score"] == 55


def test_rank_overlay_cannot_change_status_or_tier():
    c = _candidate(datetime.now(timezone.utc))
    before = (c["status"], c["discovery_tier"])
    weights = {
        "recommendations": [
            {"feature": "bucket:anomaly_ge_45", "horizon": "24h", "status": "EVIDENCE_READY", "recommended_rank_delta": 1},
            {"feature": "bucket:velocity_ge_35", "horizon": "24h", "status": "EVIDENCE_READY", "recommended_rank_delta": 1},
            {"feature": "bucket:persistence_ge_55", "horizon": "24h", "status": "EVIDENCE_READY", "recommended_rank_delta": 1},
            {"feature": "bucket:revival_ge_65", "horizon": "24h", "status": "EVIDENCE_READY", "recommended_rank_delta": 1},
        ]
    }
    out = apply_research_rank_overlay([c], weights)[0]
    assert (out["status"], out["discovery_tier"]) == before
    assert out["learning_rank"]["rank_adjustment"] == 3
    assert out["learning_rank"]["may_bypass_truth_gate"] is False
