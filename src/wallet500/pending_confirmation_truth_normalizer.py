from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
INPUT = DATA / "candidate-evidence-envelope.json"
WALLET_PROBE = DATA / "revival-wallet-coverage-probe.json"

PENDING_MARKET = "MARKET_CONFIRMATION_PENDING"
PENDING_INDEPENDENT = "INDEPENDENT_EVIDENCE_PENDING"
PENDING_WALLET = "WALLET_COVERAGE_PENDING"
OUTCOME_MARKET_NEUTRAL = "MARKET_EVIDENCE_VERIFIED_NOT_POSITIVE"
OUTCOME_INDEPENDENT_NEUTRAL = "INDEPENDENT_EVIDENCE_VERIFIED_NOT_POSITIVE"
OUTCOME_WALLET_PROBE = "WALLET_COVERAGE_VERIFIED_NON_PROMOTING_PROBE"
OUTCOME_WALLET_GAP = "WALLET_ATTRIBUTION_GAP_VERIFIED_FAIL_CLOSED"
WALLET_PROBE_MAX_AGE_SECONDS = 7200


def _numeric(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


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


def _wallet_probe_index(probe: dict, now: datetime) -> tuple[dict[str, dict], bool]:
    if not isinstance(probe, dict):
        return {}, False
    truth = probe.get("truth_contract") if isinstance(probe.get("truth_contract"), dict) else {}
    if (
        probe.get("version") != "REVIVAL_WALLET_COVERAGE_PROBE_V1"
        or probe.get("mode") != "RESEARCH_ONLY_EXACT_PAIR_WALLET_COVERAGE_PROBE"
        or truth.get("probe_is_coverage_only_not_accumulation_alpha") is not True
        or truth.get("probe_never_changes_candidate_promotion") is not True
        or truth.get("probe_never_changes_real_alert_gate") is not True
        or truth.get("unresolved_target_mint_touch_fails_closed") is not True
    ):
        return {}, False
    stamp = _dt(probe.get("generated_at"))
    fresh = bool(stamp and 0 <= (now - stamp.astimezone(timezone.utc)).total_seconds() <= WALLET_PROBE_MAX_AGE_SECONDS)
    if not fresh:
        return {}, False
    index = {}
    for row in probe.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        token = str(row.get("token_address") or "").strip()
        if token:
            index[token] = row
    return index, True


def _wallet_probe_classification(candidate: dict, probe_index: dict[str, dict], probe_fresh: bool) -> tuple[str, dict | None]:
    if not probe_fresh:
        return "PENDING", None
    token = str(candidate.get("token_address") or "").strip()
    expected_pair = str(candidate.get("pair_address") or "").strip()
    row = probe_index.get(token)
    if not isinstance(row, dict):
        return "PENDING", None
    row_pair = str(row.get("pair_address") or "").strip()
    safe_role = row.get("promotion_eligible") is False and row.get("positive") is False
    pair_ok = bool(expected_pair and row_pair and expected_pair.lower() == row_pair.lower())
    if not pair_ok or not safe_role:
        return "PENDING", row
    if row.get("coverage_verified") is True:
        return "VERIFIED", row
    if row.get("unresolved_target_touch") is True and row.get("target_mint_touched") is True:
        return "ATTRIBUTION_GAP", row
    return "PENDING", row


def normalize(payload: dict, wallet_probe: dict | None = None, now: datetime | None = None) -> dict:
    """Make PENDING mean missing/unverified only, never verified-neutral or a proven gap.

    The broad wallet probe can close WALLET_COVERAGE_PENDING in two truthful ways:
    (1) coverage was verified, or (2) an exact target-mint touch was verified but signed
    owner attribution could not be proven. The second case is an explicit fail-closed
    attribution gap, not positive wallet evidence. Neither case contributes to promotion.
    """
    now = now or datetime.now(timezone.utc)
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    market_neutral = 0
    independent_neutral = 0
    wallet_probe_verified = 0
    wallet_attribution_gap = 0
    probe_index, probe_fresh = _wallet_probe_index(wallet_probe or {}, now)

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

        wallet_class, probe_row = _wallet_probe_classification(candidate, probe_index, probe_fresh)
        if PENDING_WALLET in pending and wallet_class in {"VERIFIED", "ATTRIBUTION_GAP"}:
            pending = [x for x in pending if x != PENDING_WALLET]
            coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
            coverage["wallet_coverage_observed"] = True
            coverage["wallet_coverage_observation_role"] = "NON_PROMOTING_BROAD_PROBE"
            coverage["wallet_coverage_probe_status"] = (probe_row or {}).get("status")
            if wallet_class == "VERIFIED":
                if OUTCOME_WALLET_PROBE not in outcomes:
                    outcomes.append(OUTCOME_WALLET_PROBE)
                coverage["wallet_attribution_resolved"] = bool((probe_row or {}).get("resolved_signed_owner"))
                wallet_probe_verified += 1
            else:
                if OUTCOME_WALLET_GAP not in outcomes:
                    outcomes.append(OUTCOME_WALLET_GAP)
                coverage["wallet_attribution_resolved"] = False
                coverage["wallet_attribution_gap_fail_closed"] = True
                wallet_attribution_gap += 1
            candidate["coverage"] = coverage

        candidate["pending_confirmations"] = sorted(set(pending))
        candidate["verification_outcomes"] = sorted(set(outcomes))

    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    counts["market_confirmation_pending"] = sum(
        1 for c in candidates if PENDING_MARKET in (c.get("pending_confirmations") or [])
    )
    counts["independent_evidence_pending"] = sum(
        1 for c in candidates if PENDING_INDEPENDENT in (c.get("pending_confirmations") or [])
    )
    counts["wallet_coverage_pending"] = sum(
        1 for c in candidates if PENDING_WALLET in (c.get("pending_confirmations") or [])
    )
    counts["market_evidence_verified_not_positive"] = sum(
        1 for c in candidates if OUTCOME_MARKET_NEUTRAL in (c.get("verification_outcomes") or [])
    )
    counts["independent_evidence_verified_not_positive"] = sum(
        1 for c in candidates if OUTCOME_INDEPENDENT_NEUTRAL in (c.get("verification_outcomes") or [])
    )
    counts["wallet_coverage_verified_non_promoting_probe"] = sum(
        1 for c in candidates if OUTCOME_WALLET_PROBE in (c.get("verification_outcomes") or [])
    )
    counts["wallet_attribution_gap_verified_fail_closed"] = sum(
        1 for c in candidates if OUTCOME_WALLET_GAP in (c.get("verification_outcomes") or [])
    )
    counts["true_pending_candidates"] = sum(
        1 for c in candidates if bool(c.get("pending_confirmations"))
    )
    payload["counts"] = counts

    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth["pending_semantics_missing_or_unverified_only"] = True
    truth["verified_not_positive_is_not_pending"] = True
    truth["verified_wallet_attribution_gap_is_not_pending_and_never_positive"] = True
    truth["broad_wallet_probe_is_non_promoting_coverage_only"] = True
    truth["normalizer_changes_candidate_promotion"] = False
    truth["normalizer_changes_real_alert_gate"] = False
    payload["truth_contract"] = truth
    payload["pending_confirmation_normalization"] = {
        "version": 3,
        "market_reclassified_verified_not_positive": market_neutral,
        "independent_reclassified_verified_not_positive": independent_neutral,
        "wallet_reclassified_coverage_observed_non_promoting": wallet_probe_verified,
        "wallet_reclassified_attribution_gap_fail_closed": wallet_attribution_gap,
        "wallet_probe_fresh": probe_fresh,
        "wallet_probe_rows": len(probe_index),
        "promotion_changed": False,
        "real_alert_gate_changed": False,
    }
    return payload


def run(path: Path = INPUT, wallet_probe_path: Path = WALLET_PROBE) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    probe = json.loads(wallet_probe_path.read_text(encoding="utf-8")) if wallet_probe_path.exists() else {}
    payload = normalize(payload, probe)
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
