import json
from datetime import datetime, timezone

from wallet500.reawakening_telegram import run


def target(triggered_at="2026-09-01T18:50:00+00:00"):
    return {
        "status": "SURVIVOR_REAWAKENING_SHADOW_WATCH",
        "token_key": "bsc:TOKEN",
        "chain": "bsc",
        "token": "TOKEN",
        "pair_address": "PAIR",
        "triggered_at": triggered_at,
        "price_usd": .001,
        "confirmation_observations": 2,
        "confirmation_span_minutes": 15,
        "metrics": {
            "liquidity_usd": 80_000,
            "gain_since_reject_pct": 25,
            "volume_h1_usd": 60_000,
            "turnover_h1": 0.75,
            "buy_sell_ratio_h1": 1.3,
            "txns_h1": 400,
        },
    }


def write_source(tmp_path, rows):
    (tmp_path / "reawakening-shadow.json").write_text(json.dumps({"targets": rows}))


def test_fresh_trigger_is_sent_once(tmp_path, monkeypatch):
    write_source(tmp_path, [target()])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    messages = []
    now = datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc)
    first = run(str(tmp_path), now=now, sender=lambda _b, _c, text: messages.append(text), chat_resolver=lambda _b: "chat")
    second = run(str(tmp_path), now=now, sender=lambda _b, _c, text: messages.append(text), chat_resolver=lambda _b: "chat")
    assert first["delivered_count"] == 1
    assert second["delivered_count"] == 0
    assert len(messages) == 2
    assert "Wallet500 מחובר" in messages[0]
    assert "עדיין לא BUY" in messages[1]
    assert "שינוי מאז הפסילה: +25.0%" in messages[1]
    assert "חלון אישור: 15 דקות" in messages[1]


def test_historical_trigger_is_suppressed(tmp_path, monkeypatch):
    write_source(tmp_path, [target("2026-08-31T16:39:00+00:00")])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    messages = []
    report = run(str(tmp_path), now=datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc), sender=lambda _b, _c, text: messages.append(text), chat_resolver=lambda _b: "chat")
    assert report["delivered_count"] == 0
    assert report["stale_suppressed_count"] == 1
    assert len(messages) == 1
    assert "Wallet500 מחובר" in messages[0]


def test_missing_secrets_fails_closed_without_send(tmp_path, monkeypatch):
    write_source(tmp_path, [target()])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    report = run(str(tmp_path), now=datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc), sender=lambda *_: (_ for _ in ()).throw(AssertionError()))
    assert report["configured"] is False
    assert report["delivered_count"] == 0


def test_chat_id_can_be_resolved_without_secret(tmp_path, monkeypatch):
    write_source(tmp_path, [target()])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    seen = []
    report = run(
        str(tmp_path),
        now=datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc),
        sender=lambda _b, chat, _text: seen.append(chat),
        chat_resolver=lambda _b: "123456",
    )
    assert report["configured"] is True
    assert report["chat_resolution"] == "PRIVATE_WALLET500_HANDSHAKE"
    assert seen == ["123456", "123456"]
    assert report["connection_confirmation_sent"] is True
    assert "123456" not in json.dumps(report)


def test_connection_confirmation_is_sent_only_once(tmp_path, monkeypatch):
    write_source(tmp_path, [])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    messages = []
    kwargs = {
        "now": datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc),
        "sender": lambda _b, _c, text: messages.append(text),
        "chat_resolver": lambda _b: "123456",
    }
    first = run(str(tmp_path), **kwargs)
    second = run(str(tmp_path), **kwargs)
    assert first["connection_confirmation_sent"] is True
    assert second["connection_confirmation_sent"] is False
    assert len(messages) == 1
    assert "Wallet500 מחובר" in messages[0]
