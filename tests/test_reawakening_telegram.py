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
        "metrics": {"liquidity_usd": 80_000, "return_pct": 25, "turnover_h1": 1.2, "buy_sell_ratio_h1": 1.3, "activity_h1": 300},
    }


def write_source(tmp_path, rows):
    (tmp_path / "reawakening-shadow.json").write_text(json.dumps({"targets": rows}))


def test_fresh_trigger_is_sent_once(tmp_path, monkeypatch):
    write_source(tmp_path, [target()])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    messages = []
    now = datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc)
    first = run(str(tmp_path), now=now, sender=lambda _b, _c, text: messages.append(text))
    second = run(str(tmp_path), now=now, sender=lambda _b, _c, text: messages.append(text))
    assert first["delivered_count"] == 1
    assert second["delivered_count"] == 0
    assert len(messages) == 1
    assert "עדיין לא BUY" in messages[0]


def test_historical_trigger_is_suppressed(tmp_path, monkeypatch):
    write_source(tmp_path, [target("2026-08-31T16:39:00+00:00")])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    messages = []
    report = run(str(tmp_path), now=datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc), sender=lambda _b, _c, text: messages.append(text))
    assert report["delivered_count"] == 0
    assert report["stale_suppressed_count"] == 1
    assert messages == []


def test_missing_secrets_fails_closed_without_send(tmp_path, monkeypatch):
    write_source(tmp_path, [target()])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    report = run(str(tmp_path), now=datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc), sender=lambda *_: (_ for _ in ()).throw(AssertionError()))
    assert report["configured"] is False
    assert report["delivered_count"] == 0
