from __future__ import annotations

import json
import os
from pathlib import Path

from . import social_feed_scan as base
from . import social_feed_scan_v2 as v2
from . import social_feed_scan_v3 as v3
from . import social_mesh_public_index as public_index
from . import social_telegram_truth_hardening as telegram_truth

DEFAULT_PUBLIC_INDEX_SLOTS = 8


def _budget() -> int:
    try:
        return max(0, min(24, int(os.getenv("MESH_PUBLIC_INDEX_SLOTS", str(DEFAULT_PUBLIC_INDEX_SLOTS)))))
    except (TypeError, ValueError):
        return DEFAULT_PUBLIC_INDEX_SLOTS


def _run_truth_hardened_v3(data: Path) -> dict:
    original_telegram_scan = base._scan_public_telegram
    original_v2_attribution = v2._attribution_v2
    base._scan_public_telegram = telegram_truth.scan_public_telegram
    v2._attribution_v2 = telegram_truth.attribution_v2
    try:
        return v3.run(data)
    finally:
        base._scan_public_telegram = original_telegram_scan
        v2._attribution_v2 = original_v2_attribution


def _telegram_timestamp_health(payload: dict) -> dict:
    ok_targets = 0
    messages = 0
    timestamped = 0
    dropped = 0
    missing_timestamp_status = 0
    for target in payload.get("targets") or []:
        if not isinstance(target, dict):
            continue
        for status in target.get("provider_status") or []:
            if not isinstance(status, dict) or status.get("provider") != "telegram_official":
                continue
            if status.get("status") == "OK":
                ok_targets += 1
                messages += int(status.get("count") or 0)
                timestamped += int(status.get("timestamped_count") or 0)
                dropped += int(status.get("dropped_untimestamped") or 0)
                if status.get("timestamp_required") is not True:
                    missing_timestamp_status += 1
    return {
        "official_targets_ok": ok_targets,
        "messages_accepted": messages,
        "timestamped_messages": timestamped,
        "dropped_untimestamped": dropped,
        "timestamp_required": True,
        "official_author_match_required": True,
        "freshness_source": "TELEGRAM_ORIGINAL_DATETIME",
        "status_contract_violations": missing_timestamp_status,
    }


def run(output_dir: str | Path = "data") -> dict:
    data = Path(output_dir)
    payload = _run_truth_hardened_v3(data)
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

    payload["version"] = max(7, int(payload.get("version") or 0))
    payload["provider_status_counts"] = provider_counts
    payload["telegram_truth_hardening"] = _telegram_timestamp_health(payload)
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
        "TELEGRAM_PUBLIC_MESSAGES_REQUIRE_ORIGINAL_PUBLISHED_AT_FOR_FRESHNESS",
        "TELEGRAM_UNTIMESTAMPED_PUBLIC_MESSAGES_ARE_DROPPED_NOT_ASSUMED_FRESH",
        "TELEGRAM_OFFICIAL_CONTEXT_REQUIRES_EXACT_AUTHOR_HANDLE_MATCH",
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
        "telegram_truth": payload.get("telegram_truth_hardening"),
        "mesh_public_index": payload.get("mesh_public_index"),
        "mesh_config": payload.get("mesh_provider_config"),
        "mesh_breakers": payload.get("mesh_provider_circuit_breakers"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
