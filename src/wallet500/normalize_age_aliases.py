"""Normalize legacy `60d_plus` labels in derived decision JSON.

Backward compatible reader, forward-clean writer. Numeric verified age remains the
only proof; this module never invents age and never upgrades a candidate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FILES = (
    "data/revival-1000-latest.json",
    "data/candidate-evidence-envelope.json",
    "data/real-alerts.json",
    "data/revival-funnel-diagnostics.json",
    "data/decision-snapshot-integrity.json",
)


def _walk(x: Any) -> int:
    changed = 0
    if isinstance(x, dict):
        if "market_age_verified_60d_plus" in x:
            legacy = x.pop("market_age_verified_60d_plus")
            days = x.get("market_age_min_days") if x.get("market_age_min_days") is not None else x.get("market_age_days")
            try:
                numeric = int(days)
            except (TypeError, ValueError):
                numeric = 0
            # Canonical boolean says only that age provenance exists; threshold is
            # always checked separately against the numeric value.
            x.setdefault("market_age_verified", bool(legacy is True and numeric > 0))
            changed += 1
        if "age_verified_60d_plus" in x:
            legacy_count = x.pop("age_verified_60d_plus")
            x.setdefault("age_verified_90d_plus", legacy_count)
            changed += 1
        for v in list(x.values()):
            changed += _walk(v)
    elif isinstance(x, list):
        for v in x:
            changed += _walk(v)
    return changed


def normalize(paths=FILES) -> dict:
    result = {"files": {}, "total_changes": 0}
    for name in paths:
        p = Path(name)
        if not p.exists():
            result["files"][name] = {"state": "MISSING", "changes": 0}
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"AGE_ALIAS_INPUT_CORRUPT:{name}:{type(exc).__name__}") from exc
        count = _walk(data)
        if count:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["files"][name] = {"state": "VALID", "changes": count}
        result["total_changes"] += count
    return result


if __name__ == "__main__":
    print(json.dumps(normalize(), indent=2))
