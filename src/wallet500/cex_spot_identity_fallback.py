from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Wallet500/2.1", "Accept": "application/json"}
DEX_SEARCH = "https://api.dexscreener.com/latest/dex/search?q="
DEX_TOKEN = "https://api.dexscreener.com/latest/dex/tokens/"
MIN_MARKET_AGE_DAYS = 90
MAX_PRICE_ERROR_PCT = 12.0
SUPPORTED_CHAINS = {
    "solana", "ethereum", "bsc", "base", "arbitrum", "polygon", "avalanche", "sui", "optimism", "harmony"
}
USD_LIKE_QUOTES = {"USD", "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI"}


def _f(value: object) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _base_symbol(value: object) -> str:
    s = str(value or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()
    return s[:-4] if s.endswith("USDT") else s


def _cex_reference_price(alert: dict) -> float:
    prices = []
    for market in alert.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if str(market.get("market_type") or "spot").lower() != "spot":
            continue
        if market.get("regional_market") is True or market.get("volume_comparable_usd_like") is False:
            continue
        quote = str(market.get("quote_symbol") or "").upper().strip()
        symbol = str(market.get("symbol") or alert.get("symbol") or "").upper().replace("-", "").replace("_", "").replace("/", "")
        if quote:
            if quote not in USD_LIKE_QUOTES:
                continue
        elif not any(symbol.endswith(q) for q in USD_LIKE_QUOTES):
            continue
        price = _f(market.get("price"))
        if price > 0:
            prices.append(price)
    prices.sort()
    if prices:
        n = len(prices)
        return prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2.0
    milestones = alert.get("milestones") if isinstance(alert.get("milestones"), dict) else {}
    for name in ("first_watch", "first_alert", "first_anomaly", "first_seen"):
        row = milestones.get(name) if isinstance(milestones.get(name), dict) else {}
        price = _f(row.get("reference_price"))
        if price > 0:
            return price
    return 0.0


def _get(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _age_days(created_ms: object) -> int:
    try:
        created = datetime.fromtimestamp(float(created_ms) / 1000.0, tz=timezone.utc)
    except Exception:
        return -1
    return int((datetime.now(timezone.utc) - created).total_seconds() // 86400)


def _same_addr(chain: str, left: object, right: object) -> bool:
    a, b = str(left or "").strip(), str(right or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "polygon", "avalanche", "optimism", "harmony"}:
        return a.lower() == b.lower()
    return a == b


def _exact_token_pool_universe(best: dict, ref: float) -> dict:
    """Expand a uniquely resolved token into price-coherent exact base-token pools.

    The strict symbol+price+age fallback establishes the token identity first. Only
    after that proof do we query by exact contract address. Sibling pools never
    establish identity by themselves and quote-side pools are omitted here because
    DexScreener priceUsd represents the base token.
    """
    chain = str(best.get("chain") or "").lower().strip()
    token = str(best.get("token_address") or "").strip()
    if not chain or not token:
        return {}

    try:
        payload = _get(DEX_TOKEN + urllib.parse.quote(token, safe=""))
    except Exception:
        payload = {"pairs": []}

    pools = []
    seen = set()
    for pair in (payload or {}).get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        if str(pair.get("chainId") or "").lower().strip() != chain:
            continue
        base_token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        if not _same_addr(chain, base_token.get("address"), token):
            continue
        pair_address = str(pair.get("pairAddress") or "").strip()
        price = _f(pair.get("priceUsd"))
        if not pair_address or price <= 0:
            continue
        err = abs(price / ref - 1.0) * 100.0
        if err > MAX_PRICE_ERROR_PCT:
            continue
        key = pair_address.lower() if chain in {"ethereum", "bsc", "base", "arbitrum", "polygon", "avalanche", "optimism", "harmony"} else pair_address
        if key in seen:
            continue
        seen.add(key)
        pools.append({
            "chain": chain,
            "token_address": token,
            "pair_address": pair_address,
            "dex": pair.get("dexId"),
            "price_usd": price,
            "liquidity_usd": _f((pair.get("liquidity") or {}).get("usd")),
            "volume_h1": _f((pair.get("volume") or {}).get("h1")),
            "volume_h24": _f((pair.get("volume") or {}).get("h24")),
            "pair_created_at": pair.get("pairCreatedAt"),
            "exact_token_side": "BASE",
            "provider": "DEXSCREENER_TOKEN_PAIRS",
            "url": pair.get("url"),
        })

    primary_key = str(best.get("pair_address") or "")
    primary_norm = primary_key.lower() if chain in {"ethereum", "bsc", "base", "arbitrum", "polygon", "avalanche", "optimism", "harmony"} else primary_key
    if primary_key and primary_norm not in seen:
        pools.append({
            "chain": chain,
            "token_address": token,
            "pair_address": primary_key,
            "dex": best.get("dex"),
            "price_usd": _f(best.get("price_usd")),
            "liquidity_usd": _f(best.get("liquidity_usd")),
            "volume_h1": _f(best.get("volume_h1")),
            "volume_h24": _f(best.get("volume_h24")),
            "pair_created_at": best.get("pair_created_at"),
            "exact_token_side": "BASE",
            "provider": "DEXSCREENER_SEARCH",
            "url": best.get("dex_url"),
        })

    pools.sort(
        key=lambda x: (_f(x.get("liquidity_usd")), _f(x.get("volume_h24"))),
        reverse=True,
    )
    total = sum(_f(x.get("liquidity_usd")) for x in pools)
    return {
        "dex_total_liquidity_usd": round(total, 2),
        "dex_pool_count": len(pools),
        "dex_tradable_pool_count_50k": sum(1 for x in pools if _f(x.get("liquidity_usd")) >= 50_000),
        "dex_liquidity_scope": "STRICT_FALLBACK_EXACT_TOKEN_BASE_POOLS",
        "liquidity_gate_metric": "EXECUTION_POOL_LIQUIDITY_USD",
        "dex_liquidity_pools_top5": pools[:5],
    }


def resolve(alert: dict) -> dict | None:
    """Strict fallback for missing or inconclusive CoinGecko age evidence.

    A fallback is accepted only when DexScreener exposes an exact base-token symbol,
    a real token+pair address, >=90d pair age, and a price within 12% of the CEX median.
    Ambiguous token identities fail closed. This resolves identity only; it never waives
    production liquidity, holder, survival or REAL ALERT gates.
    """
    base = _base_symbol(alert.get("symbol"))
    ref = _cex_reference_price(alert)
    if not base or ref <= 0:
        return None
    try:
        payload = _get(DEX_SEARCH + urllib.parse.quote(base, safe=""))
    except Exception:
        return None

    rows = []
    for pair in (payload or {}).get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        chain = str(pair.get("chainId") or "").lower().strip()
        if chain not in SUPPORTED_CHAINS:
            continue
        base_token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        if str(base_token.get("symbol") or "").upper().strip() != base:
            continue
        token = str(base_token.get("address") or "").strip()
        pair_address = str(pair.get("pairAddress") or "").strip()
        price = _f(pair.get("priceUsd"))
        age = _age_days(pair.get("pairCreatedAt"))
        if not token or not pair_address or price <= 0 or age < MIN_MARKET_AGE_DAYS:
            continue
        err = abs(price / ref - 1.0) * 100.0
        if err > MAX_PRICE_ERROR_PCT:
            continue
        rows.append({
            "chain": chain,
            "token_address": token,
            "pair_address": pair_address,
            "dex": pair.get("dexId"),
            "dex_url": pair.get("url"),
            "price_usd": price,
            "liquidity_usd": _f((pair.get("liquidity") or {}).get("usd")),
            "volume_h1": _f((pair.get("volume") or {}).get("h1")),
            "volume_h24": _f((pair.get("volume") or {}).get("h24")),
            "pair_created_at": pair.get("pairCreatedAt"),
            "market_age_min_days": age,
            "price_error_pct": err,
        })

    # Deduplicate by exact token identity, keeping the deepest pair for that token.
    best_by_token = {}
    for row in rows:
        key = (row["chain"], row["token_address"].lower())
        old = best_by_token.get(key)
        if old is None or (row["price_error_pct"], -row["liquidity_usd"]) < (old["price_error_pct"], -old["liquidity_usd"]):
            best_by_token[key] = row
    unique = sorted(best_by_token.values(), key=lambda x: (x["price_error_pct"], -x["liquidity_usd"]))
    if not unique:
        return None

    best = unique[0]
    if len(unique) > 1:
        second = unique[1]
        # Require meaningful separation when two different token identities fit the same symbol.
        if second["price_error_pct"] <= max(3.0, best["price_error_pct"] * 1.8):
            return None

    created = datetime.fromtimestamp(float(best["pair_created_at"]) / 1000.0, tz=timezone.utc).isoformat()
    pool_universe = _exact_token_pool_universe(best, ref)
    ratio = max(ref, best["price_usd"]) / min(ref, best["price_usd"])
    return {
        **alert,
        **best,
        "market_age_verified": True,
        "market_age_evidence_at": created,
        "market_age_evidence_source": "DEXSCREENER_EXACT_SYMBOL_PRICE_PAIR_AGE_FALLBACK",
        "cex_identity_preflight_verified": True,
        "cex_identity_preflight": {
            "method": "DEXSCREENER_EXACT_BASE_SYMBOL_PLUS_CEX_PRICE_COHERENCE_PLUS_PAIR_AGE",
            "reference_price": ref,
            "price_error_pct": round(best["price_error_pct"], 4),
            "candidate_token_count": len(unique),
        },
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "identity_candidate_source": "STRICT_DEXSCREENER_CEX_FALLBACK",
        "pair_provider": "DEXSCREENER_SEARCH",
        "exact_token_side": "BASE",
        "dex_price_usd": best["price_usd"],
        "dex_liquidity_usd": best["liquidity_usd"],
        "execution_pool_liquidity_usd": best["liquidity_usd"],
        "dex_volume_h1": best["volume_h1"],
        "dex_volume_h24": best["volume_h24"],
        "cex_reference_price_usd": ref,
        "dex_execution_price_usd": best["price_usd"],
        "cex_dex_price_ratio": round(ratio, 6),
        "max_cex_dex_price_ratio": max(1.0, 1.0 / (1.0 - MAX_PRICE_ERROR_PCT / 100.0)),
        "execution_pair_price_coherent": True,
        "registry_learning_eligible": False,
        **pool_universe,
    }
