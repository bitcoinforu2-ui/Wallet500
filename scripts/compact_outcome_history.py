#!/usr/bin/env python3
"""Bound Wallet500 live outcome files without deleting historical evidence.

The live tracker keeps every token/call and all immutable summary fields. Older
per-observation history rows are moved verbatim into gzip-compressed JSONL shards
under data/outcome-archive/. The configured hot tail is preferred, but if the
live JSON would still exceed the publish ceiling the tail is reduced
adaptively, never below the two observations required by risk comparisons.

This is a storage/layout operation only. It does not change qualification,
liquidity, exact-pair, holder/cluster, scoring, alert logic, or historical
outcomes.
"""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

DATA = Path("data")
TRACKER = DATA / "outcome-tracker.json"
SIGNALS = DATA / "signal-outcomes.json"
ARCHIVE_DIR = DATA / "outcome-archive"
HOT_HISTORY = int(os.environ.get("WALLET500_OUTCOME_HOT_HISTORY", "24"))
SHARD_UNCOMPRESSED_BYTES = int(os.environ.get("WALLET500_OUTCOME_ARCHIVE_SHARD_BYTES", str(16 * 1024 * 1024)))
MAX_LIVE_BYTES = int(os.environ.get("WALLET500_OUTCOME_MAX_LIVE_BYTES", str(70 * 1024 * 1024)))
RUN_ID = os.environ.get("GITHUB_RUN_ID") or "local"
RUN_ATTEMPT = os.environ.get("GITHUB_RUN_ATTEMPT") or "1"
MIN_HOT_HISTORY = 2


def _write_json(path: Path, payload) -> None:
    # Compact serialization is lossless and materially reduces Git blob size.
    path.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )


def _flush_shard(rows: list[dict], index: int) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"history-run-{RUN_ID}-attempt-{RUN_ATTEMPT}-{index:03d}.jsonl.gz"
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing immutable outcome archive shard: {path}")
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
    return path


def main() -> None:
    if HOT_HISTORY < MIN_HOT_HISTORY:
        raise SystemExit("HOT_HISTORY must retain at least 2 observations for risk comparisons")
    if not TRACKER.is_file():
        print("No outcome tracker present; nothing to compact")
        return

    tracker = json.loads(TRACKER.read_text(encoding="utf-8"))
    records = tracker.get("tokens")
    if not isinstance(records, dict):
        raise SystemExit("Malformed outcome tracker: tokens must be an object")

    pending: list[dict] = []
    pending_bytes = 0
    shard_index = 1
    shards: list[Path] = []
    archived_observations = 0
    touched_tokens: set[str] = set()

    def flush() -> None:
        nonlocal pending, pending_bytes, shard_index
        if not pending:
            return
        shards.append(_flush_shard(pending, shard_index))
        shard_index += 1
        pending = []
        pending_bytes = 0

    def archive_to_tail(target_hot: int) -> None:
        """Move rows outside target_hot verbatim to immutable shards."""
        nonlocal pending_bytes, archived_observations
        for token_key, rec in records.items():
            if not isinstance(rec, dict):
                continue
            history = rec.get("history")
            if not isinstance(history, list) or len(history) <= target_hot:
                continue
            old = history[:-target_hot]
            rec["history"] = history[-target_hot:]
            touched_tokens.add(token_key)
            archived_observations += len(old)
            row = {
                "version": 1,
                "source_run_id": str(RUN_ID),
                "source_run_attempt": str(RUN_ATTEMPT),
                "token_key": token_key,
                "chain": rec.get("chain"),
                "token": rec.get("token"),
                "entry_pair_address": rec.get("entry_pair_address"),
                "observations": old,
            }
            encoded_len = len(json.dumps(row, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) + 1
            if pending and pending_bytes + encoded_len > SHARD_UNCOMPRESSED_BYTES:
                flush()
            pending.append(row)
            pending_bytes += encoded_len
        flush()

    effective_hot = HOT_HISTORY
    archive_to_tail(effective_hot)

    def write_and_measure() -> tuple[int, int]:
        tracker["history_storage"] = {
            "mode": "HOT_TAIL_PLUS_IMMUTABLE_GZIP_JSONL_ARCHIVE",
            "hot_history_per_token": effective_hot,
            "configured_hot_history_per_token": HOT_HISTORY,
            "minimum_hot_history_per_token": MIN_HOT_HISTORY,
            "adaptive_compaction": effective_hot < HOT_HISTORY,
            "archived_this_run": archived_observations,
            "archive_shards_this_run": [str(p) for p in shards],
            "preserves_all_token_records": True,
            "preserves_all_observations": True,
        }
        _write_json(TRACKER, tracker)
        _write_json(SIGNALS, list(records.values()))
        return TRACKER.stat().st_size, SIGNALS.stat().st_size

    tracker_size, signals_size = write_and_measure()

    # Storage-only adaptive fallback. If 24 hot rows/token still cannot fit under
    # the verified-publish ceiling, progressively archive more history. No row is
    # deleted; every removed observation is written verbatim to immutable shards.
    while (tracker_size > MAX_LIVE_BYTES or signals_size > MAX_LIVE_BYTES) and effective_hot > MIN_HOT_HISTORY:
        effective_hot = max(MIN_HOT_HISTORY, effective_hot // 2)
        archive_to_tail(effective_hot)
        tracker_size, signals_size = write_and_measure()

    if tracker_size > MAX_LIVE_BYTES or signals_size > MAX_LIVE_BYTES:
        raise SystemExit(
            f"Compaction insufficient even at safe minimum hot tail: tracker={tracker_size} bytes "
            f"signals={signals_size} bytes; limit={MAX_LIVE_BYTES}. Refusing publication rather "
            f"than weakening truth/integrity rules."
        )

    print(
        f"Outcome history compacted safely: tokens={len(records)} touched={len(touched_tokens)} "
        f"archived_observations={archived_observations} shards={len(shards)} "
        f"tracker_bytes={tracker_size} signal_bytes={signals_size} "
        f"configured_hot_history={HOT_HISTORY} effective_hot_history={effective_hot}"
    )


if __name__ == "__main__":
    main()
