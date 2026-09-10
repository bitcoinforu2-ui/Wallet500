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
