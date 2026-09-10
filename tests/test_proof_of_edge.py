from datetime import datetime, timezone
import json

from wallet500.proof_of_edge import MODE, run


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _alpha_signal(token: str, pair: str, ret: float) -> dict:
    return {
        "lane": "PRODUCTION_FIRST_QUALIFIED",
        "key": f"bsc|{token}|{pair}",
        "chain": "bsc",
        "token": token,
        "pair_address": pair,
        "event_at": "2026-09-10T00:00:00+00:00",
        "entry_price_usd": 1.0,
        "entry_liquidity_usd": 50000,
        "checkpoints": {"24h": {"friction_adjusted_return_pct": ret}},
    }


def _alpha_control(token: str, pair: str, source_key: str, ret: float) -> dict:
    return {
        "lane": "REJECTED_TRADABLE_CONTROL",
        "key": f"bsc|{token}|{pair}",
        "chain": "bsc",
        "token": token,
        "pair_address": pair,
        "event_at": "2026-09-10T00:00:00+00:00",
        "entry_price_usd": 1.0,
        "entry_liquidity_usd": 50000,
        "source_record_key": source_key,
        "checkpoints": {"24h": {"friction_adjusted_return_pct": ret}},
    }


def _base_files(tmp_path, signals, controls, rejected_records):
    write(tmp_path / "alpha-proof-ledger.json", {
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "activation_at": "2026-09-03T00:00:00+00:00",
        "signals": signals,
        "controls": controls,
    })
    write(tmp_path / "alpha-proof-report.json", {"primary_proof_status": "COLLECTING_FORWARD_SAMPLE"})
    write(tmp_path / "discovery-evidence-ledger.json", {
        "records": {
            "sig": {
                "observed_at": "2026-09-10T00:00:00+00:00",
                "identity": {"chain": "bsc", "token": "0xa", "pair_address": "0xp"},
                "signals": {"anomaly_score": 91},
            }
        }
    })
    write(tmp_path / "rejected-candidate-ledger.json", {"records": rejected_records})


def test_decision_context_is_frozen_and_outcomes_are_classified(tmp_path):
    snap = {
        "chain": "bsc",
        "token": "0xb",
        "pair_address": "0xq",
        "production_risk_reasons": ["BAD_LP"],
    }
    _base_files(
        tmp_path,
        {"s1": _alpha_signal("0xa", "0xp", 40.0)},
        {"c1": _alpha_control("0xb", "0xq", "rk", 120.0)},
        {
            "rk": {
                "identity": {"chain": "bsc", "token": "0xb", "pair_address": "0xq"},
                "first_reject_source": "PRODUCTION_RISK_BLOCK",
                "first_decision_class": "REJECT",
                "first_reject_snapshot": snap,
            }
        },
    )

    first = run(tmp_path, now=datetime(2026, 9, 11, tzinfo=timezone.utc))
    assert first["mode"] == MODE
    assert first["integrity"]["status"] == "PASS"
    assert first["decision_matrix"]["24h"]["class_counts"]["TRUE_POSITIVE_WINNER"] == 1
    assert first["decision_matrix"]["24h"]["class_counts"]["MISSED_BIG_WINNER"] == 1
    assert first["exceptions_24h"]["missed_winners"][0]["reasons"] == [
        "BAD_LP",
        "SOURCE:PRODUCTION_RISK_BLOCK",
    ]
    assert first["guardrails"]["production_scoring_changed"] is False
    assert first["guardrails"]["automatic_weight_mutation"] is False

    ledger_before = json.loads((tmp_path / "proof-of-edge-ledger.json").read_text())
    contexts_before = {
        key: (row["decision_context"], row["decision_context_sha256"])
        for key, row in ledger_before["records"].items()
    }

    write(tmp_path / "discovery-evidence-ledger.json", {"records": {}})
    write(tmp_path / "rejected-candidate-ledger.json", {"records": {}})
    second = run(tmp_path, now=datetime(2026, 9, 12, tzinfo=timezone.utc))
    ledger_after = json.loads((tmp_path / "proof-of-edge-ledger.json").read_text())
    contexts_after = {
        key: (row["decision_context"], row["decision_context_sha256"])
        for key, row in ledger_after["records"].items()
    }
    assert contexts_after == contexts_before
    assert second["integrity"]["status"] == "PASS"


def test_blocker_review_requires_repeated_missed_winner_evidence(tmp_path):
    controls = {}
    rejected = {}
    for i, ret in enumerate((25.0, 30.0, 35.0, -25.0, 40.0), start=1):
        token = f"0x{i}"
        pair = f"0xp{i}"
        source_key = f"rk{i}"
        controls[f"c{i}"] = _alpha_control(token, pair, source_key, ret)
        rejected[source_key] = {
            "identity": {"chain": "bsc", "token": token, "pair_address": pair},
            "first_reject_source": "LIVE_SURVIVAL_FAILED",
            "first_decision_class": "REJECT",
            "first_reject_snapshot": {
                "chain": "bsc",
                "token": token,
                "pair_address": pair,
                "live_survival_reasons": ["LIQUIDITY_BELOW_POLICY"],
            },
        }

    _base_files(tmp_path, {}, controls, rejected)
    report = run(tmp_path, now=datetime(2026, 9, 11, tzinfo=timezone.utc))
    blocker = next(x for x in report["blocker_attribution_24h"] if x["reason"] == "LIQUIDITY_BELOW_POLICY")
    assert blocker["n"] == 5
    assert blocker["missed_winners"] == 4
    assert blocker["avoided_losers"] == 1
    assert blocker["review_candidate"] is True
    assert report["learning_review_queue"][0]["production_change_allowed"] is False


def test_integrity_failure_is_reported_if_frozen_context_is_tampered(tmp_path):
    _base_files(tmp_path, {"s1": _alpha_signal("0xa", "0xp", 10.0)}, {}, {})
    run(tmp_path, now=datetime(2026, 9, 11, tzinfo=timezone.utc))
    ledger = json.loads((tmp_path / "proof-of-edge-ledger.json").read_text())
    rec = next(iter(ledger["records"].values()))
    rec["decision_context"]["evidence"]["entry_price_usd"] = 999
    write(tmp_path / "proof-of-edge-ledger.json", ledger)

    report = run(tmp_path, now=datetime(2026, 9, 12, tzinfo=timezone.utc))
    assert report["integrity"]["status"] == "FAIL"
    assert report["integrity"]["hash_mismatch_count"] == 1
