import json
from pathlib import Path

from wallet500 import qualified_intelligence as qi


def test_key_is_chain_aware():
    assert qi._key("bsc", "0xAbC") == "bsc:0xabc"
    assert qi._key("solana", "AbC123") == "solana:AbC123"


def test_listing_match_requires_exact_contract(tmp_path):
    qi.LISTING_LEDGER = tmp_path / "global-listing-ledger.json"
    qi.LISTING_LEDGER.write_text(json.dumps({
        "records": {
            "a": {"last_observation": {"source": "moonshot", "token": "ExactMint111", "stage": "RISING"}},
            "b": {"last_observation": {"source": "mexc", "token": "OtherMint222", "stage": "NEW"}},
        }
    }))
    rows = qi._listing_matches("ExactMint111")
    assert len(rows) == 1
    assert rows[0]["source"] == "moonshot"
    assert rows[0]["exact_contract_match"] is True


def test_targets_only_accept_existing_qualified_status(tmp_path):
    qi.QUALIFIED = tmp_path / "qualified-candidates.json"
    qi.REVIVAL_QUALIFIED = tmp_path / "revival-qualified.json"
    qi.QUALIFIED.write_text(json.dumps([
        {"chain": "solana", "token": "A", "qualification": "QUALIFIED"},
        {"chain": "solana", "token": "B", "qualification": "REJECTED"},
    ]))
    qi.REVIVAL_QUALIFIED.write_text(json.dumps([
        {"chain": "bsc", "token": "0xABC", "qualification": "REVIVAL_QUALIFIED"},
        {"chain": "bsc", "token": "0xDEF", "qualification": "REVIVAL_WATCH"},
    ]))
    rows = qi._targets()
    assert {(x["chain"], x["token"]) for x in rows} == {("solana", "A"), ("bsc", "0xABC")}


def test_run_fail_closed_without_provider_data(tmp_path, monkeypatch):
    (tmp_path / "qualified-candidates.json").write_text(json.dumps([
        {
            "chain": "bsc",
            "token": "0x10dae197ffa2c8783455ac5ebcac103857f07777",
            "pair_address": "0xpair",
            "qualification": "QUALIFIED",
            "qualified_at": "2026-09-03T00:00:00+00:00",
        }
    ]))
    (tmp_path / "revival-qualified.json").write_text("[]")
    (tmp_path / "global-listing-ledger.json").write_text(json.dumps({"records": {}}))
    (tmp_path / "social-organic-acceleration.json").write_text(json.dumps({"tokens": []}))
    monkeypatch.setattr(qi, "_social_events", lambda identity: ([], [{"provider": "test", "status": "NOT_CONFIGURED"}]))

    out = qi.run(tmp_path)
    assert out["candidate_count"] == 1
    row = out["dossiers"][0]
    assert row["production_impact"] == "NONE"
    assert row["research_only"] is True
    assert row["holders"]["status"] == "NOT_IMPLEMENTED_FOR_CHAIN"
    assert row["whales_gte_0_1pct"]["status"] == "NOT_IMPLEMENTED_FOR_CHAIN"
    assert "BALANCE_DELTA_NEQ_BUY_SELL_WITHOUT_SWAP_EVIDENCE" in row["truth_rules"]


def test_first_crossing_is_immutable_point_in_time(tmp_path, monkeypatch):
    candidate = {
        "chain": "bsc",
        "token": "0x10dae197ffa2c8783455ac5ebcac103857f07777",
        "qualification": "QUALIFIED",
        "qualified_at": "2026-09-03T00:00:00+00:00",
    }
    (tmp_path / "qualified-candidates.json").write_text(json.dumps([candidate]))
    (tmp_path / "revival-qualified.json").write_text("[]")
    (tmp_path / "global-listing-ledger.json").write_text(json.dumps({"records": {}}))
    (tmp_path / "social-organic-acceleration.json").write_text(json.dumps({"tokens": []}))
    monkeypatch.setattr(qi, "_social_events", lambda identity: ([], []))

    first = qi.run(tmp_path)["dossiers"][0]
    second = qi.run(tmp_path)["dossiers"][0]
    assert first["first_crossing_capture"] is True
    assert second["first_crossing_capture"] is False
    assert first["first_qualified_seen_at"] == second["first_qualified_seen_at"]
