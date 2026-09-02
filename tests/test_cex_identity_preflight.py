from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from wallet500 import cex_identity_preflight as p


def old_date(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_ambiguous_symbol_uses_strict_cex_price_coherence(tmp_path, monkeypatch):
    path = tmp_path / "cex.json"
    path.write_text(json.dumps({
        "alerts": [{
            "symbol": "UAIUSDT",
            "markets": [
                {"exchange": "gate", "price": 0.566},
                {"exchange": "kucoin", "price": 0.568},
                {"exchange": "bitget", "price": 0.567},
            ],
            "exchanges": ["gate", "kucoin", "bitget"],
        }]
    }))
    monkeypatch.setattr(p, "_fetch_by_symbols", lambda _symbols: {
        "UAI": [
            {"id": "wrong-uai", "symbol": "uai", "current_price": 0.031, "ath_date": old_date(600), "atl_date": old_date(500)},
            {"id": "unifai-network", "symbol": "uai", "current_price": 0.567, "ath_date": old_date(300), "atl_date": old_date(250)},
        ]
    })
    report = p.run(path)
    out = json.loads(path.read_text())
    assert report["accepted"] == 1
    assert out["alerts"][0]["coingecko_id"] == "unifai-network"
    assert out["alerts"][0]["cex_identity_preflight_verified"] is True
    assert out["alerts"][0]["cex_identity_preflight"]["method"] == "CEX_PRICE_COHERENCE"
    assert out["alerts"][0]["market_age_min_days"] >= 180


def test_ambiguous_symbol_stays_fail_closed_when_not_distinguishable(tmp_path, monkeypatch):
    path = tmp_path / "cex.json"
    path.write_text(json.dumps({
        "alerts": [{"symbol": "AMBUSD T".replace(" ", ""), "markets": [{"exchange": "gate", "price": 1.0}], "exchanges": ["gate"]}]
    }))
    monkeypatch.setattr(p, "_fetch_by_symbols", lambda _symbols: {
        "AMB": [
            {"id": "amb-a", "symbol": "amb", "current_price": 1.01, "ath_date": old_date(500), "atl_date": old_date(400)},
            {"id": "amb-b", "symbol": "amb", "current_price": 0.99, "ath_date": old_date(500), "atl_date": old_date(400)},
        ]
    })
    monkeypatch.setattr(p, "_ticker_overlap", lambda *_args, **_kwargs: 0)
    report = p.run(path)
    assert report["accepted"] == 0
    assert report["rejected"] == 1
    assert report["rejections"][0]["reason"] == "AGE_IDENTITY_AMBIGUOUS"


def test_resolved_but_young_coin_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "cex.json"
    path.write_text(json.dumps({"alerts": [{"symbol": "YNGUSDT", "markets": [{"price": 2.0}]}]}))
    monkeypatch.setattr(p, "_fetch_by_symbols", lambda _symbols: {
        "YNG": [{"id": "young", "symbol": "yng", "current_price": 2.0, "ath_date": old_date(40), "atl_date": old_date(20)}]
    })
    report = p.run(path)
    assert report["accepted"] == 0
    assert report["rejections"][0]["reason"] == "UNDER_180_DAYS_OR_AGE_UNVERIFIED"
