import json
from datetime import datetime, timezone

from wallet500.stage_transition_telegram import run


NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def _write(tmp_path, candidates):
    (tmp_path / "candidate-evidence-envelope.json").write_text(
        json.dumps({"candidates": candidates}), encoding="utf-8"
    )


def _row(status="VERIFIED_WATCH", pair="PairA"):
    return {
        "token_address": "MintA",
        "symbol": "AAA",
        "pair_address": pair,
        "status": status,
        "market": {"liquidity_usd": 75000},
        "coverage": {"verified_independent_count": 3, "positive_independent_count": 2},
        "pending_confirmations": ["INDEPENDENT_EVIDENCE_PENDING"],
    }


def _never_send(*_args):
    raise AssertionError("stage Telegram must stay silent under FINAL_BUY_ONLY policy")


def test_first_run_baselines_without_historical_spam(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("PAPER_BUY_CANDIDATE")])
    report = run(str(tmp_path), NOW, sender=_never_send)
    assert report["baseline_only"] is True
    assert report["eligible_count"] == 0
    assert report["delivered_count"] == 0


def test_all_stage_transitions_are_internal_only(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("VERIFIED_WATCH")])
    run(str(tmp_path), NOW, sender=_never_send)

    for status in ("EVIDENCE_READY", "PAPER_BUY_CANDIDATE", "STRONG_GENESIS", "EXCEPTIONAL_GENESIS"):
        _write(tmp_path, [_row(status)])
        report = run(str(tmp_path), NOW, sender=_never_send)
        assert report["eligible_count"] == 0
        assert report["delivered_count"] == 0
        assert report["error_count"] == 0
        assert report["policy"]["telegram_delivery_enabled"] is False
        assert report["policy"]["final_buy_only"] is True
        assert report["policy"]["minimum_user_facing_stage"] == "DISABLED_FINAL_BUY_ONLY"


def test_exact_pair_change_never_creates_stage_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("EVIDENCE_READY", "PairA")])
    run(str(tmp_path), NOW, sender=_never_send)
    _write(tmp_path, [_row("PAPER_BUY_CANDIDATE", "PairB")])
    report = run(str(tmp_path), NOW, sender=_never_send)
    assert report["eligible_count"] == 0
    assert report["delivered_count"] == 0


def test_stage_state_still_tracks_engine_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("EVIDENCE_READY")])
    run(str(tmp_path), NOW, sender=_never_send)
    _write(tmp_path, [_row("PAPER_BUY_CANDIDATE")])
    report = run(str(tmp_path), NOW, sender=_never_send)
    assert report["delivered_count"] == 0
    state = json.loads((tmp_path / "stage-transition-telegram-state.json").read_text())
    key = "MintA|paira"
    assert state["candidates"][key]["stage"] == "PAPER_BUY_CANDIDATE"
