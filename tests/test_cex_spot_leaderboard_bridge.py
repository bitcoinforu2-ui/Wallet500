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


def test_current_four_part_state_key_keeps_raw_market_id_out_of_canonical_symbol(tmp_path: Path):
    state = {
        "version": 3,
        "markets": {
            "spot:gate:BRUSDT:BR_USDT": [{
                "observed_at": "2026-09-14T15:48:44+00:00",
                "price": 0.51485,
                "change_24h_pct": 82.18,
                "volume_24h": 3_234_519.08,
            }],
            "spot:kucoin:BRUSDT:BR-USDT": [{
                "observed_at": "2026-09-14T15:48:44+00:00",
                "price": 0.51519,
                "change_24h_pct": 79.9,
                "volume_24h": 1_617_898.89,
            }],
        },
        "signal_milestones": {},
    }
    _write(tmp_path / "cex-spot-state.json", state)
    _write(tmp_path / "cex-spot-revival-radar.json", {"version": 4, "watchlist": [], "alerts": []})

    report = bridge.run(tmp_path, "2026-09-14T15:50:00+00:00")
    radar = json.loads((tmp_path / "cex-spot-revival-radar.json").read_text())

    assert report["injected_count"] == 1
    assert report["leaderboard_symbols"] == 1
    row = radar["watchlist"][0]
    assert row["symbol"] == "BRUSDT"
    assert row["confirmations"] == 2
    assert {m["market_id"] for m in row["markets"]} == {"BR_USDT", "BR-USDT"}
    assert all(":" not in m["symbol"] for m in row["markets"])


def test_upbit_native_turnover_is_never_scored_as_usd(tmp_path: Path):
    state = {
        "version": 3,
        "markets": {
            "spot:upbit:EDGEUSDT:KRW-EDGE": [{
                "observed_at": "2026-09-19T07:10:00+00:00",
                "price": 131.0,
                "change_24h_pct": 40.0,
                "volume_24h": 32_000_000_000.0,
                "quote_symbol": "KRW",
                "volume_comparable_usd_like": False,
                "regional_market": True,
                "market_id": "KRW-EDGE",
            }],
        },
        "signal_milestones": {},
    }
    _write(tmp_path / "cex-spot-state.json", state)
    _write(tmp_path / "cex-spot-revival-radar.json", {"version": 4, "watchlist": [], "alerts": []})

    report = bridge.run(tmp_path, "2026-09-19T07:11:00+00:00")
    item = report["leaderboard"][0]
    radar = json.loads((tmp_path / "cex-spot-revival-radar.json").read_text())
    row = radar["watchlist"][0]

    assert item["symbol"] == "EDGEUSDT"
    assert item["volume_24h_max"] == 0
    assert item["volume_24h_scope"] == "USD_LIKE_QUOTES_ONLY"
    assert item["regional_exchanges"] == ["upbit"]
    assert item["boosted_score"] == 28
    assert row["confirmations"] == 1
    assert row["coherent_confirmations"] == 0


def test_regional_exchange_never_inflates_leaderboard_action_coherence(tmp_path: Path):
    state = {
        "version": 3,
        "markets": {
            "spot:gate:TESTUSDT:TEST_USDT": [{
                "observed_at": "2026-09-19T07:10:00+00:00",
                "price": 0.10,
                "change_24h_pct": 30.0,
                "volume_24h": 300_000.0,
                "quote_symbol": "USDT",
                "volume_comparable_usd_like": True,
                "regional_market": False,
            }],
            "spot:upbit:TESTUSDT:KRW-TEST": [{
                "observed_at": "2026-09-19T07:10:00+00:00",
                "price": 140.0,
                "change_24h_pct": 45.0,
                "volume_24h": 50_000_000_000.0,
                "quote_symbol": "KRW",
                "volume_comparable_usd_like": False,
                "regional_market": True,
            }],
        },
        "signal_milestones": {},
    }
    _write(tmp_path / "cex-spot-state.json", state)
    _write(tmp_path / "cex-spot-revival-radar.json", {"version": 4, "watchlist": [], "alerts": []})

    bridge.run(tmp_path, "2026-09-19T07:11:00+00:00")
    radar = json.loads((tmp_path / "cex-spot-revival-radar.json").read_text())
    row = radar["watchlist"][0]

    assert row["confirmations"] == 2
    assert row["coherent_confirmations"] == 1
    assert row["leaderboard_usd_like_exchanges"] == ["gate"]
    assert row["leaderboard_regional_exchanges"] == ["upbit"]
