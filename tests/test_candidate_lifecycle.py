import json

from wallet500.candidate_lifecycle import MODE, build


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def sample_record():
    return {
        "lane": "VERIFIED_WATCH_SHADOW",
        "key": "solana|TOK|PAIR",
        "chain": "solana",
        "token_address": "TOK",
        "pair_address": "PAIR",
        "event_at": "2026-09-10T10:00:00+00:00",
        "enrolled_at": "2026-09-10T10:01:00+00:00",
        "entry_price_usd": 1.0,
        "decision_snapshot": {"entry": {"readiness_passed": 6, "readiness_total": 7, "missing_gates": ["STRONG_DECISION_LANE"], "verified_execution_liquidity_usd": 100000}},
        "checkpoints": {"6h": {"friction_adjusted_return_pct": 23.0}},
        "latest_return_pct": 25.0,
        "latest_friction_adjusted_return_pct": 23.0,
    }


def test_candidate_moves_to_shadow_instead_of_disappearing(tmp_path):
    write(tmp_path / "research-sample-ledger.json", {"mode": "RESEARCH_ONLY_FORWARD_SAMPLE_ACCELERATOR_V1", "updated_at": "2026-09-10T16:00:00+00:00", "records": {"SHADOW|solana|TOK|PAIR": sample_record()}})
    write(tmp_path / "research-sample-report.json", {"gate_attribution_24h": [], "learning_review_queue": [], "sample_acceleration": {"mature_24h_count": 0}})
    write(tmp_path / "real-alerts.json", {"generated_at": "2026-09-10T16:00:00+00:00", "alerts": [], "verified_watch": []})
    out = build(tmp_path, observed_at="2026-09-10T16:00:01+00:00")
    assert out["mode"] == MODE
    assert out["candidate_count"] == 1
    row = out["candidates"][0]
    assert row["lifecycle_state"] == "SHADOW_LEARNING"
    assert row["reason_code"] == "LEFT_LIVE_RADAR"
    assert row["outcome"]["status"] == "WINNER"
    assert out["truth_contract"]["candidate_never_disappears_when_it_leaves_live_radar"] is True


def test_live_six_of_seven_gets_decision_blocked_reason(tmp_path):
    write(tmp_path / "research-sample-ledger.json", {"records": {"SHADOW|solana|TOK|PAIR": sample_record()}})
    write(tmp_path / "research-sample-report.json", {})
    write(tmp_path / "real-alerts.json", {"alerts": [], "verified_watch": [{"chain": "solana", "token_address": "TOK", "pair_address": "PAIR", "symbol": "RAY", "readiness_passed": 6, "readiness_total": 7, "missing_gates": ["STRONG_DECISION_LANE"], "exact_pair_verified": True, "blockers": ["NO_STRONG_DECISION_LANE"]}]})
    out = build(tmp_path)
    row = out["candidates"][0]
    assert row["lifecycle_state"] == "LIVE_6_OF_7"
    assert row["reason_code"] == "DECISION_BLOCKED"
    assert row["symbol"] == "RAY"


def test_promoted_candidate_is_kept_with_promotion_reason(tmp_path):
    write(tmp_path / "research-sample-ledger.json", {"records": {"SHADOW|solana|TOK|PAIR": sample_record()}})
    write(tmp_path / "research-sample-report.json", {})
    write(tmp_path / "real-alerts.json", {"verified_watch": [], "alerts": [{"chain": "solana", "token_address": "TOK", "pair_address": "PAIR", "symbol": "TOK"}]})
    out = build(tmp_path)
    row = out["candidates"][0]
    assert row["lifecycle_state"] == "PROMOTED"
    assert row["reason_code"] == "PROMOTED_REAL_ALERT"


def test_previous_real_alert_losing_only_confirmation_gates_enters_revalidation(tmp_path):
    write(tmp_path / "research-sample-ledger.json", {"records": {"SHADOW|solana|TOK|PAIR": sample_record()}})
    write(tmp_path / "research-sample-report.json", {})
    write(tmp_path / "candidate-lifecycle.json", {
        "candidates": [{
            "identity_key": "solana|TOK|PAIR",
            "lifecycle_state": "PROMOTED",
            "current_source_lanes": ["CEX_REVIVAL", "MULTICHAIN_VETERAN_REVIVAL"],
        }]
    })
    write(tmp_path / "real-alerts.json", {
        "alerts": [],
        "verified_watch": [{
            "chain": "solana",
            "token_address": "TOK",
            "pair_address": "PAIR",
            "symbol": "VVV",
            "readiness_passed": 5,
            "readiness_total": 7,
            "missing_gates": ["STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION"],
            "exact_pair_verified": True,
            "blockers": ["NO_STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION_LT_2"],
            "source_lanes": ["CEX_REVIVAL"],
        }],
    })
    out = build(tmp_path)
    row = out["candidates"][0]
    assert row["lifecycle_state"] == "LIVE_CONFIRMATION_LOST"
    assert row["reason_code"] == "CONFIRMATION_REVALIDATION_REQUIRED"
    assert row["transition"] == "PROMOTED->LIVE_CONFIRMATION_LOST"
    assert row["confirmation_revalidation_required"] is True
    assert row["actionable"] is False
    assert row["automatic_buy"] is False
    assert row["lost_source_lanes"] == ["MULTICHAIN_VETERAN_REVIVAL"]
    assert out["truth_contract"]["confirmation_loss_does_not_preserve_real_alert"] is True


def test_hard_gate_failure_never_masquerades_as_confirmation_loss(tmp_path):
    write(tmp_path / "research-sample-ledger.json", {"records": {"SHADOW|solana|TOK|PAIR": sample_record()}})
    write(tmp_path / "research-sample-report.json", {})
    write(tmp_path / "candidate-lifecycle.json", {"candidates": [{"identity_key": "solana|TOK|PAIR", "lifecycle_state": "PROMOTED"}]})
    write(tmp_path / "real-alerts.json", {
        "alerts": [],
        "verified_watch": [{
            "chain": "solana",
            "token_address": "TOK",
            "pair_address": "PAIR",
            "symbol": "TOK",
            "readiness_passed": 4,
            "readiness_total": 7,
            "missing_gates": ["EXECUTION_LIQUIDITY", "STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION"],
            "exact_pair_verified": True,
            "blockers": ["EXECUTION_POOL_LIQUIDITY_LT_15K", "NO_STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION_LT_2"],
        }],
    })
    out = build(tmp_path)
    row = out["candidates"][0]
    assert row["lifecycle_state"] == "LIVE_REGRESSED"
    assert row["reason_code"] == "FAILED_OR_UNVERIFIED_LIQUIDITY"
    assert row["confirmation_revalidation_required"] is False
