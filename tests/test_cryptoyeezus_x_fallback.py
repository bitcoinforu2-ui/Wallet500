from __future__ import annotations

import json
from pathlib import Path

import wallet500.cryptoyeezus_x_fallback as xf


def _paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(xf, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(xf, "CALLS_PATH", tmp_path / "calls.json")
    monkeypatch.setattr(xf, "LATEST_PATH", tmp_path / "latest.json")


def _write(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _tweet(tweet_id: str, text: str):
    return {
        "rest_id": tweet_id,
        "core": {
            "user_results": {
                "result": {
                    "legacy": {"screen_name": "CryptoYeezussss"}
                }
            }
        },
        "legacy": {
            "id_str": tweet_id,
            "full_text": text,
            "created_at": "Sun Sep 13 08:00:00 +0000 2026",
        },
    }


def test_extract_syndication_rows_author_locks_and_skips_retweets():
    payload = {
        "props": {
            "pageProps": {
                "timeline": [
                    _tweet("100", "Gamboled a bag on $RUFUS"),
                    _tweet("101", "RT @someone something"),
                    {
                        "rest_id": "102",
                        "core": {"user_results": {"result": {"legacy": {"screen_name": "SomeoneElse"}}}},
                        "legacy": {
                            "id_str": "102",
                            "full_text": "Buying $FAKE",
                            "created_at": "Sun Sep 13 08:01:00 +0000 2026",
                        },
                    },
                ]
            }
        }
    }
    rows = xf.extract_syndication_rows(payload)
    assert [row["id"] for row in rows] == ["100"]
    assert rows[0]["author"] == "CryptoYeezussss"


def test_extract_fxtwitter_rows_author_locks_and_skips_retweets():
    payload = {
        "code": 200,
        "results": [
            {
                "id": "200",
                "text": "Gamboled a bag on $RUFUS",
                "created_at": "Sun Sep 13 08:00:00 +0000 2026",
                "author": {"screen_name": "CryptoYeezussss"},
                "url": "https://x.com/CryptoYeezussss/status/200",
            },
            {
                "id": "201",
                "text": "RT @someone noise",
                "created_at": "Sun Sep 13 08:01:00 +0000 2026",
                "author": {"screen_name": "CryptoYeezussss"},
            },
            {
                "id": "202",
                "text": "Buying $FAKE",
                "created_at": "Sun Sep 13 08:02:00 +0000 2026",
                "author": {"screen_name": "SomeoneElse"},
            },
        ],
    }
    rows = xf.extract_fxtwitter_rows(payload)
    assert [row["id"] for row in rows] == ["200"]
    assert rows[0]["provider"] == "x_fxtwitter_public"
    assert rows[0]["author"] == "CryptoYeezussss"


def test_first_successful_fallback_is_baseline_only(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    _write(xf.LATEST_PATH, {
        "providers": {"x": {"status": "HTTP_402"}},
        "latest_events": [],
        "new_posts": 0,
        "new_call_events": 0,
    })
    _write(xf.STATE_PATH, {
        "version": 1,
        "bootstrapped": True,
        "seen_posts": [],
        "tokens": {},
    })
    _write(xf.CALLS_PATH, {"events": []})
    rows = [{
        "source": "x",
        "id": "100",
        "author": "CryptoYeezussss",
        "published_at": "2026-09-13T08:00:00+00:00",
        "text": "Gamboled a bag on $RUFUS",
        "url": "https://x.com/CryptoYeezussss/status/100",
    }]
    monkeypatch.setattr(xf, "fetch_syndication", lambda: (rows, {"provider": "x_fxtwitter_public", "status": "OK_FXTWITTER_PUBLIC", "count": 1}))
    monkeypatch.setattr(xf, "_event_from_row", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("baseline must not create live events")))

    result = xf.run()
    assert result["status"] == "BASELINE_BOOTSTRAPPED"
    state = json.loads(xf.STATE_PATH.read_text())
    assert state["x_fallback_bootstrapped"] is True
    assert "x:100" in state["seen_posts"]
    calls = json.loads(xf.CALLS_PATH.read_text())
    assert calls["events"] == []
    latest = json.loads(xf.LATEST_PATH.read_text())
    assert latest["providers"]["x"]["effective_status"] == "OK_WITH_PUBLIC_FALLBACK"
    assert latest["providers"]["x"]["redundancy_provider"] == "x_fxtwitter_public"


def test_new_fallback_post_flows_to_priority_queue(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    _write(xf.LATEST_PATH, {
        "providers": {"x": {"status": "HTTP_402"}},
        "latest_events": [],
        "new_posts": 0,
        "new_call_events": 0,
    })
    _write(xf.STATE_PATH, {
        "version": 1,
        "bootstrapped": True,
        "x_fallback_bootstrapped": True,
        "seen_posts": ["x:99"],
        "tokens": {},
    })
    _write(xf.CALLS_PATH, {"events": []})
    rows = [{
        "source": "x",
        "id": "100",
        "author": "CryptoYeezussss",
        "published_at": "2026-09-13T08:00:00+00:00",
        "text": "Gamboled a bag on $RUFUS",
        "url": "https://x.com/CryptoYeezussss/status/100",
    }]
    monkeypatch.setattr(xf, "fetch_syndication", lambda: (rows, {"provider": "x_fxtwitter_public", "status": "OK_FXTWITTER_PUBLIC", "count": 1}))
    fake_event = {
        "event_id": "x:100:symbol:RUFUS",
        "event_type": "FIRST_MENTION",
        "source": "x",
        "source_post_id": "100",
        "published_at": "2026-09-13T08:00:00+00:00",
        "observed_at": "2026-09-13T08:01:00+00:00",
        "url": "https://x.com/CryptoYeezussss/status/100",
        "symbol": "RUFUS",
        "text": "Gamboled a bag on $RUFUS",
        "market_snapshot": None,
        "risk_flags": ["TICKER_ONLY_IDENTITY_UNRESOLVED"],
        "automatic_buy": False,
        "research_only": True,
    }
    monkeypatch.setattr(xf, "_event_from_row", lambda *args, **kwargs: dict(fake_event))
    monkeypatch.setattr(xf, "_find_cross_post", lambda event, events: None)

    result = xf.run()
    assert result["new_call_events"] == 1
    latest = json.loads(xf.LATEST_PATH.read_text())
    assert latest["latest_events"][0]["alert"]["reason"] == "DEFERRED_TO_CRYPTOYEEZUS_PRIORITY_V2"
    assert latest["providers"]["x"]["effective_status"] == "OK_WITH_PUBLIC_FALLBACK"
    assert latest["latest_events"][0]["source_provider"] == "x_fxtwitter_public"


def test_failed_x_redundancy_is_persisted_as_degraded(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    _write(xf.LATEST_PATH, {
        "providers": {"x": {"status": "HTTP_402"}},
        "latest_events": [],
        "new_posts": 0,
        "new_call_events": 0,
    })
    _write(xf.STATE_PATH, {
        "version": 1,
        "bootstrapped": True,
        "seen_posts": [],
        "tokens": {},
    })
    _write(xf.CALLS_PATH, {"events": []})
    monkeypatch.setattr(xf, "fetch_syndication", lambda: ([], {"provider": "x_public_redundancy", "status": "ALL_X_FALLBACKS_FAILED"}))

    result = xf.run()
    assert result["status"] == "FALLBACK_UNAVAILABLE"
    latest = json.loads(xf.LATEST_PATH.read_text())
    assert latest["providers"]["x"]["effective_status"] == "DEGRADED_NO_X_REDUNDANCY"
    state = json.loads(xf.STATE_PATH.read_text())
    assert state["provider_status"]["x_fallback"]["status"] == "ALL_X_FALLBACKS_FAILED"
