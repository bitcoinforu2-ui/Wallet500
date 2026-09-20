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
        "buys_h1": 8,
        "sells_h1": 4,
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
    assert mgt_q["pre_buy"] is True

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
    trio_q, trio_s1 = gate.evaluate(
        trio_target,
        trio_market,
        trio_obs,
        {"last_price": 0.0110, "watch_low_price": 0.0100},
        POLICY,
        now=t2,
    )
    assert trio_q["quarter_wave_revalidation"]["cex_market_only_fast_path"] is True
    assert trio_q["pre_buy"] is True
    assert "INTELLIGENCE_NOT_CURRENT" not in trio_q["blockers"]

    trio_market2 = dict(trio_market, price=0.0117, observed_at=t3.isoformat())
    trio_buy, _ = gate.evaluate(trio_target, trio_market2, trio_obs, trio_s1, POLICY, now=t3)
    assert trio_buy["recommended_action"] == "BUY"
    assert trio_buy["alert"] is True

    print("USER_WATCH_FINAL_BUY_CONTRACT_OK")


if __name__ == "__main__":
    main()
