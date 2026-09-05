from wallet500.survivor_pre_wave_fusion_v6 import fusion


def test_missing_transaction_layer_does_not_become_negative_evidence():
    row = {
        "pre_high": {"score": 70},
        "acceleration": {"score": 80},
        "absorption": {"score": 75},
        "intelligence_v3": {"relative_anomaly": {"score": 60}, "failure_anti_dna": {"score": 0}},
        "model_governor_v4": {"coverage_adjusted_opportunity_score": 60},
        "wallet_transaction_intelligence_v5": {"flow": {"coverage": "INSUFFICIENT_COVERAGE"}, "wallet_flow_score": {"score": 0}},
    }
    out = fusion(row)
    assert out["verified_transaction_layer_active"] is False
    assert "BUY_SELL_USD" in out["missing_confirmation_layers"]
    assert out["production_effect"] is False
    assert out["probability"] is None


def test_verified_wallet_flow_can_confirm_research_score():
    row = {
        "pre_high": {"score": 85},
        "acceleration": {"score": 90},
        "absorption": {"score": 85},
        "buy_sell_ratio_h1": 1.5,
        "holder_delta_since_prior_hourly_snapshot": 12,
        "organic_acceleration_score": 70,
        "intelligence_v3": {"relative_anomaly": {"score": 75}, "failure_anti_dna": {"score": 0}},
        "model_governor_v4": {"coverage_adjusted_opportunity_score": 80},
        "wallet_transaction_intelligence_v5": {
            "flow": {"coverage": "VERIFIED_EXACT_PAIR_SWAPS", "net_buy_usd": 25000, "unique_buyers": 18},
            "wallet_flow_score": {"score": 80},
            "smart_money": {"coverage": "VERIFIED_WALLET_LABELS_ONLY", "smart_money_net_usd": 7000},
            "buyer_clusters": {"coverage": "VERIFIED_FEED_CLUSTER_LABELS", "independent_buyer_clusters": 4},
            "wash_risk": {"status": "LOW_SIGNAL"},
        },
    }
    out = fusion(row)
    assert out["verified_transaction_layer_active"] is True
    assert out["stage"] == "PRE_WAVE_CONFIRMED_RESEARCH"
    assert "VERIFIED_NET_CAPITAL_INFLOW" in out["reasons"]
    assert "VERIFIED_SMART_MONEY_NET_BUY" in out["reasons"]
    assert out["independent_confirmation_n"] >= 4


def test_wash_risk_suppresses_fusion_score():
    base = {
        "pre_high": {"score": 80},
        "acceleration": {"score": 80},
        "absorption": {"score": 80},
        "intelligence_v3": {"relative_anomaly": {"score": 60}, "failure_anti_dna": {"score": 0}},
        "model_governor_v4": {"coverage_adjusted_opportunity_score": 70},
        "wallet_transaction_intelligence_v5": {
            "flow": {"coverage": "VERIFIED_EXACT_PAIR_SWAPS", "net_buy_usd": 10000, "unique_buyers": 10},
            "wallet_flow_score": {"score": 70},
            "smart_money": {},
            "buyer_clusters": {},
            "wash_risk": {"status": "LOW_SIGNAL"},
        },
    }
    clean = fusion(base)
    risky = fusion({**base, "wallet_transaction_intelligence_v5": {**base["wallet_transaction_intelligence_v5"], "wash_risk": {"status": "HIGH_RISK"}}})
    assert risky["score"] < clean["score"]
    assert "WASH_RISK_SUPPRESSION" in risky["reasons"]
