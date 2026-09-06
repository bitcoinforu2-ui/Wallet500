from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from . import social_feed_scan as base
from . import social_feed_scan_v2 as v2
from . import social_feed_scan_v3 as v3
from . import social_mesh_public_index as public_index
from . import social_telegram_truth_hardening as telegram_truth

DEFAULT_PUBLIC_INDEX_SLOTS = 8
EXACT_ATTRS = {"EXACT_CONTRACT", "EXACT_PAIR"}
DIRECT_SOURCES = {"x", "youtube", "reddit", "telegram", "farcaster", "discord", "threads", "bluesky"}
CREDENTIAL_REQUIREMENTS = {
    "x": ["X_BEARER_TOKEN"],
    "youtube": ["YOUTUBE_API_KEY"],
    "reddit": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "public_json_fallback"],
    "telegram_official": ["public_channel_url"],
    "telegram_mtproto": ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION"],
    "farcaster": ["NEYNAR_API_KEY"],
    "discord": ["DISCORD_BOT_TOKEN", "DISCORD_GUILD_IDS_or_DISCORD_CHANNEL_IDS"],
    "threads": ["THREADS_ACCESS_TOKEN"],
    "bluesky": ["public_appview", "optional_BSKY_IDENTIFIER", "optional_BSKY_APP_PASSWORD"],
    "social_mesh_public_index": ["none_public_rss"],
}


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


def _event_provider(event: dict) -> str | None:
    source = str(event.get("source") or "").lower()
    if source.endswith("_index") or source == "mesh_index":
        return "social_mesh_public_index"
    if source == "telegram":
        if event.get("query_kind") or event.get("channel_id") or event.get("mesh_provider"):
            return "telegram_mtproto"
        return "telegram_official"
    if source in {"x", "youtube", "reddit", "farcaster", "discord", "threads", "bluesky"}:
        return source
    return None


def _source_health(payload: dict) -> dict:
    providers = [
        "x", "youtube", "reddit", "telegram_official", "telegram_mtproto",
        "farcaster", "discord", "threads", "bluesky", "social_mesh_public_index",
    ]
    statuses: dict[str, list[str]] = defaultdict(list)
    exact_direct: dict[str, int] = defaultdict(int)
    official_context: dict[str, int] = defaultdict(int)
    index_exact: dict[str, int] = defaultdict(int)
    tokens_with_exact: dict[str, set[str]] = defaultdict(set)

    for target in payload.get("targets") or []:
        if not isinstance(target, dict):
            continue
        token = str(target.get("token_address") or "")
        for status in target.get("provider_status") or []:
            if not isinstance(status, dict):
                continue
            provider = str(status.get("provider") or "")
            value = str(status.get("status") or "UNKNOWN")
            if provider:
                statuses[provider].append(value)
        for event in target.get("events") or []:
            if not isinstance(event, dict):
                continue
            provider = _event_provider(event)
            if not provider:
                continue
            attr = str(event.get("attribution") or "")
            is_index = bool(event.get("context_only")) or str(event.get("source") or "").endswith("_index")
            if is_index and attr in EXACT_ATTRS:
                index_exact[provider] += 1
                if token:
                    tokens_with_exact[provider].add(token)
            elif attr in EXACT_ATTRS:
                exact_direct[provider] += 1
                if token:
                    tokens_with_exact[provider].add(token)
            elif attr == "OFFICIAL_CHANNEL_CONTEXT":
                official_context[provider] += 1

    direct_cfg = payload.get("direct_provider_config") or {}
    mesh_cfg = payload.get("mesh_provider_config") or {}
    configured = {
        "x": bool(direct_cfg.get("x")),
        "youtube": bool(direct_cfg.get("youtube")),
        "reddit": bool(direct_cfg.get("reddit_oauth") or direct_cfg.get("reddit_public")),
        "telegram_official": bool(direct_cfg.get("telegram_public_direct")),
        "telegram_mtproto": bool(mesh_cfg.get("telegram_mtproto")),
        "farcaster": bool(mesh_cfg.get("farcaster_neynar")),
        "discord": bool(mesh_cfg.get("discord_watch")),
        "threads": bool(mesh_cfg.get("threads_keyword")),
        "bluesky": bool(mesh_cfg.get("bluesky_public")),
        "social_mesh_public_index": bool((payload.get("mesh_public_index") or {}).get("enabled")),
    }

    rows = {}
    summary = defaultdict(int)
    for provider in providers:
        status_values = sorted(set(statuses.get(provider) or []))
        has_ok = any(s.startswith("OK") or "INDEX_OK" in s for s in status_values)
        has_failure = any(
            s.startswith("HTTP_") or s.startswith("CIRCUIT_BREAKER_") or "NETWORK" in s or "ERROR" in s
            for s in status_values
        )
        is_not_configured = bool(status_values) and all(s == "NOT_CONFIGURED" for s in status_values)
        exact_n = int(exact_direct.get(provider) or 0)
        official_n = int(official_context.get(provider) or 0)
        indexed_n = int(index_exact.get(provider) or 0)

        if exact_n > 0:
            state = "ACTIVE_EXACT_EVIDENCE"
        elif official_n > 0:
            state = "ACTIVE_OFFICIAL_CONTEXT"
        elif indexed_n > 0:
            state = "INDEX_CONTEXT_ONLY"
        elif is_not_configured or not configured.get(provider, False):
            state = "NOT_CONFIGURED"
        elif has_failure:
            state = "DEGRADED_UNKNOWN"
        elif has_ok:
            state = "ACTIVE_NO_EXACT_EVIDENCE"
        else:
            state = "UNKNOWN"
        summary[state] += 1
        rows[provider] = {
            "state": state,
            "configured": bool(configured.get(provider)),
            "statuses": status_values,
            "exact_direct_events": exact_n,
            "official_context_events": official_n,
            "indexed_exact_context_events": indexed_n,
            "tokens_with_exact_evidence": len(tokens_with_exact.get(provider) or set()),
            "credential_requirements": CREDENTIAL_REQUIREMENTS.get(provider, []),
            "unknown_is_not_zero": True,
            "score_effect": "NONE_PROVIDER_HEALTH_ONLY",
        }

    return {
        "version": 1,
        "summary": dict(summary),
        "providers": rows,
        "truth": {
            "configuration_is_not_evidence": True,
            "index_context_never_counts_as_organic": True,
            "provider_health_does_not_modify_token_scores": True,
            "secret_values_never_exposed": True,
        },
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

    payload["version"] = max(8, int(payload.get("version") or 0))
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
    payload["source_health"] = _source_health(payload)
    rules = list(payload.get("rules") or [])
    for rule in (
        "SOCIAL_MESH_PUBLIC_INDEX_REQUIRES_EXACT_MINT_OR_PAIR_IN_RETURNED_TITLE",
        "SOCIAL_MESH_PUBLIC_INDEX_IS_CONTEXT_ONLY_NEVER_ORGANIC",
        "PUBLIC_INDEX_ZERO_RESULTS_MEANS_UNKNOWN_NOT_ZERO",
        "TELEGRAM_PUBLIC_MESSAGES_REQUIRE_ORIGINAL_PUBLISHED_AT_FOR_FRESHNESS",
        "TELEGRAM_UNTIMESTAMPED_PUBLIC_MESSAGES_ARE_DROPPED_NOT_ASSUMED_FRESH",
        "TELEGRAM_OFFICIAL_CONTEXT_REQUIRES_EXACT_AUTHOR_HANDLE_MATCH",
        "SOURCE_HEALTH_CONFIGURATION_NEVER_COUNTS_AS_EVIDENCE",
        "SOURCE_HEALTH_IS_OBSERVABILITY_ONLY_NO_SCORE_EFFECT",
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
        "source_health": (payload.get("source_health") or {}).get("summary"),
        "mesh_public_index": payload.get("mesh_public_index"),
        "mesh_config": payload.get("mesh_provider_config"),
        "mesh_breakers": payload.get("mesh_provider_circuit_breakers"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
