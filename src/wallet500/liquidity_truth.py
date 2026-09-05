from __future__ import annotations

from math import sqrt

CONCENTRATED_MARKERS = (
    "meteora", "dlmm", "clmm", "whirlpool", "uniswap v3", "uniswap_v3",
    "pancakeswap v3", "pancakeswap_v3", "raydium clmm", "raydium_clmm",
    "algebra", "camelot v3", "camelot_v3", "concentrated",
)


def _f(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def is_concentrated_pool(row: dict) -> bool:
    text = " ".join(
        str(row.get(k) or "").lower()
        for k in ("dex", "dex_id", "protocol", "market_protocol", "market_program", "pool_type")
    )
    return any(marker in text for marker in CONCENTRATED_MARKERS)


def constant_product_depth_proxy(tvl_usd: float | None, price_impact_pct: float) -> float | None:
    """Conservative no-fee 50/50 CPMM quote-input proxy, never a verified depth measurement.

    If TVL ~= 2*quote_reserve, quote input that moves spot price by p is
    quote_reserve * (sqrt(1+p)-1). Fees/routing can only make realized execution worse,
    so callers must label this as a proxy and never as provider-verified depth.
    """
    tvl = _f(tvl_usd)
    if tvl is None or tvl <= 0 or price_impact_pct <= 0:
        return None
    quote_reserve = tvl / 2.0
    return quote_reserve * (sqrt(1.0 + price_impact_pct / 100.0) - 1.0)


def liquidity_truth(row: dict) -> dict:
    """Separate provider TVL/reserve from executable depth.

    Rules:
    - Provider `liquidity_usd`/reserve is TVL-style context, not automatically execution depth.
    - Explicit execution depth is accepted only when the upstream row marks it verified.
    - Concentrated/bin/DLMM pools fail closed when verified depth is absent.
    - Legacy constant-product pools may expose a conservative reserve proxy for research,
      but it is not marked verified execution depth.
    """
    pool_tvl = _f(row.get("pool_tvl_usd"))
    if pool_tvl is None:
        pool_tvl = _f(row.get("liquidity_usd"))
    if pool_tvl is None:
        pool_tvl = _f(row.get("reserve_in_usd"))

    active = _f(row.get("active_liquidity_usd"))
    concentrated = is_concentrated_pool(row)

    verified = row.get("execution_depth_verified") is True
    d1 = _f(row.get("execution_depth_usd_1pct")) if verified else None
    d2 = _f(row.get("execution_depth_usd_2pct")) if verified else None
    d5 = _f(row.get("execution_depth_usd_5pct")) if verified else None

    proxy1 = proxy2 = proxy5 = None
    if not concentrated and pool_tvl and pool_tvl > 0:
        proxy1 = constant_product_depth_proxy(pool_tvl, 1)
        proxy2 = constant_product_depth_proxy(pool_tvl, 2)
        proxy5 = constant_product_depth_proxy(pool_tvl, 5)

    if verified and d5 is not None:
        gate_status = "VERIFIED_EXECUTION_DEPTH"
        gate_value = d5
        gate_eligible = True
    elif concentrated:
        gate_status = "CONCENTRATED_POOL_DEPTH_UNVERIFIED_FAIL_CLOSED"
        gate_value = None
        gate_eligible = False
    else:
        gate_status = "CPMM_RESERVE_PROXY_ONLY_NOT_VERIFIED_DEPTH"
        gate_value = None
        gate_eligible = False

    return {
        "pool_tvl_usd": round(pool_tvl, 2) if pool_tvl is not None else None,
        "active_liquidity_usd": round(active, 2) if active is not None else None,
        "execution_depth_usd_1pct": round(d1, 2) if d1 is not None else None,
        "execution_depth_usd_2pct": round(d2, 2) if d2 is not None else None,
        "execution_depth_usd_5pct": round(d5, 2) if d5 is not None else None,
        "execution_depth_verified": bool(verified and d5 is not None),
        "execution_depth_source": row.get("execution_depth_source") if verified else None,
        "constant_product_depth_proxy_usd_1pct": round(proxy1, 2) if proxy1 is not None else None,
        "constant_product_depth_proxy_usd_2pct": round(proxy2, 2) if proxy2 is not None else None,
        "constant_product_depth_proxy_usd_5pct": round(proxy5, 2) if proxy5 is not None else None,
        "concentrated_liquidity_pool": concentrated,
        "liquidity_execution_gate_eligible": gate_eligible,
        "liquidity_execution_gate_status": gate_status,
        "liquidity_execution_gate_usd": round(gate_value, 2) if gate_value is not None else None,
        "liquidity_semantics_version": "LIQUIDITY_TRUTH_V1",
    }
