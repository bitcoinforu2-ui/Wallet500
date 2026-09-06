from __future__ import annotations

import json
import os
from pathlib import Path

from . import social_feed_scan as base
from . import social_feed_scan_v3 as v3
from . import social_mesh_public_index as public_index

DEFAULT_PUBLIC_INDEX_SLOTS = 8


def _budget() -> int:
    try:
        return max(0, min(24, int(os.getenv("MESH_PUBLIC_INDEX_SLOTS", str(DEFAULT_PUBLIC_INDEX_SLOTS)))))
    except (TypeError, ValueError):
        return DEFAULT_PUBLIC_INDEX_SLOTS


def run(output_dir: str | Path = "data") -> dict:
    data = Path(output_dir)
    payload = v3.run(data)
    budget = _budget()
    calls = 0
    indexed_events = 0
    indexed_tokens = 0
    provider_counts = dict(payload.get("provider_status_counts") or {})

    for target in payload.get("targets") or []:
        if calls >= budget:
            break
        if not isinstance(target, dict):
            continue
        identity = dict(target.get("identity") or {})
        identity.setdefault("token_address", target.get("token_address"))
        identity.setdefault("pair_address", target.get("pair_address"))
        identity.setdefault("dex_pair_address", target.get("pair_address"))
        calls += 1
        rows, status = public_index.scan_mesh_public_index(identity)
        statuses = list(target.get("provider_status") or [])
        statuses.append(status)
        target["provider_status"] = statuses
        key = f"{status.get('provider')}:{status.get('status')}"
        provider_counts[key] = provider_counts.get(key, 0) + 1
        if rows:
            indexed_tokens += 1
            indexed_events += len(rows)
            target["mesh_index_events"] = rows
            target["events"] = list(target.get("events") or []) + rows
        else:
            target["mesh_index_events"] = []

    payload["version"] = max(6, int(payload.get("version") or 0))
    payload["provider_status_counts"] = provider_counts
    payload["mesh_public_index"] = {
        "enabled": True,
        "calls_used": calls,
        "budget": budget,
        "tokens_with_exact_context": indexed_tokens,
        "exact_context_events": indexed_events,
        "organic_eligible": False,
        "identity_rule": "EXACT_MINT_OR_PAIR_MUST_APPEAR_IN_INDEXED_TITLE",
        "scope": ["telegram", "farcaster", "discord", "threads", "bluesky"],
    }
    rules = list(payload.get("rules") or [])
    for rule in (
        "SOCIAL_MESH_PUBLIC_INDEX_REQUIRES_EXACT_MINT_OR_PAIR_IN_RETURNED_TITLE",
        "SOCIAL_MESH_PUBLIC_INDEX_IS_CONTEXT_ONLY_NEVER_ORGANIC",
        "PUBLIC_INDEX_ZERO_RESULTS_MEANS_UNKNOWN_NOT_ZERO",
    ):
        if rule not in rules:
            rules.append(rule)
    payload["rules"] = rules
    base._write(data / base.OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "targets": payload.get("targets_scanned"),
        "mesh_public_index": payload.get("mesh_public_index"),
        "mesh_config": payload.get("mesh_provider_config"),
        "mesh_breakers": payload.get("mesh_provider_circuit_breakers"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
