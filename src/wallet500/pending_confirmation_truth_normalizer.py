from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA = Path("data")
INPUT = DATA / "candidate-evidence-envelope.json"

PENDING_MARKET = "MARKET_CONFIRMATION_PENDING"
PENDING_INDEPENDENT = "INDEPENDENT_EVIDENCE_PENDING"
OUTCOME_MARKET_NEUTRAL = "MARKET_EVIDENCE_VERIFIED_NOT_POSITIVE"
OUTCOME_INDEPENDENT_NEUTRAL = "INDEPENDENT_EVIDENCE_VERIFIED_NOT_POSITIVE"


def _numeric(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _market_observed(candidate: dict) -> bool:
    truth = candidate.get("truth") if isinstance(candidate.get("truth"), dict) else {}
    market = candidate.get("market") if isinstance(candidate.get("market"), dict) else {}
    return bool(
        truth.get("revival_source_fresh") is True
        and truth.get("exact_pair_verified") is True
        and _numeric(market.get("price_usd"))
        and _numeric(market.get("liquidity_usd"))
    )


def _independent_observed(candidate: dict) -> bool:
    coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
    return int(coverage.get("verified_independent_count") or 0) > 0


def normalize(payload: dict) -> dict:
    """Make PENDING mean missing/unverified only, never merely non-positive.

    This is diagnostics-only normalization. It never changes evidence_ready, market_positive,
    family positive flags, candidate status, discovery tier, automatic_buy, or the strict
    downstream REAL ALERT gate.
    """
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    market_neutral = 0
    independent_neutral = 0

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        pending = [str(x) for x in (candidate.get("pending_confirmations") or [])]
        outcomes = [str(x) for x in (candidate.get("verification_outcomes") or [])]

        if PENDING_MARKET in pending and _market_observed(candidate):
            pending = [x for x in pending if x != PENDING_MARKET]
            if OUTCOME_MARKET_NEUTRAL not in outcomes:
                outcomes.append(OUTCOME_MARKET_NEUTRAL)
            market_neutral += 1

        if PENDING_INDEPENDENT in pending and _independent_observed(candidate):
            pending = [x for x in pending if x != PENDING_INDEPENDENT]
            if OUTCOME_INDEPENDENT_NEUTRAL not in outcomes:
                outcomes.append(OUTCOME_INDEPENDENT_NEUTRAL)
            independent_neutral += 1

        candidate["pending_confirmations"] = sorted(set(pending))
        candidate["verification_outcomes"] = sorted(set(outcomes))

    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    counts["market_confirmation_pending"] = sum(
        1 for c in candidates if PENDING_MARKET in (c.get("pending_confirmations") or [])
    )
    counts["independent_evidence_pending"] = sum(
        1 for c in candidates if PENDING_INDEPENDENT in (c.get("pending_confirmations") or [])
    )
    counts["market_evidence_verified_not_positive"] = sum(
        1 for c in candidates if OUTCOME_MARKET_NEUTRAL in (c.get("verification_outcomes") or [])
    )
    counts["independent_evidence_verified_not_positive"] = sum(
        1 for c in candidates if OUTCOME_INDEPENDENT_NEUTRAL in (c.get("verification_outcomes") or [])
    )
    counts["true_pending_candidates"] = sum(
        1 for c in candidates if bool(c.get("pending_confirmations"))
    )
    payload["counts"] = counts

    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth["pending_semantics_missing_or_unverified_only"] = True
    truth["verified_not_positive_is_not_pending"] = True
    truth["normalizer_changes_candidate_promotion"] = False
    truth["normalizer_changes_real_alert_gate"] = False
    payload["truth_contract"] = truth
    payload["pending_confirmation_normalization"] = {
        "version": 1,
        "market_reclassified_verified_not_positive": market_neutral,
        "independent_reclassified_verified_not_positive": independent_neutral,
        "promotion_changed": False,
        "real_alert_gate_changed": False,
    }
    return payload


def run(path: Path = INPUT) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload = normalize(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "counts": payload.get("counts"),
        "pending_confirmation_normalization": payload.get("pending_confirmation_normalization"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
