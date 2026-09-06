from urllib.parse import unquote

import wallet500.social_direct_providers as direct
import wallet500.social_feed_scan_v2 as scan


IDENTITY = {
    "token_address": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump",
    "pair_address": "J3b6dvheS2Y1cbMtVz5TCWXNegSjJDbUKxdUVDPoqmS7",
    "symbol": "ARC",
    "name": "AI Rig Complex",
    "official_x": "https://x.com/arcdotfun",
    "official_telegram": "https://t.me/arcfunportal",
}


def test_direct_queries_include_exact_mint_and_pair():
    for provider in ("x", "youtube", "reddit"):
        q = direct.direct_query(IDENTITY, provider)
        assert IDENTITY["token_address"] in q
        assert IDENTITY["pair_address"] in q
    assert "from:arcdotfun" in direct.direct_query(IDENTITY, "x")


def test_attribution_accepts_exact_pair_and_official_x():
    assert scan._attribution_v2({"source": "reddit", "text": f"pair {IDENTITY['pair_address']}"}, IDENTITY) == "EXACT_PAIR"
    assert scan._attribution_v2({"source": "x", "author": "arcdotfun", "text": "official update"}, IDENTITY) == "OFFICIAL_CHANNEL_CONTEXT"
    assert scan._attribution_v2({"source": "x", "author": "someone", "text": "$ARC looks interesting"}, IDENTITY) == "NAME_SYMBOL_CONTEXT"


def test_x_direct_maps_author_id_to_username_and_scans_pair(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    captured = {}

    def fake_get(url, headers=None, timeout=18):
        captured["url"] = url
        captured["headers"] = headers
        return {
            "data": [{
                "id": "123",
                "author_id": "42",
                "created_at": "2026-09-05T10:00:00Z",
                "text": "official update",
                "public_metrics": {"like_count": 4, "retweet_count": 2, "reply_count": 1, "quote_count": 0},
            }],
            "includes": {"users": [{"id": "42", "username": "arcdotfun", "verified": True}]},
        }

    monkeypatch.setattr(direct, "_get_json", fake_get)
    rows, status = direct.scan_x(IDENTITY)
    assert status["status"] == "OK_DIRECT"
    assert rows[0]["author"] == "arcdotfun"
    assert rows[0]["engagement"] == 7
    decoded = unquote(captured["url"])
    assert IDENTITY["token_address"] in decoded
    assert IDENTITY["pair_address"] in decoded
    assert "expansions=author_id" in decoded


def test_reddit_public_fallback_works_without_oauth_and_normalizes_epoch(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    captured = {}

    def fake_get(url, headers=None, timeout=18):
        captured["url"] = url
        return {
            "data": {"children": [{"data": {
                "id": "abc",
                "author": "organic_user",
                "subreddit": "CryptoCurrency",
                "created_utc": 1788602400,
                "title": f"Watching {IDENTITY['token_address']}",
                "selftext": "independent observation",
                "score": 5,
                "num_comments": 2,
                "permalink": "/r/CryptoCurrency/comments/abc/example/",
            }}]}
        }

    monkeypatch.setattr(direct, "_get_json", fake_get)
    rows, status = direct.scan_reddit(IDENTITY)
    assert status["status"] == "OK_DIRECT_PUBLIC"
    assert "www.reddit.com/search.json" in captured["url"]
    assert rows[0]["published_at"].endswith("+00:00")
    assert rows[0]["engagement"] == 7


def test_provider_config_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-x")
    monkeypatch.setenv("YOUTUBE_API_KEY", "secret-y")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "secret-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret-secret")
    cfg = direct.provider_config()
    assert cfg == {
        "x": True,
        "youtube": True,
        "reddit_oauth": True,
        "reddit_public": True,
        "telegram_public_direct": True,
    }
    assert "secret" not in str(cfg).lower()
