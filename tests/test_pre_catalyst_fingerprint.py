import json
from pathlib import Path

from wallet500.pre_catalyst_fingerprint import build


def w(path: Path, name: str, payload):
    (path / name).write_text(json.dumps(payload), encoding="utf-8")


def test_sequence_is_ordered_compressed_and_forward_only(tmp_path):
    token = "Mint111111111111111111111111111111111111111"
    pair = "Pair111111111111111111111111111111111111111"
    w(tmp_path, "deep-intelligence-edge.json", {"candidates": [{
        "chain": "solana", "symbol": "OLD", "token_address": token, "pair_address": pair,
        "edge_score": 72, "edge_band": "HIGH_PRIORITY_EDGE",
    }]})
    w(tmp_path, "deep-intelligence-event-ledger.json", {"events": [
        {"chain": "solana", "token_address": token, "pair_address": pair, "category": "WALLET_HOLDER", "observed_at": "2026-09-10T10:00:00+00:00"},
        {"chain": "solana", "token_address": token, "pair_address": pair, "category": "WALLET_HOLDER", "observed_at": "2026-09-10T10:01:00+00:00"},
        {"chain": "solana", "token_address": token, "pair_address": pair, "category": "SOCIAL_EXACT", "observed_at": "2026-09-10T10:02:00+00:00", "source": "x"},
        {"chain": "solana", "token_address": token, "pair_address": pair, "category": "CEX_REVIVAL", "observed_at": "2026-09-10T10:03:00+00:00"},
    ]})
    out = build(tmp_path)
    row = out["fingerprints"][0]
    assert row["sequence"] == ["WALLET_HOLDER", "SOCIAL_EXACT", "CEX_REVIVAL"]
    assert row["transitions"] == ["WALLET_HOLDER>SOCIAL_EXACT", "SOCIAL_EXACT>CEX_REVIVAL"]
    assert row["forward_outcome"] == "PENDING"
    assert out["truth_contract"]["forward_only"] is True
    assert out["truth_contract"]["production_effect"] is False


def test_registry_persists_same_fingerprint_without_duplicate_token(tmp_path):
    token = "Mint111111111111111111111111111111111111111"
    pair = "Pair111111111111111111111111111111111111111"
    w(tmp_path, "deep-intelligence-edge.json", {"candidates": [{"chain": "solana", "symbol": "OLD", "token_address": token, "pair_address": pair, "edge_score": 50}]})
    w(tmp_path, "deep-intelligence-event-ledger.json", {"events": [{"chain": "solana", "token_address": token, "pair_address": pair, "category": "SOCIAL_EXACT", "observed_at": "2026-09-10T10:00:00+00:00"}]})
    first = build(tmp_path)
    second = build(tmp_path)
    fp = first["fingerprints"][0]["fingerprint"]
    reg = json.loads((tmp_path / "pre-catalyst-fingerprint-registry.json").read_text())
    assert second["fingerprints"][0]["fingerprint"] == fp
    assert reg["fingerprints"][fp]["observation_count"] == 1
