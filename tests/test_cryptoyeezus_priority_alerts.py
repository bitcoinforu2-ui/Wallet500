from __future__ import annotations

import json
from pathlib import Path

import wallet500.cryptoyeezus_priority_alerts as p


def _paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(p, "STATE_PATH", tmp_path / "live-state.json")
    monkeypatch.setattr(p, "CALLS_PATH", tmp_path / "calls.json")
    monkeypatch.setattr(p, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(p, "PRIORITY_STATE_PATH", tmp_path / "priority-state.json")


def _write(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _exact_market():
    return {
        "chain": "robinhood",
        "dex": "uniswap",
        "pair_address": "0xpair",
        "token_address": "0x46B6995b02B1e3Afa39033243999e00d739615F1",
        "symbol": "RUFUS",
        "price_usd": "0.00033",
        "market_cap_usd": 330000,
        "liquidity_usd": 60000,
        "volume_h1_usd": 50000,
        "volume_h24_usd": 300000,
        "dex_url": "https://dexscreener.com/robinhood/0xpair",
        "pair_identity_locked": True,
    }


def test_first_mention_uses_priority_delivery_once(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    event = {
        "event_id": "telegram:1:ca:rufus",
        "event_type": "FIRST_MENTION",
        "source": "telegram",
        "published_at": "2026-09-13T08:00:00+00:00",
        "symbol": "RUFUS",
        "text": "Gamboled a bag here on $RUFUS",
        "market_snapshot": _exact_market(),
        "risk_flags": [],
        "automatic_buy": False,
    }
    _write(p.STATE_PATH, {"tokens": {}})
    _write(p.CALLS_PATH, {"events": [dict(event)]})
    _write(p.LATEST_PATH, {"latest_events": [dict(event)]})

    sent = []
    monkeypatch.setattr(
        p,
        "_send_priority",
        lambda event, reason: sent.append((event["event_id"], reason)) or {
            "attempted": True,
            "sent": True,
            "message_id": 1,
            "delivery_policy": "CRYPTOYEEZUS_PRIORITY_V2",
            "priority_reason": reason,
        },
    )

    result = p.run()
    assert result["sent"] == 1
    assert sent == [("telegram:1:ca:rufus", "FIRST_MENTION_PRIORITY")]
    state = json.loads(p.PRIORITY_STATE_PATH.read_text())
    assert state["sent_event_ids"] == ["telegram:1:ca:rufus"]
    calls = json.loads(p.CALLS_PATH.read_text())
    assert calls["events"][0]["alert"]["sent"] is True

    p.run()
    assert len(sent) == 1


def test_ticker_only_repeat_reuses_only_prior_exact_identity(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    token = "0x46B6995b02B1e3Afa39033243999e00d739615F1"
    prior = _exact_market()
    _write(p.STATE_PATH, {
        "tokens": {
            "ca:" + token.lower(): {
                "symbol": "RUFUS",
                "token_address": token,
                "first_market_snapshot": prior,
            }
        }
    })
    event = {
        "event_id": "telegram:2:ca:rufus",
        "event_type": "REPEAT_PROMOTION",
        "source": "telegram",
        "published_at": "2026-09-13T10:30:00+00:00",
        "symbol": "RUFUS",
        "text": "$RUFUS still looks undervalued",
        "market_snapshot": None,
        "risk_flags": ["TICKER_ONLY_IDENTITY_UNRESOLVED"],
        "automatic_buy": False,
    }
    _write(p.CALLS_PATH, {"events": [dict(event)]})
    _write(p.LATEST_PATH, {"latest_events": [dict(event)]})
    _write(p.PRIORITY_STATE_PATH, {
        "version": 2,
        "sent_event_ids": ["telegram:1:ca:rufus"],
        "token_alerts": {
            "ca:" + token.lower(): {
                "last_sent_at": "2026-09-13T08:00:00+00:00",
                "sent_count": 1,
            }
        },
    })
    fresh = dict(prior)
    fresh["price_usd"] = "0.00040"
    fresh["identity_evidence"] = "PRIOR_EXACT_CALL_PLUS_FRESH_EXACT_PAIR"
    monkeypatch.setattr(p, "_fresh_exact_pair", lambda identity: fresh)
    sent = []
    monkeypatch.setattr(
        p,
        "_send_priority",
        lambda event, reason: sent.append(reason) or {
            "attempted": True,
            "sent": True,
            "delivery_policy": "CRYPTOYEEZUS_PRIORITY_V2",
            "priority_reason": reason,
        },
    )

    result = p.run()
    assert result["sent"] == 1
    assert sent == ["PERSISTENT_REPEAT_PRIORITY"]
    calls = json.loads(p.CALLS_PATH.read_text())
    row = calls["events"][0]
    assert row["market_snapshot"]["token_address"].lower() == token.lower()
    assert row["pair_identity_locked"] is True
    assert "TICKER_ONLY_IDENTITY_UNRESOLVED" not in row["risk_flags"]


def test_non_material_repeat_inside_cooldown_is_quiet(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    token = "0x46B6995b02B1e3Afa39033243999e00d739615F1"
    prior = _exact_market()
    _write(p.STATE_PATH, {
        "tokens": {
            "ca:" + token.lower(): {
                "symbol": "RUFUS",
                "token_address": token,
                "first_market_snapshot": prior,
            }
        }
    })
    event = {
        "event_id": "telegram:3:ca:rufus",
        "event_type": "REPEAT_PROMOTION",
        "source": "telegram",
        "published_at": "2026-09-13T08:30:00+00:00",
        "symbol": "RUFUS",
        "text": "$RUFUS still looks undervalued",
        "market_snapshot": None,
        "risk_flags": ["TICKER_ONLY_IDENTITY_UNRESOLVED"],
    }
    _write(p.CALLS_PATH, {"events": [dict(event)]})
    _write(p.LATEST_PATH, {"latest_events": [dict(event)]})
    _write(p.PRIORITY_STATE_PATH, {
        "version": 2,
        "sent_event_ids": ["telegram:1:ca:rufus"],
        "token_alerts": {
            "ca:" + token.lower(): {
                "last_sent_at": "2026-09-13T08:00:00+00:00",
                "sent_count": 1,
            }
        },
    })
    monkeypatch.setattr(p, "_fresh_exact_pair", lambda identity: prior)
    monkeypatch.setattr(
        p,
        "_send_priority",
        lambda event, reason: (_ for _ in ()).throw(AssertionError("must respect cooldown")),
    )

    result = p.run()
    assert result["sent"] == 0
    calls = json.loads(p.CALLS_PATH.read_text())
    assert calls["events"][0]["alert"]["reason"] == "NON_MATERIAL_REPEAT_COOLDOWN"
