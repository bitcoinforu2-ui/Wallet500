import json
from pathlib import Path

from wallet500 import cex_fast_lane as fast


def test_collection_runs_before_governance_block(tmp_path: Path, monkeypatch):
    calls = {"futures": 0, "spot": 0}

    def fake_futures(out: Path, now: str):
        calls["futures"] += 1
        payload = {
            "version": 6,
            "generated_at": now,
            "healthy_sources": 3,
            "symbols_seen": 100,
            "alerts_count": 1,
            "alerts": [{"symbol": "IDOSUSDT", "cex_revival_score": 55}],
        }
        (out / "cex-revival-radar.json").write_text(json.dumps(payload), encoding="utf-8")
        (out / "cex-learning.json").write_text(json.dumps({"updated_at": now}), encoding="utf-8")
        return payload

    def fake_spot(out: Path, now: str):
        calls["spot"] += 1
        payload = {
            "generated_at": now,
            "healthy_sources": 4,
            "markets_seen": 500,
            "symbols_seen": 350,
            "watch_count": 2,
            "alerts_count": 1,
            "production_portfolio_impact": "NONE",
        }
        (out / "cex-spot-revival-radar.json").write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(fast, "run_cex_revival", fake_futures)
    monkeypatch.setattr(fast, "run_cex_spot_revival", fake_spot)
    monkeypatch.setattr(fast, "build_real_alerts", lambda out: {"alerts_count": 0})
    monkeypatch.setattr(fast, "MIN_AGE_DAYS", 180)
    monkeypatch.setattr(fast, "APPROVED_PRODUCTION_MIN_AGE_DAYS", 7)

    result = fast.run(tmp_path)

    assert calls == {"futures": 1, "spot": 1}
    assert result["status"] == "COLLECTED_BUT_ACTIONABLE_BLOCKED_BY_GOVERNANCE"
    assert result["raw_cex_alerts"] == 1
    assert result["spot_alerts_count"] == 1

    raw = json.loads((tmp_path / "cex-revival-raw.json").read_text(encoding="utf-8"))
    assert raw["alerts"][0]["symbol"] == "IDOSUSDT"

    published = json.loads((tmp_path / "cex-revival-radar.json").read_text(encoding="utf-8"))
    assert published["collection_status"] == "FRESH_COLLECTION_CONTINUES"
    assert published["raw_alerts_before_age_gate"] == 1
    assert published["alerts"] == []
    assert published["spot_collection"]["alerts_count"] == 1
