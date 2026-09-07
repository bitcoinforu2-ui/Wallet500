from wallet500 import catalyst_focus_binance as bcf


def test_binance_message_has_fire_priority(monkeypatch):
    event = {
        "source_owner": "binance",
        "source_id": "BINANCE_TELEGRAM",
        "symbol": "ABC",
        "chain": "bsc",
        "contract": "0x1111111111111111111111111111111111111111",
        "pair_address": "0x2222222222222222222222222222222222222222",
        "event_type": "SPOT_LISTING_EXPECTED",
        "binance_intelligence": {
            "applicable": True,
            "priority": "FIRE_PRIORITY",
            "relationship_score": 80,
            "relationship_grade": "HIGH",
            "relationship_class": "MULTI_STAGE_BINANCE_JOURNEY",
            "historical_official_events": 2,
            "program_journey": ["BINANCE_ALPHA", "SPOT_LISTING"],
            "ecosystem_involvement": {"status": "NOT_VERIFIED", "tags": []},
        },
        "market": {},
        "decision_score": 80,
        "grade": "A",
        "exchange_score": 98,
        "market_readiness_score": 80,
        "risk_score": 10,
    }
    text = bcf.startmsg(event)
    assert "🔥🔥 BINANCE PRIORITY ALERT" in text
    assert "80/100" in text
    assert "not probability and not BUY" in text


def test_non_binance_message_unchanged():
    event = {
        "source_owner": "mexc",
        "source_id": "MEXC_SPOT_LISTINGS",
        "symbol": "ABC",
        "market": {},
        "decision_score": 80,
        "grade": "A",
        "exchange_score": 60,
        "market_readiness_score": 80,
        "risk_score": 10,
        "binance_intelligence": {"applicable": False, "production_effect": False},
    }
    assert "BINANCE PRIORITY" not in bcf.startmsg(event)


def test_delisted_machine_state_can_never_be_focus_eligible(monkeypatch):
    event = {
        "source_owner": "coinbase",
        "source_id": "COINBASE_PRODUCTS",
        "source_kind": "OFFICIAL_MACHINE_STATE",
        "symbol": "ZEC",
        "event_type": "SPOT_LISTING_EXPECTED",
        "impact_score": 100,
        "excerpt": "COINBASE_PRODUCTS instrument change ZEC state=delisted type=spot start=None",
        "machine_state": {"state": "delisted", "start": None, "type": "spot"},
    }
    monkeypatch.setattr(
        bcf,
        "_BASE_SCORE_EVENT",
        lambda e: {
            **e,
            "decision_score": 89.17,
            "grade": "A+",
            "focus_eligible": True,
            "decision": "FOCUS_UNTIL_LISTING",
            "blockers": [],
        },
    )
    monkeypatch.setattr(bcf, "enrich_event", lambda e, data: e)
    scored = bcf.score_event(event)
    assert scored["focus_eligible"] is False
    assert scored["decision"] == "WATCH_SILENT_NEGATIVE_MACHINE_STATE"
    assert "NEGATIVE_EXCHANGE_MACHINE_STATE" in scored["blockers"]
    assert scored["negative_machine_state"] == "delisted"
    assert scored["machine_state_verdict"] == "NEGATIVE_FAIL_CLOSED"


def test_negative_state_text_also_fails_closed(monkeypatch):
    event = {
        "source_owner": "coinbase",
        "source_id": "COINBASE_PRODUCTS",
        "source_kind": "OFFICIAL_MACHINE_STATE",
        "symbol": "ABC",
        "event_type": "SPOT_LISTING_EXPECTED",
        "excerpt": "instrument change ABC state=disabled type=spot",
        "machine_state": {"state": None},
    }
    monkeypatch.setattr(bcf, "_BASE_SCORE_EVENT", lambda e: {**e, "focus_eligible": True, "blockers": []})
    monkeypatch.setattr(bcf, "enrich_event", lambda e, data: e)
    scored = bcf.score_event(event)
    assert scored["focus_eligible"] is False
    assert scored["negative_machine_state"] == "disabled"
