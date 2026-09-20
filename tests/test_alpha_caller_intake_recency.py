from __future__ import annotations

import json
from datetime import datetime, timezone

import scripts.alpha_caller_intake as intake


SOL = "So11111111111111111111111111111111111111112"


def test_stale_alpha_history_skips_network_lookup(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox.json"
    events = tmp_path / "events.json"
    out = tmp_path / "out.json"

    inbox.write_text(
        json.dumps({
            "calls": [
                {
                    "caller": "Old Caller",
                    "source": "Telegram",
                    "contract": SOL,
                    "network": "solana",
                    "called_at": "2026-09-20T05:00:00+00:00",
                },
                {
                    "caller": "Fresh Caller",
                    "source": "Telegram",
                    "contract": SOL,
                    "network": "solana",
                    "called_at": "2026-09-20T09:30:00+00:00",
                },
            ]
        }),
        encoding="utf-8",
    )
    events.write_text('{"version":2,"events":[]}', encoding="utf-8")

    monkeypatch.setattr(intake, "INBOX", inbox)
    monkeypatch.setattr(intake, "EVENTS", events)
    monkeypatch.setattr(intake, "OUT", out)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 20, 10, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(intake, "datetime", FixedDatetime)

    calls = {"count": 0}

    def fake_get_json(url, timeout=12):
        calls["count"] += 1
        return {
            "pairs": [{
                "chainId": "solana",
                "pairAddress": "Pair111111111111111111111111111111111111",
                "baseToken": {"address": SOL, "symbol": "FRESH"},
                "quoteToken": {"address": "USDC"},
                "liquidity": {"usd": 50000},
                "url": "https://dexscreener.com/solana/example",
            }]
        }

    monkeypatch.setattr(intake, "get_json", fake_get_json)
    intake.main()

    doc = json.loads(out.read_text(encoding="utf-8"))
    assert calls["count"] == 1
    assert doc["candidates"][0]["status"] == "STALE_HISTORY_SKIPPED"
    assert "OUTSIDE_LIVE_WINDOW_NO_NETWORK_LOOKUP" in doc["candidates"][0]["reasons"]
    assert doc["candidates"][1]["status"] == "GATED_RESEARCH_CANDIDATE"
