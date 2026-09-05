from __future__ import annotations

import html
import json
import os
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from . import social_feed_scan as base
from . import social_direct_providers as direct
from .waking_confirmation import _broad_query

MODE = base.MODE
DEFAULT_PRIORITY_SLOTS = 8
DEFAULT_DIRECT_BUDGETS = {
    "x": 6,
    "youtube": 1,
    "reddit": 6,
}
DIRECT_ENV = {
    "x": "X_DIRECT_SLOTS",
    "youtube": "YOUTUBE_DIRECT_SLOTS",
    "reddit": "REDDIT_DIRECT_SLOTS",
}
DIRECT_CONFIG_KEY = {
    "x": "x",
    "youtube": "youtube",
    "reddit": "reddit_oauth",
}
PERMANENT_DIRECT_FAILURES = {"HTTP_401", "HTTP_402", "HTTP_403", "HTTP_429"}

_DIRECT_CALLS = {"x": 0, "youtube": 0, "reddit": 0}
_DIRECT_BREAKERS: dict[str, str] = {}

_ORIGINAL_SELECT = base._select_targets
_ORIGINAL_IDENTITY = base._identity
_ORIGINAL_ATTRIBUTION = base._attribution
_ORIGINAL_MERGE = base._merge_exact_social_events
_ORIGINAL_X = base._scan_x
_ORIGINAL_YOUTUBE = base._scan_youtube
_ORIGINAL_REDDIT = base._scan_reddit


def _direct_budget(provider: str) -> int:
    env_name = DIRECT_ENV[provider]
    default = DEFAULT_DIRECT_BUDGETS[provider]
    try:
        return max(0, int(os.getenv(env_name, str(default))))
    except (TypeError, ValueError):
        return default


def _reset_direct_runtime_state() -> None:
    _DIRECT_CALLS.update({"x": 0, "youtube": 0, "reddit": 0})
    _DIRECT_BREAKERS.clear()


def _rotating_select(envelope: dict, budget: int) -> list[dict]:
    ranked = _ORIGINAL_SELECT(envelope, 10000)
    if not ranked:
        return []
    cap = max(1, min(int(budget), len(ranked)))
    pslots = max(0, int(os.getenv("SOCIAL_SCAN_PRIORITY_SLOTS", str(DEFAULT_PRIORITY_SLOTS))))
    pslots = min(pslots, cap, len(ranked))
    priority = ranked[:pslots]
    priority_tokens = {str(x.get("token_address") or "") for x in priority}
    remainder = [x for x in ranked if str(x.get("token_address") or "") not in priority_tokens]
    slots = min(cap - len(priority), len(remainder))
    if slots <= 0:
        return priority

    previous = base._load(base.DATA / base.OUTPUT.name, {})
    previous_rotation = [
        str(x.get("token_address") or "")
        for x in (previous.get("targets") or [])
        if isinstance(x, dict) and str(x.get("token_address") or "") not in priority_tokens
    ]
    index = {str(x.get("token_address") or ""): i for i, x in enumerate(remainder)}
    prior_indices = [index[t] for t in previous_rotation if t in index]
    start = (max(prior_indices) + 1) % len(remainder) if prior_indices else 0
    rotation = [remainder[(start + i) % len(remainder)] for i in range(slots)]
    return priority + rotation


def _identity_with_pair(coin: dict):
    identity, statuses = _ORIGINAL_IDENTITY(coin)
    pair = str(coin.get("dex_pair_address") or "").strip()
    identity = dict(identity or {})
    identity["pair_address"] = pair or None
    identity["dex_pair_address"] = pair or None
    return identity, statuses


def _official_handle(url: str | None) -> str | None:
    if not url:
        return None
    try:
        path = urlparse(str(url)).path.strip("/")
        return path.split("/")[0].lower() if path else None
    except Exception:
        return None


def _attribution_v2(event: dict, identity: dict) -> str:
    text = str(event.get("text") or "")
    mint = str(identity.get("token_address") or "")
    pair = str(identity.get("pair_address") or identity.get("dex_pair_address") or "")
    if mint and mint in text:
        return "EXACT_CONTRACT"
    if pair and pair in text:
        return "EXACT_PAIR"
    src = str(event.get("source") or "").lower()
    author = str(event.get("author") or "").lower().lstrip("@")
    handle = _official_handle(identity.get("official_x"))
    if src == "x" and handle and author == handle:
        return "OFFICIAL_CHANNEL_CONTEXT"
    if src == "telegram" and identity.get("official_telegram"):
        return "OFFICIAL_CHANNEL_CONTEXT"
    return "NAME_SYMBOL_CONTEXT"


def _merge_exact_social_events_v2(scan_targets: list[dict], observed_at: str, data_dir) -> int:
    ledger = base._load(data_dir / base.LEDGER.name, {})
    old = ledger.get("events") if isinstance(ledger, dict) else []
    events = list(old) if isinstance(old, list) else []
    known = {str(x.get("fingerprint") or "") for x in events if isinstance(x, dict)}
    added = 0
    accepted = {"EXACT_CONTRACT", "EXACT_PAIR", "OFFICIAL_CHANNEL_CONTEXT"}
    for target in scan_targets:
        token = str(target.get("token_address") or "")
        pair = str(target.get("pair_address") or "")
        for event in target.get("events") or []:
            if not isinstance(event, dict) or str(event.get("source") or "") not in {"x", "youtube", "reddit", "telegram"}:
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
                fp = str(row.get("fingerprint") or "")
                if not fp or fp in known:
                    continue
                row["attribution"] = attr
                row["pair_address"] = pair
                events.append(row)
                known.add(fp)
                added += 1
    events = events[-10000:]
    base._write(data_dir / base.LEDGER.name, {
        "version": 3,
        "updated_at": observed_at,
        "method": "IMMUTABLE_SOCIAL_EVENT_LEDGER_EXACT_MINT_PAIR_OR_OFFICIAL_CONTEXT",
        "events_count": len(events),
        "new_events_this_run": added,
        "quality_metadata_preserved": True,
        "accepted_attribution": sorted(accepted),
        "events": events,
    })
    return added


def _scan_index(identity: dict, provider: str, source: str, site_query: str) -> tuple[list[dict], dict]:
    broad = _broad_query(identity)
    mint = str(identity.get("token_address") or "").strip()
    pair = str(identity.get("pair_address") or identity.get("dex_pair_address") or "").strip()
    identity_terms = [broad]
    if mint:
        identity_terms.append(f'"{mint}"')
    if pair:
        identity_terms.append(f'"{pair}"')
    q = f"({' OR '.join(identity_terms)}) ({site_query}) when:1d"
    url = "https://news.google.com/rss/search?" + urlencode({
        "q": q,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    try:
        req = Request(url, headers={"User-Agent": "Wallet500-SocialIndex/2.0", "Accept": "application/rss+xml,text/xml,*/*"})
        with urlopen(req, timeout=18) as response:
            raw = response.read()
        root = ET.fromstring(raw)
        rows = []
        for i, item in enumerate(root.findall(".//item")[:15]):
            title = html.unescape(str(item.findtext("title") or "")).strip()
            link = str(item.findtext("link") or "").strip()
            published = str(item.findtext("pubDate") or "").strip() or None
            publisher = str(item.findtext("source") or provider).strip()
            if not title:
                continue
            rows.append({
                "source": source,
                "author": publisher,
                "published_at": published,
                "text": title[:1200],
                "url": link,
                "id": f"{provider}:{i}:{title[:80]}",
                "context_only": True,
            })
        return rows, {"provider": provider, "status": "INDEX_OK", "count": len(rows)}
    except Exception as exc:
        code = getattr(exc, "code", None)
        status = f"HTTP_{code}" if code else type(exc).__name__
        return [], {"provider": provider, "status": f"INDEX_{status}"}


def _fallback(direct_fn, identity: dict, provider: str, source: str, sites: str):
    config = direct.provider_config()
    config_key = DIRECT_CONFIG_KEY[provider]
    configured = bool(config.get(config_key))
    budget = _direct_budget(provider)

    if not configured:
        events, status = [], {"provider": provider, "status": "NOT_CONFIGURED"}
    elif provider in _DIRECT_BREAKERS:
        events, status = [], {
            "provider": provider,
            "status": f"CIRCUIT_BREAKER_{_DIRECT_BREAKERS[provider]}",
        }
    elif _DIRECT_CALLS[provider] >= budget:
        events, status = [], {"provider": provider, "status": "SKIPPED_DIRECT_BUDGET"}
    else:
        _DIRECT_CALLS[provider] += 1
        events, status = direct_fn(identity)
        status_text = str((status or {}).get("status") or "UNKNOWN")
        if status_text in PERMANENT_DIRECT_FAILURES:
            _DIRECT_BREAKERS[provider] = status_text

    direct_status = str((status or {}).get("status") or "UNKNOWN")
    if direct_status.startswith("OK"):
        return events, status
    indexed, indexed_status = _scan_index(identity, provider, source, sites)
    if indexed:
        return indexed, {
            "provider": provider,
            "status": "FALLBACK_INDEX_OK_CONTEXT_ONLY",
            "count": len(indexed),
            "direct_status": direct_status,
        }
    return [], {
        "provider": provider,
        "status": direct_status,
        "index_status": indexed_status.get("status"),
    }


def _scan_x_resilient(identity: dict):
    return _fallback(direct.scan_x, identity, "x", "x_index", "site:x.com OR site:twitter.com")


def _scan_youtube_resilient(identity: dict):
    return _fallback(direct.scan_youtube, identity, "youtube", "youtube_index", "site:youtube.com")


def _scan_reddit_resilient(identity: dict):
    return _fallback(direct.scan_reddit, identity, "reddit", "reddit_index", "site:reddit.com")


def run(output_dir: str = "data") -> dict:
    _reset_direct_runtime_state()
    base._select_targets = _rotating_select
    base._identity = _identity_with_pair
    base._attribution = _attribution_v2
    base._merge_exact_social_events = _merge_exact_social_events_v2
    base._scan_x = _scan_x_resilient
    base._scan_youtube = _scan_youtube_resilient
    base._scan_reddit = _scan_reddit_resilient
    try:
        payload = base.run(output_dir)
    finally:
        base._select_targets = _ORIGINAL_SELECT
        base._identity = _ORIGINAL_IDENTITY
        base._attribution = _ORIGINAL_ATTRIBUTION
        base._merge_exact_social_events = _ORIGINAL_MERGE
        base._scan_x = _ORIGINAL_X
        base._scan_youtube = _ORIGINAL_YOUTUBE
        base._scan_reddit = _ORIGINAL_REDDIT

    payload["version"] = 3
    payload["direct_provider_config"] = direct.provider_config()
    payload["direct_provider_budget"] = {provider: _direct_budget(provider) for provider in DEFAULT_DIRECT_BUDGETS}
    payload["direct_provider_calls_used"] = dict(_DIRECT_CALLS)
    payload["direct_provider_circuit_breakers"] = dict(_DIRECT_BREAKERS)
    payload["identity_query_contract"] = {
        "primary": "EXACT_TOKEN_MINT",
        "secondary": "EXACT_PAIR_ADDRESS",
        "official_context": True,
        "broad_name_symbol_context_only": True,
        "accepted_into_social_ledger": ["EXACT_CONTRACT", "EXACT_PAIR", "OFFICIAL_CHANNEL_CONTEXT"],
    }
    payload["selection_policy"] = {
        "priority_slots": max(0, int(os.getenv("SOCIAL_SCAN_PRIORITY_SLOTS", str(DEFAULT_PRIORITY_SLOTS)))),
        "rotation_enabled": True,
        "rotation_state": "PREVIOUS_PUBLISHED_TARGET_SET_ONLY",
        "future_outcomes_used": False,
    }
    rules = list(payload.get("rules") or [])
    for rule in (
        "DIRECT_X_API_USES_EXACT_MINT_PAIR_AND_OFFICIAL_HANDLE",
        "DIRECT_YOUTUBE_API_USES_EXACT_MINT_PAIR_AND_BROAD_CONTEXT",
        "DIRECT_REDDIT_OAUTH_USES_EXACT_MINT_PAIR_AND_BROAD_CONTEXT",
        "EXACT_PAIR_MENTION_IS_VERIFIED_IDENTITY_EVIDENCE",
        "PUBLIC_SEARCH_INDEX_FALLBACK_IS_CONTEXT_ONLY_NEVER_ORGANIC_SOCIAL_PROOF",
        "DIRECT_PROVIDER_FAILURE_IS_UNKNOWN_NOT_ZERO",
        "DIRECT_PROVIDER_CALL_BUDGETS_PROTECT_X_CREDITS_AND_YOUTUBE_DAILY_QUOTA",
        "PERMANENT_DIRECT_HTTP_FAILURE_CIRCUIT_BREAKS_FOR_REMAINDER_OF_RUN",
        "PRIORITY_PLUS_ROTATION_PREVENTS_TOP_TARGET_STARVATION_OF_THE_REST_OF_UNIVERSE",
    ):
        if rule not in rules:
            rules.append(rule)
    payload["rules"] = rules
    base._write(base.DATA / base.OUTPUT.name, payload)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({
        "targets": payload.get("targets_scanned"),
        "providers": payload.get("provider_status_counts"),
        "direct_config": payload.get("direct_provider_config"),
        "direct_budget": payload.get("direct_provider_budget"),
        "direct_calls_used": payload.get("direct_provider_calls_used"),
        "direct_breakers": payload.get("direct_provider_circuit_breakers"),
        "identity_query_contract": payload.get("identity_query_contract"),
        "selection": payload.get("selection_policy"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
