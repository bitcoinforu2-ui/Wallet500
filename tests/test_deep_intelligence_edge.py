import json
from pathlib import Path

from wallet500.deep_intelligence_edge import build, _edge_band


def w(path: Path, name: str, payload):
    (path / name).write_text(json.dumps(payload), encoding="utf-8")


def candidate():
    return {
        "chain": "solana",
        "symbol": "RAY",
        "token_address": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "pair_address": "6UmmUiYoBjSrhakAobJw8BvkmJtDVxaeBtbt7rxWo1mg",
        "missing_gate": "STRONG_DECISION_LANE",
        "readiness": "6/7",
    }


def seed_minimal(tmp_path: Path):
    c = candidate()
    w(tmp_path, "six-of-seven-live-intelligence.json", {"candidate_identities": [c], "targets": []})
    for name in [
        "social-intelligence-v2.json", "social-source-scan.json", "social-organic-acceleration.json",
        "wallet-candidate-evidence.json", "revival-wallet-latest.json", "revival-holder-latest.json",
        "cex-revival-radar.json", "moonshot-future-listing-ledger.json", "moonshot-verification-ledger.json",
        "moonshot-radar.json", "revival-1000-latest.json", "liquidity-recovery-shadow.json",
        "paid-attention-watch.json", "external-signal-cohort.json",
    ]:
        w(tmp_path, name, {})
    return c


def test_edge_bands_are_attention_only():
    assert _edge_band(20) == "WAIT_FOR_MORE_EDGE"
    assert _edge_band(50) == "BUILDING_EDGE"
    assert _edge_band(70) == "HIGH_PRIORITY_EDGE"
    assert _edge_band(90) == "EXTREME_EDGE"


def test_exact_social_cex_and_moonshot_raise_edge_without_production_effect(tmp_path):
    c = seed_minimal(tmp_path)
    token, pair = c["token_address"], c["pair_address"]
    w(tmp_path, "social-source-scan.json", {"targets": [{
        "network": "solana", "token_address": token, "pair_address": pair,
        "events": [
            {"source": "x", "author": "alpha1", "attribution": "EXACT_CONTRACT", "text": f"Watching {token}"},
            {"source": "reddit", "author": "alpha2", "attribution": "EXACT_CONTRACT", "text": f"Accumulation {token}"},
        ],
    }]})
    w(tmp_path, "cex-revival-radar.json", {"alerts": [{
        "chain": "solana", "token_address": token, "pair_address": pair,
        "cex_revival_score": 55, "coherent_confirmations": 5,
    }]})
    w(tmp_path, "moonshot-future-listing-ledger.json", {"events": [{
        "chain": "solana", "token_address": token, "pair_address": pair,
        "status": "OFFICIAL_FUTURE_LISTING", "text": "future listing",
    }]})
    out = build(tmp_path)
    row = out["candidates"][0]
    assert row["edge_score"] > 0
    assert row["components"]["social_news"] > 0
    assert row["components"]["market_cex_liquidity"] > 0
    assert row["components"]["listing_promotion"] > 0
    assert row["production_effect"] is False and row["automatic_buy"] is False
    assert out["truth_contract"]["edge_score_never_bypasses_hard_gates"] is True


def test_symbol_only_noise_does_not_create_exact_social_edge(tmp_path):
    c = seed_minimal(tmp_path)
    w(tmp_path, "social-source-scan.json", {"targets": [{
        "network": "solana", "token_address": c["token_address"], "pair_address": c["pair_address"],
        "events": [{"source": "x", "author": "random", "attribution": "NAME_SYMBOL_CONTEXT", "text": "RAY to the moon"}],
    }]})
    out = build(tmp_path)
    row = out["candidates"][0]
    assert row["components"]["social_news"] == 0


def test_negative_intelligence_reduces_edge(tmp_path):
    c = seed_minimal(tmp_path)
    token, pair = c["token_address"], c["pair_address"]
    w(tmp_path, "cex-revival-radar.json", {"alerts": [{"chain": "solana", "token_address": token, "pair_address": pair, "cex_revival_score": 60, "coherent_confirmations": 6}]})
    baseline = build(tmp_path)["candidates"][0]["edge_score"]
    w(tmp_path, "external-signal-cohort.json", {"rows": [{"chain": "solana", "token_address": token, "pair_address": pair, "text": "exploit investigation and scam warning"}]})
    reduced = build(tmp_path)["candidates"][0]
    assert reduced["edge_score"] < baseline
    assert reduced["components"]["negative_intelligence_penalty"] > 0


def test_micro_event_ledger_is_deduplicated_across_runs(tmp_path):
    c = seed_minimal(tmp_path)
    token, pair = c["token_address"], c["pair_address"]
    event = {"source": "x", "author": "alpha", "attribution": "EXACT_CONTRACT", "text": token, "id": "same-event"}
    w(tmp_path, "social-source-scan.json", {"targets": [{"network": "solana", "token_address": token, "pair_address": pair, "events": [event]}]})
    first = build(tmp_path)
    second = build(tmp_path)
    ledger = json.loads((tmp_path / "deep-intelligence-event-ledger.json").read_text())
    assert first["new_micro_events"] >= 1
    assert second["new_micro_events"] == 0
    assert ledger["events_count"] >= 1
