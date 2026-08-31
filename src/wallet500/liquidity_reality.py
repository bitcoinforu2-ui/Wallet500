from __future__ import annotations

from typing import Iterable


def _f(value) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 4)


def compute_liquidity_reality(
    pools: Iterable[dict],
    *,
    market_cap_usd: float | int | None = None,
    fdv_usd: float | int | None = None,
    tradable_pool_floor_usd: float = 50_000.0,
) -> dict:
    """Aggregate same-chain DEX liquidity into a research-only reality score.

    This intentionally does not claim cross-chain or CEX depth. It also does not
    derive execution slippage from TVL because CLMM/DLMM/CPMM pool mechanics differ;
    router/order-book quotes are required for executable depth.
    """
    rows = []
    for pool in pools or []:
        if not isinstance(pool, dict):
            continue
        liq = _f(pool.get("liquidity_usd"))
        if liq <= 0:
            continue
        rows.append({**pool, "_liq": liq})

    rows.sort(key=lambda x: x["_liq"], reverse=True)
    total = sum(x["_liq"] for x in rows)
    market_cap = _f(market_cap_usd)
    fdv = _f(fdv_usd)

    if total <= 0:
        return {
            "liquidity_reality_score": 0,
            "liquidity_reality_level": "UNKNOWN",
            "liquidity_reality_scope": "CHAIN_TOKEN_ALL_DEX_POOLS",
            "liquidity_reality_mode": "RESEARCH_SHADOW_NO_PRODUCTION_IMPACT",
            "dex_total_liquidity_usd": 0.0,
            "dex_pool_count": 0,
            "meaningful_pool_count": 0,
            "tradable_pool_count": 0,
            "tradable_liquidity_usd": 0.0,
            "tradable_liquidity_share_pct": 0.0,
            "dex_liquidity_to_market_cap_pct": _pct(0.0, market_cap),
            "dex_liquidity_to_fdv_pct": _pct(0.0, fdv),
            "top_pool_share_pct": 0.0,
            "top3_pool_share_pct": 0.0,
            "liquidity_hhi": 0.0,
            "liquidity_concentration_level": "UNKNOWN",
            "execution_depth_status": "ROUTER_QUOTES_REQUIRED",
            "cex_depth_status": "NOT_CAPTURED",
            "cross_chain_status": "CANONICAL_MAPPING_REQUIRED",
            "liquidity_reality_reasons": ["NO_POSITIVE_DEX_LIQUIDITY"],
        }

    shares = [x["_liq"] / total for x in rows]
    top1 = shares[0] * 100.0
    top3 = sum(shares[:3]) * 100.0
    hhi = sum(s * s for s in shares)

    meaningful_floor = max(10_000.0, total * 0.01)
    meaningful = [x for x in rows if x["_liq"] >= meaningful_floor]
    tradable = [x for x in rows if x["_liq"] >= tradable_pool_floor_usd]
    tradable_liq = sum(x["_liq"] for x in tradable)
    tradable_share = (tradable_liq / total) * 100.0

    ratio_mcap = _pct(total, market_cap)
    ratio_fdv = _pct(total, fdv)

    ratio_score = 0
    if ratio_mcap is not None:
        if ratio_mcap >= 10:
            ratio_score = 40
        elif ratio_mcap >= 5:
            ratio_score = 36
        elif ratio_mcap >= 2:
            ratio_score = 30
        elif ratio_mcap >= 1:
            ratio_score = 24
        elif ratio_mcap >= 0.5:
            ratio_score = 16
        elif ratio_mcap > 0:
            ratio_score = 8

    if top1 <= 25:
        concentration_score = 25
        concentration_level = "LOW"
    elif top1 <= 40:
        concentration_score = 20
        concentration_level = "MODERATE"
    elif top1 <= 60:
        concentration_score = 12
        concentration_level = "HIGH"
    elif top1 <= 80:
        concentration_score = 6
        concentration_level = "VERY_HIGH"
    else:
        concentration_score = 2
        concentration_level = "EXTREME"

    mcount = len(meaningful)
    if mcount >= 8:
        breadth_score = 15
    elif mcount >= 4:
        breadth_score = 12
    elif mcount >= 2:
        breadth_score = 8
    elif mcount == 1:
        breadth_score = 4
    else:
        breadth_score = 0

    if tradable_share >= 90:
        tradable_score = 20
    elif tradable_share >= 70:
        tradable_score = 16
    elif tradable_share >= 50:
        tradable_score = 10
    elif tradable_share > 0:
        tradable_score = 5
    else:
        tradable_score = 0

    score = int(min(100, ratio_score + concentration_score + breadth_score + tradable_score))
    if ratio_mcap is None:
        level = "UNKNOWN"
    elif score >= 80:
        level = "STRONG"
    elif score >= 65:
        level = "HEALTHY"
    elif score >= 45:
        level = "THIN"
    else:
        level = "FRAGILE"

    reasons = []
    if ratio_mcap is None:
        reasons.append("MARKET_CAP_UNAVAILABLE_SCORE_PARTIAL")
    elif ratio_mcap < 1:
        reasons.append("DEX_LIQUIDITY_BELOW_1PCT_OF_MARKET_CAP")
    elif ratio_mcap < 2:
        reasons.append("DEX_LIQUIDITY_BELOW_2PCT_OF_MARKET_CAP")
    else:
        reasons.append("DEX_LIQUIDITY_AT_LEAST_2PCT_OF_MARKET_CAP")

    if top1 > 60:
        reasons.append("LIQUIDITY_CONCENTRATED_IN_TOP_POOL")
    elif top3 > 90:
        reasons.append("LIQUIDITY_CONCENTRATED_IN_TOP_3_POOLS")
    else:
        reasons.append("LIQUIDITY_REASONABLY_DISTRIBUTED")

    if tradable_share < 70:
        reasons.append("LESS_THAN_70PCT_LIQUIDITY_IN_50K_PLUS_POOLS")
    else:
        reasons.append("MOST_LIQUIDITY_IN_50K_PLUS_POOLS")

    return {
        "liquidity_reality_score": score,
        "liquidity_reality_level": level,
        "liquidity_reality_scope": "CHAIN_TOKEN_ALL_DEX_POOLS",
        "liquidity_reality_mode": "RESEARCH_SHADOW_NO_PRODUCTION_IMPACT",
        "dex_total_liquidity_usd": round(total, 2),
        "dex_pool_count": len(rows),
        "meaningful_pool_count": mcount,
        "meaningful_pool_floor_usd": round(meaningful_floor, 2),
        "tradable_pool_count": len(tradable),
        "tradable_liquidity_usd": round(tradable_liq, 2),
        "tradable_liquidity_share_pct": round(tradable_share, 2),
        "dex_liquidity_to_market_cap_pct": ratio_mcap,
        "dex_liquidity_to_fdv_pct": ratio_fdv,
        "top_pool_share_pct": round(top1, 2),
        "top3_pool_share_pct": round(top3, 2),
        "liquidity_hhi": round(hhi, 4),
        "liquidity_concentration_level": concentration_level,
        "execution_depth_status": "ROUTER_QUOTES_REQUIRED",
        "cex_depth_status": "NOT_CAPTURED",
        "cross_chain_status": "CANONICAL_MAPPING_REQUIRED",
        "liquidity_reality_reasons": reasons,
    }
