from __future__ import annotations

"""Canonical Wallet500 veteran-revival policy.

This module is the single source of truth for production-adjacent veteran/revival
eligibility. Research lanes may be stricter only when they are explicitly labeled
as separate experiments; they must never redefine the canonical operator contract.
"""

CANONICAL_MIN_MARKET_AGE_DAYS = 180
CANONICAL_MIN_EXECUTION_LIQUIDITY_USD = 50_000.0
CANONICAL_EXACT_ONCHAIN_IDENTITY_REQUIRED = True
CANONICAL_EXACT_DEX_PAIR_REQUIRED = True
CANONICAL_SYMBOL_ONLY_NEVER_ACTIONABLE = True
CANONICAL_CEX_ONLY_NEVER_REAL_ALERT = True


def canonical_policy() -> dict:
    return {
        "mode": "VETERAN_COIN_REVIVAL_ONLY",
        "minimum_verified_market_age_days": CANONICAL_MIN_MARKET_AGE_DAYS,
        "minimum_liquidity_usd": CANONICAL_MIN_EXECUTION_LIQUIDITY_USD,
        "exact_onchain_identity_required": CANONICAL_EXACT_ONCHAIN_IDENTITY_REQUIRED,
        "exact_dex_pair_required": CANONICAL_EXACT_DEX_PAIR_REQUIRED,
        "symbol_only_never_actionable": CANONICAL_SYMBOL_ONLY_NEVER_ACTIONABLE,
        "cex_only_never_real_alert": CANONICAL_CEX_ONLY_NEVER_REAL_ALERT,
    }


def policy_matches_exactly(policy: dict | None) -> bool:
    if not isinstance(policy, dict):
        return False
    try:
        age = int(policy.get("minimum_verified_market_age_days"))
        liquidity = float(policy.get("minimum_liquidity_usd"))
    except (TypeError, ValueError):
        return False
    return (
        age == CANONICAL_MIN_MARKET_AGE_DAYS
        and liquidity == CANONICAL_MIN_EXECUTION_LIQUIDITY_USD
        and policy.get("exact_onchain_identity_required") is True
        and policy.get("exact_dex_pair_required") is True
        and policy.get("symbol_only_never_actionable") is True
        and policy.get("cex_only_never_real_alert") is True
    )
