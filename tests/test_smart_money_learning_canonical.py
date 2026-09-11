import json
from pathlib import Path

from wallet500.smart_money_learning import build, patch_review


def put(root: Path, name: str, payload: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def registry_payload():
    return {
        "version": "REVIVAL_WALLET_REGISTRY_V1",
        "mode": "RESEARCH_ONLY_TIME_SAFE_SMART_MONEY_REGISTRY",
        "network": "solana",
        "generated_at": "2026-09-11T13:00:00+00:00",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "truth_contract": {
            "wallet_identity": "SIGNED_TARGET_TOKEN_OWNER_DELTA_ONLY",
            "pair_identity": "EXACT_PAIR_ONLY",
            "tier_input": "COMPLETED_PRE_WAKING_VERIFIED_BUY_EXPOSURES_ONLY",
            "as_of_t0_guard": True,
            "raw_overlap_never_implies_smart_money": True,
        },
        "counts": {
            "wallets_registry": 25720,
            "cross_token_wallets": 2615,
            "completed_eligible_exposures": 17702,
            "elite": 0,
            "strong": 0,
            "watch": 91,
            "pending_history": 25629,
        },
        "wallets": [
            {
                "wallet": "A",
                "tier_current": {"tier": "PENDING_HISTORY", "reason": "MINIMUM_COMPLETED_PREWAKING_BUY_HISTORY_NOT_MET", "completed_pre_waking_buy_exposures": 4, "distinct_completed_tokens": 2},
                "observed_distinct_tokens": 5,
                "verified_buys": 9,
                "verified_events": 12,
            },
            {
                "wallet": "B",
                "tier_current": {"tier": "PENDING_HISTORY", "reason": "MINIMUM_COMPLETED_PREWAKING_BUY_HISTORY_NOT_MET", "completed_pre_waking_buy_exposures": 2, "distinct_completed_tokens": 1},
                "observed_distinct_tokens": 3,
                "verified_buys": 5,
                "verified_events": 7,
            },
            {
                "wallet": "C",
                "tier_current": {"tier": "WATCH", "reason": "MINIMUM_HISTORY_MET_BELOW_STRONG_THRESHOLDS", "completed_pre_waking_buy_exposures": 7, "distinct_completed_tokens": 3},
                "observed_distinct_tokens": 4,
                "verified_buys": 10,
                "verified_events": 20,
            },
        ],
    }


def test_uses_canonical_counts_not_500_row_denominator(tmp_path):
    put(tmp_path, "revival-wallet-registry.json", registry_payload())
    out = build(tmp_path)
    assert out["canonical_counts"]["wallets_registry"] == 25720
    assert out["canonical_counts"]["pending_history"] == 25629
    assert out["detailed_rows_published"] == 3
    assert out["qualification_queue"][0]["wallet"] == "A"
    assert out["qualification_queue"][0]["promotion_forbidden"] is True
    assert out["truth_contract"]["queue_is_ordering_only"] is True


def test_patches_engine_review_without_changing_truth(tmp_path):
    put(tmp_path, "revival-wallet-registry.json", registry_payload())
    put(tmp_path, "engine-learning-review.json", {"version": "WALLET500_ENGINE_LEARNING_REVIEW_V1", "no_hindsight": True, "production_effect": False, "automatic_buy": False})
    result = patch_review(tmp_path)
    review = json.loads((tmp_path / "engine-learning-review.json").read_text())
    assert review["production_effect"] is False
    assert review["no_hindsight"] is True
    assert review["smart_money_quality"]["source_file"] == "revival-wallet-registry.json"
    assert result["threshold_change_allowed"] is False
