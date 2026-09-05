from datetime import datetime, timezone
from pathlib import Path

from wallet500.system_integrity_audit import (
    DOGE1_CA,
    _audit_doge1,
    _audit_liquidity_truth,
    _audit_real_alerts,
    _audit_survivors,
    _audit_wallet_flow,
    _freshness,
    run,
)


def codes(findings):
    return {x["code"] for x in findings}


def test_survivor_truth_contract_blocks_automatic_buy():
    findings = []
    payload = {
        "mode": "HOURLY_WINNER_SURVIVOR_WAVE_WATCH_V1",
        "research_only": True,
        "automatic_buy": True,
        "exact_pair_only": True,
        "source_method": "WINNER_SEPARATOR_NO_HINDSIGHT_V1",
        "survivor_n": 0,
        "liquidity_survival_floor_usd": 50000,
        "tokens": [],
    }
    _audit_survivors(payload, findings)
    assert "SURVIVOR_TRUTH_CONTRACT_BROKEN" in codes(findings)
    assert any(x["severity"] == "CRITICAL" for x in findings)


def test_survivor_pair_identity_collision_is_critical():
    findings = []
    base = {
        "mode": "HOURLY_WINNER_SURVIVOR_WAVE_WATCH_V1",
        "research_only": True,
        "automatic_buy": False,
        "exact_pair_only": True,
        "source_method": "WINNER_SEPARATOR_NO_HINDSIGHT_V1",
        "survivor_n": 2,
        "liquidity_survival_floor_usd": 50000,
    }
    row = {
        "chain": "solana",
        "pair_address": "PAIR",
        "liquidity_usd": 100000,
        "survival": "EXACT_PAIR_LIQUIDITY_SURVIVED",
    }
    payload = {**base, "tokens": [{**row, "token": "TOKEN_A"}, {**row, "token": "TOKEN_B"}]}
    _audit_survivors(payload, findings)
    assert "PAIR_IDENTITY_COLLISION" in codes(findings)


def test_survivor_below_floor_cannot_survive():
    findings = []
    payload = {
        "mode": "HOURLY_WINNER_SURVIVOR_WAVE_WATCH_V1",
        "research_only": True,
        "automatic_buy": False,
        "exact_pair_only": True,
        "source_method": "WINNER_SEPARATOR_NO_HINDSIGHT_V1",
        "survivor_n": 1,
        "liquidity_survival_floor_usd": 50000,
        "tokens": [{
            "chain": "solana",
            "token": "TOKEN",
            "pair_address": "PAIR",
            "liquidity_usd": 49999,
            "survival": "EXACT_PAIR_LIQUIDITY_SURVIVED",
        }],
    }
    _audit_survivors(payload, findings)
    assert "SURVIVOR_BELOW_LIQUIDITY_SURVIVAL_FLOOR" in codes(findings)


def test_concentrated_tvl_never_masquerades_as_execution_liquidity():
    findings = []
    yzy = {
        "chain": "solana",
        "token_address": "YZY",
        "pair_address": "PAIR",
        "dex": "meteora",
        "pool_type": "DLMM",
        "execution_depth_verified": False,
        "execution_pool_liquidity_usd": 37_200_000,
    }
    payloads = {
        "cex-revival-radar.json": {"alerts": [yzy]},
        "real-alerts.json": {"alerts": [], "verified_watch": []},
        "active-qualified-candidates.json": [],
        "production-risk-evaluations.json": [],
    }
    _audit_liquidity_truth(payloads, findings)
    assert "CONCENTRATED_TVL_MASQUERADING_AS_EXECUTION_LIQUIDITY" in codes(findings)
    assert any(x["severity"] == "CRITICAL" for x in findings)


def test_verified_execution_depth_allows_concentrated_pool():
    findings = []
    row = {
        "chain": "solana",
        "token_address": "YZY",
        "pair_address": "PAIR",
        "dex": "meteora",
        "pool_type": "DLMM",
        "execution_depth_verified": True,
        "execution_depth_usd_5pct": 500000,
        "execution_pool_liquidity_usd": 37_200_000,
    }
    payloads = {
        "cex-revival-radar.json": {"alerts": [row]},
        "real-alerts.json": {"alerts": [], "verified_watch": []},
        "active-qualified-candidates.json": [],
        "production-risk-evaluations.json": [],
    }
    _audit_liquidity_truth(payloads, findings)
    assert "CONCENTRATED_TVL_MASQUERADING_AS_EXECUTION_LIQUIDITY" not in codes(findings)


def test_real_alert_younger_than_180_days_is_critical():
    findings = []
    payload = {
        "counts": {"real_alerts": 1, "verified_watch_not_real": 0},
        "alerts": [{
            "chain": "solana",
            "token_address": "T",
            "pair_address": "P",
            "exact_identity_verified": True,
            "exact_pair_verified": True,
            "market_age_verified": True,
            "market_age_days": 179,
            "blockers": [],
        }],
        "verified_watch": [],
    }
    _audit_real_alerts(payload, findings)
    assert "ACTIONABLE_REAL_ALERT_TRUTH_VIOLATION" in codes(findings)


def test_verified_watch_cannot_leak_actionable_true():
    findings = []
    payload = {
        "counts": {"real_alerts": 0, "verified_watch_not_real": 1},
        "alerts": [],
        "verified_watch": [{"actionable_research_alert": True}],
    }
    _audit_real_alerts(payload, findings)
    assert "WATCH_ROW_ACTIONABLE_LEAK" in codes(findings)


def test_zero_wallet_flow_coverage_is_high_bottleneck_not_fake_data():
    findings = []
    payload = {
        "research_only": True,
        "production_gates_changed": False,
        "exact_pair_only": True,
        "verified_flow_token_n": 0,
        "tokens": [{"token": "T"}],
    }
    _audit_wallet_flow(payload, 1, findings)
    finding = next(x for x in findings if x["code"] == "WALLET_FLOW_ZERO_VERIFIED_COVERAGE")
    assert finding["severity"] == "HIGH"


def test_doge1_canonical_contract_is_locked():
    findings = []
    payload = {
        "version": 1,
        "observed_at": "2026-09-05T00:00:00+00:00",
        "token": {"contract_address": "WRONG"},
        "exact_pair": {"pair_address": "PAIR"},
        "holders": {}, "whales": {}, "social": {}, "listings": [], "news": [],
        "catalysts": [], "game_changer": {}, "changes_since_previous": [],
        "evidence_notes": [], "source_links": [],
    }
    _audit_doge1(payload, findings)
    assert "DOGE1_CANONICAL_CA_MISMATCH" in codes(findings)


def test_doge1_expected_contract_passes_identity_check():
    findings = []
    payload = {
        "version": 1,
        "observed_at": "2026-09-05T00:00:00+00:00",
        "token": {"contract_address": DOGE1_CA},
        "exact_pair": {"pair_address": "PAIR"},
        "holders": {}, "whales": {}, "social": {}, "listings": [], "news": [],
        "catalysts": [], "game_changer": {}, "changes_since_previous": [],
        "evidence_notes": [], "source_links": [],
    }
    _audit_doge1(payload, findings)
    assert "DOGE1_CANONICAL_CA_MISMATCH" not in codes(findings)


def test_stale_hourly_data_is_reported_as_high():
    findings = []
    _freshness(
        {"generated_at": "2026-09-05T00:00:00+00:00"},
        "x.json",
        findings,
        datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc),
        7200,
    )
    finding = next(x for x in findings if x["code"] == "DATA_SOURCE_STALE")
    assert finding["severity"] == "HIGH"


def test_repository_live_data_has_no_critical_integrity_findings():
    report = run(Path("data"), write_report=False)
    critical = [x for x in report["findings"] if x["severity"] == "CRITICAL"]
    assert critical == [], critical
