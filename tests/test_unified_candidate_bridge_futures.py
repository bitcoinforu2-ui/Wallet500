import json

from scripts import unified_candidate_bridge as bridge


def dump(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_futures_only_exact_identity_enters_unified_watch(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in [
        "spot.json", "futures.json", "cex.json", "alpha.json", "kol.json",
        "buy.json", "bootstrap.json", "events.json", "out.json"
    ]}
    monkeypatch.setattr(bridge, "SPOT", paths["spot.json"])
    monkeypatch.setattr(bridge, "FUTURES", paths["futures.json"])
    monkeypatch.setattr(bridge, "CEX_SPOT_IDENTITY", paths["cex.json"])
    monkeypatch.setattr(bridge, "ALPHA", paths["alpha.json"])
    monkeypatch.setattr(bridge, "KOL", paths["kol.json"])
    monkeypatch.setattr(bridge, "BUY_REGISTRY", paths["buy.json"])
    monkeypatch.setattr(bridge, "BOOTSTRAP", paths["bootstrap.json"])
    monkeypatch.setattr(bridge, "EVENTS", paths["events.json"])
    monkeypatch.setattr(bridge, "OUT", paths["out.json"])

    dump(paths["spot.json"], {"candidates": []})
    dump(paths["futures.json"], {"candidates": [{
        "status": "IDENTITY_RESOLVED",
        "identity_status": "RESOLVED_EXACT",
        "identity_reason": "EXACT_CHAIN_CONTRACT_PAIR",
        "symbol": "FAST",
        "network": "solana",
        "contract": "TokenFast",
        "pair": "PairFast",
        "dex_url": "https://dex.example/fast",
        "dex_liquidity_usd": 120000,
        "first_seen_at": "2026-10-06T10:00:00+00:00",
        "first_seen_price": 1.0,
        "first_seen_change_24h_pct": 6.0,
        "first_seen_quote_volume_24h_usd": 50000,
        "discovery_price": 1.18,
        "change_24h_pct": 18.0,
        "discovery_momentum_change_pct": 18.0,
        "gain_from_first_seen_pct": 18.0,
        "quote_volume_24h_usd": 300000,
        "positive_gainer_rank": 4,
        "futures_contract": "FAST_USDT",
        "futures_volume_baseline_multiple": 6.0,
        "futures_volume_scan_multiple": 2.7,
        "futures_total_size_change_pct": 21.0,
        "futures_funding_rate_pct": 0.01,
        "futures_discovery_reasons": ["FUTURES_TOP20_EARLY_MOVER"],
    }]})
    dump(paths["cex.json"], {"candidates": []})
    dump(paths["alpha.json"], {"candidates": []})
    dump(paths["kol.json"], {"candidates": []})
    dump(paths["buy.json"], {"entries": {}})
    dump(paths["bootstrap.json"], {"candidates": []})
    dump(paths["events.json"], {"version": 3, "events": []})

    bridge.main()
    doc = json.loads(paths["out.json"].read_text())
    rows = [x for x in doc["candidates"] if x.get("symbol") == "FAST"]
    assert len(rows) == 1
    row = rows[0]
    assert row["candidate_type"] == "GATE_SPOT_DISCOVERY"
    assert row["futures_early_radar"] is True
    assert row["futures_only_origin"] is True
    assert row["derivatives_intelligence"] is True
    assert row["execution_identity_scope"] == "EXACT_CHAIN_CONTRACT_PAIR_WITH_FUTURES_TRIGGER"
    assert doc["counts"]["futures_radar_only_exact"] == 1
