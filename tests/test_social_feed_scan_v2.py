import wallet500.social_feed_scan as base
import wallet500.social_feed_scan_v2 as mod


def test_priority_plus_rotation_advances(monkeypatch):
    ranked = [{"token_address": f"T{i}"} for i in range(10)]
    monkeypatch.setattr(mod, "_ORIGINAL_SELECT", lambda envelope, budget: ranked[:budget])
    monkeypatch.setenv("SOCIAL_SCAN_PRIORITY_SLOTS", "2")
    monkeypatch.setattr(
        mod.base,
        "_load",
        lambda path, default: {"targets": [
            {"token_address": "T0"},
            {"token_address": "T1"},
            {"token_address": "T2"},
            {"token_address": "T3"},
        ]},
    )
    out = mod._rotating_select({}, 4)
    assert [x["token_address"] for x in out[:2]] == ["T0", "T1"]
    assert [x["token_address"] for x in out[2:]] == ["T4", "T5"]


def test_rotation_wraps_without_dropping_priority(monkeypatch):
    ranked = [{"token_address": f"T{i}"} for i in range(6)]
    monkeypatch.setattr(mod, "_ORIGINAL_SELECT", lambda envelope, budget: ranked[:budget])
    monkeypatch.setenv("SOCIAL_SCAN_PRIORITY_SLOTS", "2")
    monkeypatch.setattr(
        mod.base,
        "_load",
        lambda path, default: {"targets": [
            {"token_address": "T0"},
            {"token_address": "T1"},
            {"token_address": "T4"},
            {"token_address": "T5"},
        ]},
    )
    out = mod._rotating_select({}, 4)
    assert [x["token_address"] for x in out] == ["T0", "T1", "T2", "T3"]


def test_coingecko_identity_429_circuit_breaks_remaining_social_targets(monkeypatch):
    calls = []

    def fake_waking_identity(coin):
        calls.append(coin.get("id"))
        statuses = [{"provider": "dexscreener_identity", "status": "OK"}]
        if coin.get("id"):
            statuses.append({"provider": "coingecko_identity", "status": "HTTP_429"})
        return {
            "token_address": coin.get("token_address"),
            "coingecko_id": coin.get("id"),
            "official_x": "https://x.com/example",
        }, statuses

    monkeypatch.setattr(base, "_waking_identity", fake_waking_identity)
    base._reset_identity_runtime_state()

    _, first_statuses = base._identity({"token_address": "MINT1", "id": "coin-one"})
    second_identity, second_statuses = base._identity({"token_address": "MINT2", "id": "coin-two"})

    assert calls == ["coin-one", None]
    assert any(x.get("status") == "HTTP_429" for x in first_statuses)
    assert second_identity["coingecko_id"] == "coin-two"
    assert any(x.get("status") == "CIRCUIT_BREAKER_HTTP_429" for x in second_statuses)
    assert any(x.get("meaning") == "UNKNOWN_NOT_ZERO" for x in second_statuses)
