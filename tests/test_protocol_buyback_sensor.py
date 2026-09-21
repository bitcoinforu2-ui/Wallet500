from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts import free_intelligence_collector as fic


def _day(offset: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


def _target():
    return {
        "symbol": "PUMP",
        "network": "solana",
        "contract": "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn",
        "pair": "2uF4Xh61rDwxnG9woyxsVQP7zuA6kLFpb3NvnRQeoiSd",
        "free_intel": {
            "buyback_sensor": {
                "enabled": True,
                "protocol_name": "pump.fun",
                "buyback_source_name": "Pump.fun Buyback API",
                "buyback_endpoint": "https://fees.pump.fun/api/buybacks",
                "defillama_fees_slug": "pump.fun",
                "source_semantics": "ONCHAIN_BURN_AGGREGATED_PROTOCOL_BUYBACK",
                "revenue_buyback_share_pct": 50,
                "min_execution_delta_usd": 25000,
                "bootstrap_current_day_min_usd": 1000000,
                "spike_multiple_7d": 1.5,
                "revenue_acceleration_multiple_7d": 1.35,
                "pressure_bps_mcap_trigger": 2,
                "corroboration_min_ratio": 0.7,
            }
        },
    }


def _series(current: float, baseline: float = 500_000.0):
    return {
        _day(-8): baseline,
        _day(-7): baseline,
        _day(-6): baseline,
        _day(-5): baseline,
        _day(-4): baseline,
        _day(-3): baseline,
        _day(-2): baseline,
        _day(-1): baseline,
        _day(0): current,
    }


def test_daily_value_series_supports_pump_and_defillama_shapes():
    pump = {"dailyBuybacks": {_day(-1): 100.0, _day(0): {"buybackUsd": 250.0}}}
    llama = {"totalDataChart": [[1720000000, 10.0], [1720086400, 20.0]]}

    p = fic.daily_value_series(pump)
    l = fic.daily_value_series(llama)

    assert p[-1] == (_day(0), 250.0)
    assert len(l) == 2
    assert l[-1][1] == 20.0


def test_buyback_sensor_emits_execution_acceleration_and_revenue_lead(monkeypatch):
    primary = {"dailyBuybacks": _series(2_000_000.0)}
    holders = {"totalDataChart": [[d, v * 0.95] for d, v in _series(2_000_000.0).items()]}
    revenue = {"totalDataChart": [[d, (4_000_000.0 if d == _day(0) else 1_200_000.0)] for d in _series(1).keys()]}

    def fake_get_json(url, headers=None, timeout=12):
        if "dailyHoldersRevenue" in url:
            return holders
        if "dailyRevenue" in url:
            return revenue
        if "fees.pump.fun/api/buybacks" in url:
            return primary
        raise AssertionError(url)

    monkeypatch.setattr(fic, "get_json", fake_get_json)
    events, snap = fic.protocol_buyback_collect(
        _target(),
        {},
        {"market_cap": 1_500_000_000.0, "liquidity": 20_000_000.0},
    )

    kinds = {e["kind"] for e in events}
    assert "buyback_execution" in kinds
    assert "buyback_acceleration" in kinds
    assert "revenue_change" in kinds
    execution = next(e for e in events if e["kind"] == "buyback_execution")
    assert execution["identity_verified"] is True
    assert execution["identity_scope"] == "EXPLICIT_PROTOCOL_TOKEN_TO_EXACT_PAIR_MAPPING"
    assert execution["observed_execution_delta_usd"] == 2_000_000.0
    assert execution["delta_mode"] == "CURRENT_DAY_FIRST_OBSERVATION"
    assert execution["cross_source_corroborated"] is True
    assert execution["first_observation"] is True
    assert snap["status"] == "OK"
    assert snap["buyback_pressure_bps_mcap"] > 0


def test_buyback_sensor_uses_same_day_increment_not_total(monkeypatch):
    primary = {"dailyBuybacks": _series(2_000_000.0)}

    def fake_get_json(url, headers=None, timeout=12):
        if "dailyHoldersRevenue" in url:
            return {"totalDataChart": [[d, v] for d, v in _series(2_000_000.0).items()]}
        if "dailyRevenue" in url:
            return {"totalDataChart": [[d, 1_000_000.0] for d in _series(1).keys()]}
        return primary

    monkeypatch.setattr(fic, "get_json", fake_get_json)
    events, snap = fic.protocol_buyback_collect(
        _target(),
        {"latest_date": _day(0), "latest_buyback_usd": 1_500_000.0},
        {"market_cap": 1_500_000_000.0, "liquidity": 20_000_000.0},
    )

    execution = next(e for e in events if e["kind"] == "buyback_execution")
    assert execution["observed_execution_delta_usd"] == 500_000.0
    assert execution["delta_mode"] == "SAME_DAY_INCREMENT"
    assert execution["first_observation"] is False
    assert snap["observed_delta_usd"] == 500_000.0



def test_buyback_acceleration_does_not_refresh_without_new_execution(monkeypatch):
    primary = {"dailyBuybacks": _series(2_000_000.0)}

    def fake_get_json(url, headers=None, timeout=12):
        if "dailyHoldersRevenue" in url:
            return {"totalDataChart": [[d, v] for d, v in _series(2_000_000.0).items()]}
        if "dailyRevenue" in url:
            return {"totalDataChart": [[d, 1_000_000.0] for d in _series(1).keys()]}
        return primary

    monkeypatch.setattr(fic, "get_json", fake_get_json)
    events, snap = fic.protocol_buyback_collect(
        _target(),
        {"latest_date": _day(0), "latest_buyback_usd": 2_000_000.0},
        {"market_cap": 1_500_000_000.0, "liquidity": 20_000_000.0},
    )

    kinds = {e["kind"] for e in events}
    assert "buyback_execution" not in kinds
    assert "buyback_acceleration" not in kinds
    assert snap["observed_delta_usd"] == 0.0



def test_buyback_sensor_fails_closed_when_sources_are_missing(monkeypatch):
    monkeypatch.setattr(fic, "get_json", lambda *args, **kwargs: None)
    events, snap = fic.protocol_buyback_collect(
        _target(),
        {},
        {"market_cap": 1_500_000_000.0, "liquidity": 20_000_000.0},
    )

    assert events == []
    assert snap["status"] == "SOURCE_UNAVAILABLE"


def test_daily_value_series_supports_declared_nested_adapter_shape():
    payload = {
        "result": {
            "history": [
                {"day": _day(-1), "notional": 125_000.0},
                {"day": _day(0), "notional": 350_000.0},
            ]
        }
    }

    series = fic.daily_value_series(
        payload,
        series_paths=["result.history"],
        value_keys=["notional"],
        date_keys=["day"],
    )

    assert series[-1] == (_day(0), 350_000.0)


def test_generic_registry_does_not_treat_corroboration_only_as_execution(monkeypatch):
    target = _target()
    target["free_intel"]["buyback_sensor"] = {
        "enabled": True,
        "defillama_fees_slug": "demo",
        "execution_sources": [
            {
                "adapter": "defillama_holders_revenue",
                "name": "Holder Revenue",
                "slug": "demo",
                "execution_proof": False,
                "corroboration_only": True,
                "semantics": "VALUE_ACCRUAL_CORROBORATION",
            }
        ],
        "min_execution_delta_usd": 25_000,
    }

    monkeypatch.setattr(
        fic,
        "get_json",
        lambda *args, **kwargs: {
            "totalDataChart": [[d, v] for d, v in _series(2_000_000.0).items()]
        },
    )
    events, snap = fic.protocol_buyback_collect(
        target,
        {},
        {"market_cap": 1_500_000_000.0, "liquidity": 20_000_000.0},
    )

    assert events == []
    assert snap["status"] == "SOURCE_UNAVAILABLE"
    assert snap["execution_proof_series_count"] == 0


def test_revenue_lead_does_not_refresh_when_same_day_funding_is_unchanged(monkeypatch):
    primary = {"dailyBuybacks": _series(2_000_000.0)}
    revenue = {
        "totalDataChart": [
            [d, (4_000_000.0 if d == _day(0) else 1_200_000.0)]
            for d in _series(1).keys()
        ]
    }

    def fake_get_json(url, headers=None, timeout=12):
        if "dailyHoldersRevenue" in url:
            return {"totalDataChart": [[d, v] for d, v in _series(2_000_000.0).items()]}
        if "dailyRevenue" in url:
            return revenue
        return primary

    monkeypatch.setattr(fic, "get_json", fake_get_json)
    events, snap = fic.protocol_buyback_collect(
        _target(),
        {
            "latest_date": _day(0),
            "latest_buyback_usd": 2_000_000.0,
            "revenue": {
                "latest_date": _day(0),
                "latest_revenue_usd": 4_000_000.0,
            },
        },
        {"market_cap": 1_500_000_000.0, "liquidity": 20_000_000.0},
    )

    kinds = {e["kind"] for e in events}
    assert "revenue_change" not in kinds
    assert snap["revenue"]["observed_funding_delta_usd"] == 0.0
