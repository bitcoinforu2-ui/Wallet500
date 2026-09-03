from wallet500.holder_concentration_shadow import sanitize_distribution, select_candidates

TOKEN_A = "11111111111111111111111111111111"
TOKEN_B = "22222222222222222222222222222222"
TOKEN_C = "33333333333333333333333333333333"
PAIR_A = "44444444444444444444444444444444"
PAIR_B = "55555555555555555555555555555555"
PAIR_C = "66666666666666666666666666666666"


def profile(token, pair, status, volume, score):
    return {
        "network": "solana",
        "token_address": token,
        "status": status,
        "hybrid_score_raw": score * 0.55,
        "hybrid_score_verified_normalized": score,
        "identity": {"exact_pair_verified": True, "dex_pair_address": pair},
        "promotion_gates": {
            "min_ignition_volume_24h_usd": 10_000,
            "volume_24h_usd": volume,
            "absolute_volume_ready": volume >= 10_000,
        },
        "market_context": {"volume_24h_usd": volume},
    }


def test_priority_prefers_ignition_then_abnormal_when_volume_gate_passes():
    rows = [
        profile(TOKEN_C, PAIR_C, "NORMAL", 100_000, 95),
        profile(TOKEN_B, PAIR_B, "ABNORMAL_ACTIVITY", 20_000, 70),
        profile(TOKEN_A, PAIR_A, "HYBRID_IGNITION", 15_000, 72),
    ]
    out = select_candidates(rows, 3)
    assert [x["token_address"] for x in out] == [TOKEN_A, TOKEN_B, TOKEN_C]
    assert out[0]["priority_reason"] == "HYBRID_IGNITION_VOLUME_GATE_PASS"
    assert out[1]["priority_reason"] == "ABNORMAL_ACTIVITY_VOLUME_GATE_PASS"


def test_ignition_below_10k_does_not_get_ignition_priority():
    rows = [profile(TOKEN_A, PAIR_A, "HYBRID_IGNITION", 9_999, 99)]
    out = select_candidates(rows, 1)
    assert out[0]["priority_reason"] == "ROTATION_RESEARCH"


def test_distribution_is_risk_only_and_keeps_token_account_semantics():
    dist = {
        "verified": True,
        "contract_match": True,
        "source": "RUGCHECK_EXACT_MINT_TOP_TOKEN_ACCOUNTS",
        "observed_at": "2026-09-04T00:00:00+00:00",
        "risk_score": 35,
        "signals": ["TOP1_TOKEN_ACCOUNT_GE_20PCT"],
        "metrics": {
            "top_holder_rows": 20,
            "top1_pct": 23.0,
            "top5_pct": 39.0,
            "top10_pct": 51.0,
            "top20_pct": 63.0,
        },
        "limitations": ["LP/burn/infrastructure exclusions are not independently verified here"],
    }
    out = sanitize_distribution(dist)
    assert out["verified"] is True
    assert out["top10_pct"] == 51.0
    assert out["positive_signal_eligible"] is False
    assert out["hybrid_score_impact"] == "NONE"
    assert out["semantics"] == "TOP_TOKEN_ACCOUNT_CONCENTRATION_NOT_OWNER_CLUSTER_CONCENTRATION"


def test_distribution_rejects_unverified_or_wrong_source():
    assert sanitize_distribution({"verified": False, "contract_match": True}) is None
    assert sanitize_distribution({"verified": True, "contract_match": True, "source": "OTHER", "metrics": {"top1_pct": 1, "top10_pct": 2}}) is None
