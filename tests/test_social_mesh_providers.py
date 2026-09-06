from urllib.parse import unquote

import wallet500.social_feed_scan_v3 as scan
import wallet500.social_mesh_intelligence_enrichment as enrich
import wallet500.social_mesh_providers as mesh


IDENTITY = {
    "token_address": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump",
    "pair_address": "J3b6dvheS2Y1cbMtVz5TCWXNegSjJDbUKxdUVDPoqmS7",
    "symbol": "ARC",
    "name": "AI Rig Complex",
    "official_telegram": "https://t.me/arcfunportal",
}


def test_mesh_provider_config_never_exposes_secrets(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "secret-hash")
    monkeypatch.setenv("TELEGRAM_SESSION", "secret-session")
    monkeypatch.setenv("NEYNAR_API_KEY", "secret-neynar")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "secret-discord")
    monkeypatch.setenv("DISCORD_GUILD_IDS", "111")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "secret-threads")

    cfg = mesh.provider_config()
    assert cfg == {
        "telegram_mtproto": True,
        "farcaster_neynar": True,
        "discord_watch": True,
        "threads_keyword": True,
        "bluesky_public": True,
    }
    assert "secret-" not in str(cfg)


def test_telegram_official_context_requires_actual_author_match():
    broad = {"source": "telegram", "author": "random_channel", "text": "$ARC"}
    official = {"source": "telegram", "author": "arcfunportal", "text": "official update"}
    exact = {
        "source": "telegram",
        "author": "random_channel",
        "text": f"watch {IDENTITY['token_address']}",
    }
    assert scan._mesh_attribution(broad, IDENTITY) == "NAME_SYMBOL_CONTEXT"
    assert scan._mesh_attribution(official, IDENTITY) == "OFFICIAL_CHANNEL_CONTEXT"
    assert scan._mesh_attribution(exact, IDENTITY) == "EXACT_CONTRACT"


def test_farcaster_uses_neynar_search_and_maps_exact_query(monkeypatch):
    monkeypatch.setenv("NEYNAR_API_KEY", "test-key")
    captured = {}

    def fake_get(url, headers=None, timeout=18):
        captured["url"] = url
        captured["headers"] = headers
        return {
            "result": {
                "casts": [{
                    "hash": "0x1234567890abcdef",
                    "text": f"watch {IDENTITY['token_address']}",
                    "timestamp": "2026-09-06T03:00:00Z",
                    "author": {"fid": 9, "username": "alpha", "follower_count": 1200},
                    "replies": {"count": 2},
                    "reactions": {"likes_count": 3, "recasts_count": 4},
                }]
            }
        }

    monkeypatch.setattr(mesh, "_get_json", fake_get)
    rows, status = mesh.scan_farcaster(IDENTITY)
    assert status["status"] == "OK_DIRECT"
    assert rows[0]["source"] == "farcaster"
    assert rows[0]["author"] == "alpha"
    decoded = unquote(captured["url"])
    assert IDENTITY["token_address"] in decoded
    assert IDENTITY["pair_address"] in decoded
    assert captured["headers"]["x-api-key"] == "test-key"


def test_threads_keyword_search_is_recent_and_exact_identity_present(monkeypatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "token")
    captured = {}

    def fake_get(url, headers=None, timeout=18):
        captured["url"] = url
        return {"data": [{
            "id": "t1",
            "username": "threader",
            "text": f"CA {IDENTITY['token_address']}",
            "timestamp": "2026-09-06T03:00:00Z",
            "permalink": "https://www.threads.net/@threader/post/t1",
        }]}

    monkeypatch.setattr(mesh, "_get_json", fake_get)
    rows, status = mesh.scan_threads(IDENTITY)
    decoded = unquote(captured["url"])
    assert status["status"] == "OK_DIRECT"
    assert "graph.threads.net/keyword_search" in decoded
    assert "search_type=RECENT" in decoded
    assert IDENTITY["token_address"] in decoded
    assert rows[0]["source"] == "threads"


def test_bluesky_public_search_requires_no_secret(monkeypatch):
    monkeypatch.delenv("BLUESKY_ACCESS_TOKEN", raising=False)
    captured = {}

    def fake_get(url, headers=None, timeout=18):
        captured["url"] = url
        return {"posts": [{
            "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
            "cid": "cid",
            "author": {"handle": "alpha.bsky.social", "did": "did:plc:abc"},
            "record": {
                "text": f"watch {IDENTITY['token_address']}",
                "createdAt": "2026-09-06T03:00:00Z",
            },
            "likeCount": 2,
            "repostCount": 1,
            "replyCount": 1,
            "quoteCount": 0,
        }]}

    monkeypatch.setattr(mesh, "_get_json", fake_get)
    rows, status = mesh.scan_bluesky(IDENTITY)
    assert status["status"] == "OK_DIRECT_PUBLIC"
    assert "public.api.bsky.app/xrpc/app.bsky.feed.searchPosts" in captured["url"]
    assert rows[0]["engagement"] == 4


def test_discord_channel_watch_filters_for_exact_identity(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "bot")
    monkeypatch.setenv("DISCORD_CHANNEL_IDS", "123")
    monkeypatch.delenv("DISCORD_GUILD_IDS", raising=False)

    def fake_get(url, headers=None, timeout=18):
        return [
            {
                "id": "1",
                "channel_id": "123",
                "author": {"id": "u1", "username": "good"},
                "timestamp": "2026-09-06T03:00:00Z",
                "content": f"watch {IDENTITY['token_address']}",
            },
            {
                "id": "2",
                "channel_id": "123",
                "author": {"id": "u2", "username": "noise"},
                "timestamp": "2026-09-06T03:00:00Z",
                "content": "unrelated message",
            },
        ]

    monkeypatch.setattr(mesh, "_get_json", fake_get)
    rows, status = mesh.scan_discord(IDENTITY)
    assert status["status"] == "OK_DIRECT"
    assert len(rows) == 1
    assert rows[0]["author"] == "good"


def test_mesh_enrichment_credits_exact_mesh_authors_without_name_only_noise():
    token = IDENTITY["token_address"]
    payload = {
        "version": 3,
        "truth_contract": {},
        "counts": {},
        "tokens": [{
            "token_address": token,
            "scores": {
                "social_momentum": 20.0,
                "kol_quality": None,
                "news_catalyst": None,
                "hype_manipulation_risk": 0.0,
                "narrative": 20.0,
                "confidence": 40.0,
            },
            "coverage": {
                "freshness_score": 100.0,
                "organic_social_available": True,
                "exact_social_events": 0,
                "news_events": 0,
            },
            "availability": {
                "social_momentum": True,
                "kol_quality": False,
                "news_catalyst": False,
                "hype_manipulation_risk": True,
                "narrative": True,
                "confidence": True,
            },
            "reasons": [],
        }],
    }
    scan_payload = {
        "targets": [{
            "token_address": token,
            "events": [
                {
                    "source": "farcaster",
                    "author": "alpha",
                    "text": token,
                    "attribution": "EXACT_CONTRACT",
                },
                {
                    "source": "bluesky",
                    "author": "beta",
                    "text": token,
                    "attribution": "EXACT_CONTRACT",
                },
                {
                    "source": "threads",
                    "author": "noise",
                    "text": "$ARC",
                    "attribution": "NAME_SYMBOL_CONTEXT",
                },
            ],
        }]
    }

    out = enrich.enrich(payload, scan_payload, {"influencers": []})
    row = out["tokens"][0]
    assert row["coverage"]["mesh_exact_social_events"] == 2
    assert row["coverage"]["independent_authors"] == 2
    assert row["availability"]["kol_quality"] is True
    assert row["scores"]["kol_quality"] > 0
    assert "SOCIAL_MESH_EXACT:bluesky,farcaster" in row["reasons"]
    assert out["truth_contract"]["social_mesh_sources_enabled"] is True
