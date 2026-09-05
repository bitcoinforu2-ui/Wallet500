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
