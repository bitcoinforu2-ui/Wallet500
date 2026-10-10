"""Regression checks for bounded background collectors.

The BUY authority is not in these collectors: failed/missing snapshots must never
advance immutable KOL signatures or fabricate fresh holder evidence.
"""
import json

from scripts import early_kol_convergence as kol
from scripts import cross_domain_intelligence_collector as cross


def test_early_kol_timeout_keeps_unprocessed_wallet_boundary(tmp_path, monkeypatch):
    config = tmp_path / "wallets.json"
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"
    candidates = tmp_path / "candidates.json"
    config.write_text(json.dumps({
        "wallets": [{"id": "a", "address": "WalletA", "enabled": True},
                    {"id": "b", "address": "WalletB", "enabled": True}],
        "wallet_delay_seconds": 0.001,
    }))
    state.write_text(json.dumps({
        "wallet_boundaries": {"a": "old_a", "b": "old_b"}, "events": [],
    }))
    monkeypatch.setattr(kol, "CONFIG", config)
    monkeypatch.setattr(kol, "STATE", state)
    monkeypatch.setattr(kol, "REPORT", report)
    monkeypatch.setattr(kol, "CANDIDATES", candidates)
    monkeypatch.setattr(kol, "recent_signatures", lambda rpc, address, limit: [
        {"signature": "new_" + address}
    ])
    monkeypatch.setattr(kol, "transaction", lambda *args: None)
    ticks = iter([0.0, 0.1, 90.0])
    monkeypatch.setattr(kol.time, "monotonic", lambda: next(ticks, 90.0))
    assert kol.main() == 0
    saved = json.loads(state.read_text())
    summary = json.loads(report.read_text())
    assert saved["wallet_boundaries"] == {"a": "old_a", "b": "old_b"}
    assert saved["next_wallet_offset"] == 0
    assert saved["scan_partial"] is True
    assert summary["wallets_attempted"] == 1
    assert json.loads(candidates.read_text())["candidates"] == []


def test_cross_domain_holder_poll_is_fair_and_preserves_unpolled_baselines(tmp_path, monkeypatch):
    state = tmp_path / "cross.json"
    events = tmp_path / "events.json"
    monkeypatch.setattr(cross, "STATE", state)
    monkeypatch.setattr(cross, "EVENTS", events)
    sample = [
        {"network": "base", "contract": "0x" + f"{i+1:040x}",
         "pair": "0x" + f"{i+100:040x}", "symbol": f"T{i}"}
        for i in range(28)
    ]
    monkeypatch.setattr(cross, "targets", lambda: sample)
    monkeypatch.setattr(cross, "global_attention_maps", lambda rows: ({}, {}))
    monkeypatch.setattr(cross, "news_snapshot", lambda row: None)
    collected = []
    def fake_holder(row):
        collected.append(row["symbol"])
        return {"provider": "TEST", "holders_count": 100}
    monkeypatch.setattr(cross, "holder_snapshot", fake_holder)
    cross.main()
    first = set(collected)
    first_state = json.loads(state.read_text())
    assert len(first) == 16
    assert first_state["holder_poll_deferred"] == 12
    assert first_state["holder_rotation_cursor"] == 8
    collected.clear()
    cross.main()
    second = set(collected)
    assert len(second) == 16
    assert first | second >= {row["symbol"] for row in sample[:24]}
    second_state = json.loads(state.read_text())
    # T8 was polled on the first run but not the second: retain the genuine
    # holder snapshot instead of overwriting it with a fake current null.
    assert second_state["tokens"][cross.ident(sample[8])[3]]["holder"]["holders_count"] == 100
    assert second_state["holder_rotation_cursor"] == 16


def test_critical_lane_reserves_pre_wave_volume_shocks_without_buy_promotion(tmp_path, monkeypatch):
    from scripts import unified_watch_engine as engine

    rows = []
    for i in range(24):
        rows.append({
            "candidate_type": "CEX_MARKET_DISCOVERY",
            "symbol": f"HOT{i}",
            "exchange": "gate",
            "currency_pair": f"HOT{i}_USDT",
            "gain_from_first_seen_pct": 80 - i,
            "discovery_momentum_change_pct": 65 - i,
            "quote_volume_24h_usd": 1_000_000,
            "positive_gainer_rank": i + 1,
        })
    for i in range(4):
        rows.append({
            "candidate_type": "CEX_MARKET_DISCOVERY",
            "symbol": f"EARLY{i}",
            "exchange": "gate",
            "currency_pair": f"EARLY{i}_USDT",
            "gain_from_first_seen_pct": 6.0,
            "discovery_momentum_change_pct": 9.0,
            "cex_relative_volume_multiple": 8.0 + i,
            "quote_volume_24h_usd": 150_000,
            "positive_gainer_rank": 40 + i,
        })
    dynamic = tmp_path / "dynamic.json"
    dynamic.write_text(json.dumps({"candidates": rows}))
    monkeypatch.setattr(engine, "DYNAMIC", dynamic)
    monkeypatch.delenv("WALLET500_CRITICAL_SPOT_CAP", raising=False)
    selected = engine.dynamic_candidates({})
    critical = [x for x in selected if x.get("critical_market_lane") is True]
    assert len(critical) == 18
    assert {f"EARLY{i}" for i in range(4)}.issubset({x["symbol"] for x in critical})
    assert len([x for x in critical if x["symbol"].startswith("HOT")]) == 14
    assert all(not row.get("dynamic_buy_candidate") for row in critical)
