from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500.confluence_matrix import WEIGHTS, build


NOW = datetime(2026, 9, 8, 21, 20, tzinfo=timezone.utc)
TOKEN = "MINT1"
PAIR = "PAIR1"


def write(root: Path, name: str, payload) -> None:
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def fusion(*, hard=None, late=False, wallets=None, holders=80, market=80, narrative=None):
    channels = {
        "market": {"available": True, "score": market},
        "holders": {"available": True, "score": holders},
        "wallets": wallets if wallets is not None else {"available": False, "score": 0},
        "smart_money": {"available": False, "score": 0},
        "narrative": narrative if narrative is not None else {"available": False, "score": 0, "confidence": 0},
    }
    return {
        "generated_at": NOW.isoformat(),
        "tokens": [{
            "chain": "solana",
            "token_address": TOKEN,
            "pair_address": PAIR,
            "symbol": "TST",
            "positive_family_count": 2,
            "channels": channels,
            "risk": {"manipulation": 0, "late_move": late, "hard_blockers": hard or []},
            "change": {"pair_volume_change_pct": 30, "holder_growth_24h_pct": 12},
        }],
    }


def real(liq=15_000):
    return {
        "generated_at": NOW.isoformat(),
        "verified_watch": [{
            "chain": "solana",
            "token_address": TOKEN,
            "pair_address": PAIR,
            "exact_pair_verified": True,
            "execution_pool_liquidity_usd": liq,
        }],
    }


def base(root: Path, **kwargs):
    write(root, "cross-signal-fusion-v2.json", fusion(**kwargs))
    write(root, "real-alerts.json", real())
    return build(root, now=NOW)


def test_weight_prior_sums_to_100_and_policy_is_exact():
    assert sum(WEIGHTS.values()) == 100
    out = build(Path("/nonexistent-wallet500-test"), now=NOW)
    assert out["canonical_policy"]["minimum_market_age_days"] == 90
    assert out["canonical_policy"]["minimum_execution_liquidity_usd"] == 15_000
    assert out["weight_contract"]["sum"] == 100
    assert out["production_change"] is False
    assert out["automatic_buy"] is False


def test_missing_lanes_reduce_confidence_without_zero_filling_alpha(tmp_path: Path):
    out = base(tmp_path)
    row = out["tokens"][0]
    assert row["signal_alpha_score"] > 60
    assert row["confidence_pct"] < 100
    assert "wallet_alpha" in row["missing_lanes"]
    assert row["lanes"]["wallet_alpha"]["score"] is None


def test_hard_blocker_forces_priority_zero(tmp_path: Path):
    out = base(tmp_path, hard=["HONEYPOT_OR_SELLABILITY_RISK"])
    row = out["tokens"][0]
    assert row["confluence_status"] == "BLOCKED"
    assert row["priority_score"] == 0
    assert "HONEYPOT_OR_SELLABILITY_RISK" in row["hard_blockers"]


def test_execution_14999_is_hard_blocked_and_15000_is_not(tmp_path: Path):
    write(tmp_path, "cross-signal-fusion-v2.json", fusion())
    write(tmp_path, "real-alerts.json", real(14_999))
    out = build(tmp_path, now=NOW)
    assert "EXECUTION_LIQUIDITY_LT_15K" in out["tokens"][0]["hard_blockers"]

    write(tmp_path, "real-alerts.json", real(15_000))
    out2 = build(tmp_path, now=NOW)
    assert "EXECUTION_LIQUIDITY_LT_15K" not in out2["tokens"][0]["hard_blockers"]
    assert out2["tokens"][0]["copyability_score"] == 70


def test_official_catalyst_requires_fresh_exact_identity_guard(tmp_path: Path):
    write(tmp_path, "cross-signal-fusion-v2.json", fusion())
    write(tmp_path, "real-alerts.json", real())
    event = {
        "chain": "solana",
        "contract": TOKEN,
        "pair_address": PAIR,
        "impact_score": 100,
        "event_type": "SPOT_LISTING_EXPECTED",
        "alert_eligible": True,
        "symbol_contract_link_verified": False,
        "identity_guard_status": "BLOCKED",
    }
    write(tmp_path, "catalyst-wire-live.json", {"updated_at": NOW.isoformat(), "events": [event]})
    out = build(tmp_path, now=NOW)
    assert out["tokens"][0]["lanes"]["official_catalyst"]["available"] is False

    event["symbol_contract_link_verified"] = True
    event["identity_guard_status"] = "PASS"
    write(tmp_path, "catalyst-wire-live.json", {"updated_at": NOW.isoformat(), "events": [event]})
    out2 = build(tmp_path, now=NOW)
    assert out2["tokens"][0]["lanes"]["official_catalyst"]["score"] == 100


def test_stale_catalyst_and_cex_never_add_positive_lane(tmp_path: Path):
    write(tmp_path, "cross-signal-fusion-v2.json", fusion())
    write(tmp_path, "real-alerts.json", real())
    old = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc).isoformat()
    write(tmp_path, "catalyst-wire-live.json", {
        "updated_at": old,
        "events": [{
            "chain": "solana", "contract": TOKEN, "pair_address": PAIR,
            "impact_score": 100, "alert_eligible": True,
            "symbol_contract_link_verified": True, "identity_guard_status": "PASS",
        }],
    })
    write(tmp_path, "cex-revival-radar.json", {
        "generated_at": old,
        "alerts": [{
            "chain": "solana", "token_address": TOKEN, "pair_address": PAIR,
            "cex_revival_score": 100, "coherent_confirmations": 7,
            "identity_registry_verified": True, "identity_status": "DEX_VERIFIED",
            "dex_activity_verified": True,
        }],
    })
    out = build(tmp_path, now=NOW)
    row = out["tokens"][0]
    assert row["lanes"]["official_catalyst"]["available"] is False
    assert row["lanes"]["cex_acceleration"]["available"] is False


def test_concentration_and_paid_promotion_are_penalties_only(tmp_path: Path):
    write(tmp_path, "cross-signal-fusion-v2.json", fusion())
    write(tmp_path, "real-alerts.json", real())
    write(tmp_path, "holder-concentration-shadow.json", {
        "generated_at": NOW.isoformat(),
        "rows": [{
            "network": "solana", "token_address": TOKEN,
            "verified": True, "contract_match": True,
            "concentration_risk_score": 50, "top1_pct": 18, "top10_pct": 45,
            "semantics": "TOP_TOKEN_ACCOUNT_CONCENTRATION_NOT_OWNER_CLUSTER_CONCENTRATION",
        }],
    })
    write(tmp_path, "paid-order-truth.json", {
        "generated_at": NOW.isoformat(),
        "verified_paid_tokens": [{
            "network": "solana", "token_address": TOKEN, "pair_address": PAIR,
            "order_type": "boost",
        }],
    })
    out = build(tmp_path, now=NOW)
    row = out["tokens"][0]
    assert row["risk"]["holder_concentration"]["penalty"] == 6
    assert row["risk"]["paid_promotion"]["penalty"] == 5
    assert "HOLDER_CONCENTRATION_RISK" in row["risk_reasons"]
    assert "VERIFIED_PAID_PROMOTION" in row["risk_reasons"]
    assert row["lanes"]["holder_growth"]["score"] == 80


def test_funding_graph_missing_is_explicit_not_invented(tmp_path: Path):
    out = base(tmp_path)
    lane = out["tokens"][0]["lanes"]["funding_cluster_independence"]
    assert lane["available"] is False
    assert lane["score"] is None
    assert "funding_cluster_independence" in out["tokens"][0]["missing_lanes"]


def test_primary_fusion_stale_fails_closed_to_empty_ranking(tmp_path: Path):
    old = datetime(2026, 9, 8, 20, 0, tzinfo=timezone.utc).isoformat()
    payload = fusion()
    payload["generated_at"] = old
    write(tmp_path, "cross-signal-fusion-v2.json", payload)
    write(tmp_path, "real-alerts.json", real())
    out = build(tmp_path, now=NOW)
    row = out["tokens"]
    assert out["system_state"] == "PRIMARY_FUSION_STALE_FAIL_CLOSED"
    assert row == []
