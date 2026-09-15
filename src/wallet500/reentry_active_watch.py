from __future__ import annotations

"""Active re-entry watch policy for promoted Wallet500 assets.

Research/decision layer only. It does not execute trades. A prior valid discovery that
became extended can return to actionable state only after a real correction and renewed
confirmation. The purpose is to prefer repeatable, risk-defined entries over chasing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReentryPolicy:
    min_pullback_from_local_peak_pct: float = 6.0
    max_pullback_from_local_peak_pct: float = 18.0
    min_rebound_from_pullback_low_pct: float = 2.0
    min_signal_score: int = 55
    min_liquidity_usd: float = 15_000.0
    target_1_pct: float = 10.0
    target_2_pct: float = 12.0
    max_risk_pct: float = 6.0


POLICY = ReentryPolicy()


def evaluate_reentry(row: dict) -> dict:
    """Return fail-closed re-entry state from point-in-time fields only."""
    def n(key, default=None):
        try:
            v = row.get(key)
            return default if v is None else float(v)
        except (TypeError, ValueError):
            return default

    price=n("current_price_usd"); peak=n("watch_peak_price_usd"); low=n("pullback_low_price_usd")
    score=n("signal_score",0) or 0; liq=n("execution_liquidity_usd",0) or 0
    exact=bool(row.get("exact_identity_verified") or row.get("exact_chain_contract_pair_verified"))
    market_ok=bool(row.get("market_context_ok"))
    catalyst_ok=bool(row.get("catalyst_scan_ok"))
    flow_ok=bool(row.get("renewed_buy_flow"))
    liquidity_ok=bool(row.get("liquidity_survival_ok"))

    missing=[]
    if not exact: missing.append("EXACT_IDENTITY_REQUIRED")
    if not all(x and x > 0 for x in (price,peak,low)): missing.append("PRICE_PATH_REQUIRED")
    if score < POLICY.min_signal_score: missing.append("SCORE_TOO_LOW")
    if liq < POLICY.min_liquidity_usd: missing.append("LIQUIDITY_TOO_LOW")
    if not market_ok: missing.append("MARKET_CONTEXT_NOT_CONFIRMED")
    if not catalyst_ok: missing.append("CATALYST_SCAN_NOT_CLEARED")
    if not flow_ok: missing.append("BUY_FLOW_NOT_RENEWED")
    if not liquidity_ok: missing.append("LIQUIDITY_SURVIVAL_NOT_CONFIRMED")

    pullback = ((price / peak)-1)*100 if price and peak else None
    rebound = ((price / low)-1)*100 if price and low else None
    depth = -pullback if pullback is not None else None
    if depth is not None and not (POLICY.min_pullback_from_local_peak_pct <= depth <= POLICY.max_pullback_from_local_peak_pct):
        missing.append("PULLBACK_DEPTH_NOT_IN_REENTRY_ZONE")
    if rebound is not None and rebound < POLICY.min_rebound_from_pullback_low_pct:
        missing.append("REBOUND_NOT_CONFIRMED")

    actionable = not missing
    entry = price if actionable else None
    return {
        "action_state": "RE_ENTRY" if actionable else "ACTIVE_WATCH",
        "actionable": actionable,
        "pullback_from_peak_pct": round(pullback,4) if pullback is not None else None,
        "rebound_from_low_pct": round(rebound,4) if rebound is not None else None,
        "entry_price_usd": entry,
        "target_1_price_usd": round(entry*(1+POLICY.target_1_pct/100),12) if entry else None,
        "target_2_price_usd": round(entry*(1+POLICY.target_2_pct/100),12) if entry else None,
        "risk_invalidation_price_usd": round(entry*(1-POLICY.max_risk_pct/100),12) if entry else None,
        "blockers": sorted(set(missing)),
        "contract": {
            "manual_decision_only": True,
            "automatic_trade": False,
            "requires_market_scan": True,
            "requires_catalyst_scan": True,
            "repeat_profit_is_hypothesis_not_guarantee": True,
        },
    }
