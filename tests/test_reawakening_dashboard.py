import json
from pathlib import Path

from wallet500.reawakening_dashboard import build


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_reawakening_dashboard_builds_near_and_trigger_rows(tmp_path: Path) -> None:
    data = tmp_path
    key_near = "solana|near|pair-near"
    key_trigger = "solana|fire|pair-fire"

    _write(
        data / "rejected-candidate-ledger.json",
        {
            "records": {
                key_near: {
                    "first_rejected_at": "2026-09-07T10:00:00+00:00",
                    "first_reject_snapshot": {
                        "symbol": "NEAR",
                        "price_usd": 1.0,
                    },
                },
                key_trigger: {
                    "first_rejected_at": "2026-09-07T10:00:00+00:00",
                    "first_reject_snapshot": {
                        "symbol": "FIRE",
                        "price_usd": 1.0,
                    },
                },
            }
        },
    )
    _write(
        data / "reawakening-forward-state.json",
        {
            "candidates": {
                key_near: {
                    "chain": "solana",
                    "token": "near",
                    "pair_address": "pair-near",
                    "first_rejected_at": "2026-09-07T10:00:00+00:00",
                    "hot_observations": [
                        {
                            "observed_at": "2026-09-07T11:00:00+00:00",
                            "pair_address": "pair-near",
                            "price_usd": 1.1,
                            "liquidity_usd": 60000,
                            "volume_h1": 50000,
                            "buys_h1": 240,
                            "sells_h1": 160,
                        }
                    ],
                }
            }
        },
    )
    _write(
        data / "reawakening-forward-report.json",
        {
            "eligible_rejects": 2,
            "state_hot_observations": 10,
            "exact_pair_successes": 1,
            "exact_pair_misses": 1,
            "observations_added_this_run": 1,
        },
    )
    _write(
        data / "reawakening-shadow.json",
        {
            "generated_at": "2026-09-07T11:00:00+00:00",
            "counts": {
                "eligible_liquidity_only_rejects": 2,
                "shadow_triggers_v2": 1,
            },
            "targets": [
                {
                    "token_key": key_trigger,
                    "chain": "solana",
                    "token": "fire",
                    "pair_address": "pair-fire",
                    "triggered_at": "2026-09-07T11:00:00+00:00",
                    "metrics": {
                        "liquidity_usd": 70000,
                        "volume_h1_usd": 65000,
                        "turnover_h1": 0.9,
                        "txns_h1": 500,
                        "buy_sell_ratio_h1": 1.5,
                    },
                }
            ],
        },
    )

    result = build(str(data))

    assert result["counts"]["tracked_eligible"] == 2
    assert result["counts"]["reawakening_triggers"] == 1
    assert result["triggers"][0]["special_marker"] == "🔥 REAWAKENED"
    assert result["triggers"][0]["symbol"] == "FIRE"
    assert result["near_recovery"][0]["symbol"] == "NEAR"
    assert result["near_recovery"][0]["snapshot_gates_passed"] == 6
    assert result["near_recovery"][0]["status"] == "SNAPSHOT_READY_WAITING_CONFIRMATION"
    assert (data / "reawakening-dashboard.json").exists()
