from __future__ import annotations

import gzip
import json
from pathlib import Path

from wallet500 import alpha_checkpoint_recovery as acr


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _obs(at: str, price: float, pair: str) -> dict:
    return {
        "observed_at": at,
        "price_usd": price,
        "liquidity_usd": 65000,
        "pair_address": pair,
        "measurement_eligible": True,
        "token_identity_verified": True,
        "price_identity_contract_version": 2,
    }


def test_recovers_first_exact_pair_observation_after_missing_horizon(tmp_path: Path) -> None:
    token = "0x1111111111111111111111111111111111111111"
    pair = "0x2222222222222222222222222222222222222222"
    key = f"bsc|{token}|{pair}"
    ledger = {
        "version": 1,
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "signals": {
            "signal": {
                "lane": "PRECURSOR_REAWAKENING",
                "key": key,
                "chain": "bsc",
                "token": token,
                "pair_address": pair,
                "event_at": "2026-09-04T01:00:00+00:00",
                "entry_price_usd": 1.0,
                "checkpoints": {
                    "1h": {
                        "captured_at": "2026-09-04T02:01:00+00:00",
                        "price_usd": 1.1,
                        "gross_return_pct": 10.0,
                        "friction_adjusted_return_pct": 8.0,
                    }
                },
            }
        },
        "controls": {},
    }
    outcomes = {
        "tokens": {
            "row": {
                "chain": "bsc",
                "token": token,
                "entry_pair_address": pair,
                "history": [
                    _obs("2026-09-04T06:59:00+00:00", 1.2, pair),
                    _obs("2026-09-04T07:05:00+00:00", 1.3, pair),
                    _obs("2026-09-04T07:20:00+00:00", 1.4, pair),
                ],
            }
        }
    }
    _write(tmp_path / "alpha-proof-ledger.json", ledger)
    _write(tmp_path / "outcome-tracker.json", outcomes)

    result = acr.recover(tmp_path)
    updated = json.loads((tmp_path / "alpha-proof-ledger.json").read_text())

    assert result["recovered"] == 3  # 5m, 15m and 6h; 1h already exists
    assert updated["signals"]["signal"]["checkpoints"]["1h"]["price_usd"] == 1.1
    assert updated["signals"]["signal"]["checkpoints"]["6h"]["captured_at"] == "2026-09-04T07:05:00+00:00"
    assert updated["signals"]["signal"]["checkpoints"]["6h"]["price_usd"] == 1.3


def test_archive_recovery_is_exact_pair_and_identity_fail_closed(tmp_path: Path) -> None:
    token = "SoToken111111111111111111111111111111111111"
    pair = "PoolExact11111111111111111111111111111111111"
    wrong_pair = "PoolWrong11111111111111111111111111111111111"
    ledger = {
        "version": 1,
        "mode": "FORWARD_ONLY_ALPHA_PROOF_V1",
        "signals": {
            "signal": {
                "lane": "PRECURSOR_REAWAKENING",
                "chain": "solana",
                "token": token,
                "pair_address": pair,
                "event_at": "2026-09-04T01:00:00+00:00",
                "entry_price_usd": 2.0,
                "checkpoints": {"5m": {}, "15m": {}, "1h": {}},
            }
        },
        "controls": {},
    }
    _write(tmp_path / "alpha-proof-ledger.json", ledger)
    _write(tmp_path / "outcome-tracker.json", {"tokens": {}})

    archive = tmp_path / "outcome-archive"
    archive.mkdir()
    shard = archive / "history-run-test-attempt-1-001.jsonl.gz"
    rows = [
        {
            "chain": "solana",
            "token": token,
            "entry_pair_address": wrong_pair,
            "observations": [_obs("2026-09-04T07:01:00+00:00", 99.0, wrong_pair)],
        },
        {
            "chain": "solana",
            "token": token,
            "entry_pair_address": pair,
            "observations": [
                {
                    **_obs("2026-09-04T07:02:00+00:00", 3.0, pair),
                    "token_identity_verified": False,
                },
                _obs("2026-09-04T07:03:00+00:00", 2.5, pair),
            ],
        },
    ]
    with gzip.open(shard, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    result = acr.recover(tmp_path)
    updated = json.loads((tmp_path / "alpha-proof-ledger.json").read_text())
    cp = updated["signals"]["signal"]["checkpoints"]["6h"]

    assert result["recovered"] == 1
    assert cp["captured_at"] == "2026-09-04T07:03:00+00:00"
    assert cp["price_usd"] == 2.5
    assert cp["recovery_provenance"] == "IMMUTABLE_EXACT_PAIR_OUTCOME_HISTORY_V1"
