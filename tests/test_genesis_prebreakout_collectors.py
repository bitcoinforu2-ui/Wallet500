from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cross_domain_intelligence_collector as cross
import free_intelligence_collector as free


def _genesis_candidate():
    return {
        "candidate_type": "GENESIS_PREBREAKOUT",
        "symbol": "GEN",
        "network": "solana",
        "contract": "GenesisMint111111111111111111111111111111",
        "pair": "GenesisPair111111111111111111111111111111",
        "genesis_final_buy_lane": True,
        "prebreakout_score": 82,
        "dex_liquidity_usd": 90000,
    }


def test_genesis_candidate_gets_same_run_free_intelligence(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    dyn = tmp_path / "unified-dynamic-candidates.json"
    spot = tmp_path / "spot-market-discovery.json"
    registry = tmp_path / "buy-zone-close-watch-registry.json"
    bootstrap = tmp_path / "new-chain-bootstrap-radar.json"
    cfg.write_text('{"tokens":[]}', encoding="utf-8")
    dyn.write_text(json.dumps({"candidates": [_genesis_candidate()]}), encoding="utf-8")
    spot.write_text('{"resolved_candidates":[]}', encoding="utf-8")
    registry.write_text('{"entries":{}}', encoding="utf-8")
    bootstrap.write_text('{"candidates":[]}', encoding="utf-8")

    monkeypatch.setattr(free, "CFG", cfg)
    monkeypatch.setattr(free, "DYNAMIC", dyn)
    monkeypatch.setattr(free, "SPOT", spot)
    monkeypatch.setattr(free, "BUY_REGISTRY", registry)
    monkeypatch.setattr(free, "BOOTSTRAP", bootstrap)

    rows = free.targets()
    assert len(rows) == 1
    assert rows[0]["candidate_type"] == "GENESIS_PREBREAKOUT"


def test_genesis_candidate_is_protected_in_cross_domain_priority(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    dyn = tmp_path / "dynamic.json"
    cfg.write_text('{"tokens":[]}', encoding="utf-8")
    dyn.write_text(json.dumps({"candidates": [_genesis_candidate()]}), encoding="utf-8")
    monkeypatch.setattr(cross, "CONFIG", cfg)
    monkeypatch.setattr(cross, "DYNAMIC", dyn)

    rows = cross.targets()
    assert len(rows) == 1
    assert rows[0]["candidate_type"] == "GENESIS_PREBREAKOUT"
