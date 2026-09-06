import json
from pathlib import Path

from wallet500.evidence_ready_visibility import repair


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def ready(symbol: str, token: str, pair: str) -> dict:
    return {
        "key": f"solana:{token}:{pair}",
        "chain": "solana",
        "token_address": token,
        "symbol": symbol,
        "pair_address": pair,
        "dex_url": f"https://dexscreener.com/solana/{pair}",
        "status": "EVIDENCE_READY",
        "production_effect": False,
        "automatic_buy": False,
        "mintability_verified": True,
        "mintable": False,
        "mint_authority": None,
        "truth": {
            "exact_identity_verified": True,
            "exact_pair_verified": True,
            "market_age_verified_180d_plus": True,
            "market_age_days": 500,
            "execution_pool_liquidity_usd": 120000,
            "execution_liquidity_floor_passed": True,
        },
        "market": {"price_usd": 0.02},
        "coverage": {
            "verified_independent_lanes": ["CEX_REVIVAL"],
            "positive_independent_lanes": ["CEX_REVIVAL"],
            "verified_independent_count": 1,
            "positive_independent_count": 1,
        },
    }


def test_repair_materializes_ready_rows_missing_from_display_capped_watch(tmp_path: Path):
    candidates = [
        ready("AAA", "mintA11111111111111111111111111111111111", "pairA11111111111111111111111111111111111"),
        ready("BBB", "mintB11111111111111111111111111111111111", "pairB11111111111111111111111111111111111"),
    ]
    write(tmp_path / "candidate-evidence-envelope.json", {"candidates": candidates})
    write(tmp_path / "real-alerts.json", {"counts": {"evidence_ready_research": 2}, "verified_watch": [], "dormant_no_activity": []})

    result = repair(tmp_path)
    real = json.loads((tmp_path / "real-alerts.json").read_text())

    assert result["canonical_count"] == 2
    assert result["materialized_missing_this_run"] == 2
    assert len(real["evidence_ready"]) == 2
    assert real["counts"]["evidence_ready_research"] == 2
    assert all(x["actionable_research_alert"] is False for x in real["evidence_ready"])
    assert all(x["automatic_buy"] is False for x in real["evidence_ready"])


def test_repair_does_not_duplicate_ready_row_already_visible_elsewhere(tmp_path: Path):
    row = ready("AAA", "mintA11111111111111111111111111111111111", "pairA11111111111111111111111111111111111")
    write(tmp_path / "candidate-evidence-envelope.json", {"candidates": [row]})
    visible = {
        "chain": "solana",
        "token_address": row["token_address"],
        "pair_address": row["pair_address"],
        "evidence_ready": True,
        "status": "EVIDENCE_READY_NOT_REAL_ALERT",
    }
    write(tmp_path / "real-alerts.json", {"counts": {}, "verified_watch": [visible], "evidence_ready": [], "dormant_no_activity": []})

    result = repair(tmp_path)
    real = json.loads((tmp_path / "real-alerts.json").read_text())

    assert result["materialized_missing_this_run"] == 0
    assert real["evidence_ready"] == []
    assert real["counts"]["evidence_ready_research"] == 1


def test_repair_removes_stale_dedicated_rows_not_in_canonical_envelope(tmp_path: Path):
    write(tmp_path / "candidate-evidence-envelope.json", {"candidates": []})
    stale = {
        "chain": "solana", "token_address": "oldmint", "pair_address": "oldpair",
        "evidence_ready": True, "status": "EVIDENCE_READY_NOT_REAL_ALERT",
    }
    write(tmp_path / "real-alerts.json", {"counts": {"evidence_ready_research": 1}, "evidence_ready": [stale]})

    repair(tmp_path)
    real = json.loads((tmp_path / "real-alerts.json").read_text())
    assert real["evidence_ready"] == []
    assert real["counts"]["evidence_ready_research"] == 0
