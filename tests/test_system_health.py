import json
from datetime import datetime, timezone

from wallet500.system_health import build_health


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _heartbeat(tmp_path, created_at="2026-08-29T23:58:00+00:00"):
    _write(tmp_path/"publish-evidence.json",{
        "version":1,
        "created_at":created_at,
        "status":"READY_TO_PUBLISH",
        "strict_validation":"PASS",
        "source_sha":"abc123",
        "run_id":"42",
    })


def test_health_is_healthy_when_critical_gates_match(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET500_WORKFLOW_DEGRADED_SECONDS", "600")
    now=datetime(2026,8,30,0,0,0,tzinfo=timezone.utc)
    _write(tmp_path/"run-summary.json",{
        "updated_at":"2026-08-29T23:55:00+00:00",
        "qualification_min_liquidity_usd":50000,
        "lane_health":{"old_coin_revival":"HEALTHY","new_token_lab":"HEALTHY"},
        "production_risk_gate":{"min_live_liquidity_usd":50000},
        "market_scan":100,"qualified":5,"revival_qualified":2,"cex_revival_alerts":20,"active_qualified":2,
    })
    _write(tmp_path/"holder-cluster-production-report.json",{
        "mode":"PRODUCTION_FAIL_CLOSED","input_count":2,"promoted_count":1,"quarantine_count":0,"blocked_count":1,
    })
    _write(tmp_path/"wallet-forensics-summary.json",{
        "updated_at":"2026-08-29T23:40:00+00:00",
        "source":"active-qualified-candidates.json",
        "lane":"PRE_PRODUCTION_EVIDENCE_GATHERING",
        "production_authorization":False,
        "active_candidates_seen":2,
        "verified_wallet_candidates":7,"solana_candidates_scanned":1,"evm_candidates_deferred":0,
    })
    _heartbeat(tmp_path)
    out=build_health(str(tmp_path),now)
    assert out["overall"]=="HEALTHY"
    assert out["pipeline_health"]=="HEALTHY"
    assert out["capability_health"]=="HEALTHY"
    assert out["checks"]["publish_pipeline"]["status"]=="HEALTHY"
    assert out["checks"]["wallet_forensics_capability"]["status"]=="HEALTHY"
    assert out["checks"]["liquidity_policy"]["status"]=="HEALTHY"
    assert out["checks"]["holder_cluster_evidence_coverage"]["status"]=="HEALTHY"
    assert out["lane_metrics"]["new_token"]["qualification_rate"]==0.05


def test_health_exposes_evidence_starvation(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET500_WORKFLOW_DEGRADED_SECONDS", "600")
    now=datetime(2026,8,30,0,0,0,tzinfo=timezone.utc)
    _write(tmp_path/"run-summary.json",{
        "updated_at":"2026-08-29T23:59:00+00:00",
        "qualification_min_liquidity_usd":50000,
        "lane_health":{"old_coin_revival":"HEALTHY","new_token_lab":"HEALTHY"},
        "production_risk_gate":{"min_live_liquidity_usd":50000},
        "active_qualified":2,
    })
    _write(tmp_path/"holder-cluster-production-report.json",{
        "mode":"PRODUCTION_FAIL_CLOSED","input_count":2,"promoted_count":0,"quarantine_count":2,"blocked_count":0,
    })
    _write(tmp_path/"wallet-forensics-summary.json",{
        "updated_at":"2026-08-29T23:59:00+00:00",
        "source":"holder-cluster-production-qualified.json",
        "lane":"PRE_PRODUCTION_EVIDENCE_GATHERING",
        "production_authorization":False,
        "active_candidates_seen":0,
    })
    _heartbeat(tmp_path)
    out=build_health(str(tmp_path),now)
    assert out["overall"]=="DEGRADED"
    assert out["checks"]["wallet_forensics"]["status"]=="DEGRADED"
    assert out["checks"]["wallet_forensics_capability"]["status"]=="DEGRADED"
    assert out["checks"]["holder_cluster_evidence_coverage"]["status"]=="DEGRADED"
    assert out["checks"]["holder_cluster_evidence_coverage"]["reason"]=="ALL_ACTIVE_CANDIDATES_QUARANTINED_FOR_INCOMPLETE_EVIDENCE"


def test_health_marks_evm_only_forensics_as_capability_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET500_WORKFLOW_DEGRADED_SECONDS", "600")
    now=datetime(2026,8,30,0,0,0,tzinfo=timezone.utc)
    _write(tmp_path/"run-summary.json",{
        "updated_at":"2026-08-29T23:59:00+00:00",
        "qualification_min_liquidity_usd":50000,
        "lane_health":{"old_coin_revival":"HEALTHY","new_token_lab":"HEALTHY"},
        "production_risk_gate":{"min_live_liquidity_usd":50000},
        "active_qualified":1,
    })
    _write(tmp_path/"holder-cluster-production-report.json",{
        "mode":"PRODUCTION_FAIL_CLOSED","input_count":1,"promoted_count":0,"quarantine_count":0,"blocked_count":1,
    })
    _write(tmp_path/"wallet-forensics-summary.json",{
        "updated_at":"2026-08-29T23:59:00+00:00",
        "source":"active-qualified-candidates.json",
        "lane":"PRE_PRODUCTION_EVIDENCE_GATHERING",
        "production_authorization":False,
        "active_candidates_seen":1,
        "verified_wallet_candidates":0,"solana_candidates_scanned":0,"evm_candidates_deferred":1,
    })
    _heartbeat(tmp_path)
    out=build_health(str(tmp_path),now)
    assert out["checks"]["wallet_forensics"]["status"]=="HEALTHY"
    assert out["checks"]["wallet_forensics_capability"]["status"]=="DEGRADED"
    assert out["pipeline_health"]=="HEALTHY"
    assert out["capability_health"]=="DEGRADED"
    assert out["overall"]=="DEGRADED"


def test_health_degrades_when_publish_evidence_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET500_WORKFLOW_DEGRADED_SECONDS", "600")
    now=datetime(2026,8,30,0,0,0,tzinfo=timezone.utc)
    _write(tmp_path/"run-summary.json",{
        "updated_at":"2026-08-29T23:59:00+00:00",
        "qualification_min_liquidity_usd":50000,
        "lane_health":{"old_coin_revival":"HEALTHY","new_token_lab":"HEALTHY"},
        "production_risk_gate":{"min_live_liquidity_usd":50000},
        "active_qualified":0,
    })
    _write(tmp_path/"holder-cluster-production-report.json",{"mode":"PRODUCTION_FAIL_CLOSED","input_count":0,"promoted_count":0,"quarantine_count":0,"blocked_count":0})
    _write(tmp_path/"wallet-forensics-summary.json",{
        "updated_at":"2026-08-29T23:59:00+00:00","source":"active-qualified-candidates.json","lane":"PRE_PRODUCTION_EVIDENCE_GATHERING","production_authorization":False,"active_candidates_seen":0,
    })
    out=build_health(str(tmp_path),now)
    assert out["checks"]["publish_pipeline"]["status"]=="DEGRADED"
    assert out["pipeline_health"]=="DEGRADED"


def test_health_fails_closed_on_liquidity_drift(tmp_path):
    now=datetime(2026,8,30,0,0,0,tzinfo=timezone.utc)
    _write(tmp_path/"run-summary.json",{
        "updated_at":"2026-08-29T23:59:00+00:00",
        "qualification_min_liquidity_usd":20000,
        "lane_health":{"old_coin_revival":"HEALTHY","new_token_lab":"HEALTHY"},
        "production_risk_gate":{"min_live_liquidity_usd":50000},
    })
    _write(tmp_path/"holder-cluster-production-report.json",{"mode":"PRODUCTION_FAIL_CLOSED"})
    _write(tmp_path/"wallet-forensics-summary.json",{"updated_at":"2026-08-29T23:59:00+00:00"})
    out=build_health(str(tmp_path),now)
    assert out["overall"]=="FAILED"
    assert out["checks"]["liquidity_policy"]["status"]=="FAILED"
