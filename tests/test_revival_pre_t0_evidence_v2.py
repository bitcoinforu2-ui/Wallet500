import json
from pathlib import Path

import pytest

from wallet500.revival_pre_t0_evidence_v2 import _canonicalize_ledger

MODE = "RESEARCH_ONLY_IMMUTABLE_PRE_T0_EVIDENCE"
VERSION = "REVIVAL_PRE_T0_EVIDENCE_V1"


def write_ledger(data: Path, records: list[dict]) -> None:
    (data / "revival-pre-t0-evidence-ledger.json").write_text(json.dumps({
        "version": VERSION,
        "mode": MODE,
        "network": "solana",
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "records": records,
        "waking_bindings": {},
    }), encoding="utf-8")


def rec(rid: str, sha: str, key: str, captured: str, price: float) -> dict:
    return {
        "record_id": rid,
        "evidence_sha256": sha,
        "key": key,
        "captured_at": captured,
        "market": {"price_usd": price},
        "immutable_after_append": True,
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
    }


def test_identity_repeat_keeps_earliest_and_preserves_unique_history(tmp_path):
    a1 = rec("PRET0-A", "A" * 64, "mint|pair", "2026-09-04T10:00:00+00:00", 1.0)
    b = rec("PRET0-B", "B" * 64, "mint|pair", "2026-09-04T10:05:00+00:00", 2.0)
    a2 = rec("PRET0-A", "A" * 64, "mint|pair", "2026-09-04T10:10:00+00:00", 3.0)
    write_ledger(tmp_path, [a1, b, a2])

    out = _canonicalize_ledger(tmp_path)
    ledger = json.loads((tmp_path / "revival-pre-t0-evidence-ledger.json").read_text())

    assert out["removed"] == 1
    assert [r["record_id"] for r in ledger["records"]] == ["PRET0-A", "PRET0-B"]
    assert ledger["records"][0]["captured_at"] == a1["captured_at"]
    assert ledger["records"][0]["market"]["price_usd"] == 1.0
    assert ledger["integrity"]["unique_record_ids"] is True


def test_unique_legacy_ledger_still_persists_integrity_marker(tmp_path):
    a = rec("PRET0-A", "A" * 64, "mint|pair", "2026-09-04T10:00:00+00:00", 1.0)
    write_ledger(tmp_path, [a])
    out = _canonicalize_ledger(tmp_path)
    ledger = json.loads((tmp_path / "revival-pre-t0-evidence-ledger.json").read_text())
    assert out["removed"] == 0
    assert ledger["integrity"]["unique_record_ids"] is True
    assert ledger["integrity"]["conflicting_same_id_policy"] == "FAIL_CLOSED"
    assert ledger["integrity"]["canonical_records_total"] == 1


def test_same_id_conflicting_hash_fails_closed(tmp_path):
    a = rec("PRET0-X", "A" * 64, "mint|pair", "2026-09-04T10:00:00+00:00", 1.0)
    bad = rec("PRET0-X", "B" * 64, "mint|pair", "2026-09-04T10:01:00+00:00", 1.1)
    write_ledger(tmp_path, [a, bad])
    with pytest.raises(RuntimeError, match="PRE_T0_V2_RECORD_ID_COLLISION"):
        _canonicalize_ledger(tmp_path)


def test_same_id_conflicting_key_fails_closed(tmp_path):
    a = rec("PRET0-X", "A" * 64, "mint|pair1", "2026-09-04T10:00:00+00:00", 1.0)
    bad = rec("PRET0-X", "A" * 64, "mint|pair2", "2026-09-04T10:01:00+00:00", 1.1)
    write_ledger(tmp_path, [a, bad])
    with pytest.raises(RuntimeError, match="PRE_T0_V2_RECORD_ID_COLLISION"):
        _canonicalize_ledger(tmp_path)
