import json

from wallet500.cross_signal_fusion_v2 import build, score_row


def base_row():
    return {
        "chain": "solana",
        "token_address": "mint",
        "symbol": "TEST",
        "status": "VERIFIED_WATCH",
        "discovery_tier": "ANOMALY_WATCH",
        "market": {"revival_score_verified": 75, "pair_volume_change_pct": 40, "liquidity_change_pct": 10},
        "adaptive_discovery": {"anomaly_score": 80, "velocity_score": 60, "persistence_score": 75, "late_move_risk": False},
        "families": {
            "holder_growth": {"verified": True, "metrics": {"growth_24h_pct": 2.5}},
            "wallet_accumulation": {"verified": True, "metrics": {"first_seen_buyers_h1": 6, "net_accumulating_wallets_h1": 5, "wallet_buy_sell_ratio_h1": 2.2}},
            "smart_money": {"verified": True, "positive": True},
        },
        "blockers": [],
    }


def test_multi_signal_can_be_hot_but_never_production():
    social = {"scores": {"narrative": 80, "confidence": 90, "social_momentum": 75, "kol_quality": 55, "news_catalyst": 60, "hype_manipulation_risk": 5}, "organic": {"acceleration_vs_prior_6h": 3.0}}
    out = score_row(base_row(), social)
    assert out["fusion_status"] in {"FUSION_HOT", "FUSION_WARM"}
    assert out["production_effect"] is False
    assert out["automatic_buy"] is False
    assert out["chain"] == "solana"


def test_low_confidence_news_cannot_create_false_warm_signal():
    row = base_row()
    row["families"]["holder_growth"] = {"verified": False, "metrics": {}}
    row["families"]["wallet_accumulation"] = {"verified": False, "metrics": {}}
    row["families"]["smart_money"] = {"verified": True, "positive": False}
    social = {"scores": {"narrative": 90, "confidence": 20, "social_momentum": 0, "kol_quality": 0, "news_catalyst": 90, "hype_manipulation_risk": 0}}
    out = score_row(row, social)
    assert out["fusion_status"] not in {"FUSION_HOT", "FUSION_WARM"}
    assert out["channels"]["narrative"]["score"] <= 20


def test_hard_blocker_cannot_be_overridden_by_social():
    row = base_row(); row["blockers"] = ["EXECUTION_LIQUIDITY_LT_15K"]
    social = {"scores": {"narrative": 100, "confidence": 100, "social_momentum": 100, "kol_quality": 100, "news_catalyst": 100, "hype_manipulation_risk": 0}}
    out = score_row(row, social)
    assert out["fusion_status"] == "HARD_TRUTH_BLOCKED"


def test_same_token_string_on_other_chain_never_receives_solana_social(tmp_path):
    sol = base_row()
    sol["token_address"] = "0xSame"
    evm = base_row()
    evm["chain"] = "base"
    evm["token_address"] = "0xSame"
    evm["symbol"] = "OTHER"
    for row in (sol, evm):
        row["families"]["holder_growth"] = {"verified": False, "metrics": {}}
        row["families"]["wallet_accumulation"] = {"verified": False, "metrics": {}}
        row["families"]["smart_money"] = {"verified": False, "positive": False}
        row["market"]["revival_score_verified"] = 10
        row["adaptive_discovery"]["anomaly_score"] = 10
    (tmp_path / "candidate-evidence-envelope.json").write_text(json.dumps({"candidates": [sol, evm]}), encoding="utf-8")
    (tmp_path / "social-intelligence-v2.json").write_text(json.dumps({
        "network": "solana",
        "tokens": [{
            "token_address": "0xSame",
            "scores": {"narrative": 100, "confidence": 100, "social_momentum": 100, "kol_quality": 100, "news_catalyst": 100, "hype_manipulation_risk": 0},
        }],
    }), encoding="utf-8")

    out = build(tmp_path)
    rows = {(x["chain"], x["token_address"]): x for x in out["tokens"]}
    assert rows[("solana", "0xSame")]["channels"]["narrative"]["available"] is True
    assert rows[("base", "0xSame")]["channels"]["narrative"]["available"] is False
    assert out["truth_contract"]["token_only_cross_chain_join_forbidden"] is True
