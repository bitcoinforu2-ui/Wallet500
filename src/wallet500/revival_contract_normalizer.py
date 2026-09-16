from __future__ import annotations

import json
import os
from pathlib import Path

SOURCE = "revival-1000-latest.json"


def run(output_dir: str | None = None) -> dict:
    out = Path(output_dir or os.getenv("WALLET500_OUTPUT_DIR", "data"))
    path = out / SOURCE
    if not path.exists():
        raise SystemExit("REVIVAL_1000_LATEST_MISSING")

    payload = json.loads(path.read_text(encoding="utf-8"))
    coins = list(payload.get("coins") or [])
    counts = payload.setdefault("counts", {})

    verified_90d = sum(
        1
        for row in coins
        if isinstance(row, dict)
        and row.get("market_age_verified") is True
        and float(row.get("market_age_min_days") or 0) >= 90
    )
    counts["age_verified_90d_plus"] = verified_90d

    # Keep the legacy field temporarily so older dashboards do not break, but mark it
    # explicitly as a compatibility alias instead of allowing 60d semantics to drift.
    counts["age_verified_60d_plus"] = verified_90d
    payload["age_count_contract"] = {
        "canonical_field": "age_verified_90d_plus",
        "minimum_market_age_days": 90,
        "legacy_alias": "age_verified_60d_plus",
        "legacy_alias_semantics": "COMPATIBILITY_ALIAS_FOR_90D_PLUS_ONLY",
        "semantic_drift_forbidden": True,
    }

    if verified_90d != len(coins):
        raise SystemExit(
            f"REVIVAL_90D_COUNT_MISMATCH verified={verified_90d} universe={len(coins)}"
        )

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "REVIVAL_90D_CONTRACT_NORMALIZED",
                "age_verified_90d_plus": verified_90d,
                "universe": len(coins),
            },
            ensure_ascii=False,
        )
    )
    return payload


if __name__ == "__main__":
    run()
