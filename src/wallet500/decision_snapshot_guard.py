from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence_ready_visibility import repair as repair_evidence_ready_visibility
from .solana_mintability_public_guard import sanitize_real_alerts

DATA = Path("data")
OUTPUT = DATA / "decision-snapshot-integrity.json"
MIN_AGE_DAYS = 180
MIN_LIQUIDITY_USD = 50_000.0
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


def _visible_evidence_ready(real: dict) -> int:
    keys = set()
    for surface in ("verified_watch", "evidence_ready", "dormant_no_activity"):
        rows = real.get(surface) if isinstance(real.get(surface), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not (
                row.get("evidence_ready") is True
                or row.get("evidence_envelope_status") == "EVIDENCE_READY"
                or row.get("status") == "EVIDENCE_READY_NOT_REAL_ALERT"
            ):
                continue
            key = (
                str(row.get("chain") or row.get("network") or ""),
                str(row.get("token_address") or row.get("token") or row.get("mint") or ""),
                str(row.get("pair_address") or row.get("dex_pair_address") or ""),
            )
            keys.add(key)
    return len(keys)


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
    if _int(truth.get("minimum_market_age_days")) != MIN_AGE_DAYS:
        fail("ENVELOPE_AGE_SCOPE_DRIFT", "Evidence envelope must enforce veteran 180d scope", truth.get("minimum_market_age_days"))
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
        fail(
            "EVIDENCE_READY_COUNT_SKEW",
            "Envelope, REAL research count and funnel must describe the same post-mintability Evidence Ready population",
            evidence_counts,
        )
    if ready_visible != ready_envelope:
        fail(
            "EVIDENCE_READY_VISIBILITY_SKEW",
            "Every canonical Evidence Ready token must remain visible on exactly one research surface, including dormant_no_activity",
            evidence_counts,
        )

    if _int(age.get("minimum_market_age_days")) != MIN_AGE_DAYS:
        fail("ACTIVE_AGE_GATE_SCOPE_DRIFT", "Active age gate must enforce 180d", age.get("minimum_market_age_days"))
    if age.get("status") == "QUARANTINED_FAIL_CLOSED_UNAPPROVED_POLICY":
        fail("STALE_7D_AGE_GOVERNOR", "Legacy 7d-vs-180d quarantine must not reappear")
    if age.get("project_scope_minimum_market_age_days") not in (None, MIN_AGE_DAYS):
        fail("ACTIVE_PROJECT_SCOPE_DRIFT", "Project scope must be 180d", age.get("project_scope_minimum_market_age_days"))

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
            and t.get("market_age_verified_180d_plus") is True
            and t.get("execution_liquidity_floor_passed") is True
        ):
            fail("EVIDENCE_READY_TRUTH_BREACH", "Evidence Ready row lacks mandatory base truth", row.get("key"))
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
                fail("SOLANA_MINTABILITY_PUBLIC_BREACH", "Mintable or unverified Solana token reached a public/research decision surface", {"surface": surface, "token": row.get("token_address")})

    for row in real.get("alerts") or []:
        if not isinstance(row, dict):
            continue
        if row.get("exact_identity_verified") is not True or row.get("exact_pair_verified") is not True:
            fail("REAL_ALERT_IDENTITY_BREACH", "REAL ALERT lacks exact identity/pair", row.get("token_address"))
        if row.get("market_age_verified") is not True or _int(row.get("market_age_days")) < MIN_AGE_DAYS:
            fail("REAL_ALERT_AGE_BREACH", "REAL ALERT is outside veteran scope", row.get("token_address"))
        if _num(row.get("execution_pool_liquidity_usd")) < MIN_LIQUIDITY_USD:
            fail("REAL_ALERT_LIQUIDITY_BREACH", "REAL ALERT lacks $50K execution pool liquidity", row.get("token_address"))
        if row.get("automatic_buy") is True:
            fail("REAL_ALERT_AUTOBUY_BREACH", "REAL ALERT must not auto-buy", row.get("token_address"))

    if isinstance(production, dict) and production:
        policy = production.get("policy") if isinstance(production.get("policy"), dict) else {}
        if _int(policy.get("minimum_verified_market_age_days")) not in (0, MIN_AGE_DAYS):
            fail("PRODUCTION_STATUS_SCOPE_DRIFT", "Production status must report 180d veteran scope", policy.get("minimum_verified_market_age_days"))

    return {
        "version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "FAIL_CLOSED_DECISION_SNAPSHOT_COHERENCE_GUARD_V3_DORMANT_SURFACE_INCLUDED",
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
            "veteran_scope_days": MIN_AGE_DAYS,
            "minimum_execution_pool_liquidity_usd": MIN_LIQUIDITY_USD,
            "exact_pair_required": True,
            "solana_mint_authority_must_be_revoked_null": True,
            "solana_mintable_tokens_allowed": False,
            "solana_unknown_mintability_allowed": False,
            "dormant_no_activity_is_guarded_public_research_surface": True,
            "evidence_ready_dormancy_does_not_erase_research_population": True,
            "evidence_ready_is_research_only": True,
            "no_hindsight": True,
        },
    }


def run(data_dir: Path = DATA, fail_on_error: bool = True) -> dict:
    # Sanitize first so stale precursor/waking rows cannot keep a mintable token
    # visible after the canonical Revival universe has correctly rejected it.
    sanitize_real_alerts(data_dir)
    # The generic watch surface is display-capped. Re-materialize any canonical
    # Evidence Ready row that was displaced by higher-priority watch rows before
    # testing snapshot coherence. This never changes alert or production truth.
    repair_evidence_ready_visibility(data_dir)
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
    print(json.dumps({"passed": payload["passed"], "counts": payload["counts"], "evidence_ready_coherence": payload.get("evidence_ready_coherence")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
