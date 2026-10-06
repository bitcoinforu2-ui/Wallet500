import json
from datetime import datetime, timezone

from scripts import futures_market_discovery_collector as radar


def test_top20_mover_is_selected_before_quarter_wave():
    row = {
        "change_24h_pct": 9.0,
        "positive_gainer_rank": 5,
        "futures_volume_baseline_multiple": 1.1,
        "futures_volume_scan_multiple": 1.0,
        "gain_from_first_seen_pct": 2.0,
        "futures_total_size_change_pct": 0.0,
    }
    reasons = radar.select_reason(row)
    assert "FUTURES_CHANGE_GE_8PCT" in reasons
    assert "FUTURES_TOP20_EARLY_MOVER" in reasons


def test_run_resolves_exact_identity_and_preserves_immutable_anchor(tmp_path, monkeypatch):
    output = tmp_path / "out.json"
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "version": 1,
        "markets": {
            "TEST_USDT": {
                "first_seen_at": "2026-10-06T10:00:00+00:00",
                "first_seen_price": 1.0,
                "first_seen_change_24h_pct": 4.0,
                "first_seen_quote_volume_24h_usd": 10000.0,
                "last_quote_volume_24h_usd": 12000.0,
                "last_total_size": 1000.0,
            }
        }
    }))

    spot = tmp_path / "spot.json"
    spot.write_text(json.dumps({"candidates": []}))
    monkeypatch.setattr(radar, "OUTPUT", output)
    monkeypatch.setattr(radar, "STATE", state)
    monkeypatch.setattr(radar, "SPOT_DISCOVERY", spot)
    monkeypatch.setattr(radar, "now_dt", lambda: datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc))

    def fake_get(url, timeout=15):
        if url.endswith("/tickers"):
            return [{
                "contract": "TEST_USDT",
                "last": "1.12",
                "change_percentage": "9.5",
                "volume_24h_quote": "30000",
                "total_size": "1250",
                "funding_rate": "0.0001",
                "high_24h": "1.15",
                "low_24h": "0.99",
                "mark_price": "1.12",
                "index_price": "1.119",
            }]
        if url.endswith("/contracts"):
            return [{"name": "TEST_USDT", "in_delisting": False}]
        raise AssertionError(url)

    monkeypatch.setattr(radar, "get_json", fake_get)
    monkeypatch.setattr(radar, "resolve_identities", lambda rows: {
        0: {
            "identity_status": "RESOLVED_EXACT",
            "identity_reason": "EXACT_CHAIN_CONTRACT_PAIR",
            "network": "solana",
            "contract": "Token111",
            "pair": "Pair111",
            "dex_url": "https://dex.example/pair",
            "dex_liquidity_usd": 90000,
            "identity_source": "test",
        }
    })

    doc = radar.run()
    assert doc["counts"]["selected"] == 1
    row = doc["candidates"][0]
    assert row["status"] == "IDENTITY_RESOLVED"
    assert row["first_seen_price"] == 1.0
    assert round(row["gain_from_first_seen_pct"], 2) == 12.0
    assert row["futures_volume_baseline_multiple"] == 3.0
    assert row["futures_total_size_change_pct"] == 25.0


def test_futures_episode_rearms_only_after_signal_goes_cold(tmp_path, monkeypatch):
    output = tmp_path / "out.json"
    state = tmp_path / "state.json"
    spot = tmp_path / "spot.json"
    spot.write_text(json.dumps({"candidates": []}))
    monkeypatch.setattr(radar, "OUTPUT", output)
    monkeypatch.setattr(radar, "STATE", state)
    monkeypatch.setattr(radar, "SPOT_DISCOVERY", spot)

    moments = iter([
        datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 6, 10, 10, tzinfo=timezone.utc),
        datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 8, 0, 10, tzinfo=timezone.utc),
    ])
    monkeypatch.setattr(radar, "now_dt", lambda: next(moments))
    monkeypatch.setattr(radar, "resolve_identities", lambda rows: {})

    calls = {"n": 0}
    def fake_get(url, timeout=15):
        if url.endswith("/contracts"):
            return [{"name": "TEST_USDT", "in_delisting": False}]
        if url.endswith("/tickers"):
            calls["n"] += 1
            changes = [10.0, 11.0, -2.0, 9.0]
            ch = changes[calls["n"] - 1]
            return [{
                "contract": "TEST_USDT",
                "last": "1.1",
                "change_percentage": str(ch),
                "volume_24h_quote": "30000",
                "total_size": "1000",
                "funding_rate": "0.0001",
            }]
        raise AssertionError(url)
    monkeypatch.setattr(radar, "get_json", fake_get)

    first = radar.run()
    second = radar.run()
    radar.run()
    fourth = radar.run()

    assert first["candidates"][0]["futures_episode_seq"] == 1
    assert second["candidates"][0]["futures_episode_seq"] == 1
    assert fourth["candidates"][0]["futures_episode_seq"] == 2
    assert fourth["candidates"][0]["futures_episode_id"] == "TEST_USDT:2"


def test_same_run_spot_identity_reuse_is_unambiguous_and_zero_cost(tmp_path, monkeypatch):
    spot = tmp_path / "spot.json"
    spot.write_text(json.dumps({
        "candidates": [
            {
                "symbol": "FAST",
                "identity_status": "RESOLVED_EXACT",
                "network": "solana",
                "contract": "TokenFast",
                "pair": "PairFast",
                "dex_url": "https://dex.example/fast",
                "dex_liquidity_usd": 123456,
            },
            {
                "symbol": "AMB",
                "identity_status": "RESOLVED_EXACT",
                "network": "ethereum",
                "contract": "0xaaa",
                "pair": "0x111",
                "dex_liquidity_usd": 50000,
            },
            {
                "symbol": "AMB",
                "identity_status": "RESOLVED_EXACT",
                "network": "bsc",
                "contract": "0xbbb",
                "pair": "0x222",
                "dex_liquidity_usd": 90000,
            },
        ]
    }))
    monkeypatch.setattr(radar, "SPOT_DISCOVERY", spot)
    identities = radar.load_same_run_spot_identities()
    assert identities["FAST"]["identity_status"] == "RESOLVED_EXACT"
    assert identities["FAST"]["contract"] == "TokenFast"
    assert identities["FAST"]["identity_reused_from_spot"] is True
    assert "AMB" not in identities
