import json
from datetime import datetime, timezone

from wallet500.system_health import build_health


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_health_is_healthy_when_critical_gates_match(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET500_WORKFLOW_DEGRADED_SECONDS", "600")
    now=datetime(2026,8,30,0,0,0,tzinfo=timezone.utc)
    _write(tmp_path/"run-summary.json",{
        "updated_at":"2026-08-29T23:55:00+00:00",
        "qualification_min_liquidity_usd":50000,
        "lane_health":{"old_coin_revival":"HEALTHY","new_token_lab":"HEALTHY"},
        "production_risk_gate":{"min_live_liquidity_usd":50000},
        "market_scan":100,"qualified":5,"revival_qualified":2,"cex_revival_alerts":20,
    })
    _write(tmp_path/"holder-cluster-production-report.json",{"mode":"PRODUCTION_FAIL_CLOSED"})
    _write(tmp_path/"wallet-forensics-summary.json",{"updated_at":"2026-08-29T23:40:00+00:00","verified_wallet_candidates":7,"solana_candidates_scanned":2,"evm_candidates_deferred":1})
    out=build_health(str(tmp_path),now)
    assert out["overall"]=="HEALTHY"
    assert out["checks"]["liquidity_policy"]["status"]=="HEALTHY"
    assert out["lane_metrics"]["new_token"]["qualification_rate"]==0.05


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
