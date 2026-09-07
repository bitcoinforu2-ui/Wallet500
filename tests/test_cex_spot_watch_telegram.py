import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500 import cex_spot_watch_telegram as mod


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def candidate(symbol="KCTUSDT"):
    return {
        "symbol": symbol,
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "market_age_verified": True,
        "market_age_min_days": 1000,
        "research_only": True,
        "actionable": False,
        "chain": "ethereum",
        "token_address": "0x63230728bc219d991d2995ce92e96c16fcf8beb6",
        "pair_address": "0xpair",
        "spot_revival_score": 31,
        "change_24h_max_pct": 45.04,
        "leaderboard_best_rank": 3,
        "leaderboard_exchanges": ["gate"],
        "confirmations": 1,
        "exchanges": ["gate"],
        "price_acceleration_max_pct": 0.3,
        "volume_acceleration_max_pct": 1.0,
        "dex_liquidity_usd": 12345,
        "dex_volume_h1": 100,
        "markets": [{"exchange": "gate", "volume_24h": 546200, "change_24h_pct": 45.04}],
        "milestones": {"first_watch": {"observed_at": "2026-09-07T06:00:00+00:00"}},
    }


def source(rows):
    return {"generated_at": "2026-09-07T07:20:00+00:00", "candidates": rows}


def test_first_configured_run_baselines_existing_candidates_without_sending(tmp_path: Path, monkeypatch):
    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda *args, **kwargs: calls.append(args) or (1, 1))

    report = mod.run(tmp_path, datetime(2026, 9, 7, 7, 30, tzinfo=timezone.utc))

    assert report["first_run_baseline"] is True
    assert report["baseline_count"] == 1
    assert report["delivered_count"] == 0
    assert calls == []


def test_new_candidate_after_initialization_sends_once_and_dedupes(tmp_path: Path, monkeypatch):
    _write(tmp_path / "cex-spot-identity-radar.json", source([]))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda token, chat, text: calls.append(text) or (77, 1))

    mod.run(tmp_path, datetime(2026, 9, 7, 7, 0, tzinfo=timezone.utc))
    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    first = mod.run(tmp_path, datetime(2026, 9, 7, 7, 15, tzinfo=timezone.utc))
    second = mod.run(tmp_path, datetime(2026, 9, 7, 7, 30, tzinfo=timezone.utc))

    assert first["delivered_count"] == 1
    assert second["delivered_count"] == 0
    assert len(calls) == 1
    assert "CEX EARLY WATCH" in calls[0]
    assert "NOT REAL ALERT / NOT BUY SIGNAL" in calls[0]
    assert "DEX execution-pool liquidity" in calls[0]


def test_reentry_after_six_hours_can_alert_again(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda token, chat, text: calls.append(text) or (88, 1))

    _write(tmp_path / "cex-spot-identity-radar.json", source([]))
    mod.run(tmp_path, datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc))

    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    mod.run(tmp_path, datetime(2026, 9, 7, 0, 15, tzinfo=timezone.utc))

    _write(tmp_path / "cex-spot-identity-radar.json", source([]))
    mod.run(tmp_path, datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc))

    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    report = mod.run(tmp_path, datetime(2026, 9, 7, 7, 0, tzinfo=timezone.utc))

    assert report["delivered_count"] == 1
    assert len(calls) == 2


def test_unverified_or_young_identity_never_sends(tmp_path: Path, monkeypatch):
    bad = candidate()
    bad["market_age_min_days"] = 100
    _write(tmp_path / "cex-spot-identity-radar.json", source([bad]))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda *args, **kwargs: calls.append(args) or (1, 1))

    report = mod.run(tmp_path, datetime(2026, 9, 7, 7, 30, tzinfo=timezone.utc))

    assert report["eligible_count"] == 0
    assert calls == []


def test_missing_secrets_never_mutates_state(tmp_path: Path, monkeypatch):
    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    report = mod.run(tmp_path, datetime(2026, 9, 7, 7, 30, tzinfo=timezone.utc))

    assert report["status"] == "SKIPPED_UNCONFIGURED_NO_STATE_WRITE"
    assert not (tmp_path / "cex-spot-telegram-state.json").exists()
