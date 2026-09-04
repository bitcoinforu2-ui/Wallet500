import json
from pathlib import Path

import wallet500.solana_mintability_public_guard as guard

SAFE = "11111111111111111111111111111111"
BAD = "22222222222222222222222222222222"


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
        "identity_pending": [],
    }
    (tmp_path / "real-alerts.json").write_text(json.dumps(payload))

    rows = {
        SAFE: {"status": "NON_MINTABLE_VERIFIED", "mintability_verified": True, "mintable": False, "mint_authority": None},
        BAD: {"status": "MINTABLE_BLOCKED", "mintability_verified": True, "mintable": True, "mint_authority": "AUTH"},
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
