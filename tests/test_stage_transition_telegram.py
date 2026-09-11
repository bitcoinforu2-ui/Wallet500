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


def test_first_run_baselines_without_historical_spam(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("EVIDENCE_READY")])
    sent = []
    report = run(str(tmp_path), NOW, sender=lambda *args: sent.append(args))
    assert report["baseline_only"] is True
    assert report["eligible_count"] == 0
    assert sent == []


def test_watch_to_evidence_ready_sends_once(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("VERIFIED_WATCH")])
    run(str(tmp_path), NOW, sender=lambda *args: (1, 1))
    _write(tmp_path, [_row("EVIDENCE_READY")])
    sent = []
    report = run(str(tmp_path), NOW, sender=lambda *args: (sent.append(args) or (55, 1)))
    assert report["eligible_count"] == 1
    assert report["delivered_count"] == 1
    assert "RESEARCH → EVIDENCE_READY" in sent[0][2]
    report2 = run(str(tmp_path), NOW, sender=lambda *args: (_ for _ in ()).throw(AssertionError("duplicate")))
    assert report2["eligible_count"] == 0


def test_raw_research_changes_stay_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("VERIFIED_WATCH")])
    run(str(tmp_path), NOW, sender=lambda *args: (1, 1))
    _write(tmp_path, [_row("BLOCKED_TRUTH")])
    report = run(str(tmp_path), NOW, sender=lambda *args: (_ for _ in ()).throw(AssertionError("research spam")))
    assert report["eligible_count"] == 0


def test_exact_pair_change_does_not_inherit_previous_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("EVIDENCE_READY", "PairA")])
    run(str(tmp_path), NOW, sender=lambda *args: (1, 1))
    _write(tmp_path, [_row("EVIDENCE_READY", "PairB")])
    sent = []
    report = run(str(tmp_path), NOW, sender=lambda *args: (sent.append(args) or (2, 1)))
    # PairB is a new identity and should be treated as a fresh stage advance, not as PairA continuation.
    assert report["eligible_count"] == 1
    assert report["delivered_count"] == 1


def test_delivery_failure_does_not_consume_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _write(tmp_path, [_row("VERIFIED_WATCH")])
    run(str(tmp_path), NOW, sender=lambda *args: (1, 1))
    _write(tmp_path, [_row("EVIDENCE_READY")])
    report = run(str(tmp_path), NOW, sender=lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
    assert report["error_count"] == 1
    retry = run(str(tmp_path), NOW, sender=lambda *args: (99, 1))
    assert retry["delivered_count"] == 1
