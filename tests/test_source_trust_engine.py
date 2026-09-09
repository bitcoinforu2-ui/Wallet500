from datetime import datetime, timezone

from wallet500 import source_trust_engine as s


def test_content_strength_rewards_explicit_trade_and_identity():
    row = {
        "text": "Bought a position because liquidity and wallet flow confirm the thesis",
        "explicit_contract": "0x" + "1" * 40,
        "market_snapshot": {"pair_address": "0x" + "2" * 40},
    }
    assert s._content_strength(row) >= 80


def test_independence_discount_for_cross_source_overlap():
    rows = [
        {"source_name": "A", "post_id": "1", "published_at": "2026-09-09T10:00:00+00:00", "symbol": "ABC"},
        {"source_name": "B", "post_id": "2", "published_at": "2026-09-09T10:30:00+00:00", "symbol": "ABC"},
    ]
    scores = s._independence_scores(rows)
    assert scores["1"] < 100
    assert scores["2"] < 100


def test_initial_call_requires_exact_identity_and_excludes_baseline():
    base = {
        "source_name": "AgentOBSRH",
        "post_id": "x1",
        "published_at": "2026-09-09T10:00:00+00:00",
        "market_snapshot": {
            "chain": "ethereum",
            "pair_address": "0x" + "2" * 40,
            "token_address": "0x" + "1" * 40,
            "price_usd": 0.01,
            "liquidity_usd": 100000,
            "pair_identity_locked": True,
        },
    }
    assert s._initial_call(base, 100) is not None
    assert s._initial_call({**base, "baseline_only": True}, 100) is None
    bad = dict(base)
    bad["market_snapshot"] = dict(base["market_snapshot"])
    bad["market_snapshot"].pop("pair_identity_locked")
    assert s._initial_call(bad, 100) is None


def test_source_trust_shrinks_small_samples_to_neutral_prior():
    calls = [{
        "source": "A",
        "identity_locked": True,
        "rug_flag": False,
        "max_drawdown_pct": -5,
        "earlyness_hours_to_20pct": 1,
        "horizons": {"24h": {"return_pct": 100}},
    }]
    card = s._source_card("A", calls)
    assert card["sample_confidence"] < 0.1
    assert 49 <= card["trust_score"] <= 55


def test_rug_definition_requires_liquidity_and_price_collapse(monkeypatch):
    call = {
        "published_at": "2026-09-09T10:00:00+00:00",
        "chain": "ethereum",
        "pair_address": "0x" + "2" * 40,
        "entry_price_usd": 1.0,
        "entry_liquidity_usd": 100000,
        "horizons": {},
        "observations": [],
        "rug_flag": False,
        "max_gain_pct": 0,
        "max_drawdown_pct": 0,
    }
    monkeypatch.setattr(s, "_pair_snapshot", lambda _: {"price_usd": 0.1, "liquidity_usd": 10000, "observed_at": "2026-09-09T12:00:00+00:00"})
    s._update_call(call, datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc))
    assert call["rug_flag"] is True


def test_missed_horizon_is_not_backfilled(monkeypatch):
    call = {
        "published_at": "2026-09-01T00:00:00+00:00",
        "chain": "ethereum",
        "pair_address": "0x" + "2" * 40,
        "entry_price_usd": 1.0,
        "entry_liquidity_usd": 100000,
        "horizons": {},
        "observations": [],
        "rug_flag": False,
        "max_gain_pct": 0,
        "max_drawdown_pct": 0,
    }
    monkeypatch.setattr(s, "_pair_snapshot", lambda _: {"price_usd": 2.0, "liquidity_usd": 100000, "observed_at": "2026-09-09T12:00:00+00:00"})
    s._update_call(call, datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc))
    assert call["horizons"]["1h"]["status"] == "MISSED_CAPTURE_WINDOW"
    assert call["horizons"]["24h"]["status"] == "MISSED_CAPTURE_WINDOW"
