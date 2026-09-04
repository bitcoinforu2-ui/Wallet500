import json
from pathlib import Path

from wallet500.revival_pre_t0_prospective import run


def write(path: Path, name: str, payload: dict):
    (path / name).write_text(json.dumps(payload), encoding="utf-8")


def base_snapshot(captured_at="2026-09-04T10:00:00+00:00"):
    return {
        "record_id": "PRET0-abc",
        "evidence_sha256": "f" * 64,
        "token_address": "Mint1111111111111111111111111111111111111",
        "pair_address": "PairAbC111111111111111111111111111111111111",
        "captured_at": captured_at,
        "confirmation_shadow": {"status": "PRE_T0_CONFIRMED"},
        "coverage": {"verified_families": 3, "positive_families_excluding_concentration": 2},
        "families": {
            "holder_acceleration": {"positive": True},
            "independent_wallet_accumulation": {"positive": True},
            "smart_money": {"positive": False},
            "concentration": {"positive": False},
            "organic_social": {"positive": False},
        },
        "market": {"revival_score_verified": 60},
    }


def seed(tmp_path: Path, captured_at="2026-09-04T10:00:00+00:00"):
    snap = base_snapshot(captured_at)
    key = snap["token_address"] + "|" + snap["pair_address"].lower()
    write(tmp_path, "revival-pre-t0-evidence-ledger.json", {
        "mode": "RESEARCH_ONLY_IMMUTABLE_PRE_T0_EVIDENCE",
        "no_hindsight": True,
        "updated_at": "2026-09-04T10:05:00+00:00",
        "waking_bindings": {key: {
            "status": "BOUND_TO_PRE_WAKING_EVIDENCE",
            "pre_t0_record_id": snap["record_id"],
            "pre_t0_captured_at": snap["captured_at"],
            "pre_t0_evidence_sha256": snap["evidence_sha256"],
            "snapshot": snap,
        }},
    })
    write(tmp_path, "revival-forensics-latest.json", {
        "mode": "RESEARCH_ONLY_REVIVAL_FORENSICS_V2",
        "network": "solana",
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "generated_at": "2026-09-05T11:00:00+00:00",
        "events": [{
            "event_id": "WAKING-1",
            "token_address": snap["token_address"],
            "symbol": "TEST",
            "t0": {"pair_address": snap["pair_address"], "waking_t0": "2026-09-04T10:05:00+00:00"},
            "outcome_class": "REVIVAL_X2",
            "completed": True,
            "completed_at": "2026-09-05T10:05:00+00:00",
            "peak_return_pct": 140.0,
            "max_drawdown_from_t0_pct": -12.0,
            "minimum_liquidity_return_pct": -5.0,
            "horizons": {
                "5m": {"available": True, "return_pct": 2.0, "pair_identity": "STRICT_MATCH"},
                "15m": {"available": True, "return_pct": 5.0, "pair_identity": "STRICT_MATCH"},
                "60m": {"available": True, "return_pct": 20.0, "pair_identity": "STRICT_MATCH"},
                "240m": {"available": True, "return_pct": 80.0, "pair_identity": "STRICT_MATCH"},
                "1440m": {"available": True, "return_pct": 120.0, "pair_identity": "STRICT_MATCH"},
            },
        }],
    })


def test_enrolls_only_valid_pre_t0_binding(tmp_path):
    seed(tmp_path)
    p = run(tmp_path)
    assert p["summary"]["enrolled_with_valid_pre_t0"] == 1
    assert p["summary"]["completed_24h"] == 1
    assert p["summary"]["winners_x2_plus"] == 1
    assert p["events"][0]["pre_t0_shadow_status"] == "PRE_T0_CONFIRMED"
    assert set(p["events"][0]["checkpoints"]) == {"5m", "15m", "60m", "240m", "1440m"}


def test_post_t0_snapshot_is_rejected(tmp_path):
    seed(tmp_path, captured_at="2026-09-04T10:06:00+00:00")
    p = run(tmp_path)
    assert p["summary"]["enrolled_with_valid_pre_t0"] == 0
    assert p["invalid_binding_counts"]["POST_T0_BINDING_FORBIDDEN"] == 1


def test_pair_identity_is_case_sensitive(tmp_path):
    seed(tmp_path)
    f = json.loads((tmp_path / "revival-forensics-latest.json").read_text())
    f["events"][0]["t0"]["pair_address"] = f["events"][0]["t0"]["pair_address"].lower()
    write(tmp_path, "revival-forensics-latest.json", f)
    p = run(tmp_path)
    assert p["summary"]["enrolled_with_valid_pre_t0"] == 0
    assert p["invalid_binding_counts"]["PAIR_MISMATCH"] == 1
