import json
from pathlib import Path

from wallet500.engine_learning_review import run as review
from wallet500.prospective_benchmark import run as benchmark


def put(root: Path, name: str, payload: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def base_revival():
    return {
        "network": "solana", "no_hindsight": True,
        "active_deep_watch": [{"network": "solana", "token_address": "T", "pair_address": "P"}],
    }


def test_evidence_freezes_only_on_first_stage_observation(tmp_path):
    put(tmp_path, "revival-1000-latest.json", base_revival())
    put(tmp_path, "waking-confirmation-latest.json", {
        "generated_at": "2026-09-11T10:00:00+00:00",
        "targets": [{"network": "solana", "token_address": "T", "confirmation_score": 10, "signals": ["EARLY"]}],
    })
    put(tmp_path, "waking-pre-t0-confirmation.json", {"generated_at": "2026-09-11T10:01:00+00:00", "targets": []})
    put(tmp_path, "real-alerts.json", {"generated_at": "2026-09-11T10:02:00+00:00", "alerts": []})
    benchmark(tmp_path, "2026-09-11T10:03:00+00:00")
    ledger=json.loads((tmp_path/"prospective-benchmark-ledger.json").read_text())
    key="solana|T|p"
    assert ledger["records"][key]["stages"]["WAKING"]["frozen_evidence"]["confirmation_score"] == 10

    put(tmp_path, "waking-confirmation-latest.json", {
        "generated_at": "2026-09-11T12:00:00+00:00",
        "targets": [{"network": "solana", "token_address": "T", "confirmation_score": 99, "signals": ["LATE"]}],
    })
    benchmark(tmp_path, "2026-09-11T12:01:00+00:00")
    ledger=json.loads((tmp_path/"prospective-benchmark-ledger.json").read_text())
    frozen=ledger["records"][key]["stages"]["WAKING"]["frozen_evidence"]
    assert frozen["confirmation_score"] == 10
    assert frozen["signals"] == ["EARLY"]
    assert ledger["records"][key]["stages"]["WAKING"]["frozen_evidence_backfilled"] is False


def test_provider_failure_never_becomes_positive_and_review_is_research_only(tmp_path):
    put(tmp_path, "prospective-benchmark-ledger.json", {
        "version": "WALLET500_PROSPECTIVE_BENCHMARK_V1",
        "no_hindsight": True, "production_effect": False,
        "records": {"solana|T|p": {"identity": "solana|T|p", "stages": {"WAKING": {"first_seen_at": "2026-09-11T10:00:00+00:00"}}}},
    })
    put(tmp_path, "prospective-benchmark-latest.json", {"counts": {"cohort": 1, "waking": 1, "pre_t0": 0, "production": 0}})
    put(tmp_path, "waking-confirmation-latest.json", {
        "targets": [{"provider_status": [{"provider": "x", "status": "HTTP_402"}, {"provider": "rugcheck", "status": "OK"}]}]
    })
    out=review(tmp_path, "2026-09-11T10:30:00+00:00")
    assert out["production_effect"] is False and out["no_hindsight"] is True
    assert out["provider_health"]["providers"]["x"]["state"] == "UNAVAILABLE"
    assert out["provider_health"]["providers"]["rugcheck"]["state"] == "HEALTHY"
    assert "x" in out["provider_health"]["degraded_providers"]


def test_no_missed_winner_is_invented_without_canonical_outcome(tmp_path):
    put(tmp_path, "prospective-benchmark-ledger.json", {
        "version": "WALLET500_PROSPECTIVE_BENCHMARK_V1", "no_hindsight": True, "production_effect": False,
        "records": {"solana|T|p": {"identity": "solana|T|p", "stages": {"PRE_T0": {"first_seen_at": "2026-09-11T10:00:00+00:00"}}}},
    })
    put(tmp_path, "prospective-benchmark-latest.json", {"counts": {"cohort": 1}})
    put(tmp_path, "waking-confirmation-latest.json", {"targets": []})
    out=review(tmp_path, "2026-09-11T11:00:00+00:00")
    assert out["missed_outcomes"]["count"] == 0
    assert out["truth_contract"]["outcome_success_threshold_invented_here"] is False


def test_exact_pair_isolation_for_same_token(tmp_path):
    put(tmp_path, "prospective-benchmark-ledger.json", {
        "version": "WALLET500_PROSPECTIVE_BENCHMARK_V1", "no_hindsight": True, "production_effect": False,
        "records": {
            "solana|T|p1": {"identity": "solana|T|p1", "stages": {"WAKING": {"first_seen_at": "2026-09-11T10:00:00+00:00"}}},
            "solana|T|p2": {"identity": "solana|T|p2", "stages": {"WAKING": {"first_seen_at": "2026-09-11T10:05:00+00:00"}}},
        },
    })
    put(tmp_path, "prospective-benchmark-latest.json", {"counts": {"cohort": 2}})
    put(tmp_path, "waking-confirmation-latest.json", {"targets": []})
    out=review(tmp_path, "2026-09-11T11:00:00+00:00")
    ids={x["identity"] for x in out["prospective_cohort"]["rows"]}
    assert ids == {"solana|T|p1", "solana|T|p2"}
