import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wallet500.learning_engine_v2 import run


def _write(p: Path, name: str, payload: dict):
    (p / name).write_text(json.dumps(payload), encoding="utf-8")


def _confluence(generated_at: str, priority: float = 60.0, market: float = 65.0, blocked=False):
    lanes = {
        "wallet_alpha": {"available": True, "score": 70, "coverage_factor": 1.0},
        "market_microstructure": {"available": True, "score": market, "coverage_factor": 1.0},
        "execution_copyability": {"available": True, "score": 90, "coverage_factor": 1.0},
        "holder_growth": {"available": True, "score": 75, "coverage_factor": 1.0},
        "funding_cluster_independence": {"available": False, "score": None, "coverage_factor": 0.0},
        "social_narrative": {"available": True, "score": 62, "coverage_factor": 0.8},
        "official_catalyst": {"available": False, "score": None, "coverage_factor": 0.0},
        "independent_confirmation": {"available": True, "score": 72, "coverage_factor": 1.0},
        "cex_acceleration": {"available": False, "score": None, "coverage_factor": 0.0},
        "price_anti_chase": {"available": True, "score": 100, "coverage_factor": 1.0},
    }
    return {
        "generated_at": generated_at,
        "weight_contract": {
            "weights": {
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
        },
        "source_health_summary": {"fresh": 7, "total": 8},
        "tokens": [{
            "chain": "solana",
            "token_address": "TOKEN1",
            "pair_address": "PAIR1",
            "symbol": "T1",
            "source_status": "VERIFIED_WATCH",
            "discovery_tier": "ANOMALY_WATCH",
            "confluence_status": "BUILDING_CONFLUENCE",
            "priority_score": priority,
            "signal_alpha_score": priority + 2,
            "confidence_pct": 70,
            "hard_blockers": ["SECURITY_FAIL"] if blocked else [],
            "lanes": lanes,
            "source_change": {
                "pair_volume_change_pct": priority - 50,
                "liquidity_change_pct": 2,
                "holder_growth_24h_pct": 5,
            },
        }],
    }


def _sample_ledger():
    return {
        "records": {
            "x": {
                "chain": "solana",
                "token_address": "TOKEN1",
                "pair_address": "PAIR1",
                "event_at": "2026-09-10T00:00:00+00:00",
                "entry_price_usd": 1.0,
                "decision_snapshot": {
                    "identity": {"chain": "solana", "token": "TOKEN1", "pair_address": "PAIR1"},
                    "entry": {
                        "observed_at": "2026-09-10T00:00:00+00:00",
                        "status": "VERIFIED_WATCH_NOT_REAL_ALERT",
                        "actionable": False,
                        "signal_score": 61,
                        "readiness_passed": 5,
                        "readiness_total": 7,
                        "blockers": ["NO_STRONG_DECISION_LANE"],
                        "missing_gates": ["STRONG_DECISION_LANE"],
                    },
                },
                "checkpoints": {
                    "1h": {"captured_at": "2026-09-10T01:00:00+00:00", "price_usd": 1.2, "gross_return_pct": 20},
                    "24h": {"captured_at": "2026-09-11T00:01:00+00:00", "price_usd": 2.1, "gross_return_pct": 110},
                },
            }
        }
    }


def _replay(ready=False):
    metric = {
        "evaluated": 20 if ready else 0,
        "precision": 0.7 if ready else None,
        "recall": 0.6 if ready else None,
        "mean_7d_return_pct_when_positive": 25 if ready else None,
    }
    return {
        "mode": "RESEARCH_ONLY_DECISION_REPLAY_V1",
        "walk_forward": {"policy_metrics": {
            "B_ACCELERATION_TURNOVER": metric,
            "D_WALLET_CAPITAL_SOCIAL": metric,
            "E_WINNER_DNA_PERSISTENCE": metric,
        }},
        "promotion_gate": {"status": "READY_FOR_REVIEW" if ready else "NOT_READY_FOR_REVIEW"},
    }


def test_missed_winner_is_research_label_not_retroactive_alert(tmp_path):
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    _write(tmp_path, "research-sample-ledger.json", _sample_ledger())
    _write(tmp_path, "decision-replay-report.json", _replay(False))
    _write(tmp_path, "confluence-matrix.json", _confluence(now.isoformat()))
    run(tmp_path, now)

    mined = json.loads((tmp_path / "missed-winner-miner.json").read_text())
    assert mined["production_effect"] is False
    assert mined["automatic_buy"] is False
    assert mined["counts"]["missed_winners"] == 1
    row = mined["missed_winners"][0]
    assert row["best_forward_return_pct"] == 110
    assert row["t0_status"] == "VERIFIED_WATCH_NOT_REAL_ALERT"
    assert row["lesson_scope"] == "RESEARCH_ONLY_NO_RETROACTIVE_T0_MUTATION"


def test_adaptive_weights_wait_for_forward_validation_and_preserve_sum(tmp_path):
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    _write(tmp_path, "research-sample-ledger.json", _sample_ledger())
    _write(tmp_path, "decision-replay-report.json", _replay(False))
    _write(tmp_path, "confluence-matrix.json", _confluence(now.isoformat()))
    run(tmp_path, now)

    weights = json.loads((tmp_path / "adaptive-learned-weights.json").read_text())
    assert weights["eligible_for_production"] is False
    assert weights["eligible_for_shadow_ranking_review"] is False
    assert weights["status"] == "STATIC_PRIOR_WAITING_FOR_FORWARD_VALIDATION"
    assert abs(sum(weights["learned_weights"].values()) - 100.0) < 0.01
    assert weights["learned_weights"]["execution_copyability"] == 14.0


def test_temporal_state_dedupes_snapshot_and_detects_acceleration(tmp_path):
    t0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    _write(tmp_path, "research-sample-ledger.json", _sample_ledger())
    _write(tmp_path, "decision-replay-report.json", _replay(False))

    _write(tmp_path, "confluence-matrix.json", _confluence(t0.isoformat(), priority=50, market=55))
    run(tmp_path, t0)
    state1 = json.loads((tmp_path / "prewave-learning-state.json").read_text())
    assert len(next(iter(state1["histories"].values()))) == 1

    # Reprocessing the identical upstream snapshot must not invent a second observation.
    run(tmp_path, t0 + timedelta(minutes=1))
    state_dup = json.loads((tmp_path / "prewave-learning-state.json").read_text())
    assert len(next(iter(state_dup["histories"].values()))) == 1

    t1 = t0 + timedelta(minutes=10)
    _write(tmp_path, "confluence-matrix.json", _confluence(t1.isoformat(), priority=62, market=66))
    run(tmp_path, t1)
    t2 = t1 + timedelta(minutes=10)
    _write(tmp_path, "confluence-matrix.json", _confluence(t2.isoformat(), priority=79, market=80))
    run(tmp_path, t2)

    prewave = json.loads((tmp_path / "prewave-learning-v2.json").read_text())
    row = prewave["tokens"][0]
    assert row["observations_in_state"] == 3
    assert row["temporal"]["priority_slope"] > 0
    assert row["temporal"]["priority_acceleration"] > 0
    assert row["confidence_score"] > 0
    assert row["production_effect"] is False


def test_hard_blocker_caps_prewave_and_never_automatic_buy(tmp_path):
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    _write(tmp_path, "research-sample-ledger.json", _sample_ledger())
    _write(tmp_path, "decision-replay-report.json", _replay(True))
    _write(tmp_path, "confluence-matrix.json", _confluence(now.isoformat(), priority=95, market=95, blocked=True))
    run(tmp_path, now)

    prewave = json.loads((tmp_path / "prewave-learning-v2.json").read_text())
    row = prewave["tokens"][0]
    assert row["prewave_score"] <= 25
    assert row["confidence_score"] <= 25
    assert row["automatic_buy"] is False
    scan = json.loads((tmp_path / "adaptive-scan-plan.json").read_text())
    assert scan["production_effect"] is False
    assert scan["truth_contract"]["no_duplicate_truth_publisher"] is True
