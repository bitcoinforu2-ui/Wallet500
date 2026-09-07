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
