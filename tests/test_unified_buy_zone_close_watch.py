from __future__ import annotations

import json

import scripts.cross_domain_intelligence_collector as cross
import scripts.free_intelligence_collector as free
import scripts.unified_candidate_bridge as bridge
import scripts.unified_watch_engine as engine


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _buy_entry():
    return {
        "identity_key": "ethereum:0xabc:0xpair",
        "candidate_type": "BUY_ZONE",
        "symbol": "BUYME",
        "network": "ethereum",
        "contract": "0xabc",
        "pair": "0xpair",
        "active": True,
        "priority": "HIGHEST",
        "close_watch": "HIGHEST",
        "deep_investigation": True,
        "full_intelligence": True,
        "first_buy_at": "2026-09-18T10:00:00+00:00",
        "last_buy_at": "2026-09-18T10:00:00+00:00",
        "buy_zone_price_usd": 1.25,
    }


def test_buy_registry_bridges_to_unified_watch_at_highest_priority(tmp_path, monkeypatch):
    spot = tmp_path / "spot.json"
    alpha = tmp_path / "alpha.json"
    registry = tmp_path / "registry.json"
    output = tmp_path / "dynamic.json"
    events = tmp_path / "events.json"

    _write(spot, {"candidates": []})
    _write(alpha, {"candidates": []})
    _write(registry, {"entries": {"ethereum:0xabc:0xpair": _buy_entry()}})
    _write(events, {"version": 3, "events": []})

    monkeypatch.setattr(bridge, "SPOT", spot)
    monkeypatch.setattr(bridge, "ALPHA", alpha)
    monkeypatch.setattr(bridge, "BUY_REGISTRY", registry)
    monkeypatch.setattr(bridge, "OUT", output)
    monkeypatch.setattr(bridge, "EVENTS", events)

    bridge.main()
    doc = json.loads(output.read_text())

    assert doc["counts"]["buy_zone"] == 1
    row = doc["candidates"][0]
    assert row["candidate_type"] == "BUY_ZONE"
    assert row["close_watch"] == "HIGHEST"
    assert row["deep_investigation"] is True
    assert row["full_intelligence"] is True

    monkeypatch.setattr(engine, "DYNAMIC", output)
    targets = engine.dynamic_candidates()
    assert len(targets) == 1
    assert targets[0]["dynamic_buy_candidate"] is True
    assert targets[0]["close_watch"] == "HIGHEST"
    assert targets[0]["deep_investigation"] is True


def test_free_intelligence_reads_new_buy_registry_directly(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    dynamic = tmp_path / "dynamic.json"
    registry = tmp_path / "registry.json"

    _write(cfg, {"tokens": []})
    _write(dynamic, {"candidates": []})
    _write(registry, {"entries": {"ethereum:0xabc:0xpair": _buy_entry()}})

    monkeypatch.setattr(free, "CFG", cfg)
    monkeypatch.setattr(free, "DYNAMIC", dynamic)
    monkeypatch.setattr(free, "BUY_REGISTRY", registry)

    targets = free.targets()
    assert len(targets) == 1
    assert targets[0]["symbol"] == "BUYME"
    assert targets[0]["deep_investigation"] is True


def test_cross_domain_prioritizes_buy_zone_over_research_cap(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    dynamic = tmp_path / "dynamic.json"
    static = []
    for n in range(45):
        static.append({
            "symbol": f"S{n}",
            "network": "ethereum",
            "contract": f"0x{n:040x}",
            "pair": f"0x{n+100:040x}",
        })
    _write(cfg, {"tokens": static})
    _write(dynamic, {"candidates": [_buy_entry()]})

    monkeypatch.setattr(cross, "CONFIG", cfg)
    monkeypatch.setattr(cross, "DYNAMIC", dynamic)

    targets = cross.targets()
    assert targets[0]["symbol"] == "BUYME"
    assert any(x.get("symbol") == "BUYME" for x in targets)
