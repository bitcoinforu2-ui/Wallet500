from __future__ import annotations
import json
import math
import time
from urllib.request import Request, urlopen
from urllib.parse import quote

from .liquidity_reality import compute_liquidity_reality

BASE = "https://api.dexscreener.com"
EVM_CHAINS = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "polygon", "optimism", "avalanche"}
VALUATION_LIQUIDITY_MULTIPLE_HARD_MAX = 20.0
VALUATION_INTERNAL_DIVERGENCE_HARD_MAX = 100.0


def _get(path: str, timeout: int = 20):
    req = Request(BASE + path, headers={"Accept": "application/json", "User-Agent": "Wallet500/0.1"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _norm_id(chain: str, value) -> str:
    value = str(value or "")
    return value.lower() if str(chain or "").lower() in EVM_CHAINS else value


def _same_id(chain: str, left, right) -> bool:
    return bool(left and right) and _norm_id(chain, left) == _norm_id(chain, right)


def _finite_positive(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _valuation_integrity(liquidity_usd: float, fdv, market_cap, *, target_side: str) -> dict:
    """Fail closed on impossible supply-derived valuation fields.

    DexScreener marketCap/fdv are useful provider hints, not immutable truth. A
    bridged/wrapped asset can expose a chain-local supply that makes those fields
    absurdly small relative to the exact pool's own USD liquidity. In that case
    Wallet500 must never use the value in scoring, ranking or a buy-facing alert.

    The raw provider values are retained for audit. Only the trusted fields are
    nulled. This preserves immutable evidence while enforcing UNKNOWN != 0.
    """
    raw_fdv = _finite_positive(fdv)
    raw_mcap = _finite_positive(market_cap)
    result = {
        "raw_provider_fdv": raw_fdv,
        "raw_provider_market_cap": raw_mcap,
        "fdv": raw_fdv,
        "market_cap": raw_mcap,
        "supply_valuation_verified": False,
        "supply_valuation_status": "UNKNOWN",
        "supply_valuation_reasons": [],
    }

    if target_side != "BASE":
        result.update(fdv=None, market_cap=None, supply_valuation_status="UNAVAILABLE_QUOTE_SIDE")
        result["supply_valuation_reasons"].append("DEX_PROVIDER_VALUATION_DESCRIBES_BASE_TOKEN")
        return result

    vals = [x for x in (raw_fdv, raw_mcap) if x is not None]
    if not vals:
        result.update(fdv=None, market_cap=None, supply_valuation_status="UNKNOWN_PROVIDER_MISSING")
        result["supply_valuation_reasons"].append("NO_POSITIVE_PROVIDER_SUPPLY_VALUATION")
        return result

    maximum = max(vals)
    minimum = min(vals)
    if len(vals) == 2 and minimum > 0 and maximum / minimum > VALUATION_INTERNAL_DIVERGENCE_HARD_MAX:
        result.update(fdv=None, market_cap=None, supply_valuation_status="QUARANTINED_PROVIDER_INTERNAL_DIVERGENCE")
        result["supply_valuation_reasons"].append("FDV_MARKET_CAP_DIVERGENCE_GT_100X")
        return result

    if liquidity_usd >= 50_000 and maximum > 0 and liquidity_usd / maximum > VALUATION_LIQUIDITY_MULTIPLE_HARD_MAX:
        result.update(fdv=None, market_cap=None, supply_valuation_status="QUARANTINED_IMPOSSIBLE_VS_EXACT_POOL_LIQUIDITY")
        result["supply_valuation_reasons"].append("EXACT_POOL_LIQUIDITY_GT_20X_PROVIDER_VALUATION")
        return result

    result["supply_valuation_verified"] = True
    result["supply_valuation_status"] = "PROVIDER_PLAUSIBILITY_PASS"
    return result


def token_pairs(chain: str, token: str) -> list[dict]:
    # Token lookup is the broad discovery path. Retry transient misses so a
    # momentary API failure does not unnecessarily quarantine a good pair.
    for attempt in range(3):
        try:
            data = _get(f"/token-pairs/v1/{quote(chain, safe='')}/{quote(token, safe='')}")
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
        if attempt < 2:
            time.sleep(0.6 * (attempt + 1))
    return []


def pair_lookup(chain: str, pair_address: str) -> dict | None:
    """Direct exact-pair fallback used only for immutable pair revalidation."""
    if not chain or not pair_address:
        return None
    for attempt in range(3):
        try:
            data = _get(f"/latest/dex/pairs/{quote(chain, safe='')}/{quote(pair_address, safe='')}")
            pairs = (data or {}).get("pairs") if isinstance(data, dict) else None
            if isinstance(pairs, list):
                for p in pairs:
                    if _same_id(chain, (p or {}).get("pairAddress"), pair_address):
                        return p
        except Exception:
            pass
        if attempt < 2:
            time.sleep(0.6 * (attempt + 1))
    return None


def _inverse_change_pct(value) -> float:
    """Translate a base-token percent move into the quote-token move.

    DexScreener priceChange is expressed for baseToken. If the tracked asset is
    quoteToken, its price versus USD moves inversely to the base/quote ratio.
    """
    try:
        pct = float(value or 0)
        factor = 1.0 + pct / 100.0
        if not math.isfinite(factor) or factor <= 0:
            return 0.0
        return (1.0 / factor - 1.0) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _pair_to_snapshot(chain: str, token: str, p: dict | None) -> dict | None:
    """Convert a DexScreener pair into a target-token snapshot, fail closed.

    DexScreener ``priceUsd`` is the USD price of *baseToken*. Historically we
    accepted it for the requested token without proving which side of the pair
    the token occupied. That can value quote-side tokens with the base token's
    price and create astronomical phantom ROI. Every snapshot now proves token
    identity and pair side first.
    """
    if not isinstance(p, dict):
        return None
    pair_address = p.get("pairAddress")
    base = p.get("baseToken") or {}
    qtok = p.get("quoteToken") or {}
    base_addr = base.get("address")
    quote_addr = qtok.get("address")
    if not pair_address or not base_addr or not quote_addr or not token:
        return None

    if _same_id(chain, token, base_addr):
        target_side = "BASE"
        target_price = _finite_positive(p.get("priceUsd"))
    elif _same_id(chain, token, quote_addr):
        target_side = "QUOTE"
        base_price_usd = _finite_positive(p.get("priceUsd"))
        base_price_in_quote = _finite_positive(p.get("priceNative"))
        target_price = (
            base_price_usd / base_price_in_quote
            if base_price_usd is not None and base_price_in_quote is not None
            else None
        )
        if target_price is not None and not math.isfinite(target_price):
            target_price = None
    else:
        # Exact pair address alone is never sufficient evidence of token identity.
        return None

    if target_price is None or target_price <= 0:
        return None

    tx = p.get("txns") or {}
    vol = p.get("volume") or {}
    ch = p.get("priceChange") or {}
    liq = p.get("liquidity") or {}
    h1 = tx.get("h1") or {}
    h24 = tx.get("h24") or {}
    liq_usd = float(liq.get("usd") or 0)
    liq_base = float(liq.get("base") or 0)
    liq_quote = float(liq.get("quote") or 0)

    def change(key: str) -> float:
        raw = float(ch.get(key) or 0)
        return raw if target_side == "BASE" else _inverse_change_pct(raw)

    if target_side == "BASE":
        buys_h1, sells_h1 = int(h1.get("buys") or 0), int(h1.get("sells") or 0)
        buys_h24, sells_h24 = int(h24.get("buys") or 0), int(h24.get("sells") or 0)
    else:
        # A DexScreener BUY is a base-token buy / quote-token sell, so swap the
        # transaction direction when the tracked asset is quoteToken.
        buys_h1, sells_h1 = int(h1.get("sells") or 0), int(h1.get("buys") or 0)
        buys_h24, sells_h24 = int(h24.get("sells") or 0), int(h24.get("buys") or 0)

    valuation = _valuation_integrity(
        liq_usd,
        p.get("fdv") if target_side == "BASE" else None,
        p.get("marketCap") if target_side == "BASE" else None,
        target_side=target_side,
    )

    return {
        "chain": chain,
        "token": token,
        "pair_address": pair_address,
        "dex": p.get("dexId"),
        "url": p.get("url"),
        "price_usd": float(target_price),
        "token_identity_verified": True,
        "target_token_side": target_side,
        "base_token_address": base_addr,
        "base_token_symbol": base.get("symbol"),
        "quote_token_address": quote_addr,
        "quote_token_symbol": qtok.get("symbol"),
        "liquidity_usd": liq_usd,
        "liquidity_base": liq_base,
        "liquidity_quote": liq_quote,
        "liquidity_composition_present": bool(liq_usd > 0 and liq_base > 0 and liq_quote > 0),
        **valuation,
        "volume_m5": float(vol.get("m5") or 0),
        "volume_h1": float(vol.get("h1") or 0),
        "volume_h6": float(vol.get("h6") or 0),
        "volume_h24": float(vol.get("h24") or 0),
        "price_change_m5": change("m5"),
        "price_change_h1": change("h1"),
        "price_change_h6": change("h6"),
        "price_change_h24": change("h24"),
        "buys_h1": buys_h1,
        "sells_h1": sells_h1,
        "buys_h24": buys_h24,
        "sells_h24": sells_h24,
        "pair_created_at": p.get("pairCreatedAt"),
    }


def _compact_pool(chain: str, token: str, p: dict) -> dict | None:
    s = _pair_to_snapshot(chain, token, p)
    if not s:
        return None
    return {
        k: s.get(k)
        for k in (
            "chain", "token", "pair_address", "dex", "url", "price_usd",
            "token_identity_verified", "target_token_side", "base_token_address",
            "quote_token_address", "liquidity_usd", "liquidity_base",
            "liquidity_quote", "quote_token_symbol", "liquidity_composition_present",
            "supply_valuation_verified", "supply_valuation_status",
            "volume_m5", "volume_h1", "buys_h1", "sells_h1", "pair_created_at",
        )
    }


def snapshot(chain: str, token: str, pair_address: str | None = None) -> dict | None:
    pairs = token_pairs(chain, token)
    if pair_address:
        for p in pairs:
            if _same_id(chain, p.get("pairAddress"), pair_address):
                return _pair_to_snapshot(chain, token, p)
        # Critical bottleneck fix: token-pairs can transiently omit a known
        # immutable pair. Verify that exact address directly before PENDING.
        direct = pair_lookup(chain, pair_address)
        return _pair_to_snapshot(chain, token, direct) if direct else None

    valid = [s for s in (_pair_to_snapshot(chain, token, p) for p in pairs) if s]
    if not valid:
        return None
    out = max(valid, key=lambda x: float(x.get("liquidity_usd") or 0))
    all_pools = [x for x in (_compact_pool(chain, token, p) for p in pairs) if x]
    out.update(
        compute_liquidity_reality(
            all_pools,
            market_cap_usd=out.get("market_cap"),
            fdv_usd=out.get("fdv"),
        )
    )
    ranked = sorted(all_pools, key=lambda x: float(x.get("liquidity_usd") or 0), reverse=True)[:8]
    out["pools"] = ranked
    return out
