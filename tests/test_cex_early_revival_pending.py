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
    assert report["version"] == 3
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


def test_w3gg_like_prewave_shadow_persists_if_identity_misses_first_scan(tmp_path: Path):
    shadow = {
        "symbol": "W3GGUSDT",
        "spot_revival_score": 20,
        "coherent_confirmations": 1,
        "change_24h_max_pct": 0.48,
        "volume_acceleration_max_pct": 178.1256,
        "volume_window_multiple_max": 1.4,
        "shadow_features": ["VOLUME_PRICE_ABSORPTION_SHADOW"],
        "slow_ignition": {"status": "NONE", "confirmations": 0},
        "milestones": {
            "first_seen": {
                "observed_at": "2026-09-04T10:50:55+00:00",
                "reference_price": 0.0004924,
            },
            "first_shadow_watch": {
                "observed_at": "2026-09-14T20:27:10+00:00",
                "reference_price": 0.0004948,
                "reference_change_24h_pct": 0.48,
                "shadow_features": ["VOLUME_PRICE_ABSORPTION_SHADOW"],
            },
        },
    }
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        json.dumps({"watchlist": [], "shadow_watchlist": [shadow]})
    )
    (tmp_path / "cex-spot-identity-radar.json").write_text(
        json.dumps({"candidates": []})
    )

    first = run(tmp_path)
    assert first["candidate_count"] == 1
    row = first["candidates"][0]
    assert row["base_symbol"] == "W3GG"
    assert row["prewave_identity_priority"] is True
    assert row["earliest_retained_milestone"] == "PREWAVE_SHADOW"
    assert row["prewave_volume_acceleration_pct"] == 178.1256
    assert row["research_only"] is True
    assert row["actionable"] is False

    # Even if the one-scan acceleration disappears, identity work remains queued.
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        json.dumps({"watchlist": [], "shadow_watchlist": []})
    )
    second = run(tmp_path)
    assert second["candidate_count"] == 1
    persisted = second["candidates"][0]
    assert persisted["prewave_identity_priority"] is True
    assert persisted["prewave_observed_at"] == "2026-09-14T20:27:10+00:00"
    assert second["truth_contract"]["prewave_shadow_persistence_is_identity_only"] is True
    assert second["truth_contract"]["prewave_shadow_never_actionable"] is True
