"""Fail-closed preflight for truth-bearing decision inputs.

This prevents missing/corrupt JSON from being silently interpreted as a genuine
zero-candidate market state. Staleness remains evaluated by the owning health
modules because freshness budgets differ by source.
"""
from __future__ import annotations

import json
from pathlib import Path

from .safe_json import load_json_state

CRITICAL_INPUTS = (
    "data/run-summary.json",
    "data/revival-1000-latest.json",
    "data/cex-revival-radar.json",
    "data/revival-holder-latest.json",
    "data/revival-wallet-registry.json",
    "data/revival-precursor-latest.json",
    "data/waking-confirmation-latest.json",
)
OUT = Path("data/truth-input-health.json")


def check(paths=CRITICAL_INPUTS) -> dict:
    rows = []
    bad = []
    for name in paths:
        r = load_json_state(name)
        item = {"path": name, "state": r.state, "error": r.error}
        rows.append(item)
        if not r.valid:
            bad.append(item)
    payload = {
        "version": 1,
        "status": "PASS" if not bad else "FAIL_CLOSED",
        "inputs": rows,
        "invalid_inputs": bad,
        "rule": "MISSING_OR_CORRUPT_TRUTH_INPUT_IS_NEVER_EQUIVALENT_TO_ZERO_CANDIDATES",
        "automatic_buy": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if bad:
        raise RuntimeError("TRUTH_INPUT_PREFLIGHT_FAIL_CLOSED:" + ",".join(x["path"] for x in bad))
    return payload


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
