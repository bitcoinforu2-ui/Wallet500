import json
from datetime import datetime, timezone

from scripts import unified_candidate_bridge as bridge


def test_public_alpha_live_queue_excludes_stale_history(tmp_path, monkeypatch):
    alpha = {
        "candidates": [
            {
                "status": "GATED_RESEARCH_CANDIDATE",
                "symbol": "FRESH",
                "network": "solana",
                "contract": "FreshMint11111111111111111111111111111111",
                "pair": "FreshPair111111111111111111111111111111111",
                "called_at": "2026-09-19T09:30:00+00:00",
                "liquidity_usd": 1000,
            },
            {
                "status": "GATED_RESEARCH_CANDIDATE",
                "symbol": "OLD",
                "network": "solana",
                "contract": "OldMint111111111111111111111111111111111",
                "pair": "OldPair1111111111111111111111111111111111",
                "called_at": "2026-09-19T01:00:00+00:00",
                "liquidity_usd": 999999,
            },
        ]
    }
    paths = {
        "SPOT": tmp_path / "spot.json",
        "CEX_SPOT_IDENTITY": tmp_path / "cex_identity.json",
        "ALPHA": tmp_path / "alpha.json",
        "BUY_REGISTRY": tmp_path / "buy.json",
        "BOOTSTRAP": tmp_path / "bootstrap.json",
        "OUT": tmp_path / "out.json",
        "EVENTS": tmp_path / "events.json",
    }
    paths["SPOT"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["CEX_SPOT_IDENTITY"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["ALPHA"].write_text(json.dumps(alpha), encoding="utf-8")
    paths["BUY_REGISTRY"].write_text('{"entries":{}}', encoding="utf-8")
    paths["BOOTSTRAP"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["EVENTS"].write_text('{"version":3,"events":[]}', encoding="utf-8")
    for name, path in paths.items():
        monkeypatch.setattr(bridge, name, path)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 19, 10, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(bridge, "datetime", FixedDatetime)
    bridge.main()

    result = json.loads(paths["OUT"].read_text(encoding="utf-8"))
    assert result["counts"]["public_alpha"] == 1
    assert result["counts"]["public_alpha_stale_excluded"] == 1
    assert result["candidates"][0]["symbol"] == "FRESH"
    assert result["candidates"][0]["alpha_age_minutes"] == 30.0


def test_alpha_age_missing_timestamp_fails_closed():
    assert bridge.alpha_age_minutes({}, current=datetime(2026, 9, 19, tzinfo=timezone.utc)) is None


def test_exact_multi_cex_identity_is_bridged_into_unified_watch(tmp_path, monkeypatch):
    paths = {
        "SPOT": tmp_path / "spot.json",
        "CEX_SPOT_IDENTITY": tmp_path / "cex_identity.json",
        "ALPHA": tmp_path / "alpha.json",
        "BUY_REGISTRY": tmp_path / "buy.json",
        "BOOTSTRAP": tmp_path / "bootstrap.json",
        "OUT": tmp_path / "out.json",
        "EVENTS": tmp_path / "events.json",
    }
    paths["SPOT"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["ALPHA"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["BUY_REGISTRY"].write_text('{"entries":{}}', encoding="utf-8")
    paths["BOOTSTRAP"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["EVENTS"].write_text('{"version":3,"events":[]}', encoding="utf-8")
    paths["CEX_SPOT_IDENTITY"].write_text(
        json.dumps({
            "candidates": [{
                "symbol": "W3GGUSDT",
                "identity_status": "DEX_VERIFIED",
                "identity_verified": True,
                "execution_pair_price_coherent": True,
                "market_age_verified": True,
                "chain": "solana",
                "token_address": "W3GGToken111111111111111111111111111111111",
                "pair_address": "W3GGPair1111111111111111111111111111111111",
                "dex_url": "https://dexscreener.com/solana/W3GGPair",
                "dex_liquidity_usd": 75000,
                "spot_revival_score": 20,
                "coherent_confirmations": 1,
                "change_24h_max_pct": 0.48,
                "markets": [{"volume_24h": 57607.0, "volume_comparable_usd_like": True}],
                "milestones": {
                    "first_shadow_watch": {
                        "observed_at": "2026-09-14T20:27:10+00:00",
                        "reference_price": 0.0004948,
                    },
                    "first_seen": {
                        "observed_at": "2026-09-04T10:50:55+00:00",
                        "reference_price": 0.0004924,
                    },
                },
            }]
        }),
        encoding="utf-8",
    )
    for name, path in paths.items():
        monkeypatch.setattr(bridge, name, path)

    bridge.main()

    result = json.loads(paths["OUT"].read_text(encoding="utf-8"))
    assert result["counts"]["cex_spot"] == 1
    row = result["candidates"][0]
    assert row["candidate_type"] == "CEX_SPOT_DISCOVERY"
    assert row["symbol"] == "W3GGUSDT"
    assert row["network"] == "solana"
    assert row["source"] == "CEX Spot Multi-Venue Exact Identity"

    events = json.loads(paths["EVENTS"].read_text(encoding="utf-8"))
    assert any(
        e.get("canonical_event_id", "").startswith("cex-spot-discovery:")
        for e in events["events"]
    )



def test_gate_market_is_canonical_and_merges_earlier_cex_history(tmp_path, monkeypatch):
    paths = {
        "SPOT": tmp_path / "spot.json",
        "CEX_SPOT_IDENTITY": tmp_path / "cex_identity.json",
        "ALPHA": tmp_path / "alpha.json",
        "BUY_REGISTRY": tmp_path / "buy.json",
        "BOOTSTRAP": tmp_path / "bootstrap.json",
        "OUT": tmp_path / "out.json",
        "EVENTS": tmp_path / "events.json",
    }
    paths["SPOT"].write_text(
        json.dumps({
            "candidates": [{
                "symbol": "PTB",
                "currency_pair": "PTB_USDT",
                "status": "IDENTITY_RESOLVED",
                "identity_status": "RESOLVED_EXACT",
                "network": "eth",
                "contract": "0x30a25cc9c9eade4d4d9e9349be6e68c3411367d3",
                "pair": "0xd40929ad9749f30eb56fe5a388d8afb226278fb875baf2c561c4e3a1f816725a",
                "dex_url": "https://dexscreener.com/ethereum/example",
                "dex_liquidity_usd": 64000,
                "first_seen_at": "2026-09-20T11:28:55+00:00",
                "first_seen_price": 0.000762,
                "first_seen_change_24h_pct": 8.1,
                "first_seen_quote_volume_24h_usd": 119277,
                "discovery_price": 0.0010,
                "change_24h_pct": 41.6,
                "discovery_momentum_change_pct": 41.6,
                "gain_from_first_seen_pct": 31.2,
                "quote_volume_24h_usd": 2180000,
                "positive_gainer_rank": 3,
                "identity_reason": "EXACT_CHAIN_CONTRACT_PAIR",
            }]
        }),
        encoding="utf-8",
    )
    paths["CEX_SPOT_IDENTITY"].write_text(
        json.dumps({
            "candidates": [{
                "symbol": "PTBUSDT",
                "base_symbol": "PTB",
                "identity_status": "DEX_VERIFIED",
                "identity_verified": True,
                "execution_pair_price_coherent": True,
                "market_age_verified": True,
                "chain": "bsc",
                "token_address": "0x95c9b514566fbd224dc2037f5914eb8ab91c9201",
                "pair_address": "0x28b7c347a58c9c30b21e51e732ee9723d910f605",
                "dex_liquidity_usd": 58000,
                "milestones": {
                    "first_cross_venue_slow_ignition": {
                        "observed_at": "2026-09-14T17:28:45+00:00",
                        "reference_price": 0.0006883,
                        "reference_change_24h_pct": 5.42,
                    }
                },
                "markets": [{
                    "exchange": "gate",
                    "market_id": "PTB_USDT",
                    "volume_24h": 2100000,
                    "volume_comparable_usd_like": True,
                }],
            }]
        }),
        encoding="utf-8",
    )
    paths["ALPHA"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["BUY_REGISTRY"].write_text('{"entries":{}}', encoding="utf-8")
    paths["BOOTSTRAP"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["EVENTS"].write_text('{"version":3,"events":[]}', encoding="utf-8")
    for name, path in paths.items():
        monkeypatch.setattr(bridge, name, path)

    bridge.main()

    result = json.loads(paths["OUT"].read_text(encoding="utf-8"))
    ptb = [x for x in result["candidates"] if x.get("symbol") == "PTB"]
    assert len(ptb) == 1
    row = ptb[0]
    assert row["candidate_type"] == "GATE_SPOT_DISCOVERY"
    assert row["network"] == "eth"
    assert row["currency_pair"] == "PTB_USDT"
    assert row["first_seen_at"] == "2026-09-14T17:28:45+00:00"
    assert row["first_seen_price"] == 0.0006883
    assert row["merged_cex_identity_history"] is True
    assert not any(x.get("symbol") == "PTBUSDT" for x in result["candidates"])
