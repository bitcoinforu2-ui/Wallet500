import json
from datetime import datetime, timezone

from scripts import unified_candidate_bridge as bridge


def test_public_alpha_live_queue_excludes_stale_history(tmp_path, monkeypatch):
    alpha = {
        "candidates": [
            {
                "status": "GATED_RESEARCH_CANDIDATE",
                "symbol": "FRESH",
                "network": "solana",
                "contract": "FreshMint11111111111111111111111111111111",
                "pair": "FreshPair111111111111111111111111111111111",
                "called_at": "2026-09-19T09:30:00+00:00",
                "liquidity_usd": 1000,
            },
            {
                "status": "GATED_RESEARCH_CANDIDATE",
                "symbol": "OLD",
                "network": "solana",
                "contract": "OldMint111111111111111111111111111111111",
                "pair": "OldPair1111111111111111111111111111111111",
                "called_at": "2026-09-19T01:00:00+00:00",
                "liquidity_usd": 999999,
            },
        ]
    }
    paths = {
        "SPOT": tmp_path / "spot.json",
        "ALPHA": tmp_path / "alpha.json",
        "BUY_REGISTRY": tmp_path / "buy.json",
        "OUT": tmp_path / "out.json",
        "EVENTS": tmp_path / "events.json",
    }
    paths["SPOT"].write_text('{"candidates":[]}', encoding="utf-8")
    paths["ALPHA"].write_text(json.dumps(alpha), encoding="utf-8")
    paths["BUY_REGISTRY"].write_text('{"entries":{}}', encoding="utf-8")
    paths["EVENTS"].write_text('{"version":3,"events":[]}', encoding="utf-8")
    for name, path in paths.items():
        monkeypatch.setattr(bridge, name, path)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 19, 10, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(bridge, "datetime", FixedDatetime)
    bridge.main()

    result = json.loads(paths["OUT"].read_text(encoding="utf-8"))
    assert result["counts"]["public_alpha"] == 1
    assert result["counts"]["public_alpha_stale_excluded"] == 1
    assert result["candidates"][0]["symbol"] == "FRESH"
    assert result["candidates"][0]["alpha_age_minutes"] == 30.0


def test_alpha_age_missing_timestamp_fails_closed():
    assert bridge.alpha_age_minutes({}, current=datetime(2026, 9, 19, tzinfo=timezone.utc)) is None
