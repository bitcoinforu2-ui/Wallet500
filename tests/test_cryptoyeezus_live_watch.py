from __future__ import annotations

import json
from pathlib import Path

import wallet500.cryptoyeezus_live_watch as y


def _paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(y, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(y, "CALLS_PATH", tmp_path / "calls.json")
    monkeypatch.setattr(y, "LATEST_PATH", tmp_path / "latest.json")


def test_extract_refs_handles_cashtags_contract_and_dex():
    text = (
        "Gambling a bag here on $AOBS and watching $HOOD "
        "0x1111111111111111111111111111111111111111 "
        "https://dexscreener.com/ethereum/0x2222222222222222222222222222222222222222"
    )
    refs = y.extract_refs(text)
    assert refs["tickers"] == ["AOBS", "HOOD"]
    assert refs["contracts"] == ["0x1111111111111111111111111111111111111111"]
    assert refs["dex_links"][0]["chain_hint"] == "ethereum"
    assert y.looks_like_call(text, refs) is True


def test_first_run_bootstraps_without_alert(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    rows = [{
        "source": "telegram",
        "id": "cryptoyeezuscalls/100",
        "author": "cryptoyeezuscalls",
        "published_at": "2026-09-07T06:00:00+00:00",
        "text": "Gambling a bag here on $AOBS",
        "url": "https://t.me/cryptoyeezuscalls/100",
    }]
    monkeypatch.setattr(y, "fetch_sources", lambda state: (rows, {"telegram": {"status": "OK"}, "x": {"status": "SKIP"}}))
    monkeypatch.setattr(y, "_send_alert", lambda event: (_ for _ in ()).throw(AssertionError("must not alert baseline")))

    result = y.run()
    assert result["status"] == "BASELINE_BOOTSTRAPPED"
    calls = json.loads((tmp_path / "calls.json").read_text())
    assert calls["events"][0]["baseline_only"] is True
    assert calls["events"][0]["alert"]["reason"] == "INITIAL_BASELINE_NO_HINDSIGHT"


def test_new_first_mention_alerts_then_repeat_does_not_reset(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    batches = [
        [],
        [{
            "source": "telegram",
            "id": "cryptoyeezuscalls/101",
            "author": "cryptoyeezuscalls",
            "published_at": "2026-09-07T06:05:00+00:00",
            "text": "Gambling a bag here on $NEWCOIN",
            "url": "https://t.me/cryptoyeezuscalls/101",
        }],
        [{
            "source": "telegram",
            "id": "cryptoyeezuscalls/101",
            "author": "cryptoyeezuscalls",
            "published_at": "2026-09-07T06:05:00+00:00",
            "text": "Gambling a bag here on $NEWCOIN",
            "url": "https://t.me/cryptoyeezuscalls/101",
        }, {
            "source": "telegram",
            "id": "cryptoyeezuscalls/102",
            "author": "cryptoyeezuscalls",
            "published_at": "2026-09-07T06:10:00+00:00",
            "text": "$NEWCOIN new ATH send it",
            "url": "https://t.me/cryptoyeezuscalls/102",
        }],
    ]
    monkeypatch.setattr(y, "fetch_sources", lambda state: (batches.pop(0), {"telegram": {"status": "OK"}, "x": {"status": "SKIP"}}))
    monkeypatch.setattr(y, "resolve_market_identity", lambda refs: (None, ["TICKER_ONLY_IDENTITY_UNRESOLVED"]))
    sent = []
    monkeypatch.setattr(y, "_send_alert", lambda event: sent.append(event["event_type"]) or {"attempted": True, "sent": True})

    y.run()
    y.run()
    state_after_first = json.loads((tmp_path / "state.json").read_text())
    first_time = state_after_first["tokens"]["symbol:NEWCOIN"]["first_seen_at"]
    y.run()

    state_after_repeat = json.loads((tmp_path / "state.json").read_text())
    assert state_after_repeat["tokens"]["symbol:NEWCOIN"]["first_seen_at"] == first_time
    assert sent == ["FIRST_MENTION", "REPEAT_PROMOTION"]


def test_cross_source_duplicate_does_not_send_second_alert(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    batches = [
        [],
        [{
            "source": "telegram",
            "id": "cryptoyeezuscalls/201",
            "author": "cryptoyeezuscalls",
            "published_at": "2026-09-07T07:00:00+00:00",
            "text": "Buying a bag of $DUPE",
            "url": "https://t.me/cryptoyeezuscalls/201",
        }],
        [{
            "source": "telegram",
            "id": "cryptoyeezuscalls/201",
            "author": "cryptoyeezuscalls",
            "published_at": "2026-09-07T07:00:00+00:00",
            "text": "Buying a bag of $DUPE",
            "url": "https://t.me/cryptoyeezuscalls/201",
        }, {
            "source": "x",
            "id": "999",
            "author": "CryptoYeezussss",
            "published_at": "2026-09-07T07:04:00+00:00",
            "text": "Buying a bag of $DUPE",
            "url": "https://x.com/CryptoYeezussss/status/999",
        }],
    ]
    monkeypatch.setattr(y, "fetch_sources", lambda state: (batches.pop(0), {"telegram": {"status": "OK"}, "x": {"status": "OK"}}))
    monkeypatch.setattr(y, "resolve_market_identity", lambda refs: (None, ["TICKER_ONLY_IDENTITY_UNRESOLVED"]))
    sent = []
    monkeypatch.setattr(y, "_send_alert", lambda event: sent.append(event["source"]) or {"attempted": True, "sent": True})

    y.run()
    y.run()
    y.run()

    calls = json.loads((tmp_path / "calls.json").read_text())
    live = [e for e in calls["events"] if not e.get("baseline_only")]
    assert sent == ["telegram"]
    assert live[-1]["event_type"] == "CROSS_POST_DUPLICATE"
    assert live[-1]["alert"]["reason"] == "CROSS_SOURCE_DEDUPLICATED"
