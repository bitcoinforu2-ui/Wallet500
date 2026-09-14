import json
from datetime import datetime, timezone
from pathlib import Path

from wallet500 import cex_spot_watch_telegram as mod


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def candidate(symbol="XTAGUSDT", alert_at="2026-09-14T09:30:00+00:00", first_move=1.46):
    return {
        "symbol": symbol,
        "spot_revival_score": 45,
        "research_only": True,
        "actionable": False,
        "automatic_buy": False,
        "coherent_confirmations": 1,
        "exchanges": ["gate"],
        "milestones": {
            "first_alert": {
                "kind": "FIRST_ALERT",
                "observed_at": alert_at,
                "reference_price": 0.0005902,
                "reference_exchange": "gate",
                "reference_change_24h_pct": first_move,
                "score": 35,
                "coherent_confirmations": 1,
            }
        },
        "markets": [{
            "exchange": "gate",
            "price": 0.00072,
            "volume_24h": 150000,
            "volume_comparable_usd_like": True,
        }],
    }


def identity(symbol="XTAGUSDT", exact=False):
    row = {
        "symbol": symbol,
        "market_age_verified": True,
        "market_age_min_days": 1000,
        "coingecko_id": "xhashtag",
        "research_only": True,
        "actionable": False,
    }
    if exact:
        row.update({
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "ethereum",
            "token_address": "0xabc",
            "pair_address": "0xpair",
            "dex_url": "https://dex.example/pair",
        })
    else:
        row.update({"identity_status": "IDENTITY_PENDING", "identity_verified": False})
    return row


def setup_sources(tmp_path: Path, rows, ids):
    _write(tmp_path / "cex-spot-revival-radar.json", {
        "generated_at": "2026-09-14T09:40:00+00:00",
        "watchlist": rows,
        "alerts": rows,
    })
    _write(tmp_path / "cex-spot-identity-radar.json", {"candidates": ids})


def test_fresh_veteran_first_alert_sends_once_even_if_exact_pair_pending(tmp_path: Path, monkeypatch):
    setup_sources(tmp_path, [candidate()], [identity(exact=False)])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda _bot, _chat, text, **_kw: calls.append(text))

    now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    first = mod.run(tmp_path, now)
    second = mod.run(tmp_path, now)

    assert first["delivered_count"] == 1
    assert second["delivered_count"] == 0
    assert len(calls) == 1
    assert "Discovery price:" in calls[0]
    assert "Exact on-chain identity: PENDING" in calls[0]
    assert "NOT A BUY ORDER" in calls[0]
    state = json.loads((tmp_path / "cex-spot-telegram-state.json").read_text())
    assert len(state["sent"]) == 1


def test_first_enabled_run_baselines_old_history_without_flood(tmp_path: Path, monkeypatch):
    setup_sources(tmp_path, [candidate(alert_at="2026-09-14T05:00:00+00:00")], [identity()])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda *_args, **_kwargs: calls.append(1))

    report = mod.run(tmp_path, datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))

    assert report["delivered_count"] == 0
    assert calls == []
    state = json.loads((tmp_path / "cex-spot-telegram-state.json").read_text())
    assert len(state["baselined"]) == 1


def test_late_first_alert_and_leveraged_products_stay_silent(tmp_path: Path, monkeypatch):
    late = candidate("MLPUSDT", first_move=80)
    leveraged = candidate("FIL5LUSDT")
    setup_sources(tmp_path, [late, leveraged], [identity("MLPUSDT"), identity("FIL5LUSDT")])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda *_args, **_kwargs: calls.append(1))

    report = mod.run(tmp_path, datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))

    assert report["eligible_event_count"] == 0
    assert report["delivered_count"] == 0
    assert calls == []


def test_unconfigured_writes_report_but_never_dedupe_state(tmp_path: Path, monkeypatch):
    setup_sources(tmp_path, [candidate()], [identity()])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    report = mod.run(tmp_path, datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))

    assert report["status"] == "SKIPPED_UNCONFIGURED_NO_STATE_WRITE"
    assert report["telegram_delivery_enabled"] is False
    assert not (tmp_path / "cex-spot-telegram-state.json").exists()
    assert (tmp_path / "cex-spot-telegram-report.json").exists()


def test_exact_identity_is_included_when_available(tmp_path: Path, monkeypatch):
    setup_sources(tmp_path, [candidate()], [identity(exact=True)])
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = []
    monkeypatch.setattr(mod, "_send", lambda _bot, _chat, text, **_kw: calls.append(text))

    report = mod.run(tmp_path, datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))

    assert report["delivered_count"] == 1
    assert "Exact on-chain identity: VERIFIED" in calls[0]
    assert "Contract: 0xabc" in calls[0]
