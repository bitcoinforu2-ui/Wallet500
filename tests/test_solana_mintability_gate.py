import json
from pathlib import Path

import wallet500.solana_mintability_gate as gate

MINT_SAFE = "11111111111111111111111111111111"
MINTABLE = "22222222222222222222222222222222"
UNKNOWN = "33333333333333333333333333333333"
AUTH = "Auth111111111111111111111111111111111111111"


def parsed_mint(authority):
    return {
        "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "data": {"parsed": {"type": "mint", "info": {"mintAuthority": authority, "freezeAuthority": None}}},
    }


def test_parse_null_mint_authority_is_only_safe_state():
    row = gate._parse_mint_account(MINT_SAFE, parsed_mint(None), "2026-09-05T00:00:00+00:00")
    assert row["status"] == "NON_MINTABLE_VERIFIED"
    assert row["mintability_verified"] is True
    assert row["mintable"] is False
    assert row["mint_authority"] is None
    assert row["immutable_safe"] is True


def test_parse_present_mint_authority_is_hard_block():
    row = gate._parse_mint_account(MINTABLE, parsed_mint(AUTH), "2026-09-05T00:00:00+00:00")
    assert row["status"] == "MINTABLE_BLOCKED"
    assert row["mintable"] is True
    assert row["mint_authority"] == AUTH
    assert gate._is_safe(row) is False


def test_unknown_or_unparsed_mint_fails_closed():
    row = gate._parse_mint_account(UNKNOWN, None, "2026-09-05T00:00:00+00:00")
    assert row["status"] == "UNVERIFIED_BLOCKED"
    assert row["mintability_verified"] is False
    assert gate._is_safe(row) is False


def test_revival_removes_mintable_and_unknown(monkeypatch, tmp_path: Path):
    payload = {
        "coins": [
            {"network": "solana", "token_address": MINT_SAFE, "symbol": "SAFE", "dex_link_type": "DEXSCREENER_VERIFIED_PAIR"},
            {"network": "solana", "token_address": MINTABLE, "symbol": "MINT", "dex_link_type": "DEXSCREENER_VERIFIED_PAIR"},
            {"network": "solana", "token_address": UNKNOWN, "symbol": "UNK", "dex_link_type": "DEXSCREENER_VERIFIED_PAIR"},
        ],
        "counts": {"universe": 3},
    }
    (tmp_path / "revival-1000-latest.json").write_text(json.dumps(payload))

    def fake_resolve(mints, state, checked_at=None):
        rows = {
            MINT_SAFE: gate._parse_mint_account(MINT_SAFE, parsed_mint(None), "t"),
            MINTABLE: gate._parse_mint_account(MINTABLE, parsed_mint(AUTH), "t"),
            UNKNOWN: gate._parse_mint_account(UNKNOWN, None, "t"),
        }
        return rows, {"version": 1, "updated_at": "t", "tokens": rows}

    monkeypatch.setattr(gate, "resolve", fake_resolve)
    report = gate.enforce_revival(tmp_path)
    out = json.loads((tmp_path / "revival-1000-latest.json").read_text())
    assert [x["symbol"] for x in out["coins"]] == ["SAFE"]
    assert out["coins"][0]["mintability_verified"] is True
    assert out["coins"][0]["mintable"] is False
    assert out["mintability_gate"]["mintable_tokens_allowed"] is False
    assert out["counts"]["mintable_rejected"] == 1
    assert out["counts"]["mintability_unverified_rejected"] == 1
    assert report["rejected"] == 2


def test_active_lane_removes_mintable_and_unverified(monkeypatch, tmp_path: Path):
    active = [
        {"chain": "solana", "token": MINT_SAFE, "symbol": "SAFE"},
        {"chain": "solana", "token": MINTABLE, "symbol": "MINT"},
        {"chain": "ethereum", "token": "0xabc", "symbol": "EVM"},
    ]
    (tmp_path / "active-qualified-candidates.json").write_text(json.dumps(active))
    (tmp_path / "watchlist.json").write_text(json.dumps(active))

    def fake_resolve(mints, state, checked_at=None):
        rows = {
            MINT_SAFE: gate._parse_mint_account(MINT_SAFE, parsed_mint(None), "t"),
            MINTABLE: gate._parse_mint_account(MINTABLE, parsed_mint(AUTH), "t"),
        }
        return rows, {"version": 1, "updated_at": "t", "tokens": rows}

    monkeypatch.setattr(gate, "resolve", fake_resolve)
    report = gate.enforce_active(tmp_path)
    out = json.loads((tmp_path / "active-qualified-candidates.json").read_text())
    symbols = {x["symbol"] for x in out}
    assert symbols == {"SAFE", "EVM"}
    assert report["rejected"] == 1


def test_verified_safe_cache_is_reused_without_rpc(monkeypatch):
    cached = gate._parse_mint_account(MINT_SAFE, parsed_mint(None), "old")
    state = {"tokens": {MINT_SAFE: cached}}
    monkeypatch.setattr(gate, "_fetch_batch", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("RPC should not run")))
    resolved, _ = gate.resolve([MINT_SAFE], state, checked_at="new")
    assert resolved[MINT_SAFE]["status"] == "NON_MINTABLE_VERIFIED"
