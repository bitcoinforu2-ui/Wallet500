import json
from datetime import datetime, timedelta, timezone

from wallet500.research_sample_accelerator import MODE, run


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def watch(token="T", pair="P", tier="NEAR_ALERT", readiness=6, execution_liq=100_000, blockers=None):
    return {
        "symbol": token,
        "chain": "solana",
        "token_address": token,
        "pair_address": pair,
        "radar_tier": tier,
        "status": "EVIDENCE_READY_NOT_REAL_ALERT" if tier == "NEAR_ALERT" else "VERIFIED_WATCH_NOT_REAL_ALERT",
        "readiness_passed": readiness,
        "readiness_total": 7,
        "missing_gates": ["STRONG_DECISION_LANE"],
        "blockers": blockers or ["NO_STRONG_DECISION_LANE"],
        "signal_score": 68.0,
        "exact_identity_verified": True,
        "exact_pair_verified": True,
        "market_age_verified": True,
        "price_usd": 1.0,
        "execution_pool_liquidity_usd": execution_liq,
    }


def test_forward_shadow_enrollment_is_separate_and_deduplicated(tmp_path):
    now = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    row = watch()
    row["watch_added_at"] = now.isoformat()
    write(tmp_path / "real-alerts.json", {"generated_at": now.isoformat(), "verified_watch": [row]})
    write(tmp_path / "alpha-proof-report.json", {
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "primary_proof_status": "COLLECTING_FORWARD_SAMPLE",
        "sample_maturity": {"mature_24h_signal_count": 1, "mature_24h_control_count": 0},
    })

    first = run(tmp_path, now=now, fetcher=lambda _: None)
    second = run(tmp_path, now=now + timedelta(minutes=5), fetcher=lambda _: None)

    assert first["mode"] == MODE
    assert first["record_count"] == 1
    assert second["record_count"] == 1
    assert second["enrolled_this_run"] == 0
    assert first["formal_alpha_proof_unchanged"] is True
    assert first["guardrails"]["real_alert_gate_changed"] is False
    assert first["guardrails"]["telegram_alerts_changed"] is False
    assert first["formal_alpha_context"]["mature_24h_signal_count"] == 1


def test_due_exact_pair_checkpoint_builds_24h_learning_stats(tmp_path):
    now = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    row = watch()
    row["watch_added_at"] = now.isoformat()
    write(tmp_path / "real-alerts.json", {"generated_at": now.isoformat(), "verified_watch": [row]})
    write(tmp_path / "alpha-proof-report.json", {})
    run(tmp_path, now=now, fetcher=lambda _: None)

    calls = []

    def fetcher(probe):
        calls.append(probe)
        return {"priceUsd": "1.50", "liquidity": {"usd": 120_000}}

    report = run(tmp_path, now=now + timedelta(hours=25), fetcher=fetcher)
    h24 = report["horizons"]["24h"]["verified_execution_subset"]
    assert len(calls) == 1
    assert report["checkpoint_fetch"]["succeeded"] == 1
    assert h24["n"] == 1
    assert h24["class_counts"]["WINNER"] == 1
    assert h24["mean_friction_adjusted_return_pct"] == 48.0
    assert report["sample_acceleration"]["usable_remaining"] == 19


def test_unverified_depth_is_observational_not_tradable(tmp_path):
    now = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    row = watch(execution_liq=0, blockers=["EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL"])
    row["liquidity_usd"] = 5_000_000
    row["watch_added_at"] = now.isoformat()
    write(tmp_path / "real-alerts.json", {"generated_at": now.isoformat(), "verified_watch": [row]})
    write(tmp_path / "alpha-proof-report.json", {})
    report = run(tmp_path, now=now, fetcher=lambda _: None)
    assert report["record_count"] == 1
    assert report["verified_execution_record_count"] == 0


def test_actionable_or_low_readiness_rows_never_enter_shadow(tmp_path):
    now = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    actionable = watch(token="A", pair="PA")
    actionable["actionable_research_alert"] = True
    low = watch(token="B", pair="PB", readiness=4)
    write(tmp_path / "real-alerts.json", {"generated_at": now.isoformat(), "verified_watch": [actionable, low]})
    write(tmp_path / "alpha-proof-report.json", {})
    report = run(tmp_path, now=now, fetcher=lambda _: None)
    assert report["record_count"] == 0
    assert report["blocked_enrollment_reasons"]["ACTIONABLE_ROW_EXCLUDED_FROM_SHADOW"] == 1
    assert report["blocked_enrollment_reasons"]["READINESS_LT_5_OF_7"] == 1
