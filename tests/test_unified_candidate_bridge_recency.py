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
