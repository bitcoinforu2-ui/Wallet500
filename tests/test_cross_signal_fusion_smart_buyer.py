import json

from wallet500.cross_signal_fusion_v2 import build, score_row


def candidate():
    return {
        "chain": "solana",
        "token_address": "Mint111",
        "symbol": "TEST",
        "market": {"revival_score_verified": 70},
        "adaptive_discovery": {"anomaly_score": 65},
        "families": {
            "holder_growth": {"verified": True, "metrics": {"growth_24h_pct": 3}},
            "wallet_accumulation": {
                "verified": True,
                "metrics": {
                    "first_seen_buyers_h1": 3,
                    "net_accumulating_wallets_h1": 3,
                    "wallet_buy_sell_ratio_h1": 1.5,
                },
            },
            "smart_money": {"verified": True, "positive": True},
        },
        "blockers": [],
    }


def test_smart_buyer_is_fused_into_wallet_lane_not_double_counted():
    buyer = {
        "available": True,
        "score": 88,
        "confidence": 0.9,
        "wallet_count": 4,
        "qualified_wallets": 4,
        "components": {"overlap": 100},
        "reasons": ["QUALITY_WALLET_OVERLAP_4"],
        "warnings": [],
    }
    result = score_row(candidate(), None, buyer)
    sbc = result["channels"]["smart_buyer_conviction"]
    assert sbc["available"] is True
    assert sbc["independent_fusion_weight"] == 0.0
    assert sbc["fused_into"] == "wallets"
    assert result["coverage_weight_pct"] == 80.0
    assert result["positive_family_count"] <= 4


def test_build_reads_smart_buyer_observations_and_exposes_conviction(tmp_path):
    (tmp_path / "candidate-evidence-envelope.json").write_text(
        json.dumps({"candidates": [candidate()]}),
        encoding="utf-8",
    )
    observations = {
        "network": "solana",
        "tokens": [
            {
                "token_address": "Mint111",
                "liquidity_usd": 100_000,
                "buyers": [
                    {
                        "wallet": f"W{i}",
                        "buy_usd": 5_000,
                        "sell_usd": 500,
                        "current_position_usd": 4_500,
                        "realized_pnl_30d": 12_000,
                        "win_rate_30d": 0.72,
                        "trades_30d": 50,
                        "winners_2x_30d": 8,
                        "winners_5x_30d": 2,
                        "entry_move_pct": 15,
                        "supply_pct": 1.0,
                        "is_accumulating": True,
                        "flags": ["smart_degen"],
                    }
                    for i in range(4)
                ],
            }
        ],
    }
    (tmp_path / "smart-buyer-observations.json").write_text(
        json.dumps(observations),
        encoding="utf-8",
    )

    result = build(tmp_path)
    token = result["tokens"][0]
    sbc = token["channels"]["smart_buyer_conviction"]
    assert result["version"] == 4
    assert result["counts"]["smart_buyer_available"] == 1
    assert sbc["available"] is True
    assert sbc["score"] >= 75
    assert sbc["confidence"] >= 65
    assert any(x.startswith("SMART_BUYER_CONVICTION_") for x in token["why_now"])


def test_low_confidence_single_whale_cannot_take_full_wallet_coverage():
    base = candidate()
    base["families"]["wallet_accumulation"] = {"verified": False, "metrics": {}}
    buyer = {
        "available": True,
        "score": 68,
        "confidence": 0.42,
        "wallet_count": 1,
        "qualified_wallets": 1,
        "components": {},
        "reasons": [],
        "warnings": ["SINGLE_WALLET_EVIDENCE"],
    }
    result = score_row(base, None, buyer)
    assert result["coverage_weight_pct"] == 68.4
    assert result["channels"]["wallets"]["score"] < 60
