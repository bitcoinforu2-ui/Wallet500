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
    assert out["truth_contract"]["cex_only_never_real_alert"] is True
    assert out["truth_contract"]["persistent_pending_priority_is_ordering_only"] is True
    assert out["truth_contract"]["no_hindsight"] is True


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
