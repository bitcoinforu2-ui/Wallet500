from __future__ import annotations

import json
from pathlib import Path

from .solana_mintability_gate import DATA, _chain, _is_safe, _load, _token, _write, resolve

LIST_KEYS = ("alerts", "verified_watch", "evidence_ready", "identity_pending")


def _family_flag(row: dict, family: str, flag: str) -> bool:
    families = row.get("families") if isinstance(row.get("families"), dict) else {}
    lane = families.get(family) if isinstance(families.get(family), dict) else {}
    return lane.get(flag) is True


def _recount_envelope(payload: dict) -> None:
    candidates = [x for x in (payload.get("candidates") or []) if isinstance(x, dict)]
    payload["counts"] = {
        "universe_with_exact_pair": len(candidates),
        "evidence_ready": sum(x.get("status") == "EVIDENCE_READY" for x in candidates),
        "verified_watch": sum(x.get("status") == "VERIFIED_WATCH" for x in candidates),
        "deep_watch": sum(x.get("status") == "DEEP_WATCH" for x in candidates),
        "blocked_truth": sum(x.get("status") == "BLOCKED_TRUTH" for x in candidates),
        "with_verified_holder_growth_lane": sum(_family_flag(x, "holder_growth", "verified") for x in candidates),
        "with_positive_holder_growth": sum(_family_flag(x, "holder_growth", "positive") for x in candidates),
        "with_verified_wallet_lane": sum(_family_flag(x, "wallet_accumulation", "verified") for x in candidates),
        "with_positive_wallet_accumulation": sum(_family_flag(x, "wallet_accumulation", "positive") for x in candidates),
        "with_positive_smart_money": sum(_family_flag(x, "smart_money", "positive") for x in candidates),
        "with_positive_cex": sum(_family_flag(x, "cex_revival", "positive") for x in candidates),
    }


def _safe_row(row: dict, truth: dict) -> dict:
    return {
        **row,
        "mintability_verified": True,
        "mintable": False,
        "mint_authority": None,
        "mintability_status": "NON_MINTABLE_VERIFIED",
        "mintability_checked_at": truth.get("checked_at"),
    }


def _real_evidence_ready_count(payload: dict) -> int:
    """REAL feed stores Evidence Ready rows inside verified_watch in V3."""
    watch = payload.get("verified_watch") if isinstance(payload.get("verified_watch"), list) else []
    explicit = payload.get("evidence_ready") if isinstance(payload.get("evidence_ready"), list) else []
    keys = set()
    for row in [*watch, *explicit]:
        if not isinstance(row, dict):
            continue
        ready = (
            row.get("evidence_ready") is True
            or row.get("evidence_envelope_status") == "EVIDENCE_READY"
            or row.get("status") == "EVIDENCE_READY_NOT_REAL_ALERT"
        )
        if ready:
            key = (
                str(row.get("chain") or row.get("network") or ""),
                _token(row),
                str(row.get("pair_address") or row.get("dex_pair_address") or ""),
            )
            keys.add(key)
    return len(keys)


def sanitize_real_alerts(data_dir: Path = DATA) -> dict:
    """Fail closed across every current decision/candidate surface.

    The Evidence Envelope and public REAL/Watch feed are sanitized with one
    on-chain mintability snapshot. The funnel is rebuilt afterwards so every
    decision surface describes the same post-rejection population. Historical
    research ledgers remain untouched for learning/audit purposes.
    """
    real_path = data_dir / "real-alerts.json"
    envelope_path = data_dir / "candidate-evidence-envelope.json"
    real = _load(real_path, {})
    envelope = _load(envelope_path, {})
    if not isinstance(real, dict):
        real = {}
    if not isinstance(envelope, dict):
        envelope = {}

    all_rows: list[dict] = []
    all_rows.extend(x for x in (envelope.get("candidates") or []) if isinstance(x, dict))
    for key in LIST_KEYS:
        value = real.get(key)
        if isinstance(value, list):
            all_rows.extend(x for x in value if isinstance(x, dict))

    mints = list(dict.fromkeys(
        _token(x) for x in all_rows
        if _chain(x) == "solana" and _token(x)
    ))
    state_path = data_dir / "solana-mintability-state.json"
    state = _load(state_path, {})
    truth, next_state = resolve(mints, state)
    truth_all = next_state.get("tokens") if isinstance(next_state.get("tokens"), dict) else {}

    removed: list[dict] = []

    if isinstance(envelope.get("candidates"), list):
        kept_candidates = []
        for row in envelope.get("candidates") or []:
            if not isinstance(row, dict) or _chain(row) != "solana":
                kept_candidates.append(row)
                continue
            token = _token(row)
            t = truth.get(token) or truth_all.get(token) or {}
            if _is_safe(t):
                safe = _safe_row(row, t)
                base_truth = safe.get("truth") if isinstance(safe.get("truth"), dict) else {}
                base_truth["mintability_verified_non_mintable"] = True
                safe["truth"] = base_truth
                kept_candidates.append(safe)
            else:
                removed.append({
                    "surface": "candidate_evidence_envelope",
                    "symbol": row.get("symbol"),
                    "token_address": token,
                    "status": t.get("status") or "UNVERIFIED_BLOCKED",
                    "mintable": t.get("mintable"),
                    "mint_authority": t.get("mint_authority"),
                    "reason": t.get("reason") or "SOLANA_MINTABILITY_NOT_VERIFIED_SAFE",
                })
        envelope["candidates"] = kept_candidates
        _recount_envelope(envelope)
        contract = envelope.get("truth_contract") if isinstance(envelope.get("truth_contract"), dict) else {}
        contract["solana_mint_authority_must_be_revoked_null"] = True
        contract["solana_mintable_tokens_allowed"] = False
        contract["solana_unknown_mintability_allowed"] = False
        envelope["truth_contract"] = contract
        envelope["mintability_guard"] = {
            "version": 1,
            "status": "ENFORCED_FAIL_CLOSED",
            "removed_not_in_candidate_universe": sum(x.get("surface") == "candidate_evidence_envelope" for x in removed),
        }
        _write(envelope_path, envelope)

    for key in LIST_KEYS:
        value = real.get(key)
        if not isinstance(value, list):
            continue
        kept = []
        for row in value:
            if not isinstance(row, dict) or _chain(row) != "solana":
                kept.append(row)
                continue
            token = _token(row)
            t = truth.get(token) or truth_all.get(token) or {}
            if _is_safe(t):
                kept.append(_safe_row(row, t))
            else:
                removed.append({
                    "surface": key,
                    "symbol": row.get("symbol"),
                    "token_address": token,
                    "status": t.get("status") or "UNVERIFIED_BLOCKED",
                    "mintable": t.get("mintable"),
                    "mint_authority": t.get("mint_authority"),
                    "reason": t.get("reason") or "SOLANA_MINTABILITY_NOT_VERIFIED_SAFE",
                })
        real[key] = kept

    counts = real.get("counts") if isinstance(real.get("counts"), dict) else {}
    counts["real_alerts"] = len(real.get("alerts") or [])
    counts["verified_watch_not_real"] = len(real.get("verified_watch") or [])
    counts["evidence_ready_research"] = _real_evidence_ready_count(real)
    counts["identity_pending_not_actionable"] = len(real.get("identity_pending") or [])
    counts["mintability_rejected_not_visible"] = sum(x.get("surface") in LIST_KEYS for x in removed)
    real["counts"] = counts
    truth_contract = real.get("truth_contract") if isinstance(real.get("truth_contract"), dict) else {}
    truth_contract["solana_mint_authority_must_be_revoked_null"] = True
    truth_contract["solana_mintable_tokens_allowed"] = False
    truth_contract["solana_unknown_mintability_allowed"] = False
    real["truth_contract"] = truth_contract
    real["mintability_public_guard"] = {
        "version": 3,
        "status": "ENFORCED_FAIL_CLOSED",
        "rule": "SOLANA_MINT_AUTHORITY_MUST_BE_REVOKED_NULL",
        "removed_not_visible": counts["mintability_rejected_not_visible"],
        "removed_from_candidate_envelope": sum(x.get("surface") == "candidate_evidence_envelope" for x in removed),
        "rejections": removed[:100],
    }
    _write(real_path, real)
    _write(state_path, next_state)

    from .revival_funnel_diagnostics import run as rebuild_funnel
    rebuild_funnel(data_dir)

    return real["mintability_public_guard"]


def main() -> None:
    print(json.dumps(sanitize_real_alerts(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
