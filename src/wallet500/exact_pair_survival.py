import json
from datetime import datetime, timezone
from pathlib import Path

from .market_data import snapshot as market_snapshot

DATA = Path("data")
ACTIVE = DATA / "active-qualified-candidates.json"
FAILED = DATA / "live-survival-failed.json"
PENDING = DATA / "live-survival-pending.json"
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
    pair = str(row.get("pair_address") or "")
    if chain in {"ethereum", "bsc"}:
        token, pair = token.lower(), pair.lower()
    return f"{chain}:{token}:{pair}"


def _merge_history(existing: list[dict], additions: list[dict]) -> list[dict]:
    rows = {_key(x): x for x in existing if isinstance(x, dict)}
    for x in additions:
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
    now = datetime.now(timezone.utc).isoformat()
    active = _load(ACTIVE, [])
    old_failed = _load(FAILED, [])
    old_pending = _load(PENDING, [])
    if not isinstance(active, list):
        active = []
    if not isinstance(old_failed, list):
        old_failed = []
    if not isinstance(old_pending, list):
        old_pending = []

    survivors, failed_now, pending_now = [], [], []
    for original in active:
        if not isinstance(original, dict):
            continue
        chain = original.get("chain")
        token = original.get("token") or original.get("mint")
        locked_pair = original.get("pair_address")
        if not chain or not token or not locked_pair:
            pending_now.append({**original,
                "live_survival_gate": "PENDING",
                "live_survival_reasons": ["MISSING_IMMUTABLE_PAIR_IDENTITY"],
                "survival_checked_at": now})
            continue

        live = market_snapshot(chain, token, locked_pair)
        if not live or str(live.get("pair_address") or "").lower() != str(locked_pair).lower():
            pending_now.append({**original,
                "live_survival_gate": "PENDING",
                "live_survival_reasons": ["LOCKED_PAIR_NOT_RETURNED"],
                "survival_checked_at": now})
            continue

        current = {**original, **live,
            "pair_address": locked_pair,
            "locked_pair_address": locked_pair,
            "pair_identity_locked": True,
            "survival_checked_at": now}
        reasons = _live_reasons(current)
        if reasons:
            failed_now.append({**current,
                "qualification": "FAILED_SURVIVAL",
                "live_survival_gate": "FAILED",
                "live_survival_reasons": reasons,
                "failed_survival_at": original.get("failed_survival_at") or now})
        else:
            survivors.append({**current,
                "qualification": "QUALIFIED",
                "live_survival_gate": "ACTIVE",
                "live_survival_reasons": ["PASSED_EXACT_PAIR_LIVE_SURVIVAL_GATE"]})

    failed_keys = {_key(x) for x in failed_now}
    pending_keys = {_key(x) for x in pending_now}
    # A token that is now failed/active must not simultaneously remain pending.
    survivor_keys = {_key(x) for x in survivors}
    retained_pending = [x for x in old_pending if _key(x) not in failed_keys | survivor_keys]
    retained_failed = [x for x in old_failed if _key(x) not in survivor_keys]

    _write(ACTIVE, survivors)
    _write(FAILED, _merge_history(retained_failed, failed_now))
    _write(PENDING, _merge_history(retained_pending, pending_now))

    report = {
        "updated_at": now,
        "method": "IMMUTABLE_EXACT_PAIR_REVALIDATION",
        "input_active": len(active),
        "active_after": len(survivors),
        "failed_now": len(failed_now),
        "pending_now": len(pending_now),
        "min_liquidity_usd": MIN_LIQUIDITY_USD,
        "min_volume_h1_usd": MIN_VOLUME_H1_USD,
        "min_txns_h1": MIN_TXNS_H1,
    }
    _write(DATA / "exact-pair-survival-report.json", report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
