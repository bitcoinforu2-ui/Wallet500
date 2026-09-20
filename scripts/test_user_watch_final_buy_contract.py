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

    print("USER_WATCH_FINAL_BUY_CONTRACT_OK")


if __name__ == "__main__":
    main()
