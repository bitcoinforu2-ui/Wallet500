import json
from pathlib import Path

from wallet500 import cex_transfer_arbitrage_shadow as arb


def _state():
    ts = "2026-09-14T06:55:10+00:00"
    return {
        "markets": {
            "spot:okx:LSKUSDT:LSK-USDT": [
                {"observed_at": ts, "price": 0.44507, "quote_symbol": "USDT"},
            ],
            "spot:kucoin:LSKUSDT:LSK-USDT": [
                {"observed_at": ts, "price": 0.9276, "quote_symbol": "USDT"},
            ],
            "spot:upbit:LSKUSDT:KRW-LSK": [
                {"observed_at": ts, "price": 548.0, "quote_symbol": "KRW"},
            ],
        }
    }


def test_lsk_like_dislocation_is_detected_but_fails_closed_without_route():
    snapshots = arb.build_snapshots(_state())
    latest = snapshots["LSKUSDT"][-1]
    row = arb.analyze_snapshot("LSKUSDT", latest["observed_at"], latest["rows"], {})
    assert row is not None
    assert row["buy_exchange"] == "okx"
    assert row["sell_exchange"] == "kucoin"
    assert row["gross_spread_pct_proxy"] > 100.0
    assert row["extreme_dislocation_shadow"] is True
    assert row["route_verified"] is False
    assert "TRANSFER_ROUTE_UNVERIFIED" in row["blockers"]
    assert "EXECUTABLE_ORDERBOOK_QUOTES_MISSING" in row["blockers"]
    assert row["actionable"] is False
    assert row["automatic_transfer"] is False


def test_regional_quote_is_not_used_for_usd_arbitrage_price():
    snapshots = arb.build_snapshots(_state())
    latest = snapshots["LSKUSDT"][-1]
    row = arb.analyze_snapshot("LSKUSDT", latest["observed_at"], latest["rows"], {})
    assert row is not None
    assert row["sell_price_proxy"] < 1.0


def test_verified_route_still_requires_executable_orderbook_quotes():
    snapshots = arb.build_snapshots(_state())
    latest = snapshots["LSKUSDT"][-1]
    routes = {
        "routes": [{
            "symbol": "LSKUSDT",
            "from_exchange": "okx",
            "to_exchange": "kucoin",
            "network": "ethereum",
            "withdraw_enabled": True,
            "deposit_enabled": True,
            "same_asset_identity_verified": True,
        }]
    }
    row = arb.analyze_snapshot("LSKUSDT", latest["observed_at"], latest["rows"], routes)
    assert row is not None
    assert row["route_verified"] is True
    assert row["transfer_feasibility"] == "ROUTE_VERIFIED_EXECUTION_UNVERIFIED"
    assert row["blockers"] == ["EXECUTABLE_ORDERBOOK_QUOTES_MISSING"]
    assert row["actionable"] is False


def test_forward_first_dislocation_is_immutable(tmp_path: Path):
    (tmp_path / "cex-spot-state.json").write_text(json.dumps(_state()))
    first = arb.run(tmp_path, "2026-09-14T07:00:00+00:00")
    saved1 = json.loads((tmp_path / "cex-transfer-arbitrage-shadow-state.json").read_text())
    observed = saved1["first_transfer_dislocation"]["LSKUSDT"]["observed_at"]

    second = arb.run(tmp_path, "2026-09-14T08:00:00+00:00")
    saved2 = json.loads((tmp_path / "cex-transfer-arbitrage-shadow-state.json").read_text())
    assert saved2["first_transfer_dislocation"]["LSKUSDT"]["observed_at"] == observed
    assert first["production_effect"] is False
    assert second["actionable"] is False
    assert second["automatic_buy"] is False
    assert second["automatic_sell"] is False
    assert second["automatic_transfer"] is False
    assert second["truth_contract"]["missing_route_or_execution_data_fails_closed"] is True
