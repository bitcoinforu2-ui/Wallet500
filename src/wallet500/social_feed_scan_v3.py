from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import social_feed_scan as base
from . import social_feed_scan_v2 as v2
from . import social_mesh_providers as mesh
from . import social_catalyst as catalyst

MODE = base.MODE
MESH_SOURCES = {"telegram", "farcaster", "discord", "threads", "bluesky"}
MESH_PROVIDERS = ("telegram_mtproto", "farcaster", "discord", "threads", "bluesky")
DEFAULT_MESH_BUDGETS = {
    "telegram_mtproto": 4,
    "farcaster": 6,
    "discord": 6,
    "threads": 6,
    "bluesky": 12,
}
MESH_ENV = {
    "telegram_mtproto": "TELEGRAM_DIRECT_SLOTS",
    "farcaster": "FARCASTER_DIRECT_SLOTS",
    "discord": "DISCORD_DIRECT_SLOTS",
    "threads": "THREADS_DIRECT_SLOTS",
    "bluesky": "BLUESKY_DIRECT_SLOTS",
}
PERMANENT_FAILURES = {"HTTP_401", "HTTP_402", "HTTP_403", "HTTP_429"}

_MESH_CALLS = {provider: 0 for provider in MESH_PROVIDERS}
_MESH_BREAKERS: dict[str, str] = {}


def _budget(provider: str) -> int:
    default = DEFAULT_MESH_BUDGETS[provider]
    try:
        return max(0, int(os.getenv(MESH_ENV[provider], str(default))))
    except (TypeError, ValueError):
        return default


def _configured(provider: str) -> bool:
    cfg = mesh.provider_config()
    key = {
        "telegram_mtproto": "telegram_mtproto",
        "farcaster": "farcaster_neynar",
        "discord": "discord_watch",
        "threads": "threads_keyword",
        "bluesky": "bluesky_public",
    }[provider]
    return bool(cfg.get(key))


def _reset_runtime_state() -> None:
    for provider in MESH_PROVIDERS:
        _MESH_CALLS[provider] = 0
    _MESH_BREAKERS.clear()


def _official_telegram_handle(url: str | None) -> str | None:
    if not url:
        return None
    try:
        path = urlparse(str(url)).path.strip("/")
        handle = path.split("/")[0] if path else ""
        if not handle or handle.startswith("+"):
            return None
        return handle.lower()
    except Exception:
        return None


def _mesh_attribution(event: dict, identity: dict) -> str:
    text = str(event.get("text") or "")
    mint = str(identity.get("token_address") or "")
    pair = str(identity.get("pair_address") or identity.get("dex_pair_address") or "")
    if mint and mint in text:
        return "EXACT_CONTRACT"
    if pair and pair in text:
        return "EXACT_PAIR"

    if str(event.get("source") or "").lower() == "telegram":
        official = _official_telegram_handle(identity.get("official_telegram"))
        author = str(event.get("author") or "").lower().lstrip("@")
        if official and author == official:
            return "OFFICIAL_CHANNEL_CONTEXT"
    return "NAME_SYMBOL_CONTEXT"


def _scan_provider(provider: str, identity: dict):
    if not _configured(provider):
        return [], {"provider": provider, "status": "NOT_CONFIGURED", "meaning": "UNKNOWN_NOT_ZERO"}
    if provider in _MESH_BREAKERS:
        return [], {
            "provider": provider,
            "status": f"CIRCUIT_BREAKER_{_MESH_BREAKERS[provider]}",
            "meaning": "UNKNOWN_NOT_ZERO",
        }
    if _MESH_CALLS[provider] >= _budget(provider):
        return [], {
            "provider": provider,
            "status": "SKIPPED_DIRECT_BUDGET",
            "meaning": "UNKNOWN_NOT_ZERO",
        }

    _MESH_CALLS[provider] += 1
    fn = mesh.MESH_SCANNERS[provider]
    events, status = fn(identity)
    status = dict(status or {})
    status.setdefault("provider", provider)
    status_text = str(status.get("status") or "UNKNOWN")
    if status_text in PERMANENT_FAILURES:
        _MESH_BREAKERS[provider] = status_text
    return events or [], status


def _merge_mesh_events(targets: list[dict], observed_at: str, data_dir: Path) -> int:
    ledger_path = data_dir / base.LEDGER.name
    ledger = base._load(ledger_path, {})
    events = list(ledger.get("events") or []) if isinstance(ledger, dict) else []
    known = {str(x.get("fingerprint") or "") for x in events if isinstance(x, dict)}
    added = 0
    accepted = {"EXACT_CONTRACT", "EXACT_PAIR", "OFFICIAL_CHANNEL_CONTEXT"}

    for target in targets:
        token = str(target.get("token_address") or "")
        pair = str(target.get("pair_address") or "")
        for event in target.get("mesh_events") or []:
            if not isinstance(event, dict) or str(event.get("source") or "") not in MESH_SOURCES:
                continue
            attr = str(event.get("attribution") or "")
            if attr not in accepted:
                continue
            raw = dict(event)
            raw.update({"contract": token, "pair_address": pair, "chain": base.NETWORK})
            if attr == "OFFICIAL_CHANNEL_CONTEXT":
                raw["project_owned"] = True
                raw["author_role"] = "official"
            for row in base._normalize(raw, observed_at):
                original_source = str(raw.get("source") or "")
                if original_source in MESH_SOURCES and row.get("source") != original_source:
                    row["source"] = original_source
                    row["fingerprint"] = catalyst._fingerprint(row)
                fp = str(row.get("fingerprint") or "")
                if not fp or fp in known:
                    continue
                row["attribution"] = attr
                row["pair_address"] = pair
                row["mesh_provider"] = True
                events.append(row)
                known.add(fp)
                added += 1

    events = events[-10000:]
    base._write(ledger_path, {
        "version": 4,
        "updated_at": observed_at,
        "method": "IMMUTABLE_SOCIAL_EVENT_LEDGER_EXACT_MINT_PAIR_OR_OFFICIAL_CONTEXT_SOCIAL_MESH",
        "events_count": len(events),
        "new_events_this_run": added,
        "quality_metadata_preserved": True,
        "accepted_attribution": sorted(accepted),
        "mesh_sources": sorted(MESH_SOURCES),
        "events": events,
    })
    return added


def run(output_dir: str | Path = "data") -> dict:
    _reset_runtime_state()
    data_dir = Path(output_dir)
    payload = v2.run(str(data_dir))
    observed_at = datetime.now(timezone.utc).isoformat()
    provider_counts = dict(payload.get("provider_status_counts") or {})

    for target in payload.get("targets") or []:
        if not isinstance(target, dict):
            continue
        identity = dict(target.get("identity") or {})
        identity.setdefault("token_address", target.get("token_address"))
        identity.setdefault("pair_address", target.get("pair_address"))
        identity.setdefault("dex_pair_address", target.get("pair_address"))
        identity.setdefault("symbol", target.get("symbol"))
        identity.setdefault("name", target.get("name"))

        mesh_events = []
        statuses = list(target.get("provider_status") or [])
        for provider in MESH_PROVIDERS:
            rows, status = _scan_provider(provider, identity)
            statuses.append(status)
            key = f"{status.get('provider')}:{status.get('status')}"
            provider_counts[key] = provider_counts.get(key, 0) + 1
            for event in rows:
                if not isinstance(event, dict):
                    continue
                row = dict(event)
                row["attribution"] = _mesh_attribution(row, identity)
                mesh_events.append(row)

        target["mesh_events"] = mesh_events
        target["events"] = list(target.get("events") or []) + mesh_events
        target["provider_status"] = statuses

    merged = _merge_mesh_events(payload.get("targets") or [], observed_at, data_dir)
    payload["version"] = 5
    payload["generated_at"] = observed_at
    payload["provider_status_counts"] = provider_counts
    payload["mesh_provider_config"] = mesh.provider_config()
    payload["mesh_provider_budget"] = {provider: _budget(provider) for provider in MESH_PROVIDERS}
    payload["mesh_provider_calls_used"] = dict(_MESH_CALLS)
    payload["mesh_provider_circuit_breakers"] = dict(_MESH_BREAKERS)
    payload["new_mesh_social_events_merged"] = merged
    payload["social_mesh"] = {
        "enabled": True,
        "sources": ["telegram_mtproto", "farcaster", "discord", "threads", "bluesky"],
        "organic_eligibility_requires_exact_identity": True,
        "official_telegram_requires_author_match": True,
        "missing_provider_is_unknown_not_zero": True,
    }

    rules = list(payload.get("rules") or [])
    for rule in (
        "TELEGRAM_MTPROTO_GLOBAL_SEARCH_REQUIRES_AUTHORIZED_STRING_SESSION",
        "TELEGRAM_OFFICIAL_CONTEXT_REQUIRES_AUTHOR_HANDLE_MATCH",
        "FARCASTER_NEYNAR_DIRECT_CAST_SEARCH",
        "DISCORD_WATCHED_GUILD_OR_CHANNEL_ONLY_NO_GLOBAL_DISCORD_CLAIM",
        "THREADS_KEYWORD_SEARCH_REQUIRES_THREADS_KEYWORD_SEARCH_SCOPE",
        "BLUESKY_PUBLIC_APPVIEW_SEARCH_POSTS_DIRECT",
        "MESH_NAME_SYMBOL_CONTEXT_NEVER_ENTERS_ORGANIC_LEDGER",
        "MESH_EXACT_MINT_PAIR_OR_VERIFIED_OFFICIAL_CONTEXT_ONLY",
        "MESH_PROVIDER_FAILURE_IS_UNKNOWN_NOT_ZERO",
        "MESH_CALL_BUDGETS_AND_CIRCUIT_BREAKERS_ENABLED",
    ):
        if rule not in rules:
            rules.append(rule)
    payload["rules"] = rules

    base._write(data_dir / base.OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "targets": payload.get("targets_scanned"),
        "mesh_config": payload.get("mesh_provider_config"),
        "mesh_budget": payload.get("mesh_provider_budget"),
        "mesh_calls": payload.get("mesh_provider_calls_used"),
        "mesh_breakers": payload.get("mesh_provider_circuit_breakers"),
        "mesh_merged": payload.get("new_mesh_social_events_merged"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
