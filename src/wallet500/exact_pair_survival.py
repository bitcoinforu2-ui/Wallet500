import json
from datetime import datetime, timezone
from pathlib import Path

from .market_data import snapshot as market_snapshot
from .fresh_solana_gate import evaluate as fresh_survival_evaluate

DATA = Path("data")
ACTIVE = DATA / "active-qualified-candidates.json"
FAILED = DATA / "live-survival-failed.json"
PENDING = DATA / "live-survival-pending.json"
OUTCOMES = DATA / "outcome-tracker.json"
MIN_LIQUIDITY_USD = 50_000.0
MIN_VOLUME_H1_USD = 15_000.0
MIN_TXNS_H1 = 50
MAX_VERIFIED_LOSS_PCT = -25.0
MAX_VERIFIED_DRAWDOWN_PCT = -25.0


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _key(row: dict) -> str:
    chain = str(row.get("chain") or "")
    token = str(row.get("token") or row.get("mint") or "")
    pair = str(row.get("pair_address") or row.get("locked_pair_address") or "")
    if chain in {"ethereum", "bsc"}:
        token, pair = token.lower(), pair.lower()
    return f"{chain}:{token}:{pair}"


def _dedupe_latest(*groups: list[dict]) -> list[dict]:
    rows = {}
    for group in groups:
        for x in group or []:
            if isinstance(x, dict):
                rows[_key(x)] = x
    return list(rows.values())


def _float(row: dict, *names: str):
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            pass
    return None


def _hard_failure_reasons(row: dict) -> list[str]:
    """Evidence already observed on the immutable pair that is sufficient to reject.

    PENDING is reserved for genuinely inconclusive data. A temporary refetch miss
    must never erase verified evidence that the pair is already non-tradable.
    """
    reasons = []
    liquidity = _float(row, "liquidity_usd", "live_liquidity_usd", "production_live_liquidity_usd")
    price = _float(row, "price_usd", "current_price_usd")
    current_return = _float(row, "live_current_return_pct", "current_return_pct")
    drawdown = _float(row, "live_peak_drawdown_pct", "peak_drawdown_pct")

    if price is not None and price <= 0:
        reasons.append("PAIR_PRICE_ZERO_OR_UNAVAILABLE")
    if liquidity is not None and liquidity < MIN_LIQUIDITY_USD:
        reasons.append("LIQUIDITY_LT_50K_HARD_BLOCK")
    if liquidity is not None and liquidity <= 1:
        reasons.append("ZERO_OR_NEAR_ZERO_LIQUIDITY")
    if current_return is not None and current_return <= MAX_VERIFIED_LOSS_PCT:
        reasons.append("VERIFIED_RETURN_BELOW_MINUS_25PCT")
    if drawdown is not None and drawdown <= MAX_VERIFIED_DRAWDOWN_PCT:
        reasons.append("VERIFIED_PEAK_DRAWDOWN_BELOW_MINUS_25PCT")
    return list(dict.fromkeys(reasons))


def _live_reasons(row: dict) -> list[str]:
    reasons = _hard_failure_reasons(row)
    volume = float(row.get("volume_h1") or 0)
    txns = int(row.get("buys_h1") or 0) + int(row.get("sells_h1") or 0)
    if volume < MIN_VOLUME_H1_USD:
        reasons.append("VOLUME_H1_LT_15K")
    if txns < MIN_TXNS_H1:
        reasons.append("TXNS_H1_LT_50")
    return list(dict.fromkeys(reasons))


def _failed(original: dict, reasons: list[str], now: str, locked_pair: str | None = None) -> dict:
    pair = locked_pair or original.get("locked_pair_address") or original.get("pair_address")
    return {**original,
        "qualification": "FAILED_SURVIVAL",
        "pair_address": pair,
        "locked_pair_address": pair,
        "pair_identity_locked": bool(pair),
        "live_survival_gate": "FAILED",
        "live_survival_reasons": list(dict.fromkeys(reasons)),
        "failed_survival_at": original.get("failed_survival_at") or now,
        "survival_checked_at": now}


def run() -> dict:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    active = _load(ACTIVE, [])
    old_failed = _load(FAILED, [])
    old_pending = _load(PENDING, [])
    outcomes = _load(OUTCOMES, {})
    if not isinstance(active, list): active = []
    if not isinstance(old_failed, list): old_failed = []
    if not isinstance(old_pending, list): old_pending = []
    if not isinstance(outcomes, dict): outcomes = {}

    cohort = _dedupe_latest(old_failed, old_pending, active)
    prior_pending = {_key(x) for x in old_pending if isinstance(x, dict)}
    prior_failed = {_key(x) for x in old_failed if isinstance(x, dict)}

    survivors, failed_now, pending_now = [], [], []
    recovered_from_pending = 0
    recovered_from_failed = 0
    hard_failed_from_cached_evidence = 0

    for original in cohort:
        chain = original.get("chain")
        token = original.get("token") or original.get("mint")
        locked_pair = original.get("locked_pair_address") or original.get("pair_address")
        key = _key(original)

        if not chain or not token or not locked_pair:
            cached_fail = _hard_failure_reasons(original)
            if cached_fail:
                failed_now.append(_failed(original, cached_fail + ["MISSING_IMMUTABLE_PAIR_IDENTITY"], now, locked_pair))
                hard_failed_from_cached_evidence += 1
            else:
                pending_now.append({**original,
                    "live_survival_gate": "PENDING",
                    "live_survival_reasons": ["MISSING_IMMUTABLE_PAIR_IDENTITY"],
                    "survival_checked_at": now})
            continue

        live = market_snapshot(chain, token, locked_pair)
        if not live or str(live.get("pair_address") or "").lower() != str(locked_pair).lower():
            cached_fail = _hard_failure_reasons(original)
            if cached_fail:
                failed_now.append(_failed(original, cached_fail + ["LOCKED_PAIR_NOT_RETURNED_BUT_LAST_VERIFIED_STATE_ALREADY_FAILED"], now, locked_pair))
                hard_failed_from_cached_evidence += 1
            else:
                pending_now.append({**original,
                    "pair_address": locked_pair,
                    "locked_pair_address": locked_pair,
                    "pair_identity_locked": True,
                    "live_survival_gate": "PENDING",
                    "live_survival_reasons": ["LOCKED_PAIR_NOT_RETURNED_NO_TERMINAL_EVIDENCE"],
                    "survival_checked_at": now})
            continue

        current = {**original, **live,
            "pair_address": locked_pair,
            "locked_pair_address": locked_pair,
            "pair_identity_locked": True,
            "survival_checked_at": now}

        # $50K is a production hard floor. Apply it before any fresh-launch waiting
        # logic so an obviously non-tradable/dead pair can never be labelled PENDING.
        immediate_fail = _hard_failure_reasons(current)
        if immediate_fail:
            failed_now.append(_failed(current, immediate_fail, now, locked_pair))
            continue

        staged = fresh_survival_evaluate(current, outcomes, now_dt)
        stage_gate = staged.get("live_survival_gate")
        if stage_gate == "PENDING":
            pending_now.append({**staged,
                "qualification": "PENDING",
                "pair_address": locked_pair,
                "locked_pair_address": locked_pair,
                "pair_identity_locked": True,
                "survival_checked_at": now})
            continue
        if stage_gate == "FAILED":
            failed_now.append(_failed(staged, staged.get("live_survival_reasons") or ["FAILED_FRESH_SURVIVAL_GATE"], now, locked_pair))
            continue

        reasons = _live_reasons(staged)
        if reasons:
            failed_now.append(_failed(staged, reasons, now, locked_pair))
        else:
            recovered = key in prior_pending or key in prior_failed
            survivor = {**staged,
                "qualification": "QUALIFIED",
                "live_survival_gate": "ACTIVE",
                "live_survival_reasons": ["PASSED_EXACT_PAIR_LIVE_SURVIVAL_GATE"],
                "recovered_to_active": recovered,
                "recovered_at": now if recovered else original.get("recovered_at"),
                "survival_checked_at": now}
            survivors.append(survivor)
            if key in prior_pending: recovered_from_pending += 1
            if key in prior_failed: recovered_from_failed += 1

    _write(ACTIVE, survivors)
    _write(FAILED, failed_now)
    _write(PENDING, pending_now)

    report = {
        "updated_at": now,
        "method": "PERSISTENT_IMMUTABLE_EXACT_PAIR_REVALIDATION_V2",
        "input_active": len(active),
        "input_pending": len(old_pending),
        "input_failed": len(old_failed),
        "recheck_cohort": len(cohort),
        "active_after": len(survivors),
        "failed_now": len(failed_now),
        "pending_now": len(pending_now),
        "hard_failed_from_cached_evidence": hard_failed_from_cached_evidence,
        "recovered_from_pending": recovered_from_pending,
        "recovered_from_failed": recovered_from_failed,
        "min_liquidity_usd": MIN_LIQUIDITY_USD,
        "min_volume_h1_usd": MIN_VOLUME_H1_USD,
        "min_txns_h1": MIN_TXNS_H1,
        "rule": "PENDING_ONLY_WHEN_INCONCLUSIVE; VERIFIED_SUB_50K_ZERO_LIQUIDITY_OR_MAJOR_DRAWDOWN_IS_FAILED",
    }
    _write(DATA / "exact-pair-survival-report.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
