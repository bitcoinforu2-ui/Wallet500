import json

from wallet500 import multichain_veteran_revival as mod


GXE = "0x510975eda48a97e0ca228dd04d1217292487bea6"


def _seed(tmp_path):
    (tmp_path / "cex-identity-registry.json").write_text(json.dumps({"symbols": {}}), encoding="utf-8")
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "watchlist": [{
            "symbol": "GXEUSDT",
            "spot_revival_score": 55,
            "exchanges": ["gate"],
            "coherent_confirmations": 1,
        }]
    }), encoding="utf-8")
    (tmp_path / "cex-spot-identity-radar.json").write_text(json.dumps({
        "status": "OK",
        "candidates": [{
            "symbol": "GXEUSDT",
            "spot_revival_score": 55,
            "exchanges": ["gate"],
            "coherent_confirmations": 1,
            "coingecko_id": "project-xeno",
            "market_age_verified": True,
            "market_age_evidence_at": "2023-01-01T00:00:00+00:00",
            "market_age_evidence_source": "COINGECKO_TEST",
            "identity_status": "DEX_VERIFIED",
            "identity_verified": True,
            "chain": "ethereum",
            "token_address": GXE,
            "pair_address": "0xpair",
        }]
    }), encoding="utf-8")


def test_dynamic_exact_identity_injects_candidate_without_manual_registry(tmp_path):
    _seed(tmp_path)
    rows = mod._discover_spot_registry_candidates(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["chain"] == "ethereum"
    assert row["token"].lower() == GXE
    assert row["dynamic_cex_spot_identity_verified"] is True
    assert "cex-spot-dynamic-exact-identity" in row["discovery_sources"]


def test_dynamic_exact_identity_confirms_current_spot_watch(tmp_path):
    _seed(tmp_path)
    out = mod._spot_exact_confirmation(tmp_path, "ethereum", GXE)
    assert out["verified"] is True
    assert out["reason"] == "DYNAMIC_EXACT_IDENTITY_PLUS_CEX_SPOT_WATCH"
    assert out["spot_revival_score"] == 55
