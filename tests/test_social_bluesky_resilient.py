from urllib.error import HTTPError

import wallet500.social_bluesky_resilient as bsky


IDENTITY = {
    "token_address": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump",
    "symbol": "ARC",
    "name": "AI Rig Complex",
}


def _post(text=None):
    return {
        "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
        "author": {"handle": "alpha.bsky.social", "did": "did:plc:abc"},
        "record": {"text": text or IDENTITY["token_address"], "createdAt": "2026-09-06T04:00:00Z"},
        "likeCount": 1,
        "repostCount": 1,
    }


def _raise_403(*args, **kwargs):
    raise HTTPError("https://example.invalid", 403, "Forbidden", {}, None)


def test_official_public_appview_is_primary_and_does_not_use_legacy_or_auth(monkeypatch):
    captured = []

    def fake_public(url, timeout=18):
        captured.append(url)
        return {"posts": [_post()]}

    monkeypatch.setattr(bsky, "_get_public_json", fake_public)
    monkeypatch.setattr(bsky.mesh, "scan_bluesky", lambda identity: (_ for _ in ()).throw(AssertionError("legacy should not run")))
    monkeypatch.setattr(bsky, "_post_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("auth should not run")))

    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows
    assert status["status"] == "OK_DIRECT_PUBLIC_OFFICIAL_APPVIEW"
    assert status["endpoint"] == "https://public.api.bsky.app"
    assert status["auth_fallback"] == "NOT_NEEDED"
    assert status["legacy_public_fallback"] == "NOT_NEEDED"
    assert captured and all(url.startswith("https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?") for url in captured)


def test_official_public_empty_success_is_still_observed_not_failure(monkeypatch):
    monkeypatch.setattr(bsky, "_get_public_json", lambda url, timeout=18: {"posts": []})
    monkeypatch.setattr(bsky.mesh, "scan_bluesky", lambda identity: (_ for _ in ()).throw(AssertionError("legacy should not run")))
    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows == []
    assert status["status"] == "OK_DIRECT_PUBLIC_OFFICIAL_APPVIEW"
    assert status["count"] == 0
    assert status["meaning"] is None


def test_legacy_public_is_only_compatibility_fallback_after_official_failure(monkeypatch):
    monkeypatch.setattr(bsky, "_get_public_json", _raise_403)
    monkeypatch.setattr(
        bsky.mesh,
        "scan_bluesky",
        lambda identity: ([{"source": "bluesky", "text": IDENTITY["token_address"]}], {"provider": "bluesky", "status": "OK_DIRECT_PUBLIC"}),
    )
    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows
    assert status["status"] == "OK_DIRECT_PUBLIC_LEGACY_FALLBACK"
    assert status["official_public_status"] == "HTTP_403"
    assert status["official_public_endpoint"] == "https://public.api.bsky.app"
    assert status["legacy_public_fallback"] == "USED"


def test_both_public_403_without_credentials_is_explicit_auth_boundary(monkeypatch):
    monkeypatch.delenv("BSKY_IDENTIFIER", raising=False)
    monkeypatch.delenv("BSKY_APP_PASSWORD", raising=False)
    monkeypatch.setattr(bsky, "_get_public_json", _raise_403)
    monkeypatch.setattr(
        bsky.mesh,
        "scan_bluesky",
        lambda identity: ([], {"provider": "bluesky", "status": "HTTP_403"}),
    )
    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows == []
    assert status["status"] == "PUBLIC_SEARCH_BLOCKED_AUTH_REQUIRED"
    assert status["endpoint"] == "https://public.api.bsky.app"
    assert status["official_public_status"] == "HTTP_403"
    assert status["legacy_public_status"] == "HTTP_403"
    assert status["public_search_blocked"] is True
    assert status["public_search_observation"] == "BOTH_PUBLIC_APPVIEW_SEARCH_PATHS_HTTP_403"
    assert status["auth_fallback"] == "NOT_CONFIGURED"
    assert status["activation_required"] == "CONFIGURE_BSKY_IDENTIFIER_AND_BSKY_APP_PASSWORD"
    assert status["auth_required_for_reliable_search"] is True
    assert status["meaning"] == "UNKNOWN_NOT_ZERO"


def test_auth_fallback_after_both_public_paths_fail(monkeypatch):
    monkeypatch.setenv("BSKY_IDENTIFIER", "wallet500.bsky.social")
    monkeypatch.setenv("BSKY_APP_PASSWORD", "app-pass")
    monkeypatch.setattr(bsky, "_get_public_json", _raise_403)
    monkeypatch.setattr(
        bsky.mesh,
        "scan_bluesky",
        lambda identity: ([], {"provider": "bluesky", "status": "HTTP_403"}),
    )
    monkeypatch.setattr(bsky, "_post_json", lambda url, payload, timeout=18: {"accessJwt": "jwt"})
    monkeypatch.setattr(bsky, "_get_json", lambda url, token, timeout=18: {"posts": [_post()]})

    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows[0]["source"] == "bluesky"
    assert status["status"] == "OK_DIRECT_AUTH"
    assert status["official_public_status"] == "HTTP_403"
    assert status["legacy_public_status"] == "HTTP_403"
    assert status["auth_fallback"] == "USED"
