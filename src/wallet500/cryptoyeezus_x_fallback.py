from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

from .cryptoyeezus_live_watch import (
    CALLS_PATH,
    LATEST_PATH,
    STATE_PATH,
    X_HANDLE,
    _event_from_row,
    _find_cross_post,
    _load,
    _post_key,
    _write,
)

SYNDICATION_URL = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{X_HANDLE}"
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _screen_name(node: dict) -> str | None:
    core = node.get("core") or {}
    result = (((core.get("user_results") or {}).get("result")) or {})
    legacy = result.get("legacy") or {}
    name = legacy.get("screen_name")
    if name:
        return str(name)

    user = node.get("user") or {}
    legacy = user.get("legacy") or {}
    name = legacy.get("screen_name") or user.get("screen_name")
    return str(name) if name else None


def _iso_created_at(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            return None


def extract_syndication_rows(payload: dict) -> list[dict]:
    rows: dict[str, dict] = {}
    wanted = X_HANDLE.lower()
    for node in _walk(payload):
        legacy = node.get("legacy")
        if not isinstance(legacy, dict):
            continue
        text = str(legacy.get("full_text") or legacy.get("text") or "").strip()
        tweet_id = str(legacy.get("id_str") or node.get("rest_id") or node.get("id_str") or "").strip()
        if not text or not tweet_id.isdigit():
            continue
        author = (_screen_name(node) or "").strip().lstrip("@").lower()
        if author != wanted:
            continue
        if text.startswith("RT @"):
            continue
        published_at = _iso_created_at(legacy.get("created_at"))
        if not published_at:
            continue
        rows[tweet_id] = {
            "source": "x",
            "id": tweet_id,
            "author": X_HANDLE,
            "published_at": published_at,
            "text": text[:1500],
            "url": f"https://x.com/{X_HANDLE}/status/{tweet_id}",
            "direct_provider": False,
            "provider": "x_syndication_public",
        }
    return sorted(rows.values(), key=lambda row: str(row.get("published_at") or ""))


def fetch_syndication() -> tuple[list[dict], dict]:
    try:
        req = Request(
            SYNDICATION_URL,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Mozilla/5.0 Wallet500-XFallback/1.0",
            },
        )
        with urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
        match = NEXT_DATA_RE.search(body)
        if not match:
            return [], {"provider": "x_syndication_public", "status": "NO_NEXT_DATA"}
        payload = json.loads(html_lib.unescape(match.group(1)))
        rows = extract_syndication_rows(payload)
        return rows, {
            "provider": "x_syndication_public",
            "status": "OK_SYNDICATION" if rows else "EMPTY_SYNDICATION",
            "count": len(rows),
            "url": SYNDICATION_URL,
        }
    except Exception as exc:
        return [], {
            "provider": "x_syndication_public",
            "status": f"{type(exc).__name__}:{str(exc)[:120]}",
            "url": SYNDICATION_URL,
        }


def run() -> dict:
    observed_at = _now_iso()
    latest = _load(LATEST_PATH, {"providers": {}, "latest_events": []})
    direct_x = ((latest.get("providers") or {}).get("x") or {})
    direct_status = str(direct_x.get("status") or "")
    if direct_status.startswith("OK"):
        latest["x_fallback"] = {"status": "DIRECT_X_HEALTHY_SKIP_FALLBACK"}
        _write(LATEST_PATH, latest)
        return latest["x_fallback"]

    rows, fallback_status = fetch_syndication()
    latest["x_fallback"] = fallback_status
    providers = latest.setdefault("providers", {})
    x_status = providers.setdefault("x", {})
    if str(fallback_status.get("status") or "").startswith("OK"):
        x_status["redundancy_status"] = "OK_SYNDICATION"
        x_status["effective_status"] = "OK_WITH_PUBLIC_FALLBACK"
    else:
        x_status["redundancy_status"] = fallback_status.get("status")
        x_status["effective_status"] = direct_status or fallback_status.get("status")

    state = _load(STATE_PATH, {
        "version": 1,
        "bootstrapped": True,
        "run_count": 0,
        "seen_posts": [],
        "tokens": {},
    })
    seen = {str(x) for x in state.get("seen_posts") or []}

    if not state.get("x_syndication_bootstrapped"):
        if str(fallback_status.get("status") or "").startswith("OK"):
            for row in rows:
                seen.add(_post_key(row))
            state["x_syndication_bootstrapped"] = True
            state["x_syndication_baseline_at"] = observed_at
            state["seen_posts"] = list(seen)[-1500:]
            state.setdefault("provider_status", {})["x_fallback"] = fallback_status
            _write(STATE_PATH, state)
            _write(LATEST_PATH, latest)
        return {
            "status": "BASELINE_BOOTSTRAPPED" if state.get("x_syndication_bootstrapped") else "FALLBACK_UNAVAILABLE",
            "provider": fallback_status,
            "new_call_events": 0,
        }

    new_rows = [row for row in rows if _post_key(row) not in seen]
    calls_doc = _load(CALLS_PATH, {"events": []})
    events = calls_doc.setdefault("events", [])
    new_events = []

    for row in new_rows:
        seen.add(_post_key(row))
        event = _event_from_row(row, state, observed_at, resolve_market=True)
        if not event:
            continue
        cross_post = _find_cross_post(event, events)
        if cross_post:
            event["event_type"] = "CROSS_POST_DUPLICATE"
            event["canonical_event_id"] = cross_post.get("event_id")
            event["alert"] = {
                "attempted": False,
                "sent": False,
                "reason": "CROSS_SOURCE_DEDUPLICATED",
            }
            cross_post.setdefault("cross_posts", []).append({
                "source": "x",
                "published_at": event.get("published_at"),
                "url": event.get("url"),
                "source_post_id": event.get("source_post_id"),
                "provider": "x_syndication_public",
            })
        else:
            event["alert"] = {
                "attempted": False,
                "sent": False,
                "reason": "DEFERRED_TO_CRYPTOYEEZUS_PRIORITY_V2",
            }
        event["source_provider"] = "x_syndication_public"
        events.append(event)
        new_events.append(event)

    state["seen_posts"] = list(seen)[-1500:]
    state.setdefault("provider_status", {})["x_fallback"] = fallback_status
    state["x_syndication_last_run_at"] = observed_at
    calls_doc["events"] = events[-2000:]
    calls_doc["updated_at"] = observed_at
    calls_doc["event_count"] = len(calls_doc["events"])

    current_latest = list(latest.get("latest_events") or [])
    latest["latest_events"] = (current_latest + new_events)[-20:]
    latest["new_posts"] = int(latest.get("new_posts") or 0) + len(new_rows)
    latest["new_call_events"] = int(latest.get("new_call_events") or 0) + len(new_events)
    latest["x_fallback_new_posts"] = len(new_rows)
    latest["x_fallback_new_call_events"] = len(new_events)

    _write(STATE_PATH, state)
    _write(CALLS_PATH, calls_doc)
    _write(LATEST_PATH, latest)
    return {
        "status": fallback_status.get("status"),
        "new_posts": len(new_rows),
        "new_call_events": len(new_events),
    }


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
