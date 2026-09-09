import json
from pathlib import Path

from wallet500.near_alert_observatory import build, run


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_near_alert_observatory_is_research_only_and_ranks_closest(tmp_path: Path):
    _write(tmp_path / "real-alerts.json", {
        "counts": {"real_alerts": 0, "near_alert_not_real": 1, "verified_watch_not_real": 2, "new_watch_24h": 2},
        "verified_watch": [
            {
                "symbol": "FIVE", "chain": "solana", "token_address": "A", "pair_address": "PA",
                "radar_tier": "VERIFIED_WATCH", "readiness_passed": 5, "readiness_total": 7,
                "readiness_pct": 71.4, "missing_gates": ["STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION"],
                "blockers": ["NO_STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION_LT_2"],
                "signal_score": 90, "exact_identity_verified": True, "exact_pair_verified": True,
                "market_age_verified": True,
                "execution_pool_liquidity_usd": 0,
                "provider_reported_pool_value_usd": 100_000,
                "dex_volume_h1": 5_000,
                "dex_volume_h24": 80_000,
                "dex_activity_truth": {"volume_h1_usd": 5_000, "volume_h24_usd": 80_000, "verified": True},
            },
            {
                "symbol": "SIX", "chain": "solana", "token_address": "B", "pair_address": "PB",
                "radar_tier": "NEAR_ALERT", "readiness_passed": 6, "readiness_total": 7,
                "readiness_pct": 85.7, "missing_gates": ["STRONG_DECISION_LANE"],
                "blockers": ["NO_STRONG_DECISION_LANE"], "signal_score": 70,
                "exact_identity_verified": True, "exact_pair_verified": True, "market_age_verified": True,
                "execution_pool_liquidity_usd": 250_000,
                "dex_volume_h1": 25_000,
                "buys_h1": 40,
                "sells_h1": 20,
            },
        ],
    })
    _write(tmp_path / "revival-funnel-diagnostics.json", {
        "lanes": {
            "solana_veteran_revival": {"universe": 298},
            "evidence_promotion": {"universe_with_exact_pair": 285, "evidence_ready": 6, "blocked_truth": 32},
            "reawakening_recovery": {"eligible_liquidity_only_rejects": 388, "outcome_tracker_matches": 380, "shadow_triggers_v2": 0},
        },
        "blockers": [{"code": "EXECUTION_LIQUIDITY_LT_15K", "count": 29, "classification": "HARD_TRUTH_OR_RISK_BLOCKER"}],
        "pending_confirmations": [{"code": "PRECURSOR_EVIDENCE_INSUFFICIENT", "count": 96, "classification": "PENDING_CONFIRMATION_NOT_HARD_FAILURE"}],
    })
    _write(tmp_path / "reawakening-shadow.json", {"mode": "RESEARCH_ONLY_SURVIVOR_REAWAKENING_V2", "contract": "FALSE_NEGATIVE_RECOVERY_RECHECK_V2", "counts": {"eligible_liquidity_only_rejects": 388, "shadow_triggers_v2": 0}})
    _write(tmp_path / "real-alert-10usd-summary.json", {"mode": "PAPER_ONLY_NO_REAL_MONEY", "position_size_usd": 10, "positions_total": 0, "roi_pct": 0, "new_entry_trigger": "SUCCESSFULLY_DELIVERED_NEW_TELEGRAM_REAL_ALERT_AFTER_ACTIVATION_ONLY"})

    out = build(tmp_path)
    assert out["production_change"] is False
    assert out["automatic_buy"] is False
    assert out["truth_contract"]["real_alert_gate_changed"] is False
    assert out["truth_contract"]["near_alert_is_not_real_alert"] is True
    assert out["closest_to_real_alert"][0]["symbol"] == "SIX"
    assert out["near_alert_leaderboard"][0]["readiness_passed"] == 6
    assert out["near_alert_leaderboard"][0]["automatic_buy"] is False
    assert out["near_alert_leaderboard"][0]["liquidity_usd"] == 250_000
    assert out["near_alert_leaderboard"][0]["dex_volume_h1"] == 25_000
    assert out["near_alert_leaderboard"][0]["turnover_h1"] == 0.1
    assert out["near_alert_leaderboard"][0]["buys_h1"] == 40
    assert out["closest_to_real_alert"][1]["liquidity_usd"] == 100_000
    assert out["closest_to_real_alert"][1]["execution_pool_liquidity_usd"] == 0
    assert out["closest_to_real_alert"][1]["liquidity_display_semantics"] == "PROVIDER_REPORTED_EXACT_PAIR_POOL_VALUE_INFORMATIONAL_ONLY"
    assert out["closest_to_real_alert"][1]["market_activity_verified"] is True
    assert out["summary"]["liquidity_only_false_negative_population"] == 388
    assert out["canonical_hard_blockers"][0]["count"] == 29
    assert out["pending_confirmations"][0]["count"] == 96


def test_run_writes_observatory_file(tmp_path: Path):
    _write(tmp_path / "real-alerts.json", {"counts": {}, "verified_watch": []})
    _write(tmp_path / "revival-funnel-diagnostics.json", {})
    _write(tmp_path / "reawakening-shadow.json", {})
    _write(tmp_path / "real-alert-10usd-summary.json", {})
    out = run(tmp_path)
    saved = json.loads((tmp_path / "near-alert-observatory.json").read_text(encoding="utf-8"))
    assert saved["mode"] == out["mode"]
    assert saved["truth_contract"]["signal_score_is_probability"] is False
