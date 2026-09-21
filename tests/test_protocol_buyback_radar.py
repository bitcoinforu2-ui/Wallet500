from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import protocol_buyback_radar as radar


NOW = datetime.now(timezone.utc)
TOKEN = {
    "id": "demo",
    "protocol_name": "Demo",
    "symbol": "DEMO",
    "network": "solana",
    "contract": "Demo111111111111111111111111111111111111111",
    "pair": "Pair111111111111111111111111111111111111111",
    "dex_url": "https://example.test/pair",
    "min_liquidity_usd": 50_000,
    "min_volume_h1_usd": 15_000,
    "min_activity_h1": 50,
    "min_buy_sell_ratio": 1.2,
    "radar_pre_execution_score": 38,
    "radar_execution_score": 50,
}


def event(kind, family, *, minutes_ago=0, direction=1, **extra):
    ts = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return {
        "symbol": "DEMO",
        "network": TOKEN["network"],
        "contract": TOKEN["contract"],
        "pair": TOKEN["pair"],
        "family": family,
        "kind": kind,
        "direction": direction,
        "strength": 80,
        "confidence": 90,
        "event_time": ts,
        "observed_at": ts,
        **extra,
    }


def market_event(**extra):
    return event(
        "verified_market_snapshot",
        "market_microstructure",
        direction=0,
        identity_verified=True,
        price_usd=1.0,
        liquidity_usd=200_000,
        volume_h1_usd=50_000,
        buys_h1=80,
        sells_h1=20,
        price_change_h1_pct=5,
        price_change_h24_pct=20,
        **extra,
    )


def test_execution_pressure_escalates_to_internal_close_watch():
    events = [
        market_event(),
        event(
            "buyback_execution",
            "supply_tokenomics",
            identity_verified=True,
            observed_execution_delta_usd=1_500_000,
            latest_buyback_usd=2_000_000,
            multiple_vs_7d=2.0,
            buyback_pressure_bps_mcap=6.0,
            buyback_to_liquidity_pct=10.0,
            cross_source_corroborated=True,
        ),
        event(
            "buyback_acceleration",
            "supply_tokenomics",
            identity_verified=True,
            multiple_vs_7d=2.0,
        ),
        event("smart_money_netflow", "wallet_flow"),
    ]

    result = radar.evaluate(TOKEN, events, current=NOW)

    assert result["candidate"] is True
    assert result["status"] == "EXECUTION_CONFIRMED"
    assert result["radar_score"] >= 50
    assert result["direct_buy_eligible"] is False
    assert result["telegram_eligible"] is False
    assert result["truth_contract"]["buyback_signal_is_not_buy"] is True


def test_revenue_funding_pressure_can_prearm_before_execution():
    events = [
        market_event(),
        event(
            "revenue_change",
            "fundamental_usage",
            lead_signal=True,
            does_not_prove_execution=True,
            expected_buyback_funding_usd=500_000,
            revenue_multiple_vs_7d=1.7,
        ),
    ]

    result = radar.evaluate(TOKEN, events, current=NOW)

    assert result["candidate"] is True
    assert result["status"] == "PRE_EXECUTION_FUNDING_PRESSURE"
    assert result["execution"]["observed_execution_delta_usd"] == 0
    assert result["funding"]["expected_buyback_funding_usd"] == 500_000
    assert result["truth_contract"]["revenue_signal_does_not_prove_execution"] is True


def test_hard_risk_blocks_buyback_escalation():
    events = [
        market_event(),
        event(
            "buyback_execution",
            "supply_tokenomics",
            observed_execution_delta_usd=2_000_000,
            multiple_vs_7d=2.5,
            buyback_pressure_bps_mcap=10,
        ),
        event(
            "critical_liquidity_drain",
            "market_microstructure",
            direction=-1,
            hard_risk=True,
        ),
    ]

    result = radar.evaluate(TOKEN, events, current=NOW)

    assert result["candidate"] is False
    assert "HARD_RISK_PRESENT" in result["blockers"]
    assert "critical_liquidity_drain" in result["hard_risks"]


def test_stale_buyback_event_does_not_rearm_forever():
    events = [
        market_event(),
        event(
            "buyback_execution",
            "supply_tokenomics",
            minutes_ago=240,
            observed_execution_delta_usd=5_000_000,
            multiple_vs_7d=3.0,
            buyback_pressure_bps_mcap=20,
        ),
    ]

    result = radar.evaluate(TOKEN, events, current=NOW)

    assert result["candidate"] is False
    assert result["status"] == "WATCH"


def test_exact_identity_is_mandatory():
    broken = dict(TOKEN)
    broken["pair"] = ""
    result = radar.evaluate(broken, [], current=NOW)

    assert result["candidate"] is False
    assert result["status"] == "BLOCKED_IDENTITY"
    assert "EXACT_CHAIN_CONTRACT_PAIR_MISSING" in result["blockers"]


def test_active_registry_entries_have_exact_identity_and_explicit_source_semantics():
    path = Path(__file__).resolve().parents[1] / "data/protocol-buyback-registry.json"
    doc = json.loads(path.read_text())
    active = [x for x in doc.get("entries") or [] if x.get("active") is True]

    assert active
    for row in active:
        assert radar.identity(row) is not None
        sensor = row.get("buyback_sensor") or {}
        sources = sensor.get("execution_sources") or []
        assert sources
        execution_sources = [s for s in sources if s.get("execution_proof") is True]
        assert execution_sources
        for source in sources:
            assert source.get("adapter")
            assert source.get("semantics")
