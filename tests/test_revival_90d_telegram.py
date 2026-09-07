from __future__ import annotations

import json
from datetime import datetime, timezone

from wallet500 import revival_90d_telegram as mod


def _row(**overrides):
    row = {
        "chain": "bsc",
        "token": "0xabc",
        "base_token_address": "0xAbC",
        "base_token_symbol": "FIRE",
        "pair_address": "0xPair",
        "pair_created_at": int(datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp() * 1000),
        "liquidity_usd": 20_000,
        "revival_score": 72,
        "volume_h1": 22_000,
        "buys_h1": 40,
        "sells_h1": 30,
        "url": "https://dexscreener.com/bsc/0xpair",
    }
    row.update(overrides)
    return row


def test_gate_accepts_90d_15k_research_case():
    ok, meta = mod._eligibility(_row(), datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert ok is True
    assert meta["liquidity_usd"] == 20_000
    assert meta["market_age_days"] >= 90


def test_gate_rejects_under_15k_and_wrong_identity():
    ok, meta = mod._eligibility(
        _row(liquidity_usd=14_999, base_token_address="0xdef"),
        datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    assert ok is False
    assert "LIQUIDITY_LT_15K" in meta["blockers"]
    assert "BASE_TOKEN_IDENTITY_NOT_VERIFIED" in meta["blockers"]


def test_three_fire_message_and_transition_dedupe(tmp_path, monkeypatch):
    (tmp_path / mod.SOURCE).write_text(json.dumps([_row()]), encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    messages = []

    def fake_send(token, chat_id, text):
        messages.append(text)
        return 123, 1

    monkeypatch.setattr(mod, "_send", fake_send)
    now = datetime(2026, 9, 7, 19, 0, tzinfo=timezone.utc)
    first = mod.run(str(tmp_path), now=now)
    second = mod.run(str(tmp_path), now=now)

    assert first["delivered_count"] == 1
    assert second["delivered_count"] == 0
    assert len(messages) == 1
    assert messages[0].startswith("🔥🔥🔥 REVIVAL 90D / 15K")
    assert "Production 180d/$50K gate: UNCHANGED" in messages[0]
    assert first["truth_contract"]["research_only"] is True
    assert first["truth_contract"]["production_gate_changed"] is False


def test_no_secrets_never_marks_sent(tmp_path, monkeypatch):
    (tmp_path / mod.SOURCE).write_text(json.dumps([_row()]), encoding="utf-8")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    result = mod.run(str(tmp_path), now=datetime(2026, 9, 7, 19, 0, tzinfo=timezone.utc))
    assert result["configured"] is False
    assert result["delivered_count"] == 0
    assert not (tmp_path / mod.STATE).exists()
