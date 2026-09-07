import json
from pathlib import Path

from wallet500 import cex_spot_leaderboard_bridge as bridge


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _state(*rows):
    markets = {}
    for exchange, symbol, change, volume, price in rows:
        markets[f"spot:{exchange}:{symbol}"] = [
            {
                "observed_at": "2026-09-07T07:20:00+00:00",
                "price": price,
                "change_24h_pct": change,
                "volume_24h": volume,
            }
        ]
    return {"version": 1, "markets": markets, "signal_milestones": {}}


def test_kct_like_smooth_top_gainer_is_injected_without_becoming_actionable(tmp_path: Path):
    _write(tmp_path / "cex-spot-state.json", _state(("gate", "KCTUSDT", 45.04, 546_200, 0.0029854)))
    _write(tmp_path / "cex-spot-revival-radar.json", {"version": 1, "watchlist": [], "alerts": []})

    report = bridge.run(tmp_path, "2026-09-07T07:30:00+00:00")
    radar = json.loads((tmp_path / "cex-spot-revival-radar.json").read_text())

    assert report["status"] == "OK"
    assert report["injected_count"] == 1
    row = radar["watchlist"][0]
    assert row["symbol"] == "KCTUSDT"
    assert row["spot_revival_score"] >= bridge.WATCH_SCORE
    assert row["leaderboard_watch"] is True
    assert row["leaderboard_best_rank"] == 1
    assert "LEADERBOARD_TOP10" in row["coherent_feature_hits"]
    assert row["research_only"] is True
    assert row["actionable"] is False
    assert row["identity_required_before_actionable"] is True


def test_high_move_with_too_little_turnover_is_not_injected(tmp_path: Path):
    _write(tmp_path / "cex-spot-state.json", _state(("gate", "THINUSDT", 120.0, 19_999, 0.001)))
    _write(tmp_path / "cex-spot-revival-radar.json", {"version": 1, "watchlist": [], "alerts": []})

    report = bridge.run(tmp_path, "2026-09-07T07:30:00+00:00")
    radar = json.loads((tmp_path / "cex-spot-revival-radar.json").read_text())

    assert report["leaderboard_symbols"] == 0
    assert report["injected_count"] == 0
    assert radar["watchlist"] == []


def test_existing_candidate_is_annotated_not_duplicated(tmp_path: Path):
    _write(tmp_path / "cex-spot-state.json", _state(("mexc", "NYMUSDT", 76.0, 331_000, 0.0326)))
    _write(
        tmp_path / "cex-spot-revival-radar.json",
        {
            "version": 1,
            "watchlist": [
                {
                    "symbol": "NYMUSDT",
                    "spot_revival_score": 36,
                    "status": "DNA_WATCH_RESEARCH",
                    "research_only": True,
                    "actionable": False,
                    "reasons": [],
                    "coherent_feature_hits": ["MOMENTUM"],
                    "confirmations": 3,
                    "coherent_confirmations": 2,
                }
            ],
            "alerts": [],
        },
    )

    report = bridge.run(tmp_path, "2026-09-07T07:30:00+00:00")
    radar = json.loads((tmp_path / "cex-spot-revival-radar.json").read_text())

    assert report["annotated_count"] == 1
    assert report["injected_count"] == 0
    assert len(radar["watchlist"]) == 1
    assert radar["watchlist"][0]["leaderboard_watch"] is True
