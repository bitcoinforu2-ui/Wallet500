from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _age_seconds(ts: str | None, now: datetime) -> float | None:
    if not ts:
        return None
    try:
        dt=datetime.fromisoformat(str(ts).replace("Z","+00:00"))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return max(0.0,(now-dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def build_health(output_dir: str = "data", now: datetime | None = None) -> dict:
    cfg=Settings(); out=Path(output_dir); now=now or datetime.now(timezone.utc)
    summary=_load(out/"run-summary.json",{})
    holder=_load(out/"holder-cluster-production-report.json",{})
    wallet=_load(out/"wallet-forensics-summary.json",{})
    primary_age=_age_seconds(summary.get("updated_at") if isinstance(summary,dict) else None,now)
    wallet_age=_age_seconds(wallet.get("updated_at") if isinstance(wallet,dict) else None,now)
    lane=(summary.get("lane_health") or {}) if isinstance(summary,dict) else {}
    prod=(summary.get("production_risk_gate") or {}) if isinstance(summary,dict) else {}
    qualification_floor=float(summary.get("qualification_min_liquidity_usd") or 0) if isinstance(summary,dict) else 0.0
    production_floor=float(prod.get("min_live_liquidity_usd") or 0) if isinstance(prod,dict) else 0.0

    checks={}
    checks["primary_scan"]={"status":"HEALTHY" if primary_age is not None and primary_age<=cfg.workflow_degraded_seconds else "DEGRADED","age_seconds":round(primary_age,1) if primary_age is not None else None,"max_age_seconds":cfg.workflow_degraded_seconds}
    checks["old_coin_revival"]={"status":lane.get("old_coin_revival") or "DEGRADED"}
    checks["new_token_lab"]={"status":lane.get("new_token_lab") or "DEGRADED"}
    checks["holder_cluster_fail_closed"]={"status":"HEALTHY" if holder.get("mode")=="PRODUCTION_FAIL_CLOSED" else "FAILED","mode":holder.get("mode")}
    floor_ok=qualification_floor>=cfg.verified_min_liquidity_usd and production_floor>=cfg.verified_min_liquidity_usd
    checks["liquidity_policy"]={"status":"HEALTHY" if floor_ok else "FAILED","configured_min_usd":cfg.verified_min_liquidity_usd,"qualification_min_usd":qualification_floor or None,"production_min_usd":production_floor or None}
    if wallet_age is None:
        wallet_status="DEGRADED"
    elif wallet_age>3600:
        wallet_status="DEGRADED"
    else:
        wallet_status="HEALTHY"
    checks["wallet_forensics"]={"status":wallet_status,"age_seconds":round(wallet_age,1) if wallet_age is not None else None,"verified_wallet_candidates":wallet.get("verified_wallet_candidates",0) if isinstance(wallet,dict) else 0,"solana_candidates_scanned":wallet.get("solana_candidates_scanned",0) if isinstance(wallet,dict) else 0,"evm_candidates_deferred":wallet.get("evm_candidates_deferred",0) if isinstance(wallet,dict) else 0}

    statuses=[x.get("status") for x in checks.values()]
    overall="FAILED" if "FAILED" in statuses else "DEGRADED" if "DEGRADED" in statuses else "HEALTHY"
    market_scan=int(summary.get("market_scan",0) or 0) if isinstance(summary,dict) else 0
    qualified=int(summary.get("qualified",0) or 0) if isinstance(summary,dict) else 0
    revival_qualified=int(summary.get("revival_qualified",0) or 0) if isinstance(summary,dict) else 0
    cex_alerts=int(summary.get("cex_revival_alerts",0) or 0) if isinstance(summary,dict) else 0
    lane_metrics={"policy_target_attention_pct":((summary.get("intelligence_policy") or {}).get("target_attention_pct") or {"old_coin_revival":90,"new_token_research":10}) if isinstance(summary,dict) else {"old_coin_revival":90,"new_token_research":10},"new_token":{"market_scan":market_scan,"qualified":qualified,"qualification_rate":round(qualified/market_scan,6) if market_scan else None},"revival":{"qualified":revival_qualified,"cex_revival_alerts":cex_alerts},"allocation_decision":"HOLD_CURRENT_POLICY_UNTIL_FORWARD_OUTCOME_SAMPLE_IS_LARGE_ENOUGH"}
    return {"version":1,"updated_at":now.isoformat(),"overall":overall,"checks":checks,"lane_metrics":lane_metrics}


def run(output_dir: str = "data") -> dict:
    out=Path(output_dir); health=build_health(output_dir); _write(out/"system-health.json",health)
    summary=_load(out/"run-summary.json",{})
    if isinstance(summary,dict):
        summary["system_health"]={"overall":health["overall"],"checks":health["checks"],"lane_metrics":health["lane_metrics"]}; _write(out/"run-summary.json",summary)
    print(json.dumps({"overall":health["overall"],"checks":{k:v.get("status") for k,v in health["checks"].items()}},indent=2)); return health


if __name__=="__main__":
    run()
