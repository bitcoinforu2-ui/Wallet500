from __future__ import annotations

from wallet500.config import Settings
from wallet500.hot_email_alerts import MIN_LIQUIDITY_USD as EMAIL_MIN_LIQUIDITY_USD
from wallet500.hot_email_alerts import MIN_MARKET_AGE_DAYS as EMAIL_MIN_MARKET_AGE_DAYS
from wallet500.policy import (
    CANONICAL_MIN_EXECUTION_LIQUIDITY_USD,
    CANONICAL_MIN_MARKET_AGE_DAYS,
    canonical_policy,
    policy_matches_exactly,
)
from wallet500.production_status import MIN_LIQUIDITY_USD as STATUS_MIN_LIQUIDITY_USD
from wallet500.production_status import MIN_MARKET_AGE_DAYS as STATUS_MIN_MARKET_AGE_DAYS


def test_canonical_policy_is_exactly_90d_15k():
    assert CANONICAL_MIN_MARKET_AGE_DAYS == 90
    assert CANONICAL_MIN_EXECUTION_LIQUIDITY_USD == 15_000.0
    assert policy_matches_exactly(canonical_policy()) is True


def test_core_operator_surfaces_share_canonical_policy(monkeypatch):
    monkeypatch.delenv("WALLET500_VERIFIED_MIN_LIQUIDITY_USD", raising=False)
    assert Settings().verified_min_liquidity_usd == CANONICAL_MIN_EXECUTION_LIQUIDITY_USD
    assert STATUS_MIN_MARKET_AGE_DAYS == CANONICAL_MIN_MARKET_AGE_DAYS
    assert STATUS_MIN_LIQUIDITY_USD == CANONICAL_MIN_EXECUTION_LIQUIDITY_USD
    assert EMAIL_MIN_MARKET_AGE_DAYS == CANONICAL_MIN_MARKET_AGE_DAYS
    assert EMAIL_MIN_LIQUIDITY_USD == CANONICAL_MIN_EXECUTION_LIQUIDITY_USD


def test_stricter_is_drift_not_canonical():
    assert policy_matches_exactly({
        "minimum_verified_market_age_days": 180,
        "minimum_liquidity_usd": 50_000.0,
        "exact_onchain_identity_required": True,
        "exact_dex_pair_required": True,
        "symbol_only_never_actionable": True,
        "cex_only_never_real_alert": True,
    }) is False
