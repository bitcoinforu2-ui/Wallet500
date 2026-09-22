from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import free_intelligence_collector as free_intel
import spot_cex_fast_handoff as handoff


def test_same_run_recovered_primary_cex_identity_enters_free_intelligence(tmp_path, monkeypatch):
    cfg = tmp_path / "unified-watch-config.json"
    dyn = tmp_path / "unified-dynamic-candidates.json"
    spot = tmp_path / "spot-market-discovery.json"
    bootstrap = tmp_path / "new-chain-bootstrap-radar.json"
    registry = tmp_path / "buy-zone-close-watch-registry.json"

    cfg.write_text(json.dumps({"tokens": []}))
    spot.write_text(json.dumps({"resolved_candidates": []}))
    bootstrap.write_text(json.dumps({"candidates": []}))
    registry.write_text(json.dumps({"entries": {}}))

    primary = {
        "candidate_type": "CEX_SPOT_DISCOVERY",
        "symbol": "AURORAUSDT",
        "network": "ethereum",
        "contract": "0xaaaaaa20d9e0e2461697782ef11675f668207961",
        "pair": "0x629d22e6eeac46a11dbc96be93b90aee9309be4c",
        "asset_pool_role": "PRIMARY",
        "asset_pool_rank": 1,
        "positive_gainer_rank": 1,
        "change_24h_pct": 180,
        "quote_volume_24h_usd": 1_900_000,
        "dex_liquidity_usd": 440_000,
    }
    sibling = {
        **primary,
        "pair": "0x41cddf3043144c6e360f2b43fe6a0420c1b8ee9f81987c2747434a11b57f7e98",
        "asset_pool_role": "SIBLING",
        "asset_pool_rank": 2,
        "dex_liquidity_usd": 12_000,
    }
    dyn.write_text(json.dumps({"candidates": [primary, sibling]}))

    monkeypatch.setattr(free_intel, "CFG", cfg)
    monkeypatch.setattr(free_intel, "DYNAMIC", dyn)
    monkeypatch.setattr(free_intel, "SPOT", spot)
    monkeypatch.setattr(free_intel, "BOOTSTRAP", bootstrap)
    monkeypatch.setattr(free_intel, "BUY_REGISTRY", registry)
    monkeypatch.setenv("WALLET500_CRITICAL_FREE_INTEL_HOT_CAP", "12")

    rows = free_intel.targets()
    assert len(rows) == 1
    assert rows[0]["pair"].lower() == primary["pair"].lower()
    assert rows[0]["asset_pool_role"] == "PRIMARY"


def test_cex_execution_evidence_is_fresh_bounded_and_exact_identity_only():
    target = {
        "symbol": "AURORAUSDT",
        "network": "ethereum",
        "contract": "0xaaaaaa20d9e0e2461697782ef11675f668207961",
        "pair": "0x629d22e6eeac46a11dbc96be93b90aee9309be4c",
        "exchange": "gate",
    }
    current = {
        **target,
        "identity_key": (
            "ethereum:0xaaaaaa20d9e0e2461697782ef11675f668207961:"
            "0x629d22e6eeac46a11dbc96be93b90aee9309be4c"
        ),
        "observed_at": "2026-09-22T10:29:45+00:00",
        "cex_execution_verified": True,
        "cex_market_price_spread_pct": 0.85,
        "cex_depth_1pct_usd": 3279.12,
        "cex_orderbook_spread_pct": 0.117,
        "cex_bid_ask_depth_ratio": 6.03,
    }
    sensor = {
        "baseline_multiple": 16.9,
        "current_rank": 1,
        "current_volume_usd": 1_984_779,
    }

    events = handoff._cex_execution_events(target, current, sensor)
    assert {e["kind"] for e in events} == {
        "cex_relative_volume_execution",
        "cex_orderbook_bid_depth_imbalance",
    }
    assert all(e["identity_verified"] is True for e in events)
    assert all(e["family"] == "market_microstructure" for e in events)

    incoherent = dict(current, cex_market_price_spread_pct=3.1)
    assert handoff._cex_execution_events(target, incoherent, sensor) == []

    cex_only = dict(current, identity_key="cex:gate:AURORA_USDT")
    assert handoff._cex_execution_events(target, cex_only, sensor) == []
