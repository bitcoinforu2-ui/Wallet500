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
    assert out["truth_contract"]["cex_only_never_real_alert"] is True


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
