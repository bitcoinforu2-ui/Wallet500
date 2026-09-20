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
    assert out["alerts"][0]["market_age_min_days"] >= 90


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
    assert report["rejections"][0]["reason"] == "AGE_MINIMUM_NOT_PROVEN_BY_COINGECKO_EXTREMA"
    assert report["recent_extrema_never_prove_young"] is True


def test_curated_native_registry_disambiguates_harmony_one_without_symbol_only_action(tmp_path, monkeypatch):
    path = tmp_path / "cex.json"
    path.write_text(json.dumps({
        "alerts": [{
            "symbol": "ONEUSDT",
            "markets": [
                {"exchange": "gate", "price": 0.00419},
                {"exchange": "mexc", "price": 0.00420},
                {"exchange": "kucoin", "price": 0.00418},
            ],
            "exchanges": ["gate", "mexc", "kucoin"],
        }]
    }))
    (tmp_path / "native-asset-identity-registry.json").write_text(json.dumps({
        "assets": {
            "harmony": {
                "symbol": "ONE",
                "chain": "harmony",
                "token_address": "0xcF664087a5bB0237a0BAd6742852ec6c8d69A27a",
                "representation_type": "CANONICAL_WRAPPED_NATIVE",
                "evidence_source": "HARMONY_OFFICIAL_DOCS_WRAPPED_ONE",
                "discovery_symbol_lookup": True,
            }
        }
    }))
    monkeypatch.setattr(p, "_fetch_by_symbols", lambda _symbols: {
        "ONE": [
            {"id": "one-token-a", "symbol": "one", "current_price": 0.00421, "ath_date": old_date(500), "atl_date": old_date(450)},
            {"id": "one-token-b", "symbol": "one", "current_price": 0.00418, "ath_date": old_date(500), "atl_date": old_date(450)},
            {"id": "one-token-c", "symbol": "one", "current_price": 1.0, "ath_date": old_date(500), "atl_date": old_date(450)},
            {"id": "harmony", "symbol": "one", "current_price": 0.00419, "ath_date": old_date(2500), "atl_date": old_date(2000)},
            {"id": "one-token-d", "symbol": "one", "current_price": 0.0039, "ath_date": old_date(500), "atl_date": old_date(450)},
            {"id": "one-token-e", "symbol": "one", "current_price": 0.04, "ath_date": old_date(500), "atl_date": old_date(450)},
            {"id": "one-token-f", "symbol": "one", "current_price": 4.0, "ath_date": old_date(500), "atl_date": old_date(450)},
        ]
    })
    monkeypatch.setattr(p, "_ticker_overlap", lambda *_args, **_kwargs: 0)

    report = p.run(path)
    out = json.loads(path.read_text())

    assert report["accepted"] == 1
    assert out["alerts"][0]["coingecko_id"] == "harmony"
    evidence = out["alerts"][0]["cex_identity_preflight"]
    assert evidence["method"] == "CURATED_NATIVE_REGISTRY_EXACT_COINGECKO_ID"
    assert evidence["registry_coingecko_id"] == "harmony"
    assert evidence["research_only_identity_hint"] is True
    assert report["curated_native_registry_enabled"] is True
    assert report["curated_native_registry_never_bypasses_downstream_exact_pair_or_buy_safety"] is True


def test_duplicate_curated_native_symbol_does_not_disambiguate_preflight(tmp_path, monkeypatch):
    path = tmp_path / "cex.json"
    path.write_text(json.dumps({
        "alerts": [{
            "symbol": "ONEUSDT",
            "markets": [{"exchange": "gate", "price": 0.00419}],
            "exchanges": ["gate"],
        }]
    }))
    (tmp_path / "native-asset-identity-registry.json").write_text(json.dumps({
        "assets": {
            "harmony": {
                "symbol": "ONE",
                "chain": "harmony",
                "token_address": "0xaaa",
                "representation_type": "CANONICAL_WRAPPED_NATIVE",
                "discovery_symbol_lookup": True,
            },
            "other-one": {
                "symbol": "ONE",
                "chain": "other",
                "token_address": "0xbbb",
                "representation_type": "CANONICAL_WRAPPED_NATIVE",
                "discovery_symbol_lookup": True,
            },
        }
    }))
    monkeypatch.setattr(p, "_fetch_by_symbols", lambda _symbols: {
        "ONE": [
            {"id": "harmony", "symbol": "one", "current_price": 0.00419, "ath_date": old_date(2000), "atl_date": old_date(1500)},
            {"id": "other-one", "symbol": "one", "current_price": 0.00418, "ath_date": old_date(500), "atl_date": old_date(400)},
        ]
    })
    monkeypatch.setattr(p, "_ticker_overlap", lambda *_args, **_kwargs: 0)

    report = p.run(path)
    assert report["accepted"] == 0
    assert report["rejections"][0]["reason"] == "AGE_IDENTITY_AMBIGUOUS"
    assert report["curated_native_registry_symbols"] == []
