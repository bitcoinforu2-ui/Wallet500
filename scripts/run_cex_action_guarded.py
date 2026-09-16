from __future__ import annotations

"""Wallet500 CEX Telegram action guard.

Keeps discovery/research intact while making Telegram action-only:
- canonical asset identity = chain + contract (pair changes do not create a new alert)
- exact denylist is enforced before promotion
- stale/failed discoveries and already-extended moves do not alert
- BUY_ZONE means entry timing is still acceptable, not merely that discovery was correct
- duplicate pools for the same asset collapse to the strongest execution pool
- Telegram distinguishes exact execution-pair liquidity from the deepest verified
  same-token pool so pair depth is never presented as total asset liquidity
"""

import json
import urllib.parse
from datetime import datetime, timezone
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


def _addr_equal(chain: str, left: object, right: object) -> bool:
    a = str(left or "").strip()
    b = str(right or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"}:
        return a.lower() == b.lower()
    return a == b


def _execution_liquidity(row: dict, metrics: dict) -> float:
    return max(
        float(metrics.get("execution_liquidity_usd") or 0.0),
        float(row.get("execution_pool_liquidity_usd") or 0.0),
        float(row.get("dex_pair_liquidity_usd") or 0.0),
        float(row.get("dex_liquidity_usd") or 0.0),
        float(row.get("liquidity_usd") or 0.0),
    )


def best_verified_pool_context(row: dict, metrics: dict) -> dict:
    """Return deepest same-token pool that independently passes identity/price/age checks.

    The currently selected execution pair is always a verified baseline because the
    promotion gate already requires exact identity, pair, price coherence and age.
    A deeper pool only replaces that baseline when DexScreener returns the exact
    same token address on the same chain and the pool independently passes the same
    CEX price-coherence and veteran-age constraints.
    """
    chain = str(row.get("chain") or "").lower().strip()
    token = str(row.get("token_address") or "").strip()
    execution_pair = str(row.get("pair_address") or "").strip()
    execution_liquidity = _execution_liquidity(row, metrics)
    current_price = float(metrics.get("current_price") or 0.0)

    baseline = {
        "liquidity_usd": execution_liquidity,
        "pair_address": execution_pair,
        "dex": str(row.get("dex") or "verified exact pair"),
        "url": str(row.get("dex_url") or row.get("url") or ""),
        "price_usd": float(row.get("dex_price_usd") or row.get("price_usd") or current_price or 0.0),
        "source": "CURRENT_EXACT_EXECUTION_PAIR",
    }
    result = {
        "best_verified_pool_liquidity_usd": execution_liquidity,
        "best_verified_pool_pair_address": execution_pair,
        "best_verified_pool_dex": baseline["dex"],
        "best_verified_pool_url": baseline["url"],
        "best_verified_pool_price_usd": baseline["price_usd"],
        "best_verified_pool_check_complete": False,
        "best_verified_pool_source": baseline["source"],
        "best_verified_pool_is_execution_pair": True,
        "liquidity_context": "EXECUTION_PAIR_BASELINE_ONLY",
    }
    if not chain or not token or current_price <= 0:
        return result

    url = (
        "https://api.dexscreener.com/token-pairs/v1/"
        + urllib.parse.quote(chain, safe="")
        + "/"
        + urllib.parse.quote(token, safe="")
    )
    try:
        payload = promo._get(url, timeout=8)
    except Exception:
        return result

    pairs = payload if isinstance(payload, list) else ((payload or {}).get("pairs") or [])
    now = datetime.now(timezone.utc)
    verified = [baseline] if execution_liquidity > 0 else []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        pair_chain = str(pair.get("chainId") or "").lower().strip()
        if pair_chain != chain:
            continue
        base_token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        # DexScreener priceUsd is the base-token price, so only base-side exact-token
        # pools can be price-coherence verified without inventing a quote conversion.
        if not _addr_equal(chain, base_token.get("address"), token):
            continue
        pair_address = str(pair.get("pairAddress") or "").strip()
        if not pair_address:
            continue
        price = float(pair.get("priceUsd") or 0.0)
        if price <= 0:
            continue
        price_error = abs(price / current_price - 1.0) * 100.0
        if price_error > promo.MAX_CEX_DEX_PRICE_ERROR_PCT:
            continue
        created_ms = float(pair.get("pairCreatedAt") or 0.0)
        if created_ms <= 0:
            continue
        try:
            created = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc)
        except Exception:
            continue
        age_days = (now - created).total_seconds() / 86400.0
        if age_days < promo.MIN_MARKET_AGE_DAYS:
            continue
        liquidity = float(((pair.get("liquidity") or {}).get("usd")) or 0.0)
        if liquidity <= 0:
            continue
        verified.append({
            "liquidity_usd": liquidity,
            "pair_address": pair_address,
            "dex": str(pair.get("dexId") or "verified pool"),
            "url": str(pair.get("url") or ""),
            "price_usd": price,
            "source": "DEXSCREENER_EXACT_TOKEN_SAME_CHAIN_PRICE_AGE_VERIFIED",
        })

    result["best_verified_pool_check_complete"] = True
    if not verified:
        result["liquidity_context"] = "NO_VERIFIED_POOL_RETURNED"
        return result

    best = max(verified, key=lambda x: float(x.get("liquidity_usd") or 0.0))
    same_pair = _addr_equal(chain, best.get("pair_address"), execution_pair)
    result.update({
        "best_verified_pool_liquidity_usd": float(best.get("liquidity_usd") or 0.0),
        "best_verified_pool_pair_address": best.get("pair_address"),
        "best_verified_pool_dex": best.get("dex"),
        "best_verified_pool_url": best.get("url"),
        "best_verified_pool_price_usd": float(best.get("price_usd") or 0.0),
        "best_verified_pool_source": best.get("source"),
        "best_verified_pool_is_execution_pair": same_pair,
        "liquidity_context": "EXECUTION_PAIR_IS_DEEPEST_VERIFIED" if same_pair else "DEEPER_SAME_TOKEN_POOL_VERIFIED",
    })
    return result


def guarded_message(row: dict, metrics: dict, now: str, event_id: str) -> str:
    context = best_verified_pool_context(row, metrics)
    metrics.update(context)
    text = _ORIGINAL_MESSAGE(row, metrics, now, event_id)
    execution = _execution_liquidity(row, metrics)
    best = float(context.get("best_verified_pool_liquidity_usd") or 0.0)
    dex = str(context.get("best_verified_pool_dex") or "verified pool")
    complete = context.get("best_verified_pool_check_complete") is True
    same_pair = context.get("best_verified_pool_is_execution_pair") is True

    replacement = [f"Execution pair liquidity: {promo._fmt_money(execution)} ✅ min $15K"]
    if complete:
        replacement.append(f"Best verified pool liquidity: {promo._fmt_money(best)} · {dex} ✅")
        if same_pair:
            replacement.append("Liquidity context: execution pair is deepest verified pool ✅")
        else:
            replacement.append("Liquidity context: deeper same-token pool exists; execution-pair depth ≠ total asset depth ✅")
    else:
        replacement.append(f"Best verified pool liquidity: ≥{promo._fmt_money(best)} · deeper-pool scan unavailable ⚠️")
        replacement.append("Liquidity context: exact execution pair verified; total asset depth not asserted")

    lines = []
    replaced = False
    for line in text.splitlines():
        if line.startswith("Execution liquidity:"):
            lines.extend(replacement)
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.extend(replacement)
    return "🟢 BUY ZONE — ENTRY TIMING PASSED\n" + "\n".join(lines)


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
