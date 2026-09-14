import json
from pathlib import Path

from wallet500 import cex_market_fragmentation as frag


def _state():
    ts1 = "2026-09-14T06:55:10+00:00"
    ts2 = "2026-09-14T07:10:10+00:00"
    return {
        "markets": {
            "spot:okx:LSKUSDT:LSK-USDT": [
                {"observed_at": ts1, "price": 0.445, "change_24h_pct": 20.0, "volume_24h": 10_000_000, "quote_symbol": "USDT"},
                {"observed_at": ts2, "price": 0.440, "change_24h_pct": 18.0, "volume_24h": 20_000_000, "quote_symbol": "USDT"},
            ],
            "spot:kucoin:LSKUSDT:LSK-USDT": [
                {"observed_at": ts1, "price": 0.927, "change_24h_pct": 25.0, "volume_24h": 4_000_000, "quote_symbol": "USDT"},
                {"observed_at": ts2, "price": 0.900, "change_24h_pct": 23.0, "volume_24h": 8_000_000, "quote_symbol": "USDT"},
            ],
            "spot:upbit:LSKUSDT:KRW-LSK": [
                {"observed_at": ts1, "price": 548.0, "change_24h_pct": 108.0, "volume_24h": 569_000_000, "quote_symbol": "KRW"},
                {"observed_at": ts2, "price": 520.0, "change_24h_pct": 90.0, "volume_24h": 585_000_000, "quote_symbol": "KRW"},
            ],
        }
    }


def test_lsk_fragmentation_features_are_shadow_only():
    timeline = frag.build_timeline(_state())
    analyzed = frag.analyze_symbol(timeline["LSKUSDT"])
    first = analyzed[0]
    assert first["price_dispersion_ratio"] > 2.0
    assert "CROSS_VENUE_PRICE_DISPERSION_SHADOW" in first["shadow_features"]
    assert "REGIONAL_LEAD_DISLOCATION_SHADOW" in first["shadow_features"]
    assert "MARKET_FRAGMENTATION_COMPOSITE_SHADOW" in first["shadow_features"]
    assert first["shadow_only"] is True
    assert first["affects_score"] is False
    assert first["actionable"] is False


def test_regional_krw_price_is_not_mixed_into_usd_dispersion():
    timeline = frag.build_timeline(_state())
    first = frag.analyze_symbol(timeline["LSKUSDT"])[0]
    assert first["max_usd_like_price"] < 1.0
    assert first["min_usd_like_price"] > 0.4
    assert first["regional_venues"] == 1


def test_forward_first_feature_is_immutable(tmp_path: Path):
    state = _state()
    (tmp_path / "cex-spot-state.json").write_text(json.dumps(state))
    first = frag.run(tmp_path, "2026-09-14T07:15:00+00:00")
    saved1 = json.loads((tmp_path / "cex-market-fragmentation-state.json").read_text())
    observed = saved1["first_feature_observed"]["LSKUSDT"]["CROSS_VENUE_PRICE_DISPERSION_SHADOW"]["observed_at"]

    second = frag.run(tmp_path, "2026-09-14T08:15:00+00:00")
    saved2 = json.loads((tmp_path / "cex-market-fragmentation-state.json").read_text())
    assert saved2["first_feature_observed"]["LSKUSDT"]["CROSS_VENUE_PRICE_DISPERSION_SHADOW"]["observed_at"] == observed
    assert first["production_effect"] is False
    assert second["production_thresholds_modified"] is False
    assert second["liquidity_gate_modified"] is False
    assert second["identity_rules_modified"] is False
    assert second["focus_case"]["production_claim_allowed"] is False
