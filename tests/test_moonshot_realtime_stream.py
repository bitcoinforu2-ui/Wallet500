import json
from pathlib import Path

from wallet500 import moonshot_realtime_stream as rt


MINT = "4nV5gNwwP68zUDat26ySChREqVaQaLudfJBkSgEzpump"


def test_parse_future_listing_exact_contract():
    rows = rt.parse_stream_payload({"data": {
        "id": "123",
        "created_at": "2026-09-10T20:00:00Z",
        "text": f"🚀 $TEST is coming to Moonshot! Contract Address: {MINT}",
    }})
    assert len(rows) == 1
    assert rows[0]["event_type"] == "MOONSHOT_FUTURE_LISTING"
    assert rows[0]["token"] == MINT
    assert rows[0]["source_owner"] == "moonshot"


def test_parse_verification_exact_contract():
    rows = rt.parse_stream_payload({"data": {
        "id": "124",
        "created_at": "2026-09-10T20:00:01Z",
        "text": f"$TEST is now verified on Moonshot. Contract Address: {MINT}",
    }})
    assert len(rows) == 1
    assert rows[0]["event_type"] == "MOONSHOT_VERIFIED"
    assert rows[0]["token"] == MINT


def test_ignores_symbol_only_and_unrelated_posts():
    assert rt.parse_stream_payload({"data": {"id": "1", "text": "$TEST is coming to Moonshot!"}}) == []
    assert rt.parse_stream_payload({"data": {"id": "2", "text": f"hello Contract Address: {MINT}"}}) == []


def test_send_is_per_contract_idempotent(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rt, "STATE_DIR", tmp_path)
    monkeypatch.setattr(rt, "STATE_PATH", state_path)
    sent = []
    monkeypatch.setattr(rt.fw, "_telegram_send", lambda text: (sent.append(text) or True, "SENT"))
    event = {
        "post_id": "123",
        "event_type": "MOONSHOT_VERIFIED",
        "token": MINT,
        "symbol": "TEST",
        "source_url": "https://x.com/moonshot/status/123",
        "published_at": "2026-09-10T20:00:01Z",
    }
    state = {"sent_event_keys": []}
    assert rt._send_event(event, state) is True
    assert rt._send_event(event, state) is False
    assert len(sent) == 1
    assert MINT in sent[0]
    persisted = json.loads(Path(state_path).read_text())
    assert f"123:{MINT}" in persisted["sent_event_keys"]
