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


def test_gate_canonical_keeps_same_asset_sibling_pools_for_watch(tmp_path, monkeypatch):
    paths = {
        "SPOT": tmp_path / "spot.json",
        "CEX_SPOT_IDENTITY": tmp_path / "cex_identity.json",
        "ALPHA": tmp_path / "alpha.json",
        "BUY_REGISTRY": tmp_path / "buy.json",
        "BOOTSTRAP": tmp_path / "bootstrap.json",
        "OUT": tmp_path / "out.json",
        "EVENTS": tmp_path / "events.json",
    }
    token = "0x1111111111111111111111111111111111111111"
    gate_pair = "0x2222222222222222222222222222222222222222"
    wbnb_pair = "0x3333333333333333333333333333333333333333"

    paths["SPOT"].write_text(json.dumps({
        "candidates": [{
            "symbol": "AKE",
            "currency_pair": "AKE_USDT",
            "status": "IDENTITY_RESOLVED",
            "identity_status": "RESOLVED_EXACT",
            "network": "bsc",
            "contract": token,
            "pair": gate_pair,
            "dex_url": "https://dexscreener.com/bsc/" + gate_pair,
            "dex_liquidity_usd": 250000,
            "first_seen_at": "2026-09-22T01:57:20+00:00",
            "first_seen_price": 0.057827,
            "first_seen_change_24h_pct": 13.34,
            "first_seen_quote_volume_24h_usd": 33798632.63,
            "discovery_price": 0.0542,
            "change_24h_pct": 31.19,
            "discovery_momentum_change_pct": 31.19,
            "gain_from_first_seen_pct": -6.2,
            "quote_volume_24h_usd": 33589833.43,
            "positive_gainer_rank": 17,
        }]
    }), encoding="utf-8")
    paths["CEX_SPOT_IDENTITY"].write_text(json.dumps({
        "candidates": [{
            "symbol": "AKEUSDT",
            "base_symbol": "AKE",
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "execution_pair_price_coherent": True,
            "market_age_verified": True,
            "chain": "bsc",
            "token_address": token,
            "pair_address": gate_pair,
            "dex_url": "https://dexscreener.com/bsc/" + gate_pair,
            "dex_price_usd": 0.0542,
            "dex_liquidity_usd": 250000,
            "execution_pool_liquidity_usd": 250000,
            "dex_total_liquidity_usd": 410000,
            "dex_pool_count": 2,
            "change_24h_max_pct": 31.19,
            "leaderboard_best_rank": 17,
            "markets": [{
                "exchange": "gate",
                "market_id": "AKE_USDT",
                "volume_24h": 33589833.43,
                "volume_comparable_usd_like": True,
            }],
            "milestones": {
                "first_seen": {
                    "observed_at": "2026-09-22T01:57:20+00:00",
                    "reference_price": 0.057827,
                    "reference_change_24h_pct": 13.34,
                }
            },
            "dex_liquidity_pools_top5": [
                {
                    "chain": "bsc",
                    "token_address": token,
                    "pair_address": gate_pair,
                    "dex": "pancakeswap",
                    "price_usd": 0.0542,
                    "liquidity_usd": 250000,
                    "volume_h1": 200000,
                    "volume_h24": 5000000,
                    "provider": "DEXSCREENER_TOKEN_PAIRS",
                    "url": "https://dexscreener.com/bsc/" + gate_pair,
                },
                {
                    "chain": "bsc",
                    "token_address": token,
                    "pair_address": wbnb_pair,
                    "dex": "pancakeswap",
                    "price_usd": 0.0538,
                    "liquidity_usd": 160000,
                    "volume_h1": 350000,
                    "volume_h24": 7200000,
                    "provider": "GECKOTERMINAL_EXACT_TOKEN_POOLS",
                    "url": "https://dexscreener.com/bsc/" + wbnb_pair,
                },
            ],
        }]
    }), encoding="utf-8")
    paths["ALPHA"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["BUY_REGISTRY"].write_text('{"entries":{}}', encoding="utf-8")
    paths["BOOTSTRAP"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["EVENTS"].write_text('{"version":3,"events":[]}', encoding="utf-8")
    for name, path in paths.items():
        monkeypatch.setattr(bridge, name, path)

    bridge.main()

    result = json.loads(paths["OUT"].read_text(encoding="utf-8"))
    same_asset = [
        x for x in result["candidates"]
        if x.get("contract", "").lower() == token.lower()
    ]
    assert len(same_asset) == 2

    canonical = next(x for x in same_asset if x.get("pair", "").lower() == gate_pair.lower())
    sibling = next(x for x in same_asset if x.get("pair", "").lower() == wbnb_pair.lower())

    assert canonical["candidate_type"] == "GATE_SPOT_DISCOVERY"
    assert canonical["multi_pool_watch"] is True
    assert sibling["candidate_type"] == "CEX_SPOT_DISCOVERY"
    assert sibling["multi_pool_watch"] is True
    assert sibling["asset_pool_role"] == "SIBLING"
    assert sibling["asset_identity_key"] == "bsc:" + token.lower()
    assert sibling["currency_pair"] == "AKE_USDT"
    assert sibling["execution_identity_scope"] == "EXACT_CHAIN_CONTRACT_PAIR_PLUS_CEX_MARKET"
    assert result["counts"]["multi_pool_sibling_candidates"] == 1


def test_cex_only_gate_mover_recovers_exact_identity_and_sibling_pools(tmp_path, monkeypatch):
    paths = {
        "SPOT": tmp_path / "spot.json",
        "CEX_SPOT_IDENTITY": tmp_path / "cex_identity.json",
        "ALPHA": tmp_path / "alpha.json",
        "BUY_REGISTRY": tmp_path / "buy.json",
        "BOOTSTRAP": tmp_path / "bootstrap.json",
        "OUT": tmp_path / "out.json",
        "EVENTS": tmp_path / "events.json",
    }
    token = "0x2c3a8ee94ddd97244a93bc48298f97d2c412f7db"
    primary = "0x83fcd80d7973cca1aa821590bbec66d27a2d4ad4"
    sibling = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    paths["SPOT"].write_text(json.dumps({
        "candidates": [{
            "symbol": "AKE",
            "currency_pair": "AKE_USDT",
            "source": "Gate Spot",
            "discovery_price": 0.054505,
            "change_24h_pct": 42.6,
            "discovery_momentum_change_pct": 42.6,
            "quote_volume_24h_usd": 33356392.9,
            "positive_gainer_rank": 13,
            "first_seen_at": "2026-09-22T01:57:20+00:00",
            "first_seen_price": 0.057827,
            "first_seen_change_24h_pct": 13.34,
            "status": "DISCOVERED_CEX_SPOT",
            "identity_status": "PENDING",
            "identity_reason": "RESOLUTION_BUDGET",
        }]
    }), encoding="utf-8")
    paths["CEX_SPOT_IDENTITY"].write_text(json.dumps({
        "candidates": [{
            "symbol": "AKEUSDT",
            "base_symbol": "AKE",
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "execution_pair_price_coherent": True,
            "market_age_verified": True,
            "identity_candidate_source": "STRICT_DEXSCREENER_CEX_FALLBACK",
            "chain": "bsc",
            "token_address": token,
            "pair_address": primary,
            "dex_url": "https://dexscreener.com/bsc/" + primary,
            "dex_price_usd": 0.05347,
            "dex_liquidity_usd": 31784.18,
            "execution_pool_liquidity_usd": 31784.18,
            "dex_total_liquidity_usd": 151784.18,
            "dex_pool_count": 2,
            "change_24h_max_pct": 42.6,
            "leaderboard_best_rank": 13,
            "markets": [{
                "exchange": "gate",
                "market_type": "spot",
                "symbol": "AKEUSDT",
                "market_id": "AKE_USDT",
                "quote_symbol": "USDT",
                "price": 0.054505,
                "volume_24h": 33356392.9,
                "volume_comparable_usd_like": True,
            }],
            "milestones": {
                "first_seen": {
                    "observed_at": "2026-09-22T01:57:20+00:00",
                    "reference_price": 0.057827,
                    "reference_change_24h_pct": 13.34,
                }
            },
            "dex_liquidity_pools_top5": [
                {
                    "chain": "bsc",
                    "token_address": token,
                    "pair_address": primary,
                    "dex": "pancakeswap",
                    "price_usd": 0.05347,
                    "liquidity_usd": 31784.18,
                    "volume_h1": 3622.9,
                    "volume_h24": 203710.16,
                    "provider": "DEXSCREENER_SEARCH",
                    "url": "https://dexscreener.com/bsc/" + primary,
                },
                {
                    "chain": "bsc",
                    "token_address": token,
                    "pair_address": sibling,
                    "dex": "pancakeswap",
                    "price_usd": 0.0541,
                    "liquidity_usd": 120000,
                    "volume_h1": 12000,
                    "volume_h24": 450000,
                    "provider": "DEXSCREENER_TOKEN_PAIRS",
                    "url": "https://dexscreener.com/bsc/" + sibling,
                },
            ],
        }]
    }), encoding="utf-8")
    paths["ALPHA"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["BUY_REGISTRY"].write_text('{"entries":{}}', encoding="utf-8")
    paths["BOOTSTRAP"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["EVENTS"].write_text('{"version":3,"events":[]}', encoding="utf-8")
    for name, path in paths.items():
        monkeypatch.setattr(bridge, name, path)

    bridge.main()
    result = json.loads(paths["OUT"].read_text(encoding="utf-8"))

    exact = [
        x for x in result["candidates"]
        if x.get("asset_identity_key") == "bsc:" + token
    ]
    assert len(exact) == 2
    assert {x["pair"].lower() for x in exact} == {primary, sibling}
    assert all(x["candidate_type"] == "CEX_SPOT_DISCOVERY" for x in exact)
    assert all(x["currency_pair"] == "AKE_USDT" for x in exact)
    assert all(x["execution_identity_scope"] == "EXACT_CHAIN_CONTRACT_PAIR_PLUS_CEX_MARKET" for x in exact)
    assert all(x["cex_market_identity_recovered"] is True for x in exact)
    assert any(x["asset_pool_role"] == "SIBLING" for x in exact)
    assert result["counts"]["cex_market_exact_identity_recovered"] == 1

    venue_only = [
        x for x in result["candidates"]
        if x.get("candidate_type") == "CEX_MARKET_DISCOVERY"
        and x.get("currency_pair") == "AKE_USDT"
    ]
    assert len(venue_only) == 1
