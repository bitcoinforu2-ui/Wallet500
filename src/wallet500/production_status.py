from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MIN_MARKET_AGE_DAYS = 180
MIN_LIQUIDITY_USD = 50_000.0


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _count_list(value) -> int:
    return len(value) if isinstance(value, list) else 0


def build(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    now = datetime.now(timezone.utc).isoformat()
    summary = _load(out / "run-summary.json", {})
    cex = _load(out / "cex-revival-radar.json", {})
    real = _load(out / "real-alerts.json", {})
    active = _load(out / "active-qualified-candidates.json", [])
    strict = _load(out / "strict-validation.json", {})
    health = _load(out / "system-health.json", {})
    holder = _load(out / "holder-cluster-production-report.json", {})
    publish = _load(out / "publish-evidence.json", {})

    real_counts = real.get("counts") if isinstance(real, dict) else {}
    real_counts = real_counts if isinstance(real_counts, dict) else {}
    identity_counts = cex.get("identity_counts") if isinstance(cex, dict) else {}
    identity_counts = identity_counts if isinstance(identity_counts, dict) else {}
    platform_catalog = cex.get("platform_catalog") if isinstance(cex, dict) else {}
    platform_catalog = platform_catalog if isinstance(platform_catalog, dict) else {}
    failure_summary = health.get("failure_summary") if isinstance(health, dict) else {}
    failure_summary = failure_summary if isinstance(failure_summary, dict) else {}

    real_alert_count = int(real_counts.get("real_alerts", _count_list(real.get("alerts") if isinstance(real, dict) else [])) or 0)
    watch_count = int(real_counts.get("verified_watch_not_real", _count_list(real.get("verified_watch") if isinstance(real, dict) else [])) or 0)
    pending_count = int(real_counts.get("identity_pending_not_actionable", _count_list(real.get("identity_pending") if isinstance(real, dict) else [])) or 0)
    active_count = _count_list(active)
    strict_passed = strict.get("passed") is True if isinstance(strict, dict) else False
    strict_failures = int(strict.get("failure_count", 1) or 0) if isinstance(strict, dict) else 1
    system_blockers = int(failure_summary.get("system_production_blockers", failure_summary.get("production_blockers", 0)) or 0)
    health_overall = str(health.get("overall") or "UNKNOWN") if isinstance(health, dict) else "UNKNOWN"
    production_authorized = int(holder.get("promoted_count", 0) or 0) if isinstance(holder, dict) else 0

    if not strict_passed or strict_failures:
        operator_status = "VALIDATION_BLOCKED"
    elif system_blockers > 0:
        operator_status = "DEGRADED_FAIL_CLOSED"
    elif real_alert_count > 0:
        operator_status = "ACTIONABLE_RESEARCH_ALERTS_PRESENT"
    else:
        operator_status = "READY_NO_ACTIONABLE_SIGNAL"

    observability_status = "HEALTHY" if health_overall == "HEALTHY" else "DEGRADED_NON_BLOCKING" if system_blockers == 0 else "BLOCKING"
    payload = {
        "version": 1,
        "generated_at": now,
        "canonical_operator_truth": True,
        "replaces_for_current_status": "legacy pipeline-status.json",
        "operator_status": operator_status,
        "observability_status": observability_status,
        "policy": {
            "mode": "VETERAN_COIN_REVIVAL_ONLY",
            "old_coin_revival_attention_pct": 100,
            "new_token_production_attention_pct": 0,
            "minimum_verified_market_age_days": MIN_MARKET_AGE_DAYS,
            "unknown_or_ambiguous_age": "FAIL_CLOSED_NOT_ACTIONABLE",
            "minimum_liquidity_usd": MIN_LIQUIDITY_USD,
            "exact_onchain_identity_required": True,
            "exact_dex_pair_required": True,
            "symbol_only_never_actionable": True,
            "cex_only_never_real_alert": True,
            "real_money_execution": False,
            "execution_mode": "RESEARCH_AND_PAPER_ONLY",
        },
        "cex_revival": {
            "generated_at": cex.get("generated_at") if isinstance(cex, dict) else None,
            "healthy_sources": int(cex.get("healthy_sources", 0) or 0) if isinstance(cex, dict) else 0,
            "requested_sources": _count_list(cex.get("requested_sources") if isinstance(cex, dict) else []),
            "contracts_seen": int(cex.get("contracts_seen", 0) or 0) if isinstance(cex, dict) else 0,
            "symbols_seen": int(cex.get("symbols_seen", 0) or 0) if isinstance(cex, dict) else 0,
            "alerts": int(cex.get("alerts_count", _count_list(cex.get("alerts") if isinstance(cex, dict) else [])) or 0) if isinstance(cex, dict) else 0,
            "dex_verified": int(identity_counts.get("dex_verified", 0) or 0),
            "pair_pending": int(identity_counts.get("pair_pending", 0) or 0),
            "identity_pending": int(identity_counts.get("identity_pending", 0) or 0),
            "platform_catalog": {
                "status": platform_catalog.get("status"),
                "requested_coin_ids": int(platform_catalog.get("requested_coin_ids", 0) or 0),
                "resolved_coin_ids": int(platform_catalog.get("resolved_coin_ids", 0) or 0),
                "error": platform_catalog.get("error"),
            },
        },
        "real_alert_feed": {
            "generated_at": real.get("generated_at") if isinstance(real, dict) else None,
            "real_alerts": real_alert_count,
            "verified_watch_not_real": watch_count,
            "identity_pending_not_actionable": pending_count,
            "latest_real_alert": real.get("latest_real_alert") if isinstance(real, dict) else None,
        },
        "production_funnel": {
            "active_exact_pair_candidates": active_count,
            "holder_cluster_promoted": production_authorized,
            "production_authorized_candidates": production_authorized,
            "paper_only": True,
        },
        "integrity": {
            "strict_validation_passed": strict_passed,
            "strict_validation_failure_count": strict_failures,
            "system_health_overall": health_overall,
            "system_production_blockers": system_blockers,
            "health_failure_codes": failure_summary.get("codes") or [],
        },
        "previous_publish_evidence": {
            "phase": "PRE_CURRENT_RUN_PUBLISH_STEP_PREVIOUS_COMMIT_EVIDENCE",
            "created_at": publish.get("created_at") if isinstance(publish, dict) else None,
            "status": publish.get("status") if isinstance(publish, dict) else None,
            "strict_validation": publish.get("strict_validation") if isinstance(publish, dict) else None,
            "source_sha": publish.get("source_sha") if isinstance(publish, dict) else None,
            "run_id": publish.get("run_id") if isinstance(publish, dict) else None,
            "note": "Current-run publish evidence is created after this status snapshot; this block describes the previously visible commit only.",
        },
        "legacy_context": {
            "run_summary_updated_at": summary.get("updated_at") if isinstance(summary, dict) else None,
            "pipeline_status_is_canonical": False,
        },
        "interpretation": {
            "READY_NO_ACTIONABLE_SIGNAL": "Pipeline integrity passed but no current REAL ALERT satisfies all strict research gates.",
            "ACTIONABLE_RESEARCH_ALERTS_PRESENT": "At least one strict REAL ALERT exists; this is research output, not a profit guarantee or automatic buy instruction.",
            "VALIDATION_BLOCKED": "Strict validation failed; publication/production interpretation must fail closed.",
            "DEGRADED_FAIL_CLOSED": "A system production blocker exists; candidates remain non-actionable until repaired.",
        },
    }
    return payload


def run(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    payload = build(output_dir)
    (out / "production-status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "operator_status": payload["operator_status"],
        "observability_status": payload["observability_status"],
        "real_alerts": payload["real_alert_feed"]["real_alerts"],
        "identity_pending": payload["real_alert_feed"]["identity_pending_not_actionable"],
        "strict_validation_passed": payload["integrity"]["strict_validation_passed"],
        "system_production_blockers": payload["integrity"]["system_production_blockers"],
    }, indent=2))
    return payload


if __name__ == "__main__":
    run()
