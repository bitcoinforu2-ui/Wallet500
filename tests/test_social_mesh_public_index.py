import wallet500.social_mesh_public_index as idx


IDENTITY = {
    "token_address": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump",
    "pair_address": "J3b6dvheS2Y1cbMtVz5TCWXNegSjJDbUKxdUVDPoqmS7",
}


def test_query_is_exact_identity_only():
    q = idx.build_query(IDENTITY)
    assert IDENTITY["token_address"] in q
    assert IDENTITY["pair_address"] in q
    assert "site:t.me" in q
    assert "site:bsky.app" in q
    assert "site:threads.net" in q


def test_index_rejects_name_only_noise(monkeypatch):
    xml = f'''<?xml version="1.0"?><rss><channel>
      <item><title>ARC is trending - threads.net</title><link>https://example/1</link><source>threads.net</source></item>
      <item><title>Watch {IDENTITY['token_address']} - bsky.app</title><link>https://example/2</link><source>bsky.app</source></item>
      <item><title>Pair {IDENTITY['pair_address']} - t.me</title><link>https://example/3</link><source>t.me</source></item>
    </channel></rss>'''.encode()

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return xml

    monkeypatch.setattr(idx, "urlopen", lambda req, timeout=18: Resp())
    rows, status = idx.scan_mesh_public_index(IDENTITY)
    assert status["status"] == "INDEX_OK_CONTEXT_ONLY"
    assert status["organic_eligible"] is False
    assert len(rows) == 2
    assert {x["source"] for x in rows} == {"bluesky_index", "telegram_index"}
    assert {x["attribution"] for x in rows} == {"EXACT_CONTRACT", "EXACT_PAIR"}
    assert all(x["context_only"] is True for x in rows)
    assert all(x["organic_eligible"] is False for x in rows)
