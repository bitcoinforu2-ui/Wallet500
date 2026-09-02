from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MIN_LIQUIDITY_USD = 50_000.0


def _load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _num(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _check(results: list[dict], name: str, ok: bool, evidence=None):
    results.append({"name": name, "status": "PASS" if ok else "FAIL", "evidence": evidence})


def run(output_dir: str = "data"):
    out = Path(output_dir)
    now = datetime.now(timezone.utc)
    summary = _load(out / "run-summary.json", {})
    health = _load(out / "system-health.json", {})
    holder = _load(out / "holder-cluster-production-report.json", {})
    exact = _load(out / "exact-pair-survival-report.json", {})
    paper = _load(out / "paper-truth-summary.json", {})
    active = _load(out / "active-qualified-candidates.json", [])
    decision = _load(out / "decision-engine-v1.json", {})

    checks: list[dict] = []

    q_floor = _num(summary.get("qualification_min_liquidity_usd")) if isinstance(summary, dict) else 0.0
    prod = summary.get("production_risk_gate") or {} if isinstance(summary, dict) else {}
    p_floor = _num(prod.get("min_live_liquidity_usd")) if isinstance(prod, dict) else 0.0
    e_floor = _num(exact.get("min_liquidity_usd")) if isinstance(exact, dict) else 0.0
    _check(checks, "qualification_liquidity_floor_ge_50k", q_floor >= MIN_LIQUIDITY_USD, q_floor)
    _check(checks, "production_liquidity_floor_ge_50k", p_floor >= MIN_LIQUIDITY_USD, p_floor)
    _check(checks, "exact_pair_liquidity_floor_ge_50k", e_floor >= MIN_LIQUIDITY_USD, e_floor)

    exact_method = str(exact.get("method") or "") if isinstance(exact, dict) else ""
    _check(checks, "immutable_exact_pair_revalidation", "IMMUTABLE_EXACT_PAIR" in exact_method, exact_method)

    holder_mode = holder.get("mode") if isinstance(holder, dict) else None
    _check(checks, "holder_cluster_fail_closed_mode", holder_mode == "PRODUCTION_FAIL_CLOSED", holder_mode)
    if isinstance(holder, dict):
        h_input = int(holder.get("input_count", 0) or 0)
        h_accounted = sum(int(holder.get(k, 0) or 0) for k in ("promoted_count", "quarantine_count", "blocked_count"))
        _check(checks, "holder_cluster_all_inputs_accounted", h_input == h_accounted, {"input": h_input, "accounted": h_accounted})
    else:
        _check(checks, "holder_cluster_all_inputs_accounted", False, "missing report")

    hchecks = health.get("checks") or {} if isinstance(health, dict) else {}
    liq_health = (hchecks.get("liquidity_policy") or {}).get("status") if isinstance(hchecks, dict) else None
    holder_health = (hchecks.get("holder_cluster_fail_closed") or {}).get("status") if isinstance(hchecks, dict) else None
    failure_summary = health.get("failure_summary") or {} if isinstance(health, dict) else {}
    system_blockers = int(failure_summary.get("system_production_blockers", failure_summary.get("production_blockers", 1)) or 0) if isinstance(failure_summary, dict) else 1
    _check(checks, "system_health_liquidity_policy", liq_health == "HEALTHY", liq_health)
    _check(checks, "system_health_holder_cluster_fail_closed", holder_health == "HEALTHY", holder_health)
    _check(
        checks,
        "system_health_no_production_blockers",
        system_blockers == 0,
        {
            "system_production_blockers": system_blockers,
            "overall": health.get("overall") if isinstance(health, dict) else None,
            "codes": failure_summary.get("codes") if isinstance(failure_summary, dict) else None,
        },
    )

    paper_mode = str(paper.get("mode") or "") if isinstance(paper, dict) else ""
    paper_ok = "PAPER" in paper_mode and ("NO_REAL_MONEY" in paper_mode or "NO REAL MONEY" in paper_mode)
    _check(checks, "paper_only_execution", paper_ok, paper_mode)
    _check(checks, "generic_router_booking_disabled", paper.get("generic_router_booking_disabled") is True if isinstance(paper, dict) else False, paper.get("generic_router_booking_disabled") if isinstance(paper, dict) else None)

    tm_method = str(((summary.get("time_machine") or {}).get("method")) or "") if isinstance(summary, dict) else ""
    _check(checks, "no_hindsight_replay", "NO_HINDSIGHT" in tm_method, tm_method)

    active_ok = isinstance(active, list)
    active_failures = []
    if active_ok:
        for i, row in enumerate(active):
            if not isinstance(row, dict):
                active_failures.append({"index": i, "reason": "NON_OBJECT"})
                continue
            pair = str(row.get("pair_address") or "").lower()
            locked = str(row.get("locked_pair_address") or "").lower()
            identity_ok = bool(pair) and bool(locked) and pair == locked and row.get("pair_identity_locked") is True
            live_liq = _num(row.get("production_live_liquidity_usd") or row.get("live_liquidity_usd") or row.get("liquidity_usd"))
            if not identity_ok:
                active_failures.append({"index": i, "pair_address": pair, "locked_pair_address": locked, "reason": "PAIR_IDENTITY_NOT_LOCKED"})
            if live_liq < MIN_LIQUIDITY_USD:
                active_failures.append({"index": i, "liquidity_usd": live_liq, "reason": "ACTIVE_SUB_50K_LIQUIDITY"})
    _check(checks, "active_exact_pair_and_liquidity_integrity", active_ok and not active_failures, {"active_count": len(active) if isinstance(active, list) else None, "failures": active_failures[:20]})

    decision_mode = str(decision.get("mode") or "") if isinstance(decision, dict) else ""
    decision_contract = decision.get("truth_contract") or {} if isinstance(decision, dict) else {}
    decision_learning = decision.get("learning") or {} if isinstance(decision, dict) else {}
    _check(
        checks,
        "decision_engine_shadow_only",
        decision_mode == "SHADOW_DECISION_ONLY_NO_REAL_MONEY_NO_PRODUCTION_GATE_CHANGE" and decision.get("production_change") is False,
        {"mode": decision_mode, "production_change": decision.get("production_change") if isinstance(decision, dict) else None},
    )
    contract_ok = (
        isinstance(decision_contract, dict)
        and decision_contract.get("exact_pair_required") is True
        and decision_contract.get("liquidity_floor_required") is True
        and decision_contract.get("holder_cluster_fail_closed_for_buy") is True
        and decision_contract.get("lp_protection_fail_closed_for_buy") is True
        and decision_contract.get("executable_exit_depth_fail_closed_for_buy") is True
        and decision_contract.get("no_hindsight") is True
        and decision_contract.get("real_money_execution") is False
    )
    _check(checks, "decision_engine_fail_closed_contract", contract_ok, decision_contract)
    _check(
        checks,
        "decision_engine_no_auto_weight_changes",
        isinstance(decision_learning, dict) and decision_learning.get("auto_weight_changes") is False,
        decision_learning.get("auto_weight_changes") if isinstance(decision_learning, dict) else None,
    )
    decision_rows = decision.get("decisions") if isinstance(decision, dict) else None
    invalid_buys = []
    if isinstance(decision_rows, list):
        for i, row in enumerate(decision_rows):
            if not isinstance(row, dict) or row.get("recommended_action") != "BUY":
                continue
            hard = row.get("hard_safety_failures") or []
            gaps = row.get("evidence_gaps") or []
            if hard or gaps:
                invalid_buys.append({"index": i, "key": row.get("key"), "hard": hard, "gaps": gaps})
    _check(
        checks,
        "decision_engine_buy_has_complete_evidence",
        isinstance(decision_rows, list) and not invalid_buys,
        {"decision_count": len(decision_rows) if isinstance(decision_rows, list) else None, "invalid_buys": invalid_buys[:20]},
    )

    failures = [c for c in checks if c["status"] != "PASS"]
    payload = {
        "version": 2,
        "updated_at": now.isoformat(),
        "mode": "FAIL_CLOSED_PRODUCTION_INTEGRITY_VALIDATION",
        "minimum_liquidity_usd": MIN_LIQUIDITY_USD,
        "checks": checks,
        "passed": not failures,
        "failure_count": len(failures),
        "policy": "Validation may block publication; it never relaxes thresholds, pair identity, holder/cluster evidence, immutable track record, no-hindsight, paper-only rules, or the Decision Engine V1 shadow-only contract.",
    }
    (out / "strict-validation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "failure_count": payload["failure_count"], "failures": failures}, indent=2))
    if failures:
        failed_checks = ",".join(c["name"] for c in failures)
        print(f"::error title=Wallet500 strict validation failed::failed_checks={failed_checks}")
        raise SystemExit(1)
    return payload


if __name__ == "__main__":
    run()
