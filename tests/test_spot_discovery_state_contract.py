from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import spot_market_discovery_collector as spot


def test_multi_window_hot_mover_and_state_retention(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    output_path = tmp_path / "output.json"
    config_path = tmp_path / "config.json"
    native_path = tmp_path / "native.json"

    config_path.write_text(json.dumps({"cex_research_watch_targets": []}))
    native_path.write_text(json.dumps({"assets": {}}))
    state_path.write_text(json.dumps({
        "version": 1,
        "pairs": {
            "MGT_USDT": {
                "symbol": "MGT",
                "first_seen_at": "2026-09-20T14:15:55+00:00",
                "first_seen_price": 0.0000751,
                "first_seen_change_24h_pct": 10.78,
                "first_seen_quote_volume_24h_usd": 205.05,
                "last_seen_at": "2026-09-20T23:41:35+00:00",
                "peak_discovery_momentum_change_pct": 357.29,
                "hot_until": "2099-01-01T00:00:00+00:00",
                "identity_status": "RESOLVED_EXACT",
                "identity_reason": "EXACT_CHAIN_CONTRACT_PAIR",
                "network": "bsc",
                "contract": "0x3c6256f234ba638e5883c46b3fedb00ea2e66b8a",
                "pair": "0xdce2e6fe348f8c8a2b08bbff8f447c64224d75fb",
                "dex_url": "https://dexscreener.com/bsc/example",
            },
            "OLD_USDT": {
                "symbol": "OLD",
                "first_seen_at": "2098-12-31T00:00:00+00:00",
                "first_seen_price": 1.0,
                "last_seen_at": "2098-12-31T12:00:00+00:00",
                "identity_status": "PENDING",
            },
        },
    }))

    monkeypatch.setattr(spot, "STATE", state_path)
    monkeypatch.setattr(spot, "OUTPUT", output_path)
    monkeypatch.setattr(spot, "CONFIG", config_path)
    monkeypatch.setattr(spot, "NATIVE_IDENTITY", native_path)

    contract = "0x3c6256f234ba638e5883c46b3fedb00ea2e66b8a"
    pair = "0xdce2e6fe348f8c8a2b08bbff8f447c64224d75fb"

    def fake_get_json(url, timeout=12):
        if "/spot/tickers" in url:
            assert "timezone=all" in url
            return [{
                "currency_pair": "MGT_USDT",
                "last": "0.00024468",
                "change_percentage": "2.0",
                "change_utc0": "1.5",
                "change_utc8": "266.01",
                "quote_volume": "29830",
                "high_24h": "0.00031",
                "low_24h": "0.00007",
            }]
        if "/spot/currency_pairs" in url:
            return [{
                "id": "MGT_USDT",
                "base": "MGT",
                "quote": "USDT",
                "trade_status": "tradable",
                "type": "normal",
                "st_tag": False,
            }]
        if "/wallet/currency_chains" in url:
            return [{"chain": "BSC", "contract_address": contract}]
        if "api.dexscreener.com/latest/dex/tokens/" in url:
            return {"pairs": [{
                "chainId": "bsc",
                "pairAddress": pair,
                "baseToken": {"address": contract},
                "quoteToken": {"address": "0xusdt"},
                "liquidity": {"usd": 2000},
                "url": "https://dexscreener.com/bsc/example",
            }]}
        raise AssertionError(url)

    monkeypatch.setattr(spot, "get_json", fake_get_json)
    result = spot.run()

    row = next(x for x in result["candidates"] if x["symbol"] == "MGT")
    assert row["discovery_momentum_change_pct"] == 266.01
    assert row["first_seen_price"] == 0.0000751
    assert row["identity_status"] == "RESOLVED_EXACT"

    persisted = json.loads(state_path.read_text())["pairs"]
    assert persisted["MGT_USDT"]["first_seen_price"] == 0.0000751
    assert persisted["MGT_USDT"]["peak_discovery_momentum_change_pct"] >= 357.29
    assert "OLD_USDT" in persisted
