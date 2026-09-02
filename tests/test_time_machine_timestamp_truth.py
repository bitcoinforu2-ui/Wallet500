import json
from pathlib import Path

from wallet500.time_machine import run_time_machine


def test_time_machine_uses_timestamp_horizons_and_tracks_drawdown(tmp_path: Path):
    state = {
        "markets": {
            "gate:TESTUSDT": [
                {"observed_at":"2026-09-02T00:00:00+00:00","price":100,"volume_24h":1000,"open_interest":100,"funding_rate":0},
                {"observed_at":"2026-09-02T00:05:00+00:00","price":102,"volume_24h":1100,"open_interest":105,"funding_rate":0.0006},
                {"observed_at":"2026-09-02T00:10:00+00:00","price":90,"volume_24h":1150,"open_interest":106,"funding_rate":0.0006},
                {"observed_at":"2026-09-02T00:20:00+00:00","price":112,"volume_24h":1200,"open_interest":108,"funding_rate":0.0006},
                {"observed_at":"2026-09-02T00:40:00+00:00","price":120,"volume_24h":1300,"open_interest":110,"funding_rate":0.0006},
                {"observed_at":"2026-09-02T01:10:00+00:00","price":108,"volume_24h":1350,"open_interest":112,"funding_rate":0.0006},
            ]
        }
    }
    (tmp_path / "cex-state.json").write_text(json.dumps(state), encoding="utf-8")

    payload = run_time_machine(tmp_path, "2026-09-02T02:00:00+00:00")

    assert payload["method"] == "NO_HINDSIGHT_TIMESTAMP_EXACT_REPLAY"
    assert payload["horizons_seconds"]["15m"] == 900
    sample = next(x for x in payload["samples"] if x["observed_at"] == "2026-09-02T00:05:00+00:00")
    # 15m is resolved by actual elapsed time (00:20), not by the next list index.
    assert sample["returns_at_horizon_pct"]["15m"] == round((112 / 102 - 1) * 100, 4)
    # The adverse move at 00:10 must remain visible even though price later rallies.
    assert sample["max_drawdown_pct"] == round((90 / 102 - 1) * 100, 4)
    assert sample["max_gain_pct"] >= sample["returns_at_horizon_pct"]["15m"]
