from __future__ import annotations

import json
from pathlib import Path

import wallet500.cryptoyeezus_identity_guard as g


def test_quarantines_wsol_mint_mislabelled_as_hood(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(g, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(g, "CALLS_PATH", tmp_path / "calls.json")
    monkeypatch.setattr(g, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(g, "PRIORITY_STATE_PATH", tmp_path / "priority.json")
    monkeypatch.setattr(g, "CORRECTIONS_PATH", tmp_path / "corrections.json")

    addr = "So11111111111111111111111111111111111111112"
    event_id = "x:2099155314952085789:ca:" + addr.lower()
    event = {
        "event_id": event_id,
        "event_type": "FIRST_MENTION",
        "source": "x",
        "source_post_id": "2099155314952085789",
        "url": "https://x.com/CryptoYeezussss/status/2099155314952085789",
        "symbol": "HOOD",
        "explicit_contract": addr,
        "market_snapshot": None,
        "pair_identity_locked": False,
        "risk_flags": [],
    }
    (tmp_path / "state.json").write_text(json.dumps({
        "tokens": {
            "ca:" + addr.lower(): {
                "symbol": "HOOD",
                "token_address": addr,
                "first_seen_at": "2026-09-13T15:16:42+00:00",
                "first_market_snapshot": None,
            }
        }
    }))
    (tmp_path / "calls.json").write_text(json.dumps({"events": [event]}))
    (tmp_path / "latest.json").write_text(json.dumps({"latest_events": [dict(event)]}))
    (tmp_path / "priority.json").write_text(json.dumps({
        "sent_event_ids": [event_id],
        "token_alerts": {
            "ca:" + addr.lower(): {
                "last_event_id": event_id,
                "sent_count": 1,
            }
        },
    }))

    out = g.run()
    assert out["new_corrections"] >= 1

    state = json.loads((tmp_path / "state.json").read_text())
    assert "ca:" + addr.lower() not in state["tokens"]
    assert state["tokens"]["symbol:HOOD"]["token_address"] is None
    assert state["tokens"]["symbol:HOOD"]["quarantined_contract_candidate"] == addr.lower()

    calls = json.loads((tmp_path / "calls.json").read_text())
    repaired = calls["events"][0]
    assert repaired["explicit_contract"] is None
    assert repaired["identity_status"] == "QUARANTINED_FALSE_EXACT_IDENTITY"
    assert "FALSE_EXACT_IDENTITY_QUARANTINED" in repaired["risk_flags"]

    priority = json.loads((tmp_path / "priority.json").read_text())
    bad_key = "ca:" + addr.lower()
    assert bad_key not in priority["token_alerts"]
    assert bad_key in priority["quarantined_token_alerts"]
    assert event_id in priority["sent_event_ids"]  # historical delivery audit retained


def test_does_not_quarantine_actual_sol_identity(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(g, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(g, "CALLS_PATH", tmp_path / "calls.json")
    monkeypatch.setattr(g, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(g, "PRIORITY_STATE_PATH", tmp_path / "priority.json")
    monkeypatch.setattr(g, "CORRECTIONS_PATH", tmp_path / "corrections.json")
    addr = "So11111111111111111111111111111111111111112"
    (tmp_path / "state.json").write_text(json.dumps({"tokens": {"ca:" + addr.lower(): {"symbol": "SOL", "token_address": addr}}}))
    (tmp_path / "calls.json").write_text(json.dumps({"events": []}))
    (tmp_path / "latest.json").write_text(json.dumps({"latest_events": []}))
    (tmp_path / "priority.json").write_text(json.dumps({"sent_event_ids": [], "token_alerts": {}}))
    out = g.run()
    assert out["new_corrections"] == 0
    state = json.loads((tmp_path / "state.json").read_text())
    assert "ca:" + addr.lower() in state["tokens"]
