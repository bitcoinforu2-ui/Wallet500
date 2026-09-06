import json
from pathlib import Path

from wallet500 import coin_intelligence_profiles as cip


def write(root: Path, name: str, payload):
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def test_profile_accumulates_independent_sources_and_negative_evidence(tmp_path):
    token = "So11111111111111111111111111111111111111112"
    write(tmp_path, "cross-source-correlation.json", {
        "updated_at": "2026-09-07T08:00:00+00:00",
        "assets": {
            f"solana:{token}": {
                "chain": "solana",
                "token": token,
                "symbol": "ABC",
                "identity_confidence": "EXACT_CHAIN_CONTRACT",
                "last_seen_any_source_at": "2026-09-07T08:00:00+00:00",
                "confirmation_tier": "DOUBLE_SOURCE_CONFIRMED",
                "source_confirmation_count": 2,
                "exchange_confirmation_count": 2,
                "sources_seen": ["kraken", "okx"],
                "exchange_sources_seen": ["kraken", "okx"],
                "evidence": [
                    {
                        "chain": "solana", "token": token, "source_owner": "kraken",
                        "source_category": "exchange", "lane": "GLOBAL_LISTING_INTELLIGENCE",
                        "event_type": "LISTING", "first_seen_at": "2026-09-07T07:00:00+00:00",
                        "last_seen_at": "2026-09-07T07:00:00+00:00",
                    },
                    {
                        "chain": "solana", "token": token, "source_owner": "okx",
                        "source_category": "exchange", "lane": "GLOBAL_LISTING_INTELLIGENCE",
                        "event_type": "LISTING", "first_seen_at": "2026-09-07T08:00:00+00:00",
                        "last_seen_at": "2026-09-07T08:00:00+00:00",
                    },
                ],
            }
        },
    })
    write(tmp_path, "holder-cluster-gate.json", {
        "updated_at": "2026-09-07T08:01:00+00:00",
        "rows": [{
            "chain": "solana", "token": token, "symbol": "ABC",
            "status": "BLOCK", "adjusted_top10_pct": 81, "risk_reasons": ["WHALE_CLUSTER_RISK"],
        }],
    })
    latest, ledger, archive, dna = cip.build(tmp_path, at="2026-09-07T08:02:00+00:00")
    p = ledger["profiles"][f"solana:{token}"]
    assert p["evidence_summary"]["distinct_source_owners"] >= 3
    assert p["evidence_summary"]["negative_events"] >= 1
    assert "kraken" in p["sources_seen"]
    assert "okx" in p["sources_seen"]
    assert p["outcome"]["label"] == "UNLABELED"
    assert dna["profiles"][f"solana:{token}"]["fingerprint"]["feature_coverage_count"] >= 2
    assert latest["automatic_trade"] is False


def test_symbol_collision_never_merges_different_contracts(tmp_path):
    a = "So11111111111111111111111111111111111111112"
    b = "11111111111111111111111111111111"
    write(tmp_path, "revival-1000-latest.json", {
        "generated_at": "2026-09-07T09:00:00+00:00",
        "coins": [
            {"chain": "solana", "token_address": a, "symbol": "SAME", "price_usd": 1, "volume_24h_usd": 10000},
            {"chain": "solana", "token_address": b, "symbol": "SAME", "price_usd": 2, "volume_24h_usd": 20000},
        ],
    })
    _, ledger, _, _ = cip.build(tmp_path, at="2026-09-07T09:01:00+00:00")
    assert f"solana:{a}" in ledger["profiles"]
    assert f"solana:{b}" in ledger["profiles"]
    assert len(ledger["profiles"]) == 2


def test_repeated_identical_snapshot_deduplicates_material_event(tmp_path):
    token = "So11111111111111111111111111111111111111112"
    payload = {
        "generated_at": "2026-09-07T10:00:00+00:00",
        "coins": [{
            "chain": "solana", "token_address": token, "symbol": "A",
            "price_usd": 1.0, "volume_24h_usd": 10000, "liquidity_usd": 50000,
        }],
    }
    write(tmp_path, "revival-1000-latest.json", payload)
    _, ledger1, archive1, _ = cip.build(tmp_path, at="2026-09-07T10:01:00+00:00")
    write(tmp_path, cip.LEDGER.name, ledger1)
    write(tmp_path, cip.ARCHIVE.name, archive1)
    _, ledger2, _, _ = cip.build(tmp_path, at="2026-09-07T10:02:00+00:00")
    p = ledger2["profiles"][f"solana:{token}"]
    assert p["stats"]["material_events"] == 1
    assert len(p["timeline"]) == 1
    assert p["timeline"][0]["seen_count"] == 2


def test_new_market_state_appends_new_event_and_preserves_old(tmp_path):
    token = "So11111111111111111111111111111111111111112"
    write(tmp_path, "revival-1000-latest.json", {
        "generated_at": "2026-09-07T11:00:00+00:00",
        "coins": [{"chain": "solana", "token_address": token, "price_usd": 1, "volume_24h_usd": 10000}],
    })
    _, ledger1, archive1, _ = cip.build(tmp_path, at="2026-09-07T11:01:00+00:00")
    write(tmp_path, cip.LEDGER.name, ledger1)
    write(tmp_path, cip.ARCHIVE.name, archive1)
    write(tmp_path, "revival-1000-latest.json", {
        "generated_at": "2026-09-07T11:05:00+00:00",
        "coins": [{"chain": "solana", "token_address": token, "price_usd": 1.4, "volume_24h_usd": 30000}],
    })
    _, ledger2, _, _ = cip.build(tmp_path, at="2026-09-07T11:06:00+00:00")
    p = ledger2["profiles"][f"solana:{token}"]
    assert p["stats"]["material_events"] == 2
    assert len(p["timeline"]) == 2
    prices = [e["facts"].get("price_usd") for e in p["timeline"]]
    assert 1.0 in prices and 1.4 in prices


def test_provisional_evm_attaches_only_when_unique_exact_chain_exists(tmp_path):
    token = "0x" + "a" * 40
    write(tmp_path, "global-listing-ledger.json", {
        "records": {
            "x": {
                "last_seen_at": "2026-09-07T12:00:00+00:00",
                "last_observation": {
                    "chain": "evm_unknown", "token": token, "source": "kraken",
                    "stage": "LISTING", "observed_at": "2026-09-07T12:00:00+00:00",
                },
            }
        }
    })
    write(tmp_path, "candidate-evidence-envelope.json", {
        "generated_at": "2026-09-07T12:01:00+00:00",
        "candidates": [{"chain": "base", "token_address": token, "status": "RESEARCH"}],
    })
    _, ledger, _, _ = cip.build(tmp_path, at="2026-09-07T12:02:00+00:00")
    assert f"base:{token}" in ledger["profiles"]
    assert f"evm_unknown:{token}" not in ledger["profiles"]
    p = ledger["profiles"][f"base:{token}"]
    assert "kraken" in p["sources_seen"]


def test_outcome_label_is_research_only_and_does_not_change_production(tmp_path):
    token = "So11111111111111111111111111111111111111112"
    write(tmp_path, "real-alert-10usd-summary.json", {
        "updated_at": "2026-09-07T13:00:00+00:00",
        "positions": [{
            "chain": "solana", "token": token, "symbol": "WIN",
            "status": "WINNER", "peak_return_pct": 250,
            "checkpoints": {"24h": {"return_pct": 120}},
        }],
    })
    latest, ledger, _, dna = cip.build(tmp_path, at="2026-09-07T13:01:00+00:00")
    p = ledger["profiles"][f"solana:{token}"]
    assert p["outcome"]["label"] == "WINNER"
    assert p["production_effect"] == "NONE_RESEARCH_PROFILE_ONLY"
    assert latest["production_change"] is False
    assert dna["automatic_trade"] is False
