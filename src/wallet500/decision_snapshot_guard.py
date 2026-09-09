from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .solana_mintability_public_guard import sanitize_real_alerts
from .policy import CANONICAL_MIN_EXECUTION_LIQUIDITY_USD, CANONICAL_MIN_MARKET_AGE_DAYS

DATA = Path("data")
OUTPUT = DATA / "decision-snapshot-integrity.json"
RESEARCH_MIN_AGE_DAYS = 90
RESEARCH_MIN_LIQUIDITY_USD = 15_000.0
PRODUCTION_MIN_AGE_DAYS = CANONICAL_MIN_MARKET_AGE_DAYS
PRODUCTION_MIN_LIQUIDITY_USD = CANONICAL_MIN_EXECUTION_LIQUIDITY_USD
PUBLIC_DECISION_SURFACES = ("alerts", "verified_watch", "evidence_ready", "dormant_no_activity")


def _load(path: Path, default: Any) -> Any:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _identity_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("chain") or row.get("network") or ""),
        str(row.get("token_address") or row.get("token") or row.get("mint") or ""),
        str(row.get("pair_address") or row.get("dex_pair_address") or ""),
    )


def _is_evidence_ready_visible(row: dict) -> bool:
    return bool(
        row.get("evidence_ready") is True
        or row.get("evidence_envelope_status") == "EVIDENCE_READY"
        or row.get("status") == "EVIDENCE_READY_NOT_REAL_ALERT"
    )


def _visible_evidence_ready(real: dict) -> int:
    keys = set()
    for surface in ("verified_watch", "evidence_ready", "dormant_no_activity"):
        rows = real.get(surface) if isinstance(real.get(surface), list) else []
        for row in rows:
            if not isinstance(row, dict) or not _is_evidence_ready_visible(row):
                continue
            keys.add(_identity_key(row))
    return len(keys)


def _preserve_evidence_ready_visibility(data_dir: Path) -> None:
    """Mirror only the current canonical Evidence Ready population.

    The dedicated evidence_ready surface exists solely to preserve canonical rows
    that fall outside the ranked watch-list display window. It must never retain a
    row that is no longer EVIDENCE_READY in the current sanitized Envelope.
    """
    envelope_path = data_dir / "candidate-evidence-envelope.json"
    real_path = data_dir / "real-alerts.json"
    envelope = _load(envelope_path, {})
    real = _load(real_path, {})
    if not isinstance(envelope, dict) or not isinstance(real, dict):
        return

    canonical_rows = [
        row for row in (envelope.get("candidates") or [])
        if isinstance(row, dict) and row.get("status") == "EVIDENCE_READY"
    ]
    canonical = {_identity_key(row): row for row in canonical_rows}
    canonical_keys = set(canonical)

    stale_surface_markers_pruned = 0
    for surface in ("verified_watch", "dormant_no_activity"):
        rows = real.get(surface) if isinstance(real.get(surface), list) else []
        cleaned = []
        for row in rows:
            if not isinstance(row, dict):
                cleaned.append(row)
                continue
            key = _identity_key(row)
            if _is_evidence_ready_visible(row) and key not in canonical_keys:
                row = dict(row)
                row["evidence_ready"] = False
                if row.get("evidence_envelope_status") == "EVIDENCE_READY":
                    row["evidence_envelope_status"] = "NOT_EVIDENCE_READY_CURRENT_CANONICAL"
                if row.get("status") == "EVIDENCE_READY_NOT_REAL_ALERT":
                    row["status"] = (
                        "VERIFIED_WATCH_NOT_REAL_ALERT"
                        if surface == "verified_watch"
                        else "DORMANT_NO_ACTIVITY_NOT_VERIFIED_WATCH"
                    )
                row["evidence_ready_visibility_reason"] = "STALE_CANONICAL_EVIDENCE_READY_MARKER_CLEARED"
                stale_surface_markers_pruned += 1
            cleaned.append(row)
        real[surface] = cleaned

    old_research = real.get("evidence_ready") if isinstance(real.get("evidence_ready"), list) else []
    research_rows = [
        row for row in old_research
        if isinstance(row, dict) and _identity_key(row) in canonical_keys
    ]
    pruned = len(old_research) - len(research_rows)

    existing = set()
    for surface in ("verified_watch", "dormant_no_activity"):
        rows = real.get(surface) if isinstance(real.get(surface), list) else []
        for row in rows:
            if isinstance(row, dict) and _is_evidence_ready_visible(row):
                key = _identity_key(row)
                if key in canonical_keys:
                    existing.add(key)
    for row in research_rows:
        if _is_evidence_ready_visible(row):
            existing.add(_identity_key(row))

    added = 0
    for key, row in canonical.items():
        if key in existing:
            continue
        truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
        market = row.get("market") if isinstance(row.get("market"), dict) else {}
        coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
        mirrored = {
            "chain": key[0],
            "network": key[0],
            "token_address": key[1],
            "pair_address": key[2],
            "symbol": row.get("symbol"),
            "dex_url": row.get("dex_url"),
            "status": "EVIDENCE_READY_NOT_REAL_ALERT",
            "evidence_ready": True,
            "evidence_envelope_status": "EVIDENCE_READY",
            "evidence_positive_lanes": list(coverage.get("positive_independent_lanes") or []),
            "evidence_verified_lanes": list(coverage.get("verified_independent_lanes") or []),
            "evidence_positive_count": _int(coverage.get("positive_independent_count")),
            "evidence_verified_count": _int(coverage.get("verified_independent_count")),
            "exact_identity_verified": truth.get("exact_identity_verified") is True,
            "exact_pair_verified": truth.get("exact_pair_verified") is True,
            "market_age_verified": truth.get("market_age_verified_60d_plus") is True,
            "market_age_days": _int(truth.get("market_age_days")),
            "execution_pool_liquidity_usd": _num(
                truth.get("execution_pool_liquidity_usd")
                or market.get("execution_pool_liquidity_usd")
            ),
            "mintability_verified": row.get("mintability_verified") is True,
            "mintable": row.get("mintable"),
            "mint_authority": row.get("mint_authority"),
            "mintability_status": row.get("mintability_status"),
            "mintability_checked_at": row.get("mintability_checked_at"),
            "actionable_research_alert": False,
            "production_effect": False,
            "automatic_buy": False,
            "visibility_reason": "CANONICAL_EVIDENCE_READY_PRESERVED_FROM_RANKED_WATCH_TRUNCATION",
        }
        research_rows.append(mirrored)
        existing.add(key)
        added += 1

    real["evidence_ready"] = research_rows
    counts = real.get("counts") if isinstance(real.get("counts"), dict) else {}
    counts["evidence_ready_research"] = len(existing)
    real["counts"] = counts
    bridge = real.get("evidence_ready_visibility_bridge") if isinstance(real.get("evidence_ready_visibility_bridge"), dict) else {}
    bridge.update({
        "version": 3,
        "added_this_run": added,
        "pruned_stale_this_run": pruned,
        "pruned_stale_surface_markers_this_run": stale_surface_markers_pruned,
        "canonical_visible_count": len(existing),
        "canonical_envelope_count": len(canonical_keys),
        "production_effect": False,
        "thresholds_changed": False,
        "stale_carry_over_allowed": False,
    })
    real["evidence_ready_visibility_bridge"] = bridge
    real_path.write_text(json.dumps(real, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(data_dir: Path = DATA) -> dict:
    envelope = _load(data_dir / "candidate-evidence-envelope.json", {})
    real = _load(data_dir / "real-alerts.json", {})
    funnel = _load(data_dir / "revival-funnel-diagnostics.json", {})
    age = _load(data_dir / "active-qualified-age-gate.json", {})
    production = _load(data_dir / "production-status.json", {})

    failures: list[dict[str, Any]] = []

    def fail(code: str, detail: str, actual: Any = None) -> None:
        failures.append({"code": code, "detail": detail, "actual": actual})

    ec = envelope.get("counts") if isinstance(envelope, dict) else {}
    rc = real.get("counts") if isinstance(real, dict) else {}
    lanes = funnel.get("lanes") if isinstance(funnel, dict) else {}
    ep = (lanes or {}).get("evidence_promotion") if isinstance(lanes, dict) else {}
    ec = ec if isinstance(ec, dict) else {}
    rc = rc if isinstance(rc, dict) else {}
    ep = ep if isinstance(ep, dict) else {}

    if envelope.get("mode") != "RESEARCH_ONLY_CANDIDATE_EVIDENCE_ENVELOPE_V1":
        fail("ENVELOPE_MODE_INVALID", "Canonical evidence envelope missing or wrong mode", envelope.get("mode"))
    if envelope.get("production_change") is not False or envelope.get("automatic_buy") is not False:
        fail("ENVELOPE_PRODUCTION_LEAK", "Evidence envelope must remain research-only")
    truth = envelope.get("truth_contract") if isinstance(envelope.get("truth_contract"), dict) else {}
    if _int(truth.get("minimum_market_age_days")) != RESEARCH_MIN_AGE_DAYS:
        fail("ENVELOPE_AGE_SCOPE_DRIFT", "Research evidence envelope must enforce 90d scope", truth.get("minimum_market_age_days"))
    research_liq = _num(truth.get("minimum_execution_liquidity_usd") or truth.get("minimum_liquidity_usd"))
    if research_liq != RESEARCH_MIN_LIQUIDITY_USD:
        fail("ENVELOPE_LIQUIDITY_SCOPE_DRIFT", "Research evidence envelope must enforce $15K scope", research_liq)
    if truth.get("exact_pair_required") is not True:
        fail("ENVELOPE_EXACT_PAIR_GUARD_MISSING", "Exact pair truth is mandatory")

    ready_envelope = _int(ec.get("evidence_ready"))
    ready_real = _int(rc.get("evidence_ready_research"))
    ready_funnel = _int(ep.get("evidence_ready"))
    ready_visible = _visible_evidence_ready(real)
    evidence_counts = {
        "envelope_canonical": ready_envelope,
        "real_research_count": ready_real,
        "funnel_research_count": ready_funnel,
        "visible_across_watch_evidence_dormant": ready_visible,
    }
    if len({ready_envelope, ready_real, ready_funnel}) != 1:
        fail("EVIDENCE_READY_COUNT_SKEW", "Envelope, REAL research count and funnel must describe the same post-mintability Evidence Ready population", evidence_counts)
    if ready_visible != ready_envelope:
        fail("EVIDENCE_READY_VISIBILITY_SKEW", "Every canonical Evidence Ready token must remain visible on exactly one research surface, including dormant_no_activity", evidence_counts)

    # This gate feeds the 90d research/evidence universe; it is not REAL ALERT
    # production authorization and must not be compared to the 180d production floor.
    if _int(age.get("minimum_market_age_days")) != RESEARCH_MIN_AGE_DAYS:
        fail("ACTIVE_AGE_GATE_SCOPE_DRIFT", "Research active-candidate age gate must enforce 90d", age.get("minimum_market_age_days"))
    if age.get("status") == "QUARANTINED_FAIL_CLOSED_UNAPPROVED_POLICY":
        fail("STALE_AGE_GOVERNOR", "Legacy unapproved age-policy quarantine must not reappear")
    if age.get("project_scope_minimum_market_age_days") not in (None, RESEARCH_MIN_AGE_DAYS):
        fail("ACTIVE_PROJECT_SCOPE_DRIFT", "Research candidate scope must remain 90d", age.get("project_scope_minimum_market_age_days"))

    for row in envelope.get("candidates") or []:
        if not isinstance(row, dict) or row.get("status") != "EVIDENCE_READY":
            continue
        if row.get("production_effect") is not False or row.get("automatic_buy") is not False:
            fail("EVIDENCE_READY_PRODUCTION_LEAK", "Evidence Ready must never authorize production", row.get("key"))
        t = row.get("truth") if isinstance(row.get("truth"), dict) else {}
        c = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
        if not (
            t.get("exact_identity_verified") is True
            and t.get("exact_pair_verified") is True
            and t.get("market_age_verified_60d_plus") is True
            and t.get("execution_liquidity_floor_passed") is True
        ):
            fail("EVIDENCE_READY_TRUTH_BREACH", "Evidence Ready row lacks mandatory research base truth", row.get("key"))
        if _int(c.get("positive_independent_count")) < 1:
            fail("EVIDENCE_READY_WITHOUT_INDEPENDENT_EVIDENCE", "Evidence Ready requires an independent positive lane", row.get("key"))

    for surface in PUBLIC_DECISION_SURFACES:
        for row in real.get(surface) or []:
            if not isinstance(row, dict):
                continue
            chain = str(row.get("chain") or row.get("network") or "").lower()
            if chain == "solana" and not (
                row.get("mintability_verified") is True
                and row.get("mintable") is False
                and row.get("mint_authority") is None
            ):
                fail(
                    "SOLANA_MINTABILITY_PUBLIC_BREACH",
                    "Mintable or unverified Solana token reached a public/research decision surface",
                    {"surface": surface, "token": row.get("token_address")},
                )

    for row in real.get("alerts") or []:
        if not isinstance(row, dict):
            continue
        if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
            fail("REAL_ALERT_IDENTITY_BREACH", "REAL ALERT lacks exact identity/pair", row.get("token_address"))
        if row.get("market_age_verified") is not True or _int(row.get("market_age_days")) < PRODUCTION_MIN_AGE_DAYS:
            fail("REAL_ALERT_AGE_BREACH", "REAL ALERT is outside strict production 180d scope", row.get("token_address"))
        if _num(row.get("execution_pool_liquidity_usd")) < PRODUCTION_MIN_LIQUIDITY_USD:
            fail("REAL_ALERT_LIQUIDITY_BREACH", "REAL ALERT lacks $50K execution pool liquidity", row.get("token_address"))
        if row.get("automatic_buy") is True:
            fail("REAL_ALERT_AUTOBUY_BREACH", "REAL ALERT must not auto-buy", row.get("token_address"))

    if isinstance(production, dict) and production:
        policy = production.get("policy") if isinstance(production.get("policy"), dict) else {}
        if _int(policy.get("minimum_verified_market_age_days")) != PRODUCTION_MIN_AGE_DAYS:
            fail("PRODUCTION_STATUS_SCOPE_DRIFT", "Production status must report strict 180d scope", policy.get("minimum_verified_market_age_days"))
        if _num(policy.get("minimum_liquidity_usd")) != PRODUCTION_MIN_LIQUIDITY_USD:
            fail("PRODUCTION_STATUS_LIQUIDITY_DRIFT", "Production status must report strict $50K liquidity floor", policy.get("minimum_liquidity_usd"))
        if policy.get("exact_onchain_identity_required") is not True or policy.get("exact_dex_pair_required") is not True:
            fail("PRODUCTION_STATUS_IDENTITY_DRIFT", "Production status must require exact identity and exact pair")

    return {
        "version": 6,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "FAIL_CLOSED_DECISION_SNAPSHOT_COHERENCE_GUARD_V6_DUAL_SCOPE",
        "passed": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "counts": {
            "evidence_ready": ready_envelope,
            "evidence_ready_visible": ready_visible,
            "verified_watch": _int(rc.get("verified_watch_not_real")),
            "dormant_no_activity": _int(rc.get("dormant_no_activity")),
            "real_alerts": _int(rc.get("real_alerts")),
            "identity_pending": _int(rc.get("identity_pending_not_actionable")),
            "mintability_rejected_not_visible": _int(rc.get("mintability_rejected_not_visible")),
        },
        "evidence_ready_coherence": evidence_counts,
        "truth_contract": {
            "research_scope_days": RESEARCH_MIN_AGE_DAYS,
            "research_minimum_execution_pool_liquidity_usd": RESEARCH_MIN_LIQUIDITY_USD,
            "production_scope_days": PRODUCTION_MIN_AGE_DAYS,
            "production_minimum_execution_pool_liquidity_usd": PRODUCTION_MIN_LIQUIDITY_USD,
            "research_scope_never_authorizes_real_alert": True,
            "production_scope_is_independently_stricter": True,
            "exact_pair_required": True,
            "solana_mint_authority_must_be_revoked_null": True,
            "solana_mintable_tokens_allowed": False,
            "solana_unknown_mintability_allowed": False,
            "dormant_no_activity_is_guarded_public_research_surface": True,
            "evidence_ready_dormancy_does_not_erase_research_population": True,
            "evidence_ready_rank_truncation_never_erases_research_population": True,
            "evidence_ready_is_research_only": True,
            "production_thresholds_changed": False,
            "no_hindsight": True,
        },
    }


def run(data_dir: Path = DATA, fail_on_error: bool = True) -> dict:
    sanitize_real_alerts(data_dir)
    _preserve_evidence_ready_visibility(data_dir)
    payload = build(data_dir)
    (data_dir / OUTPUT.name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if fail_on_error and not payload["passed"]:
        details = ";".join(
            f"{x['code']}={json.dumps(x.get('actual'), ensure_ascii=False, sort_keys=True)}"
            for x in payload["failures"]
        )
        raise SystemExit("DECISION_SNAPSHOT_COHERENCE_FAILED:" + details)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "passed": payload["passed"],
        "counts": payload["counts"],
        "evidence_ready_coherence": payload.get("evidence_ready_coherence"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
