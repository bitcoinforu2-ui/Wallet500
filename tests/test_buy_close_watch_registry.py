from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from wallet500.buy_close_watch_registry import active_registry_candidates, upsert_buy_zone_registry


NOW = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)


def _buy_row(pair: str = "0xPAIR") -> dict:
    return {
        "chain": "ETH",
        "token_address": "0xABC",
        "pair_address": pair,
        "symbol": "TEST",
        "current_price_usd": 1.25,
        "telegram_buy_decision": {
            "recommended_action": "BUY",
            "state": "BUY_ZONE",
            "model_signal": "STRONG_BUY",
            "scores": {"composite": 84.0, "confidence": 82.0},
        },
    }


def test_final_buy_enters_highest_close_watch_immediately(tmp_path):
    payload = upsert_buy_zone_registry(tmp_path, [_buy_row()], now=NOW)

    key = "ethereum:0xabc:0xpair"
    assert payload["active_count"] == 1
    assert payload["activated_this_run"] == [key]

    row = payload["entries"][key]
    assert row["candidate_type"] == "BUY_ZONE"
    assert row["priority"] == "HIGHEST"
    assert row["close_watch"] == "HIGHEST"
    assert row["deep_investigation"] is True
    assert row["full_intelligence"] is True
    assert row["wallet_holder_intelligence"] is True
    assert row["search_news_intelligence"] is True
    assert row["market_microstructure_intelligence"] is True
    assert row["automatic_trade"] is False
    assert row["first_buy_price_usd"] == 1.25


def test_non_buy_never_enters_registry(tmp_path):
    row = _buy_row()
    row["telegram_buy_decision"]["recommended_action"] = "HOLD"
    row["telegram_buy_decision"]["state"] = "HOLD"

    payload = upsert_buy_zone_registry(tmp_path, [row], now=NOW)

    assert payload["active_count"] == 0
    assert payload["entries"] == {}


def test_buy_watch_is_durable_when_later_cycle_has_no_buy(tmp_path):
    upsert_buy_zone_registry(tmp_path, [_buy_row()], now=NOW)
    later = upsert_buy_zone_registry(tmp_path, [], now=NOW + timedelta(minutes=15))

    assert later["active_count"] == 1
    active = active_registry_candidates(tmp_path)
    assert len(active) == 1
    assert active[0]["active"] is True
    assert active[0]["first_buy_at"] == NOW.isoformat()
    assert later["truth_contract"]["no_silent_auto_deactivation"] is True


def test_exact_identity_is_mandatory(tmp_path):
    row = _buy_row()
    row["pair_address"] = ""
    payload = upsert_buy_zone_registry(tmp_path, [row], now=NOW)
    assert payload["active_count"] == 0
