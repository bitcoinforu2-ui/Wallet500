from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path


def test_compactor_preserves_all_observations_in_hot_tail_plus_archive(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    history = [
        {
            "observed_at": f"2026-09-04T0{i}:00:00+00:00",
            "price_usd": float(i + 1),
            "pair_address": "PAIR",
            "measurement_eligible": True,
        }
        for i in range(5)
    ]
    tracker = {
        "tracked_tokens": 1,
        "tokens": {
            "solana:TOKEN": {
                "chain": "solana",
                "token": "TOKEN",
                "entry_pair_address": "PAIR",
                "history": history,
            }
        },
    }
    (data / "outcome-tracker.json").write_text(json.dumps(tracker), encoding="utf-8")
    (data / "signal-outcomes.json").write_text(
        json.dumps(list(tracker["tokens"].values())),
        encoding="utf-8",
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "compact_outcome_history.py"
    env = {
        **os.environ,
        "WALLET500_OUTCOME_HOT_HISTORY": "2",
        "WALLET500_OUTCOME_MAX_LIVE_BYTES": str(1024 * 1024),
        "WALLET500_OUTCOME_ARCHIVE_SHARD_BYTES": str(1024 * 1024),
        "GITHUB_RUN_ID": "pytest",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=env, check=True)

    compacted = json.loads((data / "outcome-tracker.json").read_text())
    hot = compacted["tokens"]["solana:TOKEN"]["history"]
    assert len(hot) == 2
    assert compacted["history_storage"]["preserves_all_observations"] is True
    assert compacted["history_storage"]["archived_this_run"] == 3

    shards = list((data / "outcome-archive").glob("*.jsonl.gz"))
    assert len(shards) == 1
    with gzip.open(shards[0], "rt", encoding="utf-8") as fh:
        archived_rows = [json.loads(line) for line in fh if line.strip()]
    archived = archived_rows[0]["observations"]

    assert archived + hot == history
