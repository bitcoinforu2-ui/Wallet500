from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hot_candidate_recheck as hot
import user_watch_final_buy as gate


def _intel(*, status="CURRENT", evidence=3, micro=8.0, hard_risks=None, age=0.2):
    return {
        "status": status,
        "score": 20,
        "positive_families": 1,
        "current_evidence_count": evidence,
        "evidence_age_minutes": age,
        "hard_risks": list(hard_risks or []),
        "wallet_flow_score": 0,
        "holder_network_score": 0,
        "market_microstructure_score": micro,
    }


def test_hot_plan_prioritizes_prebuy_and_excludes_stale_intelligence(monkeypatch):
    k1 = "cex:gate:FAST_USDT"
    k2 = "cex:gate:STALE_USDT"
    targets = {
        k1: {
            "candidate_type": "CEX_MARKET_DISCOVERY",
            "symbol": "FAST",
            "exchange": "gate",
            "currency_pair": "FAST_USDT",
            "execution_identity_scope": "EXACT_CEX_MARKET",
            "quarter_wave_revalidation_lane": True,
        },
        k2: {
            "candidate_type": "CEX_MARKET_DISCOVERY",
            "symbol": "STALE",
            "exchange": "gate",
            "currency_pair": "STALE_USDT",
            "execution_identity_scope": "EXACT_CEX_MARKET",
            "quarter_wave_revalidation_lane": True,
        },
    }
    monkeypatch.setattr(hot, "_target_map", lambda *_: targets)

    report = {
        "decisions": [
            {
                "identity_key": k1,
                "symbol": "FAST",
                "pre_buy": True,
                "blockers": [],
                "intelligence": _intel(),
                "quarter_wave_revalidation": {"enabled_for_target": True, "gain_from_anchor_pct": 40},
            },
            {
                "identity_key": k2,
                "symbol": "STALE",
                "pre_buy": True,
                "blockers": [],
                "intelligence": _intel(status="NOT_AVAILABLE", evidence=0, micro=0, age=None),
                "quarter_wave_revalidation": {"enabled_for_target": True, "gain_from_anchor_pct": 50},
            },
        ]
    }
    plan = hot.build_plan({}, {}, {}, report)
    assert plan["count"] == 1
    assert plan["targets"][0]["identity_key"] == k1
    assert plan["targets"][0]["reason"] == "PRE_BUY_CONFIRMATION_PENDING"
    assert plan["delay_seconds"] == 180


def test_hot_plan_accepts_bounded_quarter_wave_market_blockers(monkeypatch):
    key = "cex:gate:WAVE_USDT"
    target = {
        "candidate_type": "CEX_MARKET_DISCOVERY",
        "symbol": "WAVE",
        "exchange": "gate",
        "currency_pair": "WAVE_USDT",
        "execution_identity_scope": "EXACT_CEX_MARKET",
        "quarter_wave_revalidation_lane": True,
    }
    monkeypatch.setattr(hot, "_target_map", lambda *_: {key: target})
    report = {
        "decisions": [{
            "identity_key": key,
            "symbol": "WAVE",
            "pre_buy": False,
            "blockers": [
                "REBOUND_FROM_WATCH_LOW_NOT_CONFIRMED",
                "SHORT_TERM_PRICE_RECLAIM_NOT_CONFIRMED",
            ],
            "intelligence": _intel(),
            "quarter_wave_revalidation": {
                "enabled_for_target": True,
                "gain_from_anchor_pct": 31.5,
            },
        }]
    }
    plan = hot.build_plan({}, {}, {}, report)
    assert plan["count"] == 1
    assert plan["targets"][0]["reason"] == "QUARTER_WAVE_CLOSE_WATCH"


def test_hot_plan_never_rechecks_hard_risk(monkeypatch):
    key = "cex:gate:RISK_USDT"
    target = {
        "candidate_type": "CEX_MARKET_DISCOVERY",
        "symbol": "RISK",
        "exchange": "gate",
        "currency_pair": "RISK_USDT",
        "execution_identity_scope": "EXACT_CEX_MARKET",
        "quarter_wave_revalidation_lane": True,
    }
    monkeypatch.setattr(hot, "_target_map", lambda *_: {key: target})
    report = {
        "decisions": [{
            "identity_key": key,
            "symbol": "RISK",
            "pre_buy": False,
            "blockers": ["HARD_RISK_PRESENT"],
            "intelligence": _intel(hard_risks=["critical_holder_risk"]),
            "quarter_wave_revalidation": {
                "enabled_for_target": True,
                "gain_from_anchor_pct": 80,
            },
        }]
    }
    plan = hot.build_plan({}, {}, {}, report)
    assert plan["count"] == 0


def _cex_market(key: str, now: datetime, price: float) -> dict:
    return {
        "identity_key": key,
        "price": price,
        "liquidity": 100000,
        "volume_h1": 0,
        "buys_h1": 0,
        "sells_h1": 0,
        "spread_pct": 0.10,
        "observed_at": now.isoformat(),
        "cex_quote_volume_24h_usd": 1_000_000,
        "cex_relative_volume_multiple": 10.0,
        "positive_gainer_rank": 1,
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "cex_orderbook_spread_pct": 0.10,
        "cex_depth_1pct_usd": 100000,
        "cex_bid_ask_depth_ratio": 1.5,
    }


def _observed(key: str, now: datetime) -> dict:
    return {
        "identity_key": key,
        "market_verified": True,
        "observed_at": now.isoformat(),
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": 20,
            "families": 1,
            "current_evidence_count": 3,
            "evidence_age_minutes": 0.2,
            "hard_risks": [],
            "family_scores": {
                "market_microstructure": 8,
                "holder_network": 0,
                "wallet_flow": 0,
            },
        },
    }


def test_fast_recheck_cannot_double_count_confirmation_without_real_time_spacing():
    policy = gate._policy({
        "user_watch_final_buy_policy": {
            "min_qualified_scan_spacing_seconds": 180,
        }
    })
    target = {
        "candidate_type": "CEX_MARKET_DISCOVERY",
        "symbol": "FAST",
        "exchange": "gate",
        "currency_pair": "FAST_USDT",
        "execution_identity_scope": "EXACT_CEX_MARKET",
        "quarter_wave_revalidation_lane": True,
        "quarter_wave_anchor_price_usd": 0.80,
        "quarter_wave_gain_from_anchor_pct": 27.5,
    }
    key = gate.identity_key(target)
    t0 = datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc)
    prior = {
        "last_price": 1.00,
        "last_market_observed_at": (t0 - timedelta(minutes=15)).isoformat(),
        "watch_low_price": 0.90,
        "qualified_streak": 0,
    }

    first, state1 = gate.evaluate(
        target,
        _cex_market(key, t0, 1.02),
        _observed(key, t0),
        prior,
        policy,
        now=t0,
    )
    assert first["pre_buy"] is True
    assert first["alert"] is False
    assert first["qualified_streak"] == 1
    assert state1["last_qualified_scan_at"] == t0.isoformat()

    too_soon = t0 + timedelta(seconds=60)
    second, state2 = gate.evaluate(
        target,
        _cex_market(key, too_soon, 1.04),
        _observed(key, too_soon),
        state1,
        policy,
        now=too_soon,
    )
    assert second["qualified_this_scan"] is True
    assert second["confirmation_spacing"]["satisfied"] is False
    assert second["confirmation_spacing"]["counted_this_scan"] is False
    assert second["qualified_streak"] == 1
    assert second["alert"] is False
    assert state2["last_qualified_scan_at"] == t0.isoformat()

    eligible = t0 + timedelta(seconds=181)
    third, state3 = gate.evaluate(
        target,
        _cex_market(key, eligible, 1.06),
        _observed(key, eligible),
        state2,
        policy,
        now=eligible,
    )
    assert third["confirmation_spacing"]["satisfied"] is True
    assert third["confirmation_spacing"]["counted_this_scan"] is True
    assert third["qualified_streak"] == 2
    assert third["recommended_action"] == "BUY"
    assert third["alert"] is True
    assert state3["last_qualified_scan_at"] == eligible.isoformat()
