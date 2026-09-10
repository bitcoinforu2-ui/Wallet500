import json
from pathlib import Path

from wallet500 import cex_spot_divergence as div


def test_strong_cex_up_dex_down_divergence():
    assert div.classify(16.57, -20.84) == "CEX_UP_DEX_DOWN_STRONG_DIVERGENCE"


def test_aligned_when_moves_are_close():
    assert div.classify(12.0, 8.0) == "CEX_DEX_BROADLY_ALIGNED"


def test_missing_is_insufficient_coverage():
    assert div.classify(12.0, None) == "INSUFFICIENT_COVERAGE"


def test_run_enriches_only_exact_verified_pair(tmp_path: Path, monkeypatch):
    payload = {
        "candidates": [
            {
                "symbol": "LRCUSDT",
                "identity_status": "DEX_VERIFIED",
                "identity_verified": True,
                "chain": "ethereum",
                "pair_address": "0xpair",
                "change_24h_max_pct": 16.57,
                "research_only": True,
                "actionable": False,
            }
        ]
    }
    (tmp_path / "cex-spot-identity-radar.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(div, "_get_json", lambda url: {"pairs": [{"pairAddress": "0xpair", "priceChange": {"h24": -20.84}}]})
    report = div.run(tmp_path)
    out = json.loads((tmp_path / "cex-spot-identity-radar.json").read_text())
    row = out["candidates"][0]
    assert report["enriched_count"] == 1
    assert row["cex_dex_divergence"]["status"] == "CEX_UP_DEX_DOWN_STRONG_DIVERGENCE"
    assert row["cex_dex_divergence"]["exact_pair_verified"] is True
    assert report["truth_contract"]["production_gates_unchanged"] is True
