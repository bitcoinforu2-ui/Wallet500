"""Fast scheduled runner for the Reawakening exact-pair forward lane.

The general market-data pair lookup retries transient failures because it is used
by production-facing checks. Reawakening is a recurring research lane: its prior
state is preserved and every eligible pair is checked again on the next 15-minute
cycle. A single fail-closed direct lookup per pair therefore gives better coverage
without letting one unavailable pair consume three network attempts.
"""
from __future__ import annotations

import json
from urllib.parse import quote

from . import reawakening_forward_tracker as tracker
from .market_data import _get

DIRECT_TIMEOUT_SECONDS = 6


def single_attempt_pair_lookup(chain: str, pair_address: str) -> dict | None:
    if not chain or not pair_address:
        return None
    try:
        data = _get(
            f"/latest/dex/pairs/{quote(str(chain), safe='')}/{quote(str(pair_address), safe='')}",
            timeout=DIRECT_TIMEOUT_SECONDS,
        )
    except Exception:
        return None
    pairs = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs, list):
        return None
    expected = str(pair_address)
    case_insensitive = str(chain).lower() in {
        "ethereum", "eth", "bsc", "bnb", "base", "arbitrum",
        "polygon", "optimism", "avalanche",
    }
    for row in pairs:
        if not isinstance(row, dict):
            continue
        actual = str(row.get("pairAddress") or "")
        if (actual.lower() == expected.lower()) if case_insensitive else (actual == expected):
            return row
    return None


def run(output_dir: str = "data") -> dict:
    original = tracker.pair_lookup
    tracker.pair_lookup = single_attempt_pair_lookup
    try:
        return tracker.run(output_dir)
    finally:
        tracker.pair_lookup = original


if __name__ == "__main__":
    payload = run()
    print(json.dumps({
        "mode": payload.get("mode"),
        "counts": payload.get("counts"),
        "fast_pair_lookup_attempts_per_cycle": 1,
        "direct_timeout_seconds": DIRECT_TIMEOUT_SECONDS,
    }, indent=2))
