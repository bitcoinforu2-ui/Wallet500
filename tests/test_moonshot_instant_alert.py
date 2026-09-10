import json
from datetime import datetime, timezone

from wallet500 import moonshot_future_listing_watch as fw
from wallet500 import moonshot_instant_alert as ia


MINT = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"
NOW = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "DATA", tmp_path)
    monkeypatch.setattr(fw, "LATEST_PATH", tmp_path / "moonshot-future-listing-latest.json")
    monkeypatch.setattr(fw, "STATE_PATH", tmp_path / "moonshot-future-listing-state.json")


def _event(wallet500_pass=False):
    return {
        "event_id": fw._event_key(MINT),
        "event_type": "MOONSHOT_FUTURE_LISTING",
        "chain": "solana",
        "token": MINT,
        "symbol": "TEST",
        "source_owner": "moonshot",
        "source_url": "https://x.com/moonshot/status/123",
        "published_at": "2026-09-10T19:59:30+00:00",
        "wallet500_gate": {"pass": wallet500_pass},
    }


def test_exact_contract_alert_sends_without_real_alert_gate(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    _write(fw.LATEST_PATH, {"events": [_event(wallet500_pass=False)]})
    _write(fw.STATE_PATH, {"version": 1, "alerted": {}})

    sent = []
    monkeypatch.setattr(fw, "_telegram_send", lambda text: (sent.append(text) or True, "SENT"))

    out = ia.run(NOW)
    assert out["telegram_delivered"] == 1
    assert out["attempts"][0]["wallet500_real_alert_pass"] is False
    assert len(sent) == 1
    assert "MOONSHOT OFFICIAL ANNOUNCEMENT" in sent[0]
    assert "CONTRACT / CA" in sent[0]
    assert MINT in sent[0]
    assert "NOT A BUY SIGNAL" in sent[0]

    state = json.loads(fw.STATE_PATH.read_text())
    row = state["alerted"][fw._event_key(MINT)]
    assert row["alert_type"] == "MOONSHOT_OFFICIAL_ANNOUNCEMENT_EXACT_CONTRACT"
    assert row["wallet500_gate_required"] is False
    assert row["automatic_buy"] is False


def test_instant_alert_is_idempotent_and_prevents_duplicate(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    _write(fw.LATEST_PATH, {"events": [_event(wallet500_pass=False)]})
    _write(fw.STATE_PATH, {"version": 1, "alerted": {}})

    sent = []
    monkeypatch.setattr(fw, "_telegram_send", lambda text: (sent.append(text) or True, "SENT"))
    assert ia.run(NOW)["telegram_delivered"] == 1
    assert ia.run(NOW)["telegram_delivered"] == 0
    assert len(sent) == 1


def test_symbol_only_or_nonofficial_event_never_alerts(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    bad_symbol_only = _event()
    bad_symbol_only["token"] = ""
    bad_other_source = _event()
    bad_other_source["event_id"] = "other"
    bad_other_source["source_owner"] = "not-moonshot"
    _write(fw.LATEST_PATH, {"events": [bad_symbol_only, bad_other_source]})
    _write(fw.STATE_PATH, {"version": 1, "alerted": {}})

    sent = []
    monkeypatch.setattr(fw, "_telegram_send", lambda text: (sent.append(text) or True, "SENT"))
    out = ia.run(NOW)
    assert out["eligible_exact_contract_events"] == 0
    assert out["telegram_attempts"] == 0
    assert sent == []


def test_failed_telegram_send_is_retried_next_run(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    _write(fw.LATEST_PATH, {"events": [_event()]})
    _write(fw.STATE_PATH, {"version": 1, "alerted": {}})

    calls = []
    results = iter([(False, "HTTP_500"), (True, "SENT")])

    def fake_send(text):
        calls.append(text)
        return next(results)

    monkeypatch.setattr(fw, "_telegram_send", fake_send)
    assert ia.run(NOW)["telegram_delivered"] == 0
    assert ia.run(NOW)["telegram_delivered"] == 1
    assert len(calls) == 2
