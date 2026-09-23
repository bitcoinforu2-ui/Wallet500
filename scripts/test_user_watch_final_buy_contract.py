from __future__ import annotations

from datetime import datetime, timedelta, timezone

import user_watch_final_buy as gate


NOW = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
TARGET = {
    "symbol": "MCAT",
    "network": "solana",
    "contract": "241aTYhVXZ4WBVSFpfY37RqoCGBQ73KiRFAKvTtnmoon",
    "pair": "EcFsXQJjVCjCYWHsuhXUnZH4XB2MzF7iZ3dJu48wmoa9",
    "user_watch_final_buy_lane": True,
    "telegram_policy": "FINAL_BUY_ONLY",
    "exact_identity_required": True,
    "exact_pair_required": True,
}
KEY = gate.identity_key(TARGET)
POLICY = gate._policy({})


def market(price: float, when: datetime = NOW, buys: int = 300, sells: int = 200) -> dict:
    return {
        "identity_key": KEY,
        "price": price,
        "liquidity": 70000,
        "volume_h1": 50000,
        "buys_h1": buys,
        "sells_h1": sells,
        "spread_pct": 0.15,
        "observed_at": when.isoformat(),
    }


def observed(*, score: float = 60, families: int = 3, verified: bool = True, hard=None) -> dict:
    return {
        "identity_key": KEY,
        "market_verified": verified,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": score,
            "families": families,
            "current_evidence_count": 10,
            "evidence_age_minutes": 1,
            "hard_risks": list(hard or []),
            "family_scores": {
                "market_microstructure": 10,
                "wallet_flow": 5,
                "holder_network": 0,
            },
        },
    }


def main() -> None:
    low, _ = gate.evaluate(
        TARGET,
        market(0.00025),
        observed(score=4.9, families=1),
        {},
        POLICY,
        now=NOW,
    )
    assert low["recommended_action"] == "WAIT"
    assert "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET" in low["blockers"]

    first, s1 = gate.evaluate(
        TARGET,
        market(0.00025),
        observed(),
        {},
        POLICY,
        now=NOW,
    )
    assert first["state"] == "WATCH"
    assert first["alert"] is False
    assert "NEED_SECOND_VERIFIED_SCAN" in first["blockers"]

    t2 = NOW + timedelta(minutes=15)
    qualifying, s2 = gate.evaluate(
        TARGET,
        market(0.000265, t2),
        observed(),
        s1,
        POLICY,
        now=t2,
    )
    assert qualifying["state"] == "QUALIFYING"
    assert qualifying["qualified_streak"] == 1
    assert qualifying["pre_buy"] is True
    assert qualifying["pre_buy_alert"] is True
    assert qualifying["alert"] is False
    assert "רגע לפני קנייה / PRE-BUY" in gate.telegram_message(TARGET, qualifying)
    assert s2["pre_buy_armed"] is False

    t3 = t2 + timedelta(minutes=15)
    buy, s3 = gate.evaluate(
        TARGET,
        market(0.0002703, t3),
        observed(),
        s2,
        POLICY,
        now=t3,
    )
    assert buy["state"] == "BUY_ZONE"
    assert buy["recommended_action"] == "BUY"
    assert buy["pre_buy"] is False
    assert buy["pre_buy_alert"] is False
    assert buy["alert"] is True
    assert s3["armed"] is False

    t4 = t3 + timedelta(minutes=15)
    duplicate, _ = gate.evaluate(
        TARGET,
        market(0.0002758, t4),
        observed(),
        s3,
        POLICY,
        now=t4,
    )
    assert duplicate["state"] == "BUY_ZONE"
    assert duplicate["alert"] is False

    risky, _ = gate.evaluate(
        TARGET,
        market(0.00028, t4),
        observed(hard=["critical_liquidity_drain"]),
        s2,
        POLICY,
        now=t4,
    )
    assert risky["recommended_action"] == "WAIT"
    assert "HARD_RISK_PRESENT" in risky["blockers"]

    unverified, _ = gate.evaluate(
        TARGET,
        market(0.00028, t4),
        observed(verified=False),
        s2,
        POLICY,
        now=t4,
    )
    assert unverified["recommended_action"] == "WAIT"
    assert "EXACT_PAIR_NOT_VERIFIED_THIS_SCAN" in unverified["blockers"]

    # Publication-lag regression: fresh exact market state + fresh exact close-watch
    # intelligence may repair a missing/stale report row, but never mismatched/stale data.
    fallback_market = market(0.00028, t4)
    fresh_direct_intel = {
        "identity_key": KEY,
        "status": "CURRENT",
        "score": 60,
        "independent_positive_families": 3,
        "current_evidence_count": 10,
        "evidence_age_minutes": 1,
        "updated_at": t4.isoformat(),
        "hard_risks": [],
        "family_scores": {
            "market_microstructure": 10,
            "wallet_flow": 5,
            "holder_network": 1,
        },
    }
    repaired = gate.observed_with_fresh_intelligence_fallback(
        None,
        fallback_market,
        fresh_direct_intel,
        KEY,
        now=t4,
        max_age_seconds=float(POLICY["max_snapshot_age_seconds"]),
    )
    assert repaired is not None
    assert repaired["market_verified"] is True
    assert repaired["_fresh_state_intelligence_fallback"] is True
    repaired_decision, _ = gate.evaluate(
        TARGET,
        fallback_market,
        repaired,
        s2,
        POLICY,
        now=t4,
    )
    assert "WATCH_REPORT_ROW_MISSING" not in repaired_decision["blockers"]
    assert "INTELLIGENCE_NOT_CURRENT" not in repaired_decision["blockers"]

    stale_direct_intel = {
        **fresh_direct_intel,
        "updated_at": (t4 - timedelta(hours=2)).isoformat(),
    }
    assert gate.observed_with_fresh_intelligence_fallback(
        None,
        fallback_market,
        stale_direct_intel,
        KEY,
        now=t4,
        max_age_seconds=float(POLICY["max_snapshot_age_seconds"]),
    ) is None

    wrong_key_intel = {**fresh_direct_intel, "identity_key": "solana:wrong:wrong"}
    assert gate.observed_with_fresh_intelligence_fallback(
        None,
        fallback_market,
        wrong_key_intel,
        KEY,
        now=t4,
        max_age_seconds=float(POLICY["max_snapshot_age_seconds"]),
    ) is None

    # MCAT regression: a user-requested targeted Telegram watch must warn on
    # early price weakness + buy-flow deterioration before a larger breakdown.
    targeted = dict(TARGET)
    targeted.update({
        "targeted_telegram_watch": True,
        "targeted_telegram_events": ["RISK_WARNING", "BREAKDOWN", "PRE_BUY", "FINAL_BUY"],
        "down_levels": [0.00018, 0.00017, 0.00016, 0.00014],
        "liquidity_drop_pct": 20,
        "targeted_risk_policy": {
            "price_drop_warning_pct": 3.0,
            "price_drop_breakdown_pct": 8.0,
            "flow_warning_ratio": 1.2,
            "warning_confirmation_required": True,
            "warning_required_consecutive_scans": 2,
            "warning_min_confirmation_spacing_seconds": 180,
            "warning_max_confirmation_gap_seconds": 900,
            "warning_min_persistent_evidence_groups": 1,
            "warning_min_confirmed_risk_score": 2.5,
            "liquidity_drop_breakdown_pct": 20.0,
            "realert_additional_price_drop_pct": 8.0,
            "cooldown_seconds": 1800,
        },
    })
    warn_time = NOW + timedelta(hours=1)
    warn_market = market(
        0.00018443465403139244,
        warn_time,
        buys=9,
        sells=10,
    )
    warn_market.update({
        "liquidity": 56743.1109,
        "volume_h1": 1476.9343692398,
    })
    warn_prior = {
        "last_price": 0.00019153666430998714,
        "last_liquidity": 57759.2301,
        "last_volume_h1": 2263.11333281,
        "last_buy_sell_ratio": 1.35,
        "targeted_risk_active": False,
    }
    warn_decision, warn_state = gate.evaluate(
        targeted,
        warn_market,
        observed(),
        warn_prior,
        POLICY,
        now=warn_time,
    )
    warning = gate.targeted_risk_event(
        targeted, warn_decision, warn_prior, POLICY, warn_time
    )
    assert warning is not None
    assert warning["severity"] == "RISK_WARNING"
    assert warning["alert"] is False
    assert warning["confirmation_status"] == "PENDING"
    assert warning["confirmation_streak"] == 1
    assert any(
        reason.startswith("PRICE_WEAKNESS_WITH_FLOW_FAILURE")
        or reason.startswith("BUY_FLOW_REVERSAL")
        for reason in warning["reasons"]
    )
    assert "SELL-RISK" in gate.targeted_risk_message(targeted, warn_decision, warning)
    assert warn_state["last_buy_sell_ratio"] < 1.2

    pending_prior = {
        **warn_state,
        "targeted_risk_active": False,
        "targeted_risk_pending_streak": warning["confirmation_streak"],
        "targeted_risk_pending_first_at": warning["confirmation_first_at"],
        "targeted_risk_pending_last_at": warning["confirmation_last_at"],
        "targeted_risk_pending_groups": warning["evidence_groups"],
        "targeted_risk_pending_signature": warning["signature"],
        "targeted_risk_pending_price": warning["price_usd"],
        "targeted_risk_pending_score": warning["risk_score"],
    }

    # A duplicate read inside the minimum spacing window cannot manufacture
    # confirmation.
    too_soon_time = warn_time + timedelta(minutes=1)
    too_soon_market = market(
        0.0001828,
        too_soon_time,
        buys=10,
        sells=14,
    )
    too_soon_market.update({
        "liquidity": 56200.0,
        "volume_h1": 2200.0,
    })
    too_soon_decision, too_soon_state = gate.evaluate(
        targeted,
        too_soon_market,
        observed(),
        pending_prior,
        POLICY,
        now=too_soon_time,
    )
    too_soon = gate.targeted_risk_event(
        targeted, too_soon_decision, pending_prior, POLICY, too_soon_time
    )
    assert too_soon is not None
    assert too_soon["confirmation_status"] == "PENDING"
    assert too_soon["confirmation_streak"] == 1
    assert too_soon["alert"] is False

    confirmed_time = warn_time + timedelta(minutes=5)
    confirmed_market = market(
        0.0001817,
        confirmed_time,
        buys=10,
        sells=16,
    )
    confirmed_market.update({
        "liquidity": 55500.0,
        "volume_h1": 2500.0,
    })
    confirmed_prior = {
        **too_soon_state,
        "targeted_risk_active": False,
        "targeted_risk_pending_streak": too_soon["confirmation_streak"],
        "targeted_risk_pending_first_at": too_soon["confirmation_first_at"],
        "targeted_risk_pending_last_at": too_soon["confirmation_last_at"],
        "targeted_risk_pending_groups": too_soon["evidence_groups"],
        "targeted_risk_pending_signature": too_soon["signature"],
        "targeted_risk_pending_price": too_soon["price_usd"],
        "targeted_risk_pending_score": too_soon["risk_score"],
    }
    confirmed_decision, confirmed_state = gate.evaluate(
        targeted,
        confirmed_market,
        observed(),
        confirmed_prior,
        POLICY,
        now=confirmed_time,
    )
    confirmed_warning = gate.targeted_risk_event(
        targeted, confirmed_decision, confirmed_prior, POLICY, confirmed_time
    )
    assert confirmed_warning is not None
    assert confirmed_warning["severity"] == "RISK_WARNING"
    assert confirmed_warning["confirmation_status"] == "CONFIRMED"
    assert confirmed_warning["confirmation_streak"] >= 2
    assert confirmed_warning["alert"] is True

    # Sensor-v2 regression: total-volume expansion is inferred bearish
    # pressure, not direct sell-notional. MCAT's current combination of
    # expanding activity, weaker flow and near-floor liquidity should still
    # warn before a hard breakdown.
    quality_time = NOW + timedelta(hours=2)
    quality_market = market(
        0.0001476,
        quality_time,
        buys=23,
        sells=31,
    )
    quality_market.update({
        "liquidity": 50655.0,
        "volume_h1": 2632.998660333776,
    })
    quality_prior = {
        "last_price": 0.00014944376727484639,
        "last_liquidity": 50997.7551,
        "last_volume_h1": 1343.3666634356,
        "last_buy_sell_ratio": 0.952381,
        "targeted_risk_active": False,
    }
    quality_decision, _ = gate.evaluate(
        targeted, quality_market, observed(), quality_prior, POLICY, now=quality_time
    )
    quality = gate.targeted_risk_event(
        targeted, quality_decision, quality_prior, POLICY, quality_time
    )
    assert quality is not None
    assert quality["severity"] == "RISK_WARNING"
    assert quality["confidence"] == "HIGH"
    assert quality["confirmation_status"] == "PENDING"
    assert quality["alert"] is False
    assert quality["evidence_group_count"] >= 3
    assert any(
        x.startswith("BEARISH_TOTAL_VOLUME_EXPANSION_1.96")
        for x in quality["reasons"]
    )
    assert any(x.startswith("FLOW_DETERIORATION_") for x in quality["reasons"])
    assert any(x.startswith("LIQUIDITY_NEAR_FLOOR_") for x in quality["reasons"])
    assert not any(
        x.startswith("SELL_VOLUME_ACCELERATION_")
        for x in quality["reasons"]
    )
    quality_text = gate.targeted_risk_message(
        targeted, quality_decision, quality
    )
    assert "inferred bearish pressure" in quality_text
    assert "not measured sell-notional USD" in quality_text

    # A single inferred volume-expansion observation is not sufficient:
    # non-severe warnings now require independent corroboration.
    noise_market = market(
        0.000198,
        quality_time,
        buys=49,
        sells=51,
    )
    noise_market.update({
        "liquidity": 100000.0,
        "volume_h1": 1600.0,
    })
    noise_prior = {
        "last_price": 0.0002,
        "last_liquidity": 100000.0,
        "last_volume_h1": 1000.0,
        "last_buy_sell_ratio": 0.99,
        "targeted_risk_active": False,
    }
    noise_decision, _ = gate.evaluate(
        targeted, noise_market, observed(), noise_prior, POLICY, now=quality_time
    )
    assert gate.targeted_risk_event(
        targeted, noise_decision, noise_prior, POLICY, quality_time
    ) is None

    # A later MCAT-style flush escalates immediately to BREAKDOWN even if the
    # warning cooldown has not expired.
    breakdown_time = confirmed_time + timedelta(minutes=15)
    breakdown_market = market(
        0.0001349,
        breakdown_time,
        buys=49,
        sells=29,
    )
    breakdown_market.update({
        "liquidity": 48417.73,
        "volume_h1": 9440.09,
    })
    breakdown_prior = {
        **confirmed_state,
        "last_targeted_risk_alert_at": confirmed_time.isoformat(),
        "last_targeted_risk_alert_price": confirmed_warning["price_usd"],
        "last_targeted_risk_signature": confirmed_warning["signature"],
        "last_targeted_risk_severity": confirmed_warning["severity"],
        "targeted_risk_active": True,
    }
    breakdown_decision, _ = gate.evaluate(
        targeted,
        breakdown_market,
        observed(),
        breakdown_prior,
        POLICY,
        now=breakdown_time,
    )
    breakdown = gate.targeted_risk_event(
        targeted, breakdown_decision, breakdown_prior, POLICY, breakdown_time
    )
    assert breakdown is not None
    assert breakdown["severity"] == "BREAKDOWN"
    assert breakdown["confirmation_status"] == "BYPASSED_SEVERE"
    assert breakdown["alert"] is True
    assert 0.00018 in breakdown["crossed_down_levels"]
    assert any(x.startswith("LIQUIDITY_FLOOR_BREACH") for x in breakdown["reasons"])

    # Generic watched tokens keep the global no-spam rule.
    assert gate.targeted_risk_event(
        TARGET, warn_decision, warn_prior, POLICY, warn_time
    ) is None

    bootstrap = {
        "candidate_type": "NEW_CHAIN_BOOTSTRAP",
        "symbol": "ARCUS",
        "network": "arc",
        "contract": "0xB7C934FF18730c24e6113BB4bC5A68feEf16fD29",
        "pair": "0x0000000000000000000000000000000000000001",
        "bootstrap_final_buy_lane": True,
        "dex_url": "https://dexscreener.com/arc/example",
    }
    selected = gate.eligible_targets({"tokens": []}, {"candidates": [bootstrap]})
    assert len(selected) == 1
    assert selected[0]["symbol"] == "ARCUS"
    assert gate.identity_key(selected[0]).startswith("arc:0xb7c934")

    research_only = dict(bootstrap, bootstrap_final_buy_lane=False)
    assert gate.eligible_targets({"tokens": []}, {"candidates": [research_only]}) == []

    cex = {
        "candidate_type": "GATE_SPOT_DISCOVERY",
        "symbol": "MGT",
        "network": "bsc",
        "contract": "0x3c6256f234ba638e5883c46b3fedb00ea2e66b8a",
        "pair": "0xdce2e6fe348f8c8a2b08bbff8f447c64224d75fb",
        "dex_url": "https://dexscreener.com/bsc/example",
    }
    cex_key = gate.identity_key(cex)
    unarmed_state = {
        "tokens": {
            "SPOT:" + cex_key: {
                "identity_key": cex_key,
                "quarter_wave_revalidation_armed": False,
                "first_verified_price": 0.0001,
            }
        }
    }
    assert gate.eligible_targets({"tokens": []}, {"candidates": [cex]}, unarmed_state) == []

    armed_state = {
        "tokens": {
            "SPOT:" + cex_key: {
                "identity_key": cex_key,
                "quarter_wave_revalidation_armed": True,
                "first_verified_price": 0.0001,
                "gain_from_first_verified_pct": 31.0,
                "quarter_wave_revalidation_armed_at": NOW.isoformat(),
                "quarter_wave_revalidation_trigger_price": 0.000125,
            }
        }
    }
    selected_cex = gate.eligible_targets({"tokens": []}, {"candidates": [cex]}, armed_state)
    assert len(selected_cex) == 1
    assert selected_cex[0]["quarter_wave_revalidation_lane"] is True
    assert selected_cex[0]["quarter_wave_anchor_price_usd"] == 0.0001
    assert selected_cex[0]["telegram_policy"] == "FINAL_BUY_ONLY"

    # Once armed, the candidate remains tracked even after leaving the live mover list.
    persisted_live = dict(armed_state["tokens"]["SPOT:" + cex_key])
    persisted_live.update({
        "symbol": "MGT",
        "network": "bsc",
        "contract": cex["contract"],
        "pair": cex["pair"],
        "candidate_type": "GATE_SPOT_DISCOVERY",
        "dynamic_spot_candidate": True,
    })
    persisted_state = {"tokens": {"SPOT:" + cex_key: persisted_live}}
    persisted_selected = gate.eligible_targets(
        {"tokens": []}, {"candidates": []}, persisted_state
    )
    assert len(persisted_selected) == 1
    assert persisted_selected[0]["symbol"] == "MGT"
    assert persisted_selected[0]["quarter_wave_revalidation_lane"] is True

    # Strong exact CEX execution can replace a weak DEX execution floor, but it
    # still needs current intelligence, no hard risk and the normal two-scan confirm.
    mgt_target = dict(selected_cex[0])
    mgt_market = {
        "identity_key": cex_key,
        "price": 0.000125,
        "liquidity": 2000,
        "volume_h1": 100,
        # Thin DEX tape is intentionally neutral; positive exact-CEX depth
        # is the execution-flow proof for this lane.
        "buys_h1": 2,
        "sells_h1": 2,
        "spread_pct": 0.2,
        "observed_at": t2.isoformat(),
        "cex_quote_volume_24h_usd": 30000,
        "cex_relative_volume_multiple": 10.0,
        "positive_gainer_rank": 1,
        "cex_led_revival": True,
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "cex_orderbook_spread_pct": 0.25,
        "cex_depth_1pct_usd": 12000,
        "cex_bid_ask_depth_ratio": 1.30,
    }
    mgt_obs = observed(score=15, families=1)
    mgt_obs["identity_key"] = cex_key
    mgt_obs["intelligence"]["current_evidence_count"] = 4
    mgt_obs["intelligence"]["family_scores"]["market_microstructure"] = 15
    mgt_q, _ = gate.evaluate(
        mgt_target,
        mgt_market,
        mgt_obs,
        {"last_price": 0.00012, "watch_low_price": 0.00010},
        POLICY,
        now=t2,
    )
    assert mgt_q["quarter_wave_revalidation"]["cex_fast_path"] is True
    assert "LIQUIDITY_BELOW_FINAL_BUY_FLOOR" not in mgt_q["blockers"]
    assert "VOLUME_H1_TOO_LOW" not in mgt_q["blockers"]
    assert "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET" not in mgt_q["blockers"]
    assert "BUY_FLOW_NOT_CONFIRMED" not in mgt_q["blockers"]
    assert mgt_q["pre_buy"] is True

    # PTB-like case: DEX flow is weak, but exact Gate execution shows an extreme
    # volume/rank breakout with tight spread and sufficient executable depth.
    ptb_target = dict(mgt_target)
    ptb_target.update({
        "symbol": "PTB",
        "network": "ethereum",
        "contract": "0x30a25cc9c9eade4d4d9e9349be6e68c3411367d3",
        "pair": "0xd40929ad9749f30eb56fe5a388d8afb226278fb875baf2c561c4e3a1f816725a",
        "quarter_wave_anchor_price_usd": 0.0010062,
        "quarter_wave_gain_from_anchor_pct": 25.7,
    })
    ptb_key = gate.identity_key(ptb_target)
    ptb_market = {
        "identity_key": ptb_key,
        "price": 0.00126495,
        "liquidity": 16473,
        "volume_h1": 125,
        "buys_h1": 3,
        "sells_h1": 2,
        "spread_pct": 0.165,
        "observed_at": t2.isoformat(),
        "cex_quote_volume_24h_usd": 1348124,
        "cex_relative_volume_multiple": 9.55,
        "positive_gainer_rank": 1,
        "cex_led_revival": True,
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "cex_orderbook_spread_pct": 0.186,
        "cex_depth_1pct_usd": 3054,
        "cex_bid_ask_depth_ratio": 0.67,
    }
    ptb_obs = {
        "identity_key": ptb_key,
        "market_verified": True,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": 0,
            "families": 0,
            "current_evidence_count": 1,
            "evidence_age_minutes": 0.3,
            "hard_risks": [],
            "family_scores": {
                "market_microstructure": 0,
                "wallet_flow": 0,
                "holder_network": -5.32,
            },
        },
    }
    ptb_q, _ = gate.evaluate(
        ptb_target,
        ptb_market,
        ptb_obs,
        {"last_price": 0.001253, "watch_low_price": 0.000908},
        POLICY,
        now=t2,
    )
    assert ptb_q["quarter_wave_revalidation"]["cex_breakout_continuation"] is True
    assert "LIQUIDITY_BELOW_FINAL_BUY_FLOOR" not in ptb_q["blockers"]
    assert "MARKET_MICROSTRUCTURE_NOT_POSITIVE" not in ptb_q["blockers"]
    assert "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET" not in ptb_q["blockers"]
    assert ptb_q["pre_buy"] is True

    ptb_risky_obs = dict(ptb_obs)
    ptb_risky_obs["intelligence"] = dict(ptb_obs["intelligence"], hard_risks=["critical_holder_risk"])
    ptb_risky, _ = gate.evaluate(
        ptb_target,
        ptb_market,
        ptb_risky_obs,
        {"last_price": 0.001253, "watch_low_price": 0.000908},
        POLICY,
        now=t2,
    )
    assert "HARD_RISK_PRESENT" in ptb_risky["blockers"]
    assert ptb_risky["recommended_action"] == "WAIT"

    # Unsupported-chain/BRC-style assets are not discarded: an exact Gate market
    # identity can qualify on a stricter order-book path without inventing a DEX CA.
    trio_target = {
        "candidate_type": "CEX_MARKET_DISCOVERY",
        "symbol": "TRIO",
        "exchange": "gate",
        "currency_pair": "TRIO_USDT",
        "execution_identity_scope": "EXACT_CEX_MARKET",
        "identity_key": "cex:gate:TRIO_USDT",
        "quarter_wave_revalidation_lane": True,
        "quarter_wave_anchor_price_usd": 0.0100,
        "quarter_wave_gain_from_anchor_pct": 35.0,
    }
    trio_key = gate.identity_key(trio_target)
    assert trio_key == "cex:gate:TRIO_USDT"
    trio_market = {
        "identity_key": trio_key,
        "price": 0.0115,
        "liquidity": 15000,
        "volume_h1": 0,
        "buys_h1": 0,
        "sells_h1": 0,
        "spread_pct": 0.40,
        "observed_at": t2.isoformat(),
        "cex_quote_volume_24h_usd": 60000,
        "cex_relative_volume_multiple": 5.0,
        "positive_gainer_rank": 5,
        "cex_led_revival": True,
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "cex_orderbook_spread_pct": 0.40,
        "cex_depth_1pct_usd": 25000,
        "cex_bid_ask_depth_ratio": 1.25,
    }
    trio_obs = {
        "identity_key": trio_key,
        "market_verified": True,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "NOT_AVAILABLE",
            "score": 0,
            "families": 0,
            "current_evidence_count": 0,
            "evidence_age_minutes": None,
            "hard_risks": [],
            "family_scores": {},
        },
    }
    trio_blocked, _ = gate.evaluate(
        trio_target,
        trio_market,
        trio_obs,
        {"last_price": 0.0110, "watch_low_price": 0.0100},
        POLICY,
        now=t2,
    )
    assert trio_blocked["quarter_wave_revalidation"]["cex_market_only_fast_path"] is False
    assert trio_blocked["pre_buy"] is False
    assert "INTELLIGENCE_NOT_CURRENT" in trio_blocked["blockers"]
    assert "INTELLIGENCE_STALE_OR_UNTIMED" in trio_blocked["blockers"]
    assert "CURRENT_EVIDENCE_TOO_LOW" in trio_blocked["blockers"]
    assert "MARKET_MICROSTRUCTURE_NOT_POSITIVE" in trio_blocked["blockers"]

    # Once exact-CEX execution is paired with current, sufficiently rich
    # intelligence, the stricter market-only lane may qualify without inventing
    # DEX evidence. This preserves the fast path while keeping it fail closed.
    trio_current_obs = {
        **trio_obs,
        "intelligence": {
            "status": "CURRENT",
            "score": 0,
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
    trio_q, trio_s1 = gate.evaluate(
        trio_target,
        trio_market,
        trio_current_obs,
        {"last_price": 0.0110, "watch_low_price": 0.0100},
        POLICY,
        now=t2,
    )
    assert trio_q["quarter_wave_revalidation"]["cex_market_only_fast_path"] is True
    assert trio_q["pre_buy"] is True
    assert "INTELLIGENCE_NOT_CURRENT" not in trio_q["blockers"]
    assert "INTELLIGENCE_STALE_OR_UNTIMED" not in trio_q["blockers"]
    assert "CURRENT_EVIDENCE_TOO_LOW" not in trio_q["blockers"]
    assert "MARKET_MICROSTRUCTURE_NOT_POSITIVE" not in trio_q["blockers"]

    trio_market2 = dict(trio_market, price=0.0117, observed_at=t3.isoformat())
    trio_buy, _ = gate.evaluate(trio_target, trio_market2, trio_current_obs, trio_s1, POLICY, now=t3)
    assert trio_buy["recommended_action"] == "BUY"
    assert trio_buy["alert"] is True

    # R2-like hybrid continuation: strong exact DEX execution + CEX shock/rank
    # can override a slightly sub-threshold buy/sell ratio and shallow rebound.
    r2_target = dict(mgt_target)
    r2_target.update({
        "symbol": "R2",
        "network": "bsc",
        "contract": "0x223a20e1b83aa3832e78d4b7b132df022e739222",
        "pair": "0xfdbeffa804bc58e9edd720165f41a62b2ee251b6",
        "quarter_wave_anchor_price_usd": 0.0074577,
        "quarter_wave_gain_from_anchor_pct": 142.0,
    })
    r2_key = gate.identity_key(r2_target)
    r2_market = {
        "identity_key": r2_key,
        "price": 0.01812,
        "liquidity": 247000,
        "volume_h1": 376000,
        "buys_h1": 1597,
        "sells_h1": 1698,
        "spread_pct": 1.65,
        "observed_at": t2.isoformat(),
        "cex_quote_volume_24h_usd": 221000,
        "cex_relative_volume_multiple": 4.25,
        "positive_gainer_rank": 3,
        "cex_led_revival": True,
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "price_source_count": 2,
        "cex_market_price_spread_pct": 0.65,
        "cex_orderbook_spread_pct": 1.58,
        "cex_depth_1pct_usd": 836,
        "cex_bid_ask_depth_ratio": 14.7,
    }
    r2_obs = {
        "identity_key": r2_key,
        "market_verified": True,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": 15,
            "families": 1,
            "current_evidence_count": 15,
            "evidence_age_minutes": 0.2,
            "hard_risks": [],
            "family_scores": {
                "market_microstructure": 15,
                "wallet_flow": 0,
                "holder_network": 0,
            },
        },
    }
    r2_q, _ = gate.evaluate(
        r2_target,
        r2_market,
        r2_obs,
        {"last_price": 0.01786, "watch_low_price": 0.01786},
        POLICY,
        now=t2,
    )
    assert r2_q["quarter_wave_revalidation"]["hybrid_breakout_continuation"] is True
    assert "BUY_FLOW_NOT_CONFIRMED" not in r2_q["blockers"]
    assert "FINAL_BUY_INTELLIGENCE_CONFLUENCE_NOT_MET" not in r2_q["blockers"]
    assert "REBOUND_FROM_WATCH_LOW_NOT_CONFIRMED" not in r2_q["blockers"]
    assert r2_q["pre_buy"] is True
    assert any(x.startswith("HYBRID_CEX_DEX_BREAKOUT") for x in r2_q["proof"])

    r2_risky_obs = dict(r2_obs)
    r2_risky_obs["intelligence"] = dict(
        r2_obs["intelligence"], hard_risks=["critical_transfer_block"]
    )
    r2_risky, _ = gate.evaluate(
        r2_target,
        r2_market,
        r2_risky_obs,
        {"last_price": 0.01786, "watch_low_price": 0.01786},
        POLICY,
        now=t2,
    )
    assert r2_risky["quarter_wave_revalidation"]["hybrid_breakout_continuation"] is False
    assert "HARD_RISK_PRESENT" in r2_risky["blockers"]
    assert r2_risky["recommended_action"] == "WAIT"

    # Regression: a real 0.0 source spread is valid and must never be
    # converted into the 999 "unknown/wide" sentinel. This exact bug blocked
    # AURORA-like CEX+DEX continuation despite coherent execution data.
    aurora_target = {
        "candidate_type": "CEX_SPOT_DISCOVERY",
        "symbol": "AURORAUSDT",
        "network": "ethereum",
        "contract": "0xaaaaaa20d9e0e2461697782ef11675f668207961",
        "pair": "0x629d22e6eeac46a11dbc96be93b90aee9309be4c",
        "exchange": "gate",
        "currency_pair": "AURORA_USDT",
        "execution_identity_scope": "EXACT_CHAIN_CONTRACT_PAIR_PLUS_CEX_MARKET",
        "quarter_wave_revalidation_lane": True,
        "quarter_wave_anchor_price_usd": 0.01527,
        "quarter_wave_gain_from_anchor_pct": 294.0,
    }
    aurora_key = gate.identity_key(aurora_target)
    aurora_market = {
        "identity_key": aurora_key,
        "price": 0.06028,
        "liquidity": 443350.54,
        "volume_h1": 22357.29,
        "buys_h1": 53,
        "sells_h1": 46,
        "spread_pct": 0.0,
        "observed_at": t2.isoformat(),
        "cex_quote_volume_24h_usd": 1984779.22,
        "cex_relative_volume_multiple": 16.9006,
        "positive_gainer_rank": 1,
        "cex_led_revival": True,
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "price_source_count": 1,
        "single_source_degraded": True,
        "cex_market_price_spread_pct": 0.85,
        "cex_orderbook_spread_pct": 0.117,
        "cex_depth_1pct_usd": 3279.12,
        "cex_bid_ask_depth_ratio": 6.03,
    }
    aurora_obs = {
        "identity_key": aurora_key,
        "market_verified": True,
        "_report_age_seconds": 0,
        "intelligence": {
            "status": "CURRENT",
            "score": 10,
            "families": 1,
            "current_evidence_count": 2,
            "evidence_age_minutes": 0.1,
            "hard_risks": [],
            "family_scores": {
                "market_microstructure": 10,
                "wallet_flow": 0,
                "holder_network": 0,
            },
        },
    }
    aurora_decision, _ = gate.evaluate(
        aurora_target,
        aurora_market,
        aurora_obs,
        {
            "last_price": 0.0590,
            "last_market_observed_at": (t2 - timedelta(minutes=4)).isoformat(),
            "watch_low_price": 0.0550,
        },
        POLICY,
        now=t2,
    )
    assert aurora_decision["quarter_wave_revalidation"]["cex_fast_path"] is True
    assert "PRICE_SOURCE_SPREAD_TOO_WIDE" not in aurora_decision["blockers"]
    assert "BUY_FLOW_NOT_CONFIRMED" not in aurora_decision["blockers"]


    # Regression: PRE-BUY is one warning per opportunity episode. Two ordinary
    # observable misses must not silently re-arm another PRE-BUY.
    miss1_t = t2 + timedelta(minutes=5)
    miss1, miss1_state = gate.evaluate(
        TARGET,
        market(0.000260, miss1_t, buys=40, sells=120),
        observed(),
        s2,
        POLICY,
        now=miss1_t,
    )
    assert miss1["qualified_this_scan"] is False
    assert miss1_state["pre_buy_armed"] is False

    miss2_t = t2 + timedelta(minutes=10)
    miss2, miss2_state = gate.evaluate(
        TARGET,
        market(0.000258, miss2_t, buys=40, sells=120),
        observed(),
        miss1_state,
        POLICY,
        now=miss2_t,
    )
    assert miss2["qualified_this_scan"] is False
    assert miss2_state["observable_miss_streak"] >= 2
    assert miss2_state["pre_buy_armed"] is False

    recovery_t = t2 + timedelta(minutes=15)
    recovery, _ = gate.evaluate(
        TARGET,
        market(0.000263, recovery_t),
        observed(),
        miss2_state,
        POLICY,
        now=recovery_t,
    )
    assert recovery["pre_buy"] is True
    assert recovery["pre_buy_alert"] is False

    # A PRE-BUY cannot mature into a much more expensive chase entry merely
    # because the current scan is still green.
    chase_t = t2 + timedelta(minutes=15)
    chase, _ = gate.evaluate(
        TARGET,
        market(0.000290, chase_t),
        observed(),
        s2,
        POLICY,
        now=chase_t,
    )
    assert chase["recommended_action"] == "WAIT"
    assert "PRE_BUY_PRICE_CHASE_FROM_ALERT" in chase["blockers"]

    # Likewise, the warning expires in time; an old PRE-BUY is not a permanent
    # credential for a later FINAL BUY.
    expired_t = t2 + timedelta(minutes=61)
    expired, _ = gate.evaluate(
        TARGET,
        market(0.000269, expired_t),
        observed(),
        s2,
        POLICY,
        now=expired_t,
    )
    assert expired["recommended_action"] == "WAIT"
    assert "PRE_BUY_EPISODE_EXPIRED_REQUIRES_RESET" in expired["blockers"]

    # Migration guard for state created by the old bug: if the same exact pair
    # already emitted multiple PRE-BUY alerts without a FINAL BUY, quarantine it
    # until a genuinely fresh post-alert reset + reclaim occurs.
    duplicate_prior = dict(s2)
    duplicate_prior["pre_buy_episode_count"] = 2
    duplicate_t = t2 + timedelta(minutes=15)
    duplicate_episode, _ = gate.evaluate(
        TARGET,
        market(0.0002703, duplicate_t),
        observed(),
        duplicate_prior,
        POLICY,
        now=duplicate_t,
    )
    assert duplicate_episode["recommended_action"] == "WAIT"
    assert "PRE_BUY_DUPLICATE_EPISODE_REQUIRES_RESET" in duplicate_episode["blockers"]

    # A real new opportunity may re-arm PRE-BUY, but only after a fresh reset
    # that happened AFTER the previous PRE-BUY and a later positive reclaim.
    episode_target = dict(TARGET)
    episode_target.update({
        "quarter_wave_revalidation_lane": True,
        "quarter_wave_anchor_price_usd": 0.00020,
        "quarter_wave_gain_from_anchor_pct": 32.5,
    })
    first_ep, first_ep_state = gate.evaluate(
        episode_target,
        market(0.000250, NOW),
        observed(),
        {},
        POLICY,
        now=NOW,
    )
    assert first_ep["pre_buy"] is False

    pre_ep, pre_ep_state = gate.evaluate(
        episode_target,
        market(0.000265, t2),
        observed(),
        first_ep_state,
        POLICY,
        now=t2,
    )
    assert pre_ep["pre_buy_alert"] is True

    high_t = t2 + timedelta(minutes=5)
    high_ep, high_state = gate.evaluate(
        episode_target,
        market(0.000340, high_t),
        observed(),
        pre_ep_state,
        POLICY,
        now=high_t,
    )
    assert high_ep["recommended_action"] == "WAIT"
    assert high_state["late_entry_extension_seen"] is True

    reset_t = t2 + timedelta(minutes=10)
    reset_ep, reset_state = gate.evaluate(
        episode_target,
        market(0.000310, reset_t),
        observed(),
        high_state,
        POLICY,
        now=reset_t,
    )
    assert reset_ep["recommended_action"] == "WAIT"
    assert reset_state["late_entry_reset_seen"] is True
    assert reset_state["late_entry_reset_seen_at"] is not None

    reclaim_t = t2 + timedelta(minutes=15)
    reclaim_ep, _ = gate.evaluate(
        episode_target,
        market(0.000315, reclaim_t),
        observed(),
        reset_state,
        POLICY,
        now=reclaim_t,
    )
    assert reclaim_ep["pre_buy_episode"]["fresh_reset_reclaim"] is True
    assert reclaim_ep["pre_buy"] is True
    assert reclaim_ep["pre_buy_alert"] is True

    # A stale reset credential cannot be reused hours later. Legacy boolean-only
    # reset state also fails closed because there is no timestamp proving freshness.
    stale_reset_t = t2 + timedelta(hours=2)
    stale_reset_prior = {
        "last_price": 0.000250,
        "last_market_observed_at": (stale_reset_t - timedelta(minutes=5)).isoformat(),
        "watch_low_price": 0.000100,
        "watch_high_price": 0.000300,
        "late_entry_extension_seen": True,
        "late_entry_reset_seen": True,
        "late_entry_reset_seen_at": (stale_reset_t - timedelta(hours=2)).isoformat(),
        "late_entry_reset_max_pullback_pct": 10.0,
    }
    stale_reset, _ = gate.evaluate(
        episode_target,
        market(0.000255, stale_reset_t),
        observed(),
        stale_reset_prior,
        POLICY,
        now=stale_reset_t,
    )
    assert stale_reset["entry_timing"]["reset_reclaim_confirmed"] is False
    assert "EXTENDED_MOVE_WAIT_FOR_RESET" in stale_reset["blockers"]

    print("USER_WATCH_FINAL_BUY_CONTRACT_OK")


if __name__ == "__main__":
    main()
