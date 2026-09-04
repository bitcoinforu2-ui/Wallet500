from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import revival_pre_t0_evidence as v1

VERSION = "REVIVAL_PRE_T0_EVIDENCE_V2_INTEGRITY"
LEDGER_NAME = "revival-pre-t0-evidence-ledger.json"
LATEST_NAME = "revival-pre-t0-evidence.json"


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dt(value: object) -> datetime:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def _canonicalize_ledger(data_dir: str | Path) -> dict:
    """Repair identity-repeat duplicates without rewriting unique evidence history.

    The V1 record_id is an evidence-identity hash. If evidence moves A -> B -> A,
    V1 can append the same immutable identity twice. That is not a new evidence
    identity, so retain the earliest append. Any same-ID collision with a different
    key/hash fails closed as corruption.
    """
    data = Path(data_dir)
    path = data / LEDGER_NAME
    ledger = _load(path, {})
    if not ledger:
        return {"removed": 0, "records_total": 0}
    if ledger.get("mode") != v1.MODE or ledger.get("version") != v1.VERSION:
        raise RuntimeError("PRE_T0_V2_LEDGER_TRUTH_INVALID")

    records = [r for r in (ledger.get("records") or []) if isinstance(r, dict)]
    by_id: dict[str, dict] = {}
    order: list[str] = []
    removed = 0
    for row in records:
        rid = str(row.get("record_id") or "")
        if not rid:
            raise RuntimeError("PRE_T0_V2_RECORD_ID_MISSING")
        prior = by_id.get(rid)
        if prior is None:
            by_id[rid] = row
            order.append(rid)
            continue
        if prior.get("evidence_sha256") != row.get("evidence_sha256") or prior.get("key") != row.get("key"):
            raise RuntimeError("PRE_T0_V2_RECORD_ID_COLLISION")
        if _dt(row.get("captured_at")) < _dt(prior.get("captured_at")):
            by_id[rid] = row
        removed += 1

    if removed:
        ledger["records"] = [by_id[rid] for rid in order]
    integrity = ledger.setdefault("integrity", {})
    integrity.update({
        "record_identity_semantics": "EVIDENCE_IDENTITY_NOT_OBSERVATION_SEQUENCE",
        "duplicate_identity_policy": "KEEP_EARLIEST_EXACT_KEY_HASH_IDENTITY",
        "conflicting_same_id_policy": "FAIL_CLOSED",
        "unique_record_ids": True,
        "last_duplicate_identities_removed": removed,
        "canonical_records_total": len(by_id),
    })
    # Persist the integrity contract even when there was nothing to remove. This is
    # required for the first V2 run over an already-unique legacy ledger.
    _write(path, ledger)
    return {"removed": removed, "records_total": len(by_id), "records_by_id": by_id}


def _repair_latest(data_dir: str | Path, removed: int, records_by_id: dict[str, dict]) -> dict:
    path = Path(data_dir) / LATEST_NAME
    latest = _load(path, {})
    if not latest:
        return latest
    if latest.get("mode") != v1.MODE or latest.get("version") != v1.VERSION:
        raise RuntimeError("PRE_T0_V2_LATEST_TRUTH_INVALID")

    active = []
    for row in latest.get("active_deep_watch") or []:
        if not isinstance(row, dict):
            continue
        canonical = records_by_id.get(str(row.get("record_id") or ""))
        active.append(canonical or row)
    latest["active_deep_watch"] = active
    counts = latest.setdefault("counts", {})
    counts["records_total"] = len(records_by_id)
    counts["integrity_duplicate_identities_removed_this_run"] = removed
    latest["integrity"] = {
        "version": VERSION,
        "record_ids_unique": True,
        "identity_repeat_is_not_new_observation": True,
        "conflicting_same_id_fails_closed": True,
        "history_deletion": "ONLY_EXACT_DUPLICATE_EVIDENCE_IDENTITY",
    }
    _write(path, latest)
    return latest


def run(data_dir: str | Path = "data", now: str | None = None) -> dict:
    # First repair any legacy A->B->A duplicate so V1's strict workflow can recover.
    before = _canonicalize_ledger(data_dir)
    v1.run(data_dir, now)
    # Then canonicalize again because the current V1 run itself may return to an
    # older evidence identity and append it once more.
    after = _canonicalize_ledger(data_dir)
    records_by_id = after.get("records_by_id") or {}
    total_removed = int(before.get("removed") or 0) + int(after.get("removed") or 0)
    latest = _repair_latest(data_dir, total_removed, records_by_id)
    return latest


def main() -> None:
    payload = run()
    print(json.dumps({
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "counts": payload.get("counts"),
        "integrity": payload.get("integrity"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
