from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unified_watch_engine as engine


def test_genesis_prebreakout_is_bounded_critical_dynamic_lane(tmp_path, monkeypatch):
    path = tmp_path / "dynamic.json"
    path.write_text(
        json.dumps({
            "candidates": [{
                "candidate_type": "GENESIS_PREBREAKOUT",
                "symbol": "GEN",
                "network": "solana",
                "contract": "GenesisMint111111111111111111111111111111",
                "pair": "GenesisPair111111111111111111111111111111",
                "dex_url": "https://dexscreener.com/solana/GenesisPair",
                "dex_liquidity_usd": 90000,
                "genesis_final_buy_lane": True,
                "genesis_score": 71,
                "prebreakout_score": 82,
                "prebreakout_coverage_pct": 66,
                "prebreakout_signals": [
                    "PRESSURE_BEFORE_PRICE_EXTENSION",
                    "LIQUIDITY_COMMITMENT",
                ],
                "deep_investigation": True,
                "full_intelligence": True,
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(engine, "DYNAMIC", path)
    rows = engine.dynamic_candidates({})
    assert len(rows) == 1
    row = rows[0]
    assert row["candidate_type"] == "GENESIS_PREBREAKOUT"
    assert row["dynamic_genesis_candidate"] is True
    assert row["critical_market_lane"] is True
    assert row["deep_investigation"] is True
    assert row["full_intelligence"] is True
    assert row["genesis_final_buy_lane"] is True
    assert row["prebreakout_score"] == 82


def test_genesis_lane_is_capped_by_prebreakout_strength(tmp_path, monkeypatch):
    path = tmp_path / "dynamic.json"
    candidates = []
    for i in range(14):
        candidates.append({
            "candidate_type": "GENESIS_PREBREAKOUT",
            "symbol": f"G{i}",
            "network": "solana",
            "contract": f"GenesisMint{i:02d}",
            "pair": f"GenesisPair{i:02d}",
            "dex_liquidity_usd": 20000 + i,
            "genesis_final_buy_lane": True,
            "prebreakout_score": 60 + i,
        })
    path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    monkeypatch.setattr(engine, "DYNAMIC", path)
    rows = [x for x in engine.dynamic_candidates({}) if x["candidate_type"] == "GENESIS_PREBREAKOUT"]
    assert len(rows) == 10
    scores = sorted((x["prebreakout_score"] for x in rows), reverse=True)
    assert scores == list(range(73, 63, -1))
