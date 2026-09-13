import json
from pathlib import Path

from wallet500.accuracy_research import MODE, build


def write(path: Path, name: str, payload: dict) -> None:
    (path / name).write_text(json.dumps(payload), encoding="utf-8")


def test_accuracy_lab_is_research_only_and_preserves_production(tmp_path: Path):
    write(
        tmp_path,
        "research-sample-report.json",
        {
            "record_count": 10,
            "verified_execution_record_count": 8,
            "sample_acceleration": {"mature_24h_count": 5, "strong_target": 50, "deep_target": 100},
            "horizons": {"24h": {"verified_execution_subset": {"winner_rate_pct": 12.5}}},
            "gate_attribution_24h": [
                {
                    "gate_or_blocker": "INDEPENDENT_CONFIRMATION_LT_2",
                    "n": 4,
                    "winner_count": 1,
                    "big_winner_count": 0,
                    "winner_rate_pct": 25.0,
                    "mean_friction_adjusted_return_pct": 6.0,
                }
            ],
        },
    )
    write(
        tmp_path,
        "research-sample-ledger.json",
        {
            "records": {
                "a": {
                    "decision_snapshot": {
                        "entry": {
                            "readiness_passed": 6,
                            "readiness_total": 7,
                            "source_lane_count": 1,
                            "missing_gates": ["INDEPENDENT_CONFIRMATION"],
                            "evidence_positive_count": 1,
                        }
                    },
                    "checkpoints": {"24h": {"friction_adjusted_return_pct": 30.0}},
                },
                "b": {
                    "decision_snapshot": {
                        "entry": {
                            "readiness_passed": 5,
                            "readiness_total": 7,
                            "source_lane_count": 0,
                            "missing_gates": ["A", "B"],
                            "evidence_positive_count": 0,
                        }
                    },
                    "checkpoints": {"24h": {"friction_adjusted_return_pct": -2.0}},
                },
            }
        },
    )
    write(
        tmp_path,
        "real-alert-10usd-ledger.json",
        {
            "positions": [
                {
                    "entry_signal_dna": {"feature_coverage_ratio": 0.2},
                    "peak_return_pct": 60.0,
                    "trough_return_pct": -3.0,
                    "original_signal_t0": "2026-09-10T00:00:00Z",
                    "entry_time": "2026-09-10T06:00:00Z",
                },
                {
                    "entry_signal_dna": {"feature_coverage_ratio": 0.8},
                    "peak_return_pct": 5.0,
                    "trough_return_pct": -9.0,
                    "original_signal_t0": "2026-09-10T00:00:00Z",
                    "entry_time": "2026-09-10T02:00:00Z",
                },
            ]
        },
    )
    write(
        tmp_path,
        "decision-only-shadow.json",
        {"horizons": {"24h": {"n": 4, "winner_count": 0, "winner_rate_pct": 0.0, "mean_friction_adjusted_return_pct": 1.0}}},
    )

    out = build(tmp_path)

    assert out["mode"] == MODE
    assert out["research_only"] is True
    assert out["production_effect"] is False
    assert out["automatic_buy"] is False
    assert out["production_thresholds_modified"] is False
    assert out["guardrails"]["real_alert_gate_changed"] is False
    assert out["sample"]["mature_24h"] == 5
    assert out["sample"]["next_strong_sample_remaining"] == 45
    assert out["findings"][0]["id"] == "INDEPENDENT_CONFIRMATION_FALSE_NEGATIVE"
    assert out["findings"][0]["winner_count"] == 1
    assert out["findings"][1]["winner_count_24h"] == 0
    assert out["gate_distance"]["one_gate_short"]["winner_count"] == 1
    assert out["t0_coverage_freshness"]["low_coverage_under_50pct_count"] == 1
    assert out["barrier_probabilities"]["probabilities_publishable"] is False


def test_missing_inputs_fail_open_for_research_but_never_mutate_production(tmp_path: Path):
    out = build(tmp_path)
    assert out["mode"] == MODE
    assert out["sample"]["mature_24h"] == 0
    assert out["production_effect"] is False
    assert out["automatic_buy"] is False
    assert out["guardrails"]["no_hindsight_threshold_tuning"] is True
