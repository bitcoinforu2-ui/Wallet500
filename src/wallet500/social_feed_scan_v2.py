from __future__ import annotations

import html
import json
import os
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import social_feed_scan as base
from .waking_confirmation import _broad_query

MODE = base.MODE
DEFAULT_PRIORITY_SLOTS = 8

_ORIGINAL_SELECT = base._select_targets
_ORIGINAL_X = base._scan_x
_ORIGINAL_YOUTUBE = base._scan_youtube
_ORIGINAL_REDDIT = base._scan_reddit


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


def _scan_index(identity: dict, provider: str, source: str, site_query: str) -> tuple[list[dict], dict]:
    broad = _broad_query(identity)
    mint = str(identity.get("token_address") or "").strip()
    q = f"({broad} OR \"{mint}\") ({site_query}) when:1d"
    url = "https://news.google.com/rss/search?" + urlencode({
        "q": q,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    try:
        req = Request(url, headers={"User-Agent": "Wallet500-SocialIndex/1.0", "Accept": "application/rss+xml,text/xml,*/*"})
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


def _fallback(direct, identity: dict, provider: str, source: str, sites: str):
    events, status = direct(identity)
    direct_status = str((status or {}).get("status") or "UNKNOWN")
    if direct_status == "OK":
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
    return _fallback(_ORIGINAL_X, identity, "x", "x_index", "site:x.com OR site:twitter.com")


def _scan_youtube_resilient(identity: dict):
    return _fallback(_ORIGINAL_YOUTUBE, identity, "youtube", "youtube_index", "site:youtube.com")


def _scan_reddit_resilient(identity: dict):
    return _fallback(_ORIGINAL_REDDIT, identity, "reddit", "reddit_index", "site:reddit.com")


def run(output_dir: str = "data") -> dict:
    base._select_targets = _rotating_select
    base._scan_x = _scan_x_resilient
    base._scan_youtube = _scan_youtube_resilient
    base._scan_reddit = _scan_reddit_resilient
    payload = base.run(output_dir)
    payload["version"] = 2
    payload["selection_policy"] = {
        "priority_slots": max(0, int(os.getenv("SOCIAL_SCAN_PRIORITY_SLOTS", str(DEFAULT_PRIORITY_SLOTS)))),
        "rotation_enabled": True,
        "rotation_state": "PREVIOUS_PUBLISHED_TARGET_SET_ONLY",
        "future_outcomes_used": False,
    }
    rules = list(payload.get("rules") or [])
    for rule in (
        "PUBLIC_SEARCH_INDEX_FALLBACK_IS_CONTEXT_ONLY_NEVER_ORGANIC_SOCIAL_PROOF",
        "DIRECT_PROVIDER_FAILURE_IS_UNKNOWN_NOT_ZERO",
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
        "selection": payload.get("selection_policy"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
