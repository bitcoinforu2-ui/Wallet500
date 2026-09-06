from __future__ import annotations

import json
import os

from . import revival_prewaking_wallet_evidence as pre
from . import revival_wallet_evidence as collector

RETAIN_SECONDS = int(os.environ.get("REVIVAL_PREWAKING_RETAIN_SECONDS", "7200"))


def _i(value: object, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def retain_fresh_rotation_evidence(payload: dict) -> dict:
    """Publish still-fresh evidence from previous rotation slots without reusing stale rows.

    The RPC collector deliberately scans only a bounded target set per run. Its state,
    however, retains exact-pair forward observations for earlier rotation slots. This
    function republishes only state rows whose exact pair is still the current verified
    pair and whose last successful/attempted observation is no older than RETAIN_SECONDS.
    No row is made positive here and no production/REAL ALERT gate is changed.
    """
    now = collector._epoch_now()
    revival = collector._load(pre.REVIVAL, {})
    state = collector._load(pre.STATE, {})
    token_states = state.get("tokens") if isinstance(state.get("tokens"), dict) else {}
    ranked = pre._ranked_candidates(revival)
    ranked_by = {str(row.get("token_address") or ""): row for row in ranked}

    current_rows = [row for row in (payload.get("tokens") or []) if isinstance(row, dict)]
    published = {str(row.get("token_address") or ""): row for row in current_rows if row.get("token_address")}
    selected_tokens = list(published)
    retained = 0
    stale_skipped = 0
    pair_mismatch_skipped = 0

    for mint, target in ranked_by.items():
        if not mint or mint in published:
            continue
        token_state = token_states.get(mint)
        if not isinstance(token_state, dict):
            continue
        expected_pair = str(target.get("pair_address") or "")
        state_pair = str(token_state.get("pair_address") or "")
        if not expected_pair or state_pair.lower() != expected_pair.lower():
            pair_mismatch_skipped += 1
            continue
        last_run = token_state.get("last_run") if isinstance(token_state.get("last_run"), dict) else {}
        last_at = _i(last_run.get("at"))
        age = now - last_at if last_at > 0 else RETAIN_SECONDS + 1
        if age < 0 or age > RETAIN_SECONDS:
            stale_skipped += 1
            continue

        summary = collector._summary_for(target, token_state, now)
        summary["target_reason"] = target.get("reason")
        summary["selection_lane"] = "ROTATION_COVERAGE"
        summary["publication_lane"] = "RETAINED_ROTATION_EVIDENCE"
        summary["activity_tier"] = target.get("activity_tier")
        summary["activity_rank"] = target.get("activity_rank")
        summary["prewaking_rank_score"] = target.get("prewaking_rank_score")
        summary["source_revival_generated_at"] = target.get("source_revival_generated_at")
        summary["evidence_age_seconds"] = age
        summary["evidence_last_observed_at"] = collector._iso(last_at)
        summary["future_t0_eligibility"] = "POTENTIAL_IF_WAKING_OCCURS_AFTER_MONITOR_START"
        coverage = summary.setdefault("coverage", {})
        coverage["eligible_as_forensics_t0_wallet_evidence"] = False
        coverage["retained_rotation_evidence"] = True
        published[mint] = summary
        retained += 1

    selected_set = set(selected_tokens)
    payload["selected_target_tokens"] = selected_tokens
    payload["tokens"] = current_rows + [
        row for mint, row in published.items() if mint not in selected_set
    ]
    payload["published_wallet_evidence_rows"] = len(payload["tokens"])
    payload["rotation_retention"] = {
        "enabled": True,
        "freshness_limit_seconds": RETAIN_SECONDS,
        "selected_this_run": len(selected_tokens),
        "retained_fresh_rows": retained,
        "stale_rows_skipped": stale_skipped,
        "pair_mismatch_rows_skipped": pair_mismatch_skipped,
        "candidate_universe": len(ranked_by),
        "no_hindsight": True,
        "production_effect": False,
    }
    truth = payload.setdefault("truth_contract", {})
    truth["retained_rotation_rows_require_current_exact_pair"] = True
    truth["retained_rotation_rows_require_fresh_last_run"] = True
    truth["retained_rotation_rows_never_change_positive_status"] = True
    collector._write(pre.LATEST, payload)
    return payload


def main() -> None:
    payload = collector._load(pre.LATEST, {})
    payload = retain_fresh_rotation_evidence(payload)
    print(json.dumps({
        "targets": payload.get("targets"),
        "published_wallet_evidence_rows": payload.get("published_wallet_evidence_rows"),
        "rotation_retention": payload.get("rotation_retention"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
