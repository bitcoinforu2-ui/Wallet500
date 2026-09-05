import json

from wallet500 import cex_spot_identity as identity
from wallet500 import multichain_veteran_revival as revival


GXE = "0x510975eda48a97e0ca228dd04d1217292487bea6"


def _seed(tmp_path):
    (tmp_path / "cex-identity-registry.json").write_text(
        json.dumps({"version": 2, "symbols": {}}), encoding="utf-8"
    )
    (tmp_path / "cex-spot-revival-radar.json").write_text(json.dumps({
        "watchlist": [{
            "symbol": "GXEUSDT",
            "spot_revival_score": 55,
            "exchanges": ["gate"],
            "coherent_confirmations": 1,
        }]
    }), encoding="utf-8")


def _verified_row():
    return {
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
    }


def test_strict_dynamic_identity_self_registers_then_existing_veteran_bridge_discovers_it(tmp_path):
    _seed(tmp_path)
    report = identity._persist_verified_registry(
        tmp_path, [_verified_row()], "2026-09-05T18:10:00+00:00"
    )
    assert report["added"] == ["GXE"]

    rows = revival._discover_spot_registry_candidates(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["chain"] == "ethereum"
    assert row["token"].lower() == GXE
    assert row["registry_identity_verified"] is True
    assert "cex-spot-exact-registry-trigger" in row["discovery_sources"]

    confirmation = revival._spot_exact_confirmation(tmp_path, "ethereum", GXE)
    assert confirmation["verified"] is True
    assert confirmation["reason"] == "EXACT_REGISTRY_IDENTITY_PLUS_CEX_SPOT_WATCH"
    assert confirmation["spot_revival_score"] == 55


def test_existing_registry_conflict_is_never_overwritten(tmp_path):
    _seed(tmp_path)
    path = tmp_path / "cex-identity-registry.json"
    path.write_text(json.dumps({
        "version": 2,
        "symbols": {
            "GXE": {
                "coingecko_id": "other-coin",
                "chain": "ethereum",
                "token_address": "0xdeadbeef",
                "market_age_evidence_at": "2023-01-01T00:00:00+00:00",
            }
        },
    }), encoding="utf-8")
    report = identity._persist_verified_registry(
        tmp_path, [_verified_row()], "2026-09-05T18:10:00+00:00"
    )
    assert report["added_count"] == 0
    assert report["conflict_count"] == 1
    after = json.loads(path.read_text())
    assert after["symbols"]["GXE"]["coingecko_id"] == "other-coin"
