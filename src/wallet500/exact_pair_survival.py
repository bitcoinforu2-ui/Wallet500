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
    """Build the persistent survival cohort without losing prior PENDING/FAILED rows."""
    rows = {}
    for group in groups:
        for x in group or []:
            if isinstance(x, dict):
                rows[_key(x)] = x
    return list(rows.values())


def _live_reasons(row: dict) -> list[str]:
    reasons = []
    liquidity = float(row.get("liquidity_usd") or 0)
    volume = float(row.get("volume_h1") or 0)
    txns = int(row.get("buys_h1") or 0) + int(row.get("sells_h1") or 0)
    price = float(row.get("price_usd") or 0)
    if price <= 0:
        reasons.append("PAIR_PRICE_ZERO_OR_UNAVAILABLE")
    if liquidity < MIN_LIQUIDITY_USD:
        reasons.append("LIQUIDITY_LT_50K")
    if volume < MIN_VOLUME_H1_USD:
        reasons.append("VOLUME_H1_LT_15K")
    if txns < MIN_TXNS_H1:
        reasons.append("TXNS_H1_LT_50")
    return reasons


def run() -> dict:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    active = _load(ACTIVE, [])
    old_failed = _load(FAILED, [])
    old_pending = _load(PENDING, [])
    outcomes = _load(OUTCOMES, {})
    if not isinstance(active, list):
        active = []
    if not isinstance(old_failed, list):
        old_failed = []
    if not isinstance(old_pending, list):
        old_pending = []
    if not isinstance(outcomes, dict):
        outcomes = {}

    # Critical lifecycle rule: PENDING/FAILED candidates remain in the recheck cohort.
    # Otherwise a token can become permanently stranded simply because it was not
    # rediscovered by the current anomaly scan. Exact-pair identity is preserved.
    cohort = _dedupe_latest(old_failed, old_pending, active)
    prior_pending = {_key(x) for x in old_pending if isinstance(x, dict)}
    prior_failed = {_key(x) for x in old_failed if isinstance(x, dict)}

    survivors, failed_now, pending_now = [], [], []
    recovered_from_pending = 0
    recovered_from_failed = 0

    for original in cohort:
        chain = original.get("chain")
        token = original.get("token") or original.get("mint")
        locked_pair = original.get("locked_pair_address") or original.get("pair_address")
        key = _key(original)

        if not chain or not token or not locked_pair:
            pending_now.append({**original,
                "live_survival_gate": "PENDING",
                "live_survival_reasons": ["MISSING_IMMUTABLE_PAIR_IDENTITY"],
                "survival_checked_at": now})
            continue

        live = market_snapshot(chain, token, locked_pair)
        if not live or str(live.get("pair_address") or "").lower() != str(locked_pair).lower():
            pending_now.append({**original,
                "pair_address": locked_pair,
                "locked_pair_address": locked_pair,
                "pair_identity_locked": True,
                "live_survival_gate": "PENDING",
                "live_survival_reasons": ["LOCKED_PAIR_NOT_RETURNED"],
                "survival_checked_at": now})
            continue

        current = {**original, **live,
            "pair_address": locked_pair,
            "locked_pair_address": locked_pair,
            "pair_identity_locked": True,
            "survival_checked_at": now}

        # Re-run the fresh-launch/time/history gate on the newly fetched exact pair.
        # This prevents a recovering PENDING token from bypassing age, observation,
        # drawdown or liquidity-retention checks.
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
            failed_now.append({**staged,
                "qualification": "FAILED_SURVIVAL",
                "pair_address": locked_pair,
                "locked_pair_address": locked_pair,
                "pair_identity_locked": True,
                "failed_survival_at": original.get("failed_survival_at") or now,
                "survival_checked_at": now})
            continue

        reasons = _live_reasons(staged)
        if reasons:
            failed_now.append({**staged,
                "qualification": "FAILED_SURVIVAL",
                "live_survival_gate": "FAILED",
                "live_survival_reasons": reasons,
                "failed_survival_at": original.get("failed_survival_at") or now,
                "survival_checked_at": now})
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
            if key in prior_pending:
                recovered_from_pending += 1
            if key in prior_failed:
                recovered_from_failed += 1

    # These are CURRENT-state boards. Historical failures remain in the immutable
    # outcome/discovery evidence; a recovered candidate must not remain duplicated
    # on the current PENDING/FAILED boards.
    _write(ACTIVE, survivors)
    _write(FAILED, failed_now)
    _write(PENDING, pending_now)

    report = {
        "updated_at": now,
        "method": "PERSISTENT_IMMUTABLE_EXACT_PAIR_REVALIDATION",
        "input_active": len(active),
        "input_pending": len(old_pending),
        "input_failed": len(old_failed),
        "recheck_cohort": len(cohort),
        "active_after": len(survivors),
        "failed_now": len(failed_now),
        "pending_now": len(pending_now),
        "recovered_from_pending": recovered_from_pending,
        "recovered_from_failed": recovered_from_failed,
        "min_liquidity_usd": MIN_LIQUIDITY_USD,
        "min_volume_h1_usd": MIN_VOLUME_H1_USD,
        "min_txns_h1": MIN_TXNS_H1,
        "rule": "PENDING_AND_FAILED_ARE_RECHECKED_ON_THE_LOCKED_PAIR_EVERY_RUN",
    }
    _write(DATA / "exact-pair-survival-report.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
