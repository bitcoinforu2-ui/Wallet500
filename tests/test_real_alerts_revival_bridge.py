import json
from pathlib import Path

from wallet500.real_alerts import build


TOKEN = "Mint111111111111111111111111111111111111111"
PAIR = "Pair111111111111111111111111111111111111111"


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def seed_empty(root: Path):
    write(root, "cex-revival-radar.json", {"alerts": []})
    write(root, "revival-precursor-latest.json", {"targets": []})
    write(root, "waking-confirmation-latest.json", {"targets": []})
    write(root, "active-qualified-candidates.json", [])


def revival_row():
    return {
        "network": "solana",
        "network_verified": True,
        "token_address": TOKEN,
        "symbol": "OLD",
        "dex_pair_address": PAIR,
        "dex_link": "https://dexscreener.com/solana/" + PAIR,
        "dex_link_type": "DEXSCREENER_VERIFIED_PAIR",
        "dex_pair_liquidity_usd": 120000,
        "price_usd": 0.12,
        "market_age_verified": True,
        "market_age_min_days": 900,
        "watch_status": "WAKING_MARKET_ONLY",
        "revival_score_verified": 70,
    }


def test_revival_dex_pair_fields_feed_verified_watch(tmp_path):
    seed_empty(tmp_path)
    write(tmp_path, "revival-1000-latest.json", {"coins": [revival_row()]})
    write(tmp_path, "candidate-evidence-envelope.json", {"candidates": []})
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert result["counts"]["verified_watch_not_real"] == 1
    row = result["verified_watch"][0]
    assert row["pair_address"] == PAIR
    assert row["execution_pool_liquidity_usd"] == 120000
    assert row["liquidity_truth_source"] == "LEGACY_EXACT_PAIR:dex_pair_liquidity_usd"
    assert "REVIVAL_MARKET_STRUCTURE" in row["source_lanes"]
    assert "NO_STRONG_DECISION_LANE" in row["blockers"]


def test_evidence_ready_is_visible_but_does_not_auto_become_real_alert(tmp_path):
    seed_empty(tmp_path)
    write(tmp_path, "revival-1000-latest.json", {"coins": [revival_row()]})
    write(tmp_path, "candidate-evidence-envelope.json", {
        "candidates": [{
            "chain": "solana",
            "network": "solana",
            "token_address": TOKEN,
            "symbol": "OLD",
            "pair_address": PAIR,
            "dex_url": "https://dexscreener.com/solana/" + PAIR,
            "status": "EVIDENCE_READY",
            "production_effect": False,
            "truth": {
                "exact_identity_verified": True,
                "exact_pair_verified": True,
                "market_age_verified_180d_plus": True,
                "market_age_days": 900,
                "execution_pool_liquidity_usd": 120000,
            },
            "market": {"revival_score_verified": 70, "price_usd": 0.12},
            "coverage": {
                "positive_independent_lanes": ["WALLET_ACCUMULATION"],
                "verified_independent_lanes": ["WALLET_ACCUMULATION"],
            },
        }],
    })
    result = build(tmp_path)
    assert result["counts"]["real_alerts"] == 0
    assert result["counts"]["evidence_ready_research"] == 1
    row = result["verified_watch"][0]
    assert row["status"] == "EVIDENCE_READY_NOT_REAL_ALERT"
    assert row["evidence_ready"] is True
    assert row["evidence_positive_lanes"] == ["WALLET_ACCUMULATION"]
