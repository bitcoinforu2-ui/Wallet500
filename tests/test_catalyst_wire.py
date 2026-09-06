from pathlib import Path

from wallet500 import catalyst_wire as cw


def test_classifies_listing_and_premarket():
    assert cw._classify("Exchange will list ABC on spot tomorrow", "MEXC_SPOT_LISTINGS")[0] == "SPOT_LISTING_EXPECTED"
    assert cw._classify("ABC enters pre-market call auction", "X")[0] == "PREMARKET_OR_AUCTION"
    assert cw._classify("ABCUSDT perpetual futures will launch", "X")[0] == "FUTURES_LISTING"


def test_kraken_roadmap_is_explicit_high_impact():
    assert cw._classify("ABC token", "KRAKEN_ROADMAP") == ("EXCHANGE_ROADMAP", 96)


def test_event_id_is_stable_across_whitespace():
    a = cw._event_id("S", "ABC", "SPOT_LISTING_EXPECTED", "will   list ABC")
    b = cw._event_id("S", "ABC", "SPOT_LISTING_EXPECTED", "will list ABC")
    assert a == b


def test_preliminary_filter_does_not_use_volume_liquidity_or_holder_growth(tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "DATA", tmp_path)
    (tmp_path / "multichain-veteran-revival.json").write_text(
        '{"items":[{"symbol":"ABC","chain":"base","token":"0x1111111111111111111111111111111111111111","market_age_days":240,"volume_h1":0,"liquidity_usd":0,"holder_growth":0}]}',
        encoding="utf-8",
    )
    u = cw._candidate_universe()
    assert u["ABC"]["preliminary_filter_pass"] is True
    assert "NO_VOLUME_LIQUIDITY_HOLDER_GROWTH_WEIGHT" in u["ABC"]["filter_policy"]


def test_known_young_token_stays_outside_veteran_alert_lane(tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "DATA", tmp_path)
    (tmp_path / "manual-watchlist.json").write_text(
        '[{"symbol":"NEW","chain":"base","token":"0x2222222222222222222222222222222222222222","market_age_days":10}]',
        encoding="utf-8",
    )
    u = cw._candidate_universe()
    assert u["NEW"]["preliminary_filter_pass"] is False


def test_api_first_snapshot_is_baseline_not_alert(monkeypatch):
    universe = {"ABC": {"symbol": "ABC", "token": "0x1", "chain": "base", "preliminary_filter_pass": True}}
    monkeypatch.setattr(cw, "_get", lambda url: ("json", [{"id": "ABC_USDT", "trade_status": "tradable", "buy_start": 123, "type": "normal"}]))
    events, health, state = cw._api_events("GATE_SPOT_INSTRUMENTS", "gate", "u", universe, {})
    assert events == []
    assert health["baseline"] is True
    assert "ABC" in state["snapshot"]


def test_api_new_instrument_emits_event(monkeypatch):
    universe = {"ABC": {"symbol": "ABC", "token": "0x1", "chain": "base", "preliminary_filter_pass": True}}
    monkeypatch.setattr(cw, "_get", lambda url: ("json", [{"id": "ABC_USDT", "trade_status": "untradable", "buy_start": 999, "type": "premarket"}]))
    events, health, _ = cw._api_events("GATE_SPOT_INSTRUMENTS", "gate", "u", universe, {"snapshot": {}})
    assert len(events) == 1
    assert events[0]["event_type"] == "PREMARKET_OR_AUCTION"
