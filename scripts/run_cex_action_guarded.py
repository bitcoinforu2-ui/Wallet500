from __future__ import annotations

"""Wallet500 CEX Telegram action guard.

Keeps discovery/research intact while making Telegram action-only:
- canonical asset identity = chain + contract (pair changes do not create a new alert)
- exact denylist is enforced before promotion
- stale/failed discoveries and already-extended moves do not alert
- BUY_ZONE means entry timing is still acceptable, not merely that discovery was correct
- duplicate pools for the same asset collapse to the strongest execution pool
"""

import json
from pathlib import Path

from wallet500 import cex_fast_promotion as promo
from wallet500 import cex_fast_current_bypass as bypass

MIN_ACTION_SCORE = 50
MAX_ACTION_24H_MOVE_PCT = 35.0
# A BUY label must not chase a move that already ran materially from engine discovery.
MAX_GAIN_SINCE_DISCOVERY_PCT = 12.0
MAX_LOSS_SINCE_DISCOVERY_PCT = -12.0

EXCLUDED_ASSETS = {
    ("solana", "61v8vbaqagmpgdqi4jcawo1dmbghsyhzodcpqnev pump".replace(" ", "").lower()),
}


def canonical_key(row: dict) -> str:
    chain = str(row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"}:
        token = token.lower()
    return f"{chain}:{token}"


def is_excluded(row: dict) -> bool:
    chain = str(row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or "").strip().lower()
    return (chain, token) in EXCLUDED_ASSETS


def action_eligibility(row: object):
    ok, metrics = _ORIGINAL_ELIGIBILITY(row)
    if not isinstance(row, dict):
        return False, metrics
    blockers = list(metrics.get("blockers") or [])
    score = int(metrics.get("signal_score") or 0)
    current_change = float(metrics.get("current_change_24h_pct") or 0.0)
    signal_price = float(metrics.get("signal_price") or 0.0)
    current_price = float(metrics.get("current_price") or 0.0)
    since = ((current_price / signal_price) - 1.0) * 100.0 if signal_price > 0 and current_price > 0 else 0.0

    if is_excluded(row):
        blockers.append("EXACT_ASSET_EXCLUDED")
    if score < MIN_ACTION_SCORE:
        blockers.append("ACTION_SCORE_LT_50")
    if current_change > MAX_ACTION_24H_MOVE_PCT:
        blockers.append("ACTION_MOVE_ALREADY_EXTENDED")
    if since > MAX_GAIN_SINCE_DISCOVERY_PCT:
        blockers.append("WAIT_FOR_RETEST_ABOVE_DISCOVERY")
    if since < MAX_LOSS_SINCE_DISCOVERY_PCT:
        blockers.append("ACTION_SIGNAL_INVALIDATED_DOWNSIDE")

    metrics["since_discovery_pct"] = round(since, 4)
    metrics["max_buy_zone_gain_since_discovery_pct"] = MAX_GAIN_SINCE_DISCOVERY_PCT
    metrics["action_state"] = "BUY_ZONE" if not blockers else ("WAIT_FOR_RETEST" if blockers == ["WAIT_FOR_RETEST_ABOVE_DISCOVERY"] else "WAIT_OR_REJECT")
    metrics["blockers"] = sorted(set(blockers))
    return not blockers, metrics


def _best_per_asset(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = canonical_key(row)
        if not key.strip(":"):
            continue
        old = best.get(key)
        liq = promo._liquidity(row)
        old_liq = promo._liquidity(old) if isinstance(old, dict) else -1.0
        if old is None or liq > old_liq:
            best[key] = row
    return list(best.values())


def guarded_merge(identity_payload: dict, usdc_groups: dict[str, dict]) -> list[dict]:
    return _best_per_asset(_ORIGINAL_MERGE(identity_payload, usdc_groups))


def guarded_resolve_many(rows: list[dict]):
    resolved, failures = _ORIGINAL_RESOLVE_MANY(rows)
    return _best_per_asset(resolved), failures


def guarded_message(row: dict, metrics: dict, now: str, event_id: str) -> str:
    text = _ORIGINAL_MESSAGE(row, metrics, now, event_id)
    return "🟢 BUY ZONE — ENTRY TIMING PASSED\n" + text


def migrate_state(path: Path) -> None:
    try:
        payload = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return
    active = payload.get("active") if isinstance(payload, dict) else None
    if not isinstance(active, dict):
        return
    migrated: dict[str, dict] = {}
    changed = False
    for old_key, info in active.items():
        parts = str(old_key).split(":")
        new_key = ":".join(parts[:2]) if len(parts) >= 3 else str(old_key)
        changed = changed or new_key != old_key
        current = migrated.get(new_key)
        if current is None or str((info or {}).get("last_seen_at") or "") > str(current.get("last_seen_at") or ""):
            migrated[new_key] = info if isinstance(info, dict) else {}
    if changed:
        payload["active"] = migrated
        payload["version"] = max(int(payload.get("version") or 1), 2)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


_ORIGINAL_ELIGIBILITY = promo._eligibility
_ORIGINAL_MERGE = promo._merge_live_usdc
_ORIGINAL_RESOLVE_MANY = bypass._resolve_many
_ORIGINAL_MESSAGE = promo._message

promo._eligibility = action_eligibility
promo._identity_key = canonical_key
promo._merge_live_usdc = guarded_merge
promo._message = guarded_message
bypass._eligibility = action_eligibility
bypass._identity_key = canonical_key
bypass._resolve_many = guarded_resolve_many
bypass._message = guarded_message

for state_name in (promo.STATE_FILE, bypass.STATE_FILE):
    migrate_state(Path("data") / state_name)

assert canonical_key({"chain": "solana", "token_address": "ABC", "pair_address": "P1"}) == canonical_key({"chain": "solana", "token_address": "ABC", "pair_address": "P2"})
assert is_excluded({"chain": "solana", "token_address": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump"})

if __name__ == "__main__":
    promo.run()
    bypass.run()
