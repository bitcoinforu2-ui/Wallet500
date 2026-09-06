import json
from pathlib import Path

import wallet500.solana_mintability_public_guard as guard

SAFE = "11111111111111111111111111111111"
BAD = "22222222222222222222222222222222"
DORMANT_SAFE = "33333333333333333333333333333333"
DORMANT_BAD = "44444444444444444444444444444444"


def _truth(status="NON_MINTABLE_VERIFIED", mintable=False, authority=None):
    return {
        "status": status,
        "mintability_verified": True,
        "mintable": mintable,
        "mint_authority": authority,
    }


def test_public_guard_removes_mintable_solana(monkeypatch, tmp_path: Path):
    payload = {
        "truth_contract": {},
        "counts": {"real_alerts": 0, "verified_watch_not_real": 2, "evidence_ready_research": 0, "identity_pending_not_actionable": 0},
        "alerts": [],
        "verified_watch": [
            {"chain": "solana", "token_address": SAFE, "symbol": "SAFE"},
            {"chain": "solana", "token_address": BAD, "symbol": "BAD"},
        ],
        "evidence_ready": [],
        "dormant_no_activity": [],
        "identity_pending": [],
    }
    (tmp_path / "real-alerts.json").write_text(json.dumps(payload))

    rows = {
        SAFE: _truth(),
        BAD: _truth("MINTABLE_BLOCKED", True, "AUTH"),
    }
    monkeypatch.setattr(guard, "resolve", lambda mints, state: (rows, {"version": 1, "updated_at": "t", "tokens": rows}))
    result = guard.sanitize_real_alerts(tmp_path)
    out = json.loads((tmp_path / "real-alerts.json").read_text())
    assert [x["symbol"] for x in out["verified_watch"]] == ["SAFE"]
    assert out["verified_watch"][0]["mintability_verified"] is True
    assert out["counts"]["verified_watch_not_real"] == 1
    assert out["counts"]["mintability_rejected_not_visible"] == 1
    assert out["truth_contract"]["solana_mintable_tokens_allowed"] is False
    assert result["removed_not_visible"] == 1


def test_dormant_surface_is_guarded_and_ready_count_survives_dormancy(monkeypatch, tmp_path: Path):
    payload = {
        "truth_contract": {},
        "counts": {"real_alerts": 0, "verified_watch_not_real": 0, "evidence_ready_research": 2, "identity_pending_not_actionable": 0},
        "alerts": [],
        "verified_watch": [],
        "evidence_ready": [],
        "dormant_no_activity": [
            {
                "chain": "solana", "token_address": DORMANT_SAFE, "pair_address": "PAIR1",
                "symbol": "DORMANT_SAFE", "evidence_ready": True,
                "evidence_envelope_status": "EVIDENCE_READY",
            },
            {
                "chain": "solana", "token_address": DORMANT_BAD, "pair_address": "PAIR2",
                "symbol": "DORMANT_BAD", "evidence_ready": True,
                "evidence_envelope_status": "EVIDENCE_READY",
            },
        ],
        "identity_pending": [],
    }
    envelope = {
        "truth_contract": {},
        "candidates": [
            {"chain": "solana", "token_address": DORMANT_SAFE, "status": "EVIDENCE_READY", "families": {}},
            {"chain": "solana", "token_address": DORMANT_BAD, "status": "EVIDENCE_READY", "families": {}},
        ],
    }
    (tmp_path / "real-alerts.json").write_text(json.dumps(payload))
    (tmp_path / "candidate-evidence-envelope.json").write_text(json.dumps(envelope))

    rows = {
        DORMANT_SAFE: _truth(),
        DORMANT_BAD: _truth("MINTABLE_BLOCKED", True, "AUTH"),
    }
    monkeypatch.setattr(guard, "resolve", lambda mints, state: (rows, {"version": 1, "updated_at": "t", "tokens": rows}))
    result = guard.sanitize_real_alerts(tmp_path)
    out = json.loads((tmp_path / "real-alerts.json").read_text())
    env = json.loads((tmp_path / "candidate-evidence-envelope.json").read_text())

    assert [x["symbol"] for x in out["dormant_no_activity"]] == ["DORMANT_SAFE"]
    assert out["dormant_no_activity"][0]["mintability_verified"] is True
    assert out["counts"]["dormant_no_activity"] == 1
    assert out["counts"]["evidence_ready_research"] == 1
    assert env["counts"]["evidence_ready"] == 1
    assert out["truth_contract"]["dormant_research_surface_is_mintability_guarded"] is True
    assert "dormant_no_activity" in result["guarded_surfaces"]
    assert result["removed_not_visible"] >= 1
