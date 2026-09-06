import wallet500.social_bluesky_resilient as bsky


IDENTITY = {
    "token_address": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump",
    "symbol": "ARC",
    "name": "AI Rig Complex",
}


def test_public_success_does_not_use_auth(monkeypatch):
    monkeypatch.setattr(
        bsky.mesh,
        "scan_bluesky",
        lambda identity: ([{"source": "bluesky"}], {"provider": "bluesky", "status": "OK_DIRECT_PUBLIC"}),
    )
    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows
    assert status["auth_fallback"] == "NOT_NEEDED"


def test_403_without_credentials_stays_unknown(monkeypatch):
    monkeypatch.delenv("BSKY_IDENTIFIER", raising=False)
    monkeypatch.delenv("BSKY_APP_PASSWORD", raising=False)
    monkeypatch.setattr(
        bsky.mesh,
        "scan_bluesky",
        lambda identity: ([], {"provider": "bluesky", "status": "HTTP_403"}),
    )
    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows == []
    assert status["status"] == "HTTP_403"
    assert status["auth_fallback"] == "NOT_CONFIGURED"
    assert status["meaning"] == "UNKNOWN_NOT_ZERO"


def test_auth_fallback_after_public_403(monkeypatch):
    monkeypatch.setenv("BSKY_IDENTIFIER", "wallet500.bsky.social")
    monkeypatch.setenv("BSKY_APP_PASSWORD", "app-pass")
    monkeypatch.setattr(
        bsky.mesh,
        "scan_bluesky",
        lambda identity: ([], {"provider": "bluesky", "status": "HTTP_403"}),
    )
    monkeypatch.setattr(bsky, "_post_json", lambda url, payload, timeout=18: {"accessJwt": "jwt"})
    monkeypatch.setattr(
        bsky,
        "_get_json",
        lambda url, token, timeout=18: {"posts": [{
            "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
            "author": {"handle": "alpha.bsky.social", "did": "did:plc:abc"},
            "record": {"text": IDENTITY["token_address"], "createdAt": "2026-09-06T04:00:00Z"},
            "likeCount": 1,
        }]},
    )
    rows, status = bsky.scan_bluesky_resilient(IDENTITY)
    assert rows[0]["source"] == "bluesky"
    assert status["status"] == "OK_DIRECT_AUTH"
    assert status["auth_fallback"] == "USED"
