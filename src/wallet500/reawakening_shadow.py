from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODE = "RESEARCH_ONLY_SURVIVOR_REAWAKENING_V2"
CONTRACT = "FALSE_NEGATIVE_RECOVERY_RECHECK_V2"

MIN_LIQUIDITY_USD = 50_000.0
MIN_CONFIRMATION_SPAN_MINUTES = 15.0
MIN_LIQUIDITY_RETENTION = 0.90
MIN_GAIN_SINCE_REJECT_PCT = -25.0
MAX_GAIN_SINCE_REJECT_PCT = 50.0

# Shadow-only separator hypothesis derived from the winner/control study.
# These are not production thresholds.
MIN_VOLUME_H1_USD = 43_000.0
MIN_TURNOVER_H1 = 0.20
MIN_TXNS_H1 = 350
MIN_BUY_SELL_RATIO_H1 = 1.18
MIN_ACTIVITY_CHECKS_AVAILABLE = 3
MIN_ACTIVITY_CHECKS_PASS = 3
REQUIRED_CONSECUTIVE = 2

ELIGIBLE_SOURCE = "LIVE_SURVIVAL_FAILED"
REQUIRED_REASONS = {
    "CURRENT_LIQUIDITY_BELOW_50K",
    "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION",
}
HARD_EXCLUDED_REASONS = {
    "VERIFIED_RETURN_BELOW_MINUS_25PCT",
    "PUMP_THEN_FAST_REVERSAL",
    "PARABOLIC_MOVE_ALREADY_REVERSING",
}

MARKET_SOURCES = (
    "active-qualified-candidates.json",
    "production-risk-evaluations.json",
    "qualified-candidates.json",
    "watchlist.json",
    "fresh-solana-survival.json",
)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _dt(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "candidates", "active", "qualified", "blocked", "review"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _identity(row: dict) -> tuple[str, str, str]:
    chain = str(row.get("chain") or "").lower()
    if chain == "eth":
        chain = "ethereum"
    elif chain in {"bnb", "bsc"}:
        chain = "bsc"
    elif chain in {"sol", "solana"}:
        chain = "solana"
    token = str(row.get("token") or row.get("token_address") or row.get("mint") or "")
    pair = str(row.get("pair_address") or row.get("locked_pair_address") or row.get("pair") or "")
    if chain in {"ethereum", "bsc"}:
        token = token.lower()
        pair = pair.lower()
    return chain, token, pair


def _key(row: dict) -> str:
    chain, token, pair = _identity(row)
    return f"{chain}|{token}|{pair}"


def _first_reasons(record: dict) -> list[str]:
    snap = record.get("first_reject_snapshot")
    if not isinstance(snap, dict):
        return []
    reasons: list[str] = []
    for field in (
        "live_survival_reasons",
        "qualification_reasons",
        "production_risk_reasons",
        "holder_cluster_reasons",
    ):
        values = snap.get(field)
        if isinstance(values, list):
            reasons.extend(str(x) for x in values if x)
    return list(dict.fromkeys(reasons))


def eligible_reject(record: dict) -> tuple[bool, list[str]]:
    reasons = set(_first_reasons(record))
    checks = {
        "source_live_survival_failed": str(record.get("first_reject_source") or "") == ELIGIBLE_SOURCE,
        "liquidity_only_failure_present": "CURRENT_LIQUIDITY_BELOW_50K" in reasons,
        "other_quality_checks_passed": "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION" in reasons,
        "no_hard_reversal_reason": not bool(reasons & HARD_EXCLUDED_REASONS),
    }
    return all(checks.values()), [name.upper() for name, passed in checks.items() if passed]


def _market_snapshot(row: dict, source: str, now: str) -> dict:
    chain, token, pair = _identity(row)
    return {
        "observed_at": row.get("observed_at") or row.get("updated_at") or now,
        "chain": chain,
        "token": token,
        "pair_address": pair,
        "source": source,
        "price_usd": row.get("price_usd"),
        "liquidity_usd": row.get("live_liquidity_usd") or row.get("liquidity_usd"),
        "volume_h1": row.get("live_volume_h1") or row.get("volume_h1"),
        "buys_h1": row.get("buys_h1"),
        "sells_h1": row.get("sells_h1"),
    }


def _activity_metrics(row: dict) -> tuple[dict, dict]:
    liquidity = _f(row.get("liquidity_usd"))
    volume = _f(row.get("volume_h1"))
    buys_raw = row.get("buys_h1")
    sells_raw = row.get("sells_h1")
    buys = _i(buys_raw)
    sells = _i(sells_raw)
    txns = buys + sells
    turnover = volume / max(liquidity, 1.0)
    ratio = buys / max(sells, 1)

    availability = {
        "volume_h1": row.get("volume_h1") is not None,
        "turnover_h1": row.get("volume_h1") is not None and row.get("liquidity_usd") is not None,
        "txns_h1": buys_raw is not None and sells_raw is not None,
        "buy_sell_ratio_h1": buys_raw is not None and sells_raw is not None,
    }
    checks = {
        "volume_h1": availability["volume_h1"] and volume >= MIN_VOLUME_H1_USD,
        "turnover_h1": availability["turnover_h1"] and turnover >= MIN_TURNOVER_H1,
        "txns_h1": availability["txns_h1"] and txns >= MIN_TXNS_H1,
        "buy_sell_ratio_h1": availability["buy_sell_ratio_h1"] and ratio >= MIN_BUY_SELL_RATIO_H1,
    }
    metrics = {
        "volume_h1_usd": round(volume, 2),
        "turnover_h1": round(turnover, 4),
        "txns_h1": txns,
        "buy_sell_ratio_h1": round(ratio, 4),
        "activity_checks_available": sum(availability.values()),
        "activity_checks_passed": sum(bool(checks[k]) for k in checks if availability[k]),
    }
    return checks, metrics


def observation_passes(row: dict, reject_price: float) -> tuple[bool, list[str], dict]:
    price = _f(row.get("price_usd"))
    liquidity = _f(row.get("liquidity_usd"))
    pair = str(row.get("pair_address") or "")
    gain = (price / reject_price - 1.0) * 100.0 if reject_price > 0 and price > 0 else -10_000.0
    _activity_checks, activity_metrics = _activity_metrics(row)
    available = int(activity_metrics["activity_checks_available"])
    passed_activity = int(activity_metrics["activity_checks_passed"])
    checks = {
        "exact_pair_present": bool(pair),
        "price_present": price > 0,
        "liquidity_recovered": liquidity >= MIN_LIQUIDITY_USD,
        "anti_chase_window": MIN_GAIN_SINCE_REJECT_PCT <= gain <= MAX_GAIN_SINCE_REJECT_PCT,
        "activity_coverage": available >= MIN_ACTIVITY_CHECKS_AVAILABLE,
        "activity_separator": passed_activity >= MIN_ACTIVITY_CHECKS_PASS,
    }
    metrics = {
        "gain_since_reject_pct": round(gain, 4),
        "price_usd": price,
        "liquidity_usd": round(liquidity, 2),
        **activity_metrics,
    }
    reasons = [name.upper() for name, ok in checks.items() if ok]
    return all(checks.values()), reasons, metrics


def first_forward_trigger(record: dict, observations: list[dict] | None = None, not_before: str | None = None) -> dict | None:
    eligible, eligible_reasons = eligible_reject(record)
    if not eligible:
        return None

    snap = record.get("first_reject_snapshot") if isinstance(record.get("first_reject_snapshot"), dict) else {}
    reject_price = _f(snap.get("price_usd"))
    reject_at = _dt(snap.get("observed_at") or record.get("first_rejected_at"))
    forward_start = _dt(not_before) if not_before else None
    cutoff = reject_at
    if forward_start is not None and (cutoff is None or forward_start > cutoff):
        cutoff = forward_start
    expected_pair = str((record.get("identity") or {}).get("pair_address") or snap.get("pair_address") or "")
    chain = str((record.get("identity") or {}).get("chain") or snap.get("chain") or "").lower()
    if chain == "eth":
        chain = "ethereum"
    elif chain in {"bnb", "bsc"}:
        chain = "bsc"
    elif chain in {"sol", "solana"}:
        chain = "solana"
    if chain in {"ethereum", "bsc"}:
        expected_pair = expected_pair.lower()
    if reject_price <= 0 or not expected_pair:
        return None

    history = observations
    if history is None:
        history = record.get("reawakening_observations")
        if not isinstance(history, list):
            history = record.get("observations") if isinstance(record.get("observations"), list) else []

    ordered = sorted(
        [x for x in history if isinstance(x, dict)],
        key=lambda x: str(x.get("observed_at") or ""),
    )
    streak: list[tuple[dict, dict, list[str]]] = []
    for row in ordered:
        observed = _dt(row.get("observed_at"))
        if cutoff is not None and (observed is None or observed <= cutoff):
            continue

        row_pair = str(row.get("pair_address") or "")
        if chain in {"ethereum", "bsc"}:
            row_pair = row_pair.lower()
        if row_pair != expected_pair:
            streak = []
            continue

        passed, reasons, metrics = observation_passes(row, reject_price)
        if not passed:
            streak = []
            continue

        if streak:
            previous_row = streak[-1][0]
            previous_price = _f(previous_row.get("price_usd"))
            previous_liquidity = _f(previous_row.get("liquidity_usd"))
            current_price = _f(row.get("price_usd"))
            current_liquidity = _f(row.get("liquidity_usd"))
            if current_price < previous_price or current_liquidity < previous_liquidity * MIN_LIQUIDITY_RETENTION:
                streak = []

        streak.append((row, metrics, reasons))
        if len(streak) < REQUIRED_CONSECUTIVE:
            continue

        first_at = _dt(streak[0][0].get("observed_at"))
        current_at = _dt(streak[-1][0].get("observed_at"))
        if first_at is None or current_at is None:
            continue
        span_minutes = (current_at - first_at).total_seconds() / 60.0
        if span_minutes < MIN_CONFIRMATION_SPAN_MINUTES:
            continue

        first_row, first_metrics, _ = streak[0]
        current_row, current_metrics, current_reasons = streak[-1]
        return {
            "triggered_at": current_row.get("observed_at"),
            "first_confirmation_at": first_row.get("observed_at"),
            "confirmation_observations": len(streak),
            "confirmation_span_minutes": round(span_minutes, 2),
            "pair_address": current_row.get("pair_address"),
            "price_usd": current_row.get("price_usd"),
            "metrics": current_metrics,
            "first_confirmation_metrics": first_metrics,
            "reasons": eligible_reasons + current_reasons + [
                "PRICE_NON_FALLING_ACROSS_CONFIRMATIONS",
                "LIQUIDITY_RETENTION_CONFIRMED",
            ],
        }
    return None


def _dedupe_append(observations: list[dict], snapshot: dict) -> bool:
    fp = (
        snapshot.get("observed_at"),
        snapshot.get("source"),
        snapshot.get("price_usd"),
        snapshot.get("liquidity_usd"),
    )
    existing = {
        (x.get("observed_at"), x.get("source"), x.get("price_usd"), x.get("liquidity_usd"))
        for x in observations
        if isinstance(x, dict)
    }
    if fp in existing:
        return False
    observations.append(snapshot)
    return True


def run(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ledger = _load(out / "rejected-candidate-ledger.json", {})
    records = ledger.get("records") if isinstance(ledger, dict) and isinstance(ledger.get("records"), dict) else {}

    state_path = out / "reawakening-shadow-state.json"
    old_state = _load(state_path, {})
    now = datetime.now(timezone.utc).isoformat()
    v2_started_at = str(old_state.get("v2_started_at") or old_state.get("updated_at") or now)

    legacy_v1 = old_state.get("legacy_v1_triggers") if isinstance(old_state.get("legacy_v1_triggers"), dict) else {}
    old_v1 = old_state.get("triggers") if isinstance(old_state.get("triggers"), dict) else {}
    if old_v1:
        legacy_v1 = {**old_v1, **legacy_v1}

    candidates = old_state.get("v2_candidates") if isinstance(old_state.get("v2_candidates"), dict) else {}
    triggers = old_state.get("v2_triggers") if isinstance(old_state.get("v2_triggers"), dict) else {}

    # Primary recheck source: the immutable exact-pair outcome history already maintained
    # for the project. V1 used this source successfully; V2 only consumes observations
    # strictly after v2_started_at so historical false negatives cannot become fake
    # forward triggers.
    tracker = _load(out / "outcome-tracker.json", {})
    tracker_tokens = tracker.get("tokens") if isinstance(tracker, dict) and isinstance(tracker.get("tokens"), dict) else {}
    tracker_index: dict[str, dict] = {}
    for tracker_record in tracker_tokens.values():
        if not isinstance(tracker_record, dict):
            continue
        canonical = _key({
            "chain": tracker_record.get("chain"),
            "token": tracker_record.get("token"),
            "pair_address": tracker_record.get("entry_pair_address"),
        })
        if canonical != "||":
            tracker_index[canonical] = tracker_record

    # Small live files remain a fallback for records not yet represented in the
    # outcome tracker. They can add a current mark, but never bypass the exact-pair
    # and v2_started_at checks.
    market: dict[str, dict] = {}
    for filename in MARKET_SOURCES:
        for row in _rows(_load(out / filename, [])):
            canonical = _key(row)
            if canonical != "||":
                market[canonical] = _market_snapshot(row, filename, now)

    eligible_count = 0
    tracker_matches = 0
    fallback_market_matches = 0
    forward_history_rows = 0
    observations_added = 0
    rows = []

    v2_start_dt = _dt(v2_started_at)
    for ledger_key, record in records.items():
        if not isinstance(record, dict):
            continue
        eligible, eligible_reasons = eligible_reject(record)
        if not eligible:
            continue
        eligible_count += 1

        snap = record.get("first_reject_snapshot") if isinstance(record.get("first_reject_snapshot"), dict) else {}
        identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
        canonical = _key({
            "chain": identity.get("chain") or snap.get("chain"),
            "token": identity.get("token") or snap.get("token"),
            "pair_address": identity.get("pair_address") or snap.get("pair_address"),
        })
        cstate = candidates.get(ledger_key) if isinstance(candidates.get(ledger_key), dict) else {
            "token_key": ledger_key,
            "canonical_identity": canonical,
            "chain": identity.get("chain") or snap.get("chain"),
            "token": identity.get("token") or snap.get("token"),
            "pair_address": identity.get("pair_address") or snap.get("pair_address"),
            "first_rejected_at": record.get("first_rejected_at"),
            "first_reject_snapshot": snap,
            "eligibility_reasons": eligible_reasons,
            "fallback_observations": [],
        }
        cstate["canonical_identity"] = canonical
        cstate["v2_started_at"] = v2_started_at
        cstate["updated_at"] = now

        tracker_record = tracker_index.get(canonical)
        observations: list[dict]
        evidence_source: str
        if isinstance(tracker_record, dict):
            tracker_matches += 1
            history = tracker_record.get("history") if isinstance(tracker_record.get("history"), list) else []
            observations = [x for x in history if isinstance(x, dict)]
            if v2_start_dt is not None:
                for x in observations:
                    observed = _dt(x.get("observed_at"))
                    if observed is not None and observed > v2_start_dt:
                        forward_history_rows += 1
            evidence_source = "OUTCOME_TRACKER_EXACT_PAIR_HISTORY"
        else:
            fallback = cstate.get("fallback_observations") if isinstance(cstate.get("fallback_observations"), list) else []
            current = market.get(canonical)
            if current:
                fallback_market_matches += 1
                if _dedupe_append(fallback, current):
                    observations_added += 1
            cstate["fallback_observations"] = fallback[-500:]
            observations = cstate["fallback_observations"]
            evidence_source = "SMALL_LIVE_FILE_FALLBACK"

        candidates[ledger_key] = cstate
        found = first_forward_trigger(record, observations, not_before=v2_started_at)
        immutable = triggers.get(ledger_key)
        if found is not None and not isinstance(immutable, dict):
            immutable = {
                "token_key": ledger_key,
                "canonical_identity": canonical,
                "chain": cstate.get("chain"),
                "token": cstate.get("token"),
                "entry_pair_address": cstate.get("pair_address"),
                "first_rejected_at": cstate.get("first_rejected_at"),
                "v2_started_at": v2_started_at,
                "evidence_source": evidence_source,
                **found,
            }
            triggers[ledger_key] = immutable
        if isinstance(immutable, dict):
            rows.append({
                **immutable,
                "status": "SURVIVOR_REAWAKENING_SHADOW_WATCH",
                "production_portfolio_impact": "NONE",
            })

    rows.sort(key=lambda x: str(x.get("triggered_at") or ""), reverse=True)
    payload = {
        "version": 2,
        "mode": MODE,
        "contract": CONTRACT,
        "generated_at": now,
        "v2_started_at": v2_started_at,
        "production_portfolio_impact": "NONE",
        "production_gate_changed": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "source_ledger": "rejected-candidate-ledger.json",
        "primary_recheck_source": "outcome-tracker.json exact-pair history",
        "selection_rule": {
            "first_reject_source": ELIGIBLE_SOURCE,
            "required_reasons": sorted(REQUIRED_REASONS),
            "hard_excluded_reasons": sorted(HARD_EXCLUDED_REASONS),
        },
        "recovery_rule": {
            "liquidity_gte_usd": MIN_LIQUIDITY_USD,
            "gain_since_reject_pct_range": [MIN_GAIN_SINCE_REJECT_PCT, MAX_GAIN_SINCE_REJECT_PCT],
            "confirmation_observations": REQUIRED_CONSECUTIVE,
            "confirmation_span_minutes_gte": MIN_CONFIRMATION_SPAN_MINUTES,
            "liquidity_retention_gte": MIN_LIQUIDITY_RETENTION,
            "price_non_falling": True,
            "exact_pair_locked": True,
            "observations_must_be_after_v2_started_at": True,
        },
        "shadow_activity_hypothesis": {
            "volume_h1_gte_usd": MIN_VOLUME_H1_USD,
            "turnover_h1_gte": MIN_TURNOVER_H1,
            "txns_h1_gte": MIN_TXNS_H1,
            "buy_sell_ratio_h1_gte": MIN_BUY_SELL_RATIO_H1,
            "minimum_checks_available": MIN_ACTIVITY_CHECKS_AVAILABLE,
            "minimum_checks_passed": MIN_ACTIVITY_CHECKS_PASS,
            "basis": "midpoint-style research hypothesis from winner/control separator medians; not production thresholds",
        },
        "truth_rules": [
            "the original rejection is immutable and is never removed retroactively",
            "only LIVE_SURVIVAL_FAILED liquidity-only rejects that already passed other quality checks enter V2",
            "verified deep loss and fast/parabolic reversal reasons are hard-excluded",
            "historical outcome rows at or before v2_started_at are never eligible to create a V2 forward trigger",
            "the exact pair must remain identical and liquidity must be back above the unchanged $50K hard floor",
            "two or more qualifying observations spanning at least 15 minutes are required",
            "V2 is research-only and cannot create BUY, QUALIFIED, or production portfolio impact",
            "legacy V1 trigger history is preserved separately and does not qualify as V2 evidence",
        ],
        "counts": {
            "rejected_ledger_records": len(records),
            "eligible_liquidity_only_rejects": eligible_count,
            "outcome_tracker_records": len(tracker_tokens),
            "outcome_tracker_matches": tracker_matches,
            "forward_tracker_rows_after_v2_start": forward_history_rows,
            "fallback_market_matches_now": fallback_market_matches,
            "fallback_observations_added_this_run": observations_added,
            "shadow_triggers_v2": len(rows),
            "legacy_v1_triggers_preserved": len(legacy_v1),
        },
        "targets": rows,
    }
    state = {
        "version": 2,
        "mode": MODE,
        "updated_at": now,
        "v2_started_at": v2_started_at,
        "legacy_v1_triggers": legacy_v1,
        "v2_candidates": candidates,
        "v2_triggers": triggers,
    }
    _write(state_path, state)
    _write(out / "reawakening-shadow.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
