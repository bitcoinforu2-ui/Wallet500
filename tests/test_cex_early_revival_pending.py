import json
from pathlib import Path

from wallet500.cex_early_revival_pending import run


def test_persists_high_value_first_alert_until_exact_identity(tmp_path: Path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "watchlist": [{
            "symbol": "BFCUSDT",
            "spot_revival_score": 28,
            "coherent_confirmations": 1,
            "change_24h_max_pct": 277.19,
            "milestones": {
                "first_alert": {
                    "observed_at": "2026-09-04T12:22:15+00:00",
                    "reference_price": 0.01123,
                    "reference_exchange": "kucoin",
                    "score": 43,
                    "coherent_confirmations": 2,
                }
            },
        }]
    }))
    (tmp_path / "cex-spot-identity-radar.json").write_text(json.dumps({"candidates": []}))

    first = run(tmp_path)
    assert first["candidate_count"] == 1
    row = first["candidates"][0]
    assert row["base_symbol"] == "BFC"
    assert row["first_alert_score"] == 43
    assert row["first_alert_coherent_confirmations"] == 2
    assert row["first_alert_reference_price"] == 0.01123
    assert row["actionable"] is False

    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({"watchlist": []}))
    second = run(tmp_path)
    assert second["candidate_count"] == 1
    assert second["candidates"][0]["first_alert_reference_price"] == 0.01123

    (tmp_path / "cex-spot-identity-radar.json").write_text(json.dumps({
        "candidates": [{
            "symbol": "BFCUSDT",
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
        }]
    }))
    third = run(tmp_path)
    assert third["candidate_count"] == 0


def test_retains_earlier_coherent_acceleration_watch_before_full_alert(tmp_path: Path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "watchlist": [{
            "symbol": "EARLYUSDT",
            "spot_revival_score": 27,
            "coherent_confirmations": 2,
            "change_24h_max_pct": 18.0,
            "milestones": {
                "first_watch": {
                    "observed_at": "2026-09-10T10:00:00+00:00",
                    "reference_price": 0.10,
                    "reference_exchange": "gate",
                    "reference_change_24h_pct": 18.0,
                    "change_24h_max_pct": 18.0,
                    "score": 27,
                    "coherent_confirmations": 2,
                    "price_acceleration_max_pct": 3.2,
                    "volume_acceleration_max_pct": 12.0,
                }
            },
        }]
    }))
    (tmp_path / "cex-spot-identity-radar.json").write_text(json.dumps({"candidates": []}))

    report = run(tmp_path)
    assert report["version"] == 2
    assert report["candidate_count"] == 1
    row = report["candidates"][0]
    assert row["earliest_retained_milestone"] == "FIRST_WATCH"
    assert row["timing_quality"] == "EARLY_BREAKOUT_EVIDENCE"
    assert row["first_watch_reference_price"] == 0.10
    assert row["actionable"] is False


def test_marks_already_extended_move_as_late_research_evidence(tmp_path: Path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "watchlist": [{
            "symbol": "LATEUSDT",
            "milestones": {
                "first_alert": {
                    "observed_at": "2026-09-10T12:00:00+00:00",
                    "reference_price": 0.36,
                    "reference_exchange": "kucoin",
                    "reference_change_24h_pct": 1116.0,
                    "change_24h_max_pct": 1116.0,
                    "score": 81,
                    "coherent_confirmations": 3,
                }
            },
        }]
    }))
    (tmp_path / "cex-spot-identity-radar.json").write_text(json.dumps({"candidates": []}))

    report = run(tmp_path)
    row = report["candidates"][0]
    assert row["timing_quality"] == "LATE_BREAKOUT_ALREADY_EXTENDED"
    assert row["actionable"] is False
