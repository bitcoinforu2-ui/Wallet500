"""Canonical Wallet500 policy constants and compatibility helpers.

This module is the single code-level source of truth for research vs production
scope. Research may observe earlier/shallower candidates, but can never authorize
production. Production remains veteran-only, exact-pair, fail-closed.
"""
from __future__ import annotations

RESEARCH_MIN_MARKET_AGE_DAYS = 90
RESEARCH_MIN_LIQUIDITY_USD = 15_000.0
PRODUCTION_MIN_MARKET_AGE_DAYS = 180
PRODUCTION_MIN_LIQUIDITY_USD = 50_000.0

EXACT_IDENTITY_REQUIRED = True
EXACT_PAIR_REQUIRED = True
HOLDER_CLUSTER_FAIL_CLOSED = True
AUTOMATIC_BUY_ALLOWED = False
NEW_TOKEN_RESEARCH_ATTENTION_PCT = 0
VETERAN_REVIVAL_ATTENTION_PCT = 100

POLICY_VERSION = 1
POLICY_ID = "W500_VETERAN_REVIVAL_90D15K_RESEARCH_180D50K_PRODUCTION_EXACT_PAIR"


def verified_market_age(row: dict, *, minimum_days: int = RESEARCH_MIN_MARKET_AGE_DAYS) -> bool:
    """Canonical age check with read-only compatibility for the old 60d field.

    The legacy boolean alone is never sufficient. A numeric market_age_min_days /
    market_age_days must prove the current minimum. This prevents the misleading
    `*_60d_plus` field name from weakening today's 90d/180d rules.
    """
    if not isinstance(row, dict):
        return False
    explicit = row.get("market_age_verified") is True
    legacy = row.get("market_age_verified_60d_plus") is True
    try:
        days = int(row.get("market_age_min_days") or row.get("market_age_days") or 0)
    except (TypeError, ValueError):
        return False
    return bool((explicit or legacy) and days >= int(minimum_days))


def policy_snapshot() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "policy_id": POLICY_ID,
        "research": {
            "minimum_market_age_days": RESEARCH_MIN_MARKET_AGE_DAYS,
            "minimum_execution_liquidity_usd": RESEARCH_MIN_LIQUIDITY_USD,
            "automatic_buy": False,
        },
        "production": {
            "minimum_market_age_days": PRODUCTION_MIN_MARKET_AGE_DAYS,
            "minimum_execution_liquidity_usd": PRODUCTION_MIN_LIQUIDITY_USD,
            "exact_identity_required": EXACT_IDENTITY_REQUIRED,
            "exact_pair_required": EXACT_PAIR_REQUIRED,
            "holder_cluster_fail_closed": HOLDER_CLUSTER_FAIL_CLOSED,
            "automatic_buy": False,
        },
        "attention": {
            "veteran_revival_pct": VETERAN_REVIVAL_ATTENTION_PCT,
            "new_token_research_pct": NEW_TOKEN_RESEARCH_ATTENTION_PCT,
        },
    }
