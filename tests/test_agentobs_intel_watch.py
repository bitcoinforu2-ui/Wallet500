import json

import wallet500.agentobs_intel_watch as a


def test_classify_trade_with_contract_is_material():
    text = "Bought a position because liquidity improved 0x47366e0f257ac009e82bd46fb74e2fb50826ce98"
    refs = a.extract_refs(text)
    result = a.classify_post(text, refs)
    assert result["material"] is True
    assert "TRADE" in result["categories"]
    assert "REASONING" in result["categories"]
    assert "ONCHAIN_IDENTITY" in result["categories"]
    assert result["intelligence_score"] >= 90


def test_noise_is_not_material():
    result = a.classify_post("Good morning everyone")
    assert result["material"] is False
    assert result["intelligence_score"] == 0


def test_first_run_is_forward_only_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(a, "EVENTS_PATH", tmp_path / "events.json")
    monkeypatch.setattr(a, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(
        a,
        "fetch_x",
        lambda: ([{
            "source": "x",
            "id": "1",
            "author": "AgentOBSRH",
            "published_at": "2026-09-09T12:00:00Z",
            "text": "Bought $AOBS because liquidity improved",
            "url": "https://x.com/AgentOBSRH/status/1",
            "engagement": 10,
        }], {"provider": "x", "status": "OK_DIRECT"}),
    )
    monkeypatch.setattr(a, "resolve_market_identity", lambda refs: (None, []))
    sent = []
    monkeypatch.setattr(a, "_send", lambda *args, **kwargs: sent.append(args) or (1, 1))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    result = a.run()
    assert result["first_run_baseline"] is True
    assert result["new_posts"] == 1
    assert result["material_posts"] == 1
    assert result["telegram_alerts"] == 0
    assert sent == []


def test_second_run_alerts_only_new_material_post(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(a, "EVENTS_PATH", tmp_path / "events.json")
    monkeypatch.setattr(a, "LATEST_PATH", tmp_path / "latest.json")
    (tmp_path / "state.json").write_text(json.dumps({
        "initialized": True,
        "seen_post_keys": ["x:1"],
    }))
    monkeypatch.setattr(
        a,
        "fetch_x",
        lambda: ([
            {"source": "x", "id": "1", "author": "AgentOBSRH", "published_at": "2026-09-09T12:00:00Z", "text": "old"},
            {"source": "x", "id": "2", "author": "AgentOBSRH", "published_at": "2026-09-09T12:05:00Z", "text": "Sold $TEST position because risk increased", "url": "https://x.com/AgentOBSRH/status/2"},
        ], {"provider": "x", "status": "OK_DIRECT"}),
    )
    monkeypatch.setattr(a, "resolve_market_identity", lambda refs: (None, []))
    sent = []
    monkeypatch.setattr(a, "_send", lambda *args, **kwargs: sent.append(args) or (99, 1))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    result = a.run()
    assert result["first_run_baseline"] is False
    assert result["new_posts"] == 1
    assert result["telegram_alerts"] == 1
    assert len(sent) == 1
    events = json.loads((tmp_path / "events.json").read_text())["events"]
    assert events[-1]["production_trade_impact"] == "NONE"
    assert events[-1]["research_only"] is True
