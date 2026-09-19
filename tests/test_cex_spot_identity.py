import json
from pathlib import Path

from wallet500 import cex_spot_identity as mod


def _seed(tmp_path: Path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-05T18:00:00+00:00",
        "watchlist": [{
            "symbol": "GXEUSDT",
            "spot_revival_score": 55,
            "exchanges": ["gate"],
            "markets": [{"exchange": "gate", "symbol": "GXEUSDT", "price": 0.0001}],
        }],
    }), encoding="utf-8")


def test_dynamic_spot_identity_stays_research_only(monkeypatch, tmp_path):
    _seed(tmp_path)

    def fake_age(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "coingecko_id": "project-xeno",
            "market_age_verified": True,
            "market_age_min_days": 1000,
            "market_age_evidence_at": "2023-01-01T00:00:00+00:00",
            "market_age_evidence_source": "TEST",
        })
        path.write_text(json.dumps(p))
        return {"accepted": 1, "rejected": 0, "rejections": []}

    def fake_exact(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "ethereum",
            "token_address": "0x510975eda48a97e0ca228dd04d1217292487bea6",
            "pair_address": "0xpair",
            "dex_price_usd": 0.000102,
            "dex_liquidity_usd": 1200,
        })
        p["platform_catalog"] = {"status": "OK"}
        p["identity_contract"] = {"exact_dex_pair_required": True}
        path.write_text(json.dumps(p))
        return {"dex_verified": 1}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)
    row = out["candidates"][0]
    assert out["status"] == "OK"
    assert out["counts"]["dex_verified"] == 1
    assert row["token_address"].lower() == "0x510975eda48a97e0ca228dd04d1217292487bea6"
    assert row["research_only"] is True
    assert row["actionable"] is False
    assert row["automatic_buy"] is False
    assert row["identity_attempted_at"]
    assert row["execution_pair_price_coherent"] is True
    assert out["truth_contract"]["cex_only_never_real_alert"] is True
    assert out["truth_contract"]["persistent_pending_priority_is_ordering_only"] is True
    assert out["truth_contract"]["dynamic_exact_pair_requires_current_cex_dex_price_coherence"] is True
    assert out["truth_contract"]["no_hindsight"] is True


def test_incoherent_exact_pair_fails_closed_and_quarantines_auto_registry(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-14T10:19:52+00:00",
        "watchlist": [{
            "symbol": "CPOOLUSDT",
            "spot_revival_score": 36,
            "markets": [
                {"exchange": "kucoin", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "USDT", "price": 0.03029, "volume_comparable_usd_like": True},
                {"exchange": "mexc", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "USDT", "price": 0.03034, "volume_comparable_usd_like": True},
                {"exchange": "gate", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "USDT", "price": 0.03019, "volume_comparable_usd_like": True},
                {"exchange": "upbit", "market_type": "spot", "symbol": "CPOOLUSDT", "quote_symbol": "KRW", "price": 41.1, "volume_comparable_usd_like": False, "regional_market": True},
            ],
        }],
    }), encoding="utf-8")
    (tmp_path / "cex-identity-registry.json").write_text(json.dumps({
        "version": 3,
        "symbols": {
            "CPOOL": {
                "coingecko_id": "clearpool",
                "chain": "solana",
                "token_address": "AeXrLftu8chuY4ctc6oDeG4dUx6Yr4aqeakUMFNvACdg",
                "market_age_evidence_at": "2024-01-01T00:00:00+00:00",
                "evidence_source": "AUTO_STRICT_CEX_SPOT_CGID_AGE_PLUS_EXACT_DEX_PAIR",
                "auto_verified_pair_address": "HxErbEaAT8wYAkyxXqmQcdUshgi7VuwmSEXkixkFvnF1",
                "auto_verified_at": "2026-09-10T11:44:24+00:00"
            }
        }
    }), encoding="utf-8")

    def fake_age(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "coingecko_id": "clearpool",
            "market_age_verified": True,
            "market_age_evidence_at": "2024-01-01T00:00:00+00:00",
        })
        path.write_text(json.dumps(p))
        return {"accepted": 1, "rejected": 0, "rejections": []}

    def fake_exact(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "solana",
            "token_address": "AeXrLftu8chuY4ctc6oDeG4dUx6Yr4aqeakUMFNvACdg",
            "pair_address": "HxErbEaAT8wYAkyxXqmQcdUshgi7VuwmSEXkixkFvnF1",
            "dex_price_usd": 0.1629,
            "dex_liquidity_usd": 202579.48,
            "dex_volume_h24": 0,
        })
        p["platform_catalog"] = {"status": "OK"}
        p["identity_contract"] = {"exact_dex_pair_required": True}
        path.write_text(json.dumps(p))
        return {"dex_verified": 1}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)
    row = out["candidates"][0]
    assert row["identity_status"] == "IDENTITY_RESOLVED_PAIR_PENDING"
    assert row["identity_verified"] is False
    assert row["identity_blocker"] == "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT"
    assert row["execution_pair_price_coherent"] is False
    assert row["cex_reference_price_sample_count"] == 3
    assert row["cex_reference_price_usd"] == 0.03029
    assert row["cex_dex_price_ratio"] > 5
    assert out["counts"]["dex_verified"] == 0
    assert out["counts"]["price_incoherent"] == 1
    assert out["auto_registry"]["quarantine"]["quarantined"] == ["CPOOL"]

    registry = json.loads((tmp_path / "cex-identity-registry.json").read_text())
    assert "CPOOL" not in registry["symbols"]
    assert registry["quarantined_symbols"]["CPOOL"]["quarantine_reason"] == "DEX_PRICE_INCOHERENT_WITH_CEX_SPOT"
    assert registry["quarantined_symbols"]["CPOOL"]["immutable_detection_history_untouched"] is True


def test_provider_failure_is_fail_closed(monkeypatch, tmp_path):
    _seed(tmp_path)

    def boom(path):
        raise RuntimeError("provider down")

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", boom)
    out = mod.run(tmp_path)
    assert out["status"] == "DEGRADED_FAIL_CLOSED"
    assert out["candidates"] == []
    assert out["counts"]["dex_verified"] == 0
    assert not (tmp_path / ".cex-spot-identity-work.json").exists()


def test_empty_spot_watch_is_healthy_empty(tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(
        json.dumps({"generated_at": "2026-09-05T18:00:00+00:00", "watchlist": []}),
        encoding="utf-8",
    )
    out = mod.run(tmp_path)
    assert out["status"] == "HEALTHY_EMPTY"
    assert out["candidates"] == []


def test_persistent_unresolved_candidate_is_prioritized_even_after_leaving_current_watch(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-11T10:00:00+00:00",
        "watchlist": [{"symbol": "LOWUSDT", "spot_revival_score": 20, "coherent_confirmations": 1}],
    }), encoding="utf-8")
    (tmp_path / "cex-early-revival-pending.json").write_text(json.dumps({
        "candidates": [{
            "symbol": "STORJUSDT",
            "persistent_until_exact_identity_resolution": True,
            "timing_quality": "EARLY_BREAKOUT_EVIDENCE",
            "first_alert_score": 35,
            "first_alert_coherent_confirmations": 2,
            "first_alert_observed_at": "2026-09-06T09:41:49+00:00",
            "first_watch_price_acceleration_max_pct": 3.0,
            "first_watch_volume_acceleration_max_pct": 10.0,
        }],
    }), encoding="utf-8")

    seen = []

    def fake_age(path):
        p = json.loads(path.read_text())
        seen.extend(x["symbol"] for x in p["alerts"])
        for row in p["alerts"]:
            row.update({
                "coingecko_id": row["symbol"].lower(),
                "market_age_verified": True,
                "market_age_evidence_at": "2024-01-01T00:00:00+00:00",
            })
        path.write_text(json.dumps(p))
        return {"accepted": len(p["alerts"]), "rejected": 0, "rejections": []}

    def fake_exact(path):
        p = json.loads(path.read_text())
        for idx, row in enumerate(p["alerts"]):
            row.update({
                "identity_status": "DEX_VERIFIED",
                "identity_verified": True,
                "chain": "ethereum",
                "token_address": f"0xtoken{idx}",
                "pair_address": f"0xpair{idx}",
            })
        path.write_text(json.dumps(p))
        return {"dex_verified": len(p["alerts"])}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)

    assert seen[0] == "STORJUSDT"
    assert out["identity_queue"]["persistent_carried_when_absent_from_current_watch"] == 1
    assert out["identity_queue"]["selected_persistent_count"] == 1
    assert out["identity_queue"]["ordering_only"] is True
    assert out["production_portfolio_impact"] == "NONE"
    assert out["automatic_buy"] is False


def test_priority_never_marks_symbol_only_candidate_actionable(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({"watchlist": []}), encoding="utf-8")
    (tmp_path / "cex-early-revival-pending.json").write_text(json.dumps({
        "candidates": [{
            "symbol": "PENDINGUSDT",
            "persistent_until_exact_identity_resolution": True,
            "first_alert_score": 99,
            "first_alert_coherent_confirmations": 9,
        }],
    }), encoding="utf-8")

    def fake_age(path):
        return {"accepted": 0, "rejected": 1, "rejections": [{"symbol": "PENDINGUSDT", "reason": "AMBIGUOUS"}]}

    def fake_exact(path):
        p = json.loads(path.read_text())
        p["alerts"][0].update({"identity_status": "IDENTITY_PENDING", "identity_verified": False})
        path.write_text(json.dumps(p))
        return {"dex_verified": 0}

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    out = mod.run(tmp_path)
    row = out["candidates"][0]
    assert row["identity_verified"] is False
    assert row["actionable"] is False
    assert row["automatic_buy"] is False
    assert out["truth_contract"]["persistent_pending_never_satisfies_identity"] is True

def test_inconclusive_coingecko_extrema_uses_strict_exact_pair_age_fallback(monkeypatch, tmp_path):
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "generated_at": "2026-09-19T05:00:00+00:00",
        "watchlist": [{
            "symbol": "AKEUSDT",
            "spot_revival_score": 38,
            "coherent_confirmations": 3,
            "exchanges": ["gate", "mexc", "okx"],
            "markets": [
                {"exchange": "gate", "market_type": "spot", "symbol": "AKEUSDT", "quote_symbol": "USDT", "price": 0.0144, "volume_comparable_usd_like": True},
                {"exchange": "mexc", "market_type": "spot", "symbol": "AKEUSDT", "quote_symbol": "USDT", "price": 0.0143, "volume_comparable_usd_like": True},
            ],
        }],
    }), encoding="utf-8")

    def fake_age(path):
        p = json.loads(path.read_text())
        p["alerts"] = []
        path.write_text(json.dumps(p))
        return {
            "accepted": 0,
            "rejected": 1,
            "rejections": [{
                "symbol": "AKEUSDT",
                "base_symbol": "AKE",
                "reason": "AGE_MINIMUM_NOT_PROVEN_BY_COINGECKO_EXTREMA",
                "coingecko_id": "akedo",
            }],
        }

    def fake_exact(path):
        return {"dex_verified": 0}

    seen = {}

    def fake_fallback(row):
        seen.update(row)
        return {
            **row,
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "bsc",
            "token_address": "0x2c3a8ee94ddd97244a93bc48298f97d2c412f7db",
            "pair_address": "0xpair",
            "dex_price_usd": 0.01435,
            "dex_liquidity_usd": 3_000_000,
            "market_age_verified": True,
            "market_age_min_days": 341,
            "market_age_evidence_at": "2025-09-28T09:00:00+00:00",
            "market_age_evidence_source": "DEXSCREENER_EXACT_SYMBOL_PRICE_PAIR_AGE_FALLBACK",
        }

    monkeypatch.setattr(mod, "verify_age_and_coin_identity", fake_age)
    monkeypatch.setattr(mod, "resolve_exact_identity", fake_exact)
    monkeypatch.setattr(mod, "resolve_dex_fallback", fake_fallback)

    out = mod.run(tmp_path)
    row = out["candidates"][0]

    assert seen["coingecko_id"] == "akedo"
    assert row["identity_status"] == "DEX_VERIFIED"
    assert row["identity_verified"] is True
    assert row["market_age_verified"] is True
    assert row["age_preflight_rejection_reason"] == "AGE_MINIMUM_NOT_PROVEN_BY_COINGECKO_EXTREMA"
    assert row["research_only"] is True
    assert row["actionable"] is False
    assert out["counts"]["dex_fallback_verified"] == 1
    assert out["counts"]["age_inconclusive_fallback_verified"] == 1
    assert out["truth_contract"]["dex_fallback_for_missing_or_inconclusive_age_evidence"] is True
    assert out["truth_contract"]["dex_fallback_never_waives_ambiguous_coin_identity"] is True
