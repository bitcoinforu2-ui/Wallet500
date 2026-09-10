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
        "leaderboard_best_rank": 3,
    }


def source(rows):
    return {"generated_at": "2026-09-10T18:20:00+00:00", "candidates": rows}


def test_research_candidate_never_sends_even_with_telegram_secrets(tmp_path: Path, monkeypatch):
    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda *args, **kwargs: calls.append(args))

    report = mod.run(tmp_path, datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc))

    assert report["status"] == "RESEARCH_ONLY_NOTIFICATION_DISABLED"
    assert report["telegram_delivery_enabled"] is False
    assert report["eligible_count"] == 1
    assert report["delivered_count"] == 0
    assert report["suppressed_count"] == 1
    assert report["truth_contract"]["research_only_telegram_delivery_disabled"] is True
    assert calls == []
    assert not (tmp_path / "cex-spot-telegram-state.json").exists()


def test_repeat_runs_never_rearm_or_send_research_alerts(tmp_path: Path, monkeypatch):
    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    calls = []
    monkeypatch.setattr(mod, "_send", lambda *args, **kwargs: calls.append(args))

    first = mod.run(tmp_path, datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc))
    second = mod.run(tmp_path, datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc))

    assert first["delivered_count"] == second["delivered_count"] == 0
    assert first["suppressed_count"] == second["suppressed_count"] == 1
    assert calls == []


def test_unverified_or_young_identity_is_not_even_research_eligible(tmp_path: Path):
    bad = candidate()
    bad["market_age_min_days"] = 59
    _write(tmp_path / "cex-spot-identity-radar.json", source([bad]))

    report = mod.run(tmp_path, datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc))

    assert report["eligible_count"] == 0
    assert report["delivered_count"] == 0
    assert report["suppressed_count"] == 0


def test_report_is_written_without_telegram_configuration(tmp_path: Path, monkeypatch):
    _write(tmp_path / "cex-spot-identity-radar.json", source([candidate()]))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    report = mod.run(tmp_path, datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc))
    persisted = json.loads((tmp_path / "cex-spot-telegram-report.json").read_text(encoding="utf-8"))

    assert report == persisted
    assert report["delivered_count"] == 0
