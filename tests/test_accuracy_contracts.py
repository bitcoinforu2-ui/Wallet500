from datetime import datetime, timezone

from wallet500.accuracy_contracts import (
    ALERT_SCORE_THRESHOLD,
    AuthorityState,
    authority_state,
    candidate_authority_states,
    choose_best_exact_pair,
    normalized_acceleration,
    wallet_shadow_evidence,
)
from wallet500.policy import CANONICAL_REAL_ALERT_SCORE_THRESHOLD, canonical_policy


NOW = datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)


def test_authority_truth_is_tri_state_and_missing_is_unknown():
    assert authority_state({"mintAuthority": "AUTH"}, "mintAuthority") == AuthorityState.ACTIVE
    assert authority_state({"mintAuthority": None}, "mintAuthority") == AuthorityState.REVOKED
    assert authority_state({}, "mintAuthority") == AuthorityState.UNKNOWN
    assert authority_state({"mintAuthority": None}, "mintAuthority", provider_ok=False) == AuthorityState.UNKNOWN
    assert authority_state({"mintAuthority": ""}, "mintAuthority") == AuthorityState.UNKNOWN


def test_candidate_missing_authority_never_looks_revoked():
    states = candidate_authority_states({"chain": "solana"})
    assert states == {"mint": "UNKNOWN", "freeze": "UNKNOWN"}


def test_verified_null_mint_is_revoked_but_missing_freeze_stays_unknown():
    states = candidate_authority_states({
        "chain": "solana",
        "mintability_verified": True,
        "mintability_status": "NON_MINTABLE_VERIFIED",
        "mintable": False,
        "mint_authority": None,
    })
    assert states["mint"] == "REVOKED"
    assert states["freeze"] == "UNKNOWN"


def test_acceleration_is_time_normalized_for_uneven_windows():
    out = normalized_acceleration([
        {"observed_at": "2026-09-14T13:00:00Z", "value": 10},
        {"observed_at": "2026-09-14T13:10:00Z", "value": 20},
        {"observed_at": "2026-09-14T13:30:00Z", "value": 60},
    ], now=NOW)
    assert out["valid"] is True
    assert out["latest_rate_per_min"] == 2.0
    assert out["acceleration_per_min2"] == 0.05


def test_acceleration_rejects_duplicate_out_of_order_and_future_samples():
    duplicate = normalized_acceleration([
        {"observed_at": "2026-09-14T13:00:00Z", "value": 1},
        {"observed_at": "2026-09-14T13:00:00Z", "value": 2},
        {"observed_at": "2026-09-14T13:10:00Z", "value": 3},
    ], now=NOW)
    assert duplicate["valid"] is False
    assert duplicate["reason"] == "NON_MONOTONIC_TIMESTAMP"

    future = normalized_acceleration([
        {"observed_at": "2026-09-14T13:00:00Z", "value": 1},
        {"observed_at": "2026-09-14T13:10:00Z", "value": 2},
        {"observed_at": "2026-09-14T14:01:00Z", "value": 3},
    ], now=NOW)
    assert future["valid"] is False
    assert future["reason"] == "FUTURE_SAMPLE"


def test_pair_selector_requires_exact_identity_and_uses_quality_not_only_depth():
    stale_deep = {
        "pair_address": "STALE",
        "exact_pair_verified": True,
        "observed_at": "2026-09-14T10:00:00Z",
        "execution_pool_liquidity_usd": 2_000_000,
        "volume_h1": 100,
        "buys_h1": 1,
        "sells_h1": 1,
        "pair_age_minutes": 1000,
    }
    fresh_active = {
        "pair_address": "FRESH",
        "exact_pair_verified": True,
        "observed_at": "2026-09-14T13:55:00Z",
        "execution_pool_liquidity_usd": 120_000,
        "volume_h1": 80_000,
        "buys_h1": 120,
        "sells_h1": 80,
        "pair_age_minutes": 300,
    }
    unverified_huge = {
        "pair_address": "UNVERIFIED",
        "observed_at": "2026-09-14T13:59:00Z",
        "execution_pool_liquidity_usd": 99_000_000,
        "volume_h1": 99_000_000,
    }
    assert choose_best_exact_pair([stale_deep, fresh_active, unverified_huge], now=NOW)["pair_address"] == "FRESH"


def test_wallet_discovery_is_shadow_only_and_cannot_promote():
    out = wallet_shadow_evidence({"cluster_accumulation": True, "strong_wallet_count": 4, "wallet_cluster_score": 92})
    assert out["detected"] is True
    assert out["ranking_only"] is True
    assert out["research_shadow"] is True
    assert out["real_alert_eligible"] is False
    assert out["automatic_buy"] is False
    assert out["auto_promote"] is False


def test_real_alert_score_threshold_is_pinned_to_85():
    assert ALERT_SCORE_THRESHOLD == 85.0
    assert CANONICAL_REAL_ALERT_SCORE_THRESHOLD == 85.0
    assert canonical_policy()["real_alert_score_threshold"] == 85.0
