from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import social_mesh_providers as mesh

USER_AGENT = "Wallet500-Bluesky/1.0"


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return "NETWORK_UNAVAILABLE"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _post_json(url: str, payload: dict, timeout: int = 18) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, token: str, timeout: int = 18) -> dict:
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _queries(identity: dict) -> list[str]:
    terms = mesh._identity_terms(identity)
    out = mesh.exact_queries(identity)[:1]
    if terms.get("symbol") and len(str(terms["symbol"])) >= 3:
        out.append(f"${terms['symbol']}")
    elif terms.get("name"):
        out.append(str(terms["name"]))
    return list(dict.fromkeys(q for q in out if q))[:2]


def _map_posts(payload: dict, seen: set[str]) -> list[dict]:
    rows = []
    for item in payload.get("posts") or []:
        if not isinstance(item, dict):
            continue
        author = item.get("author") or {}
        record = item.get("record") or {}
        uri = str(item.get("uri") or "")
        if uri and uri in seen:
            continue
        if uri:
            seen.add(uri)
        rkey = uri.rsplit("/", 1)[-1] if "/" in uri else ""
        handle = str(author.get("handle") or author.get("did") or "")
        rows.append({
            "source": "bluesky",
            "id": uri or item.get("cid"),
            "author": handle,
            "author_id": author.get("did"),
            "followers": author.get("followersCount"),
            "published_at": record.get("createdAt") or item.get("indexedAt"),
            "text": str(record.get("text") or "")[:1500],
            "engagement": float(item.get("likeCount") or 0)
            + float(item.get("repostCount") or 0)
            + float(item.get("replyCount") or 0)
            + float(item.get("quoteCount") or 0),
            "url": f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else None,
            "direct_provider": True,
        })
    return rows


def scan_bluesky_resilient(identity: dict):
    public_rows, public_status = mesh.scan_bluesky(identity)
    public_status = dict(public_status or {})
    if str(public_status.get("status") or "").startswith("OK"):
        public_status["auth_fallback"] = "NOT_NEEDED"
        return public_rows, public_status

    identifier = (os.getenv("BSKY_IDENTIFIER") or "").strip()
    app_password = (os.getenv("BSKY_APP_PASSWORD") or "").strip()
    if not identifier or not app_password:
        public_status["auth_fallback"] = "NOT_CONFIGURED"
        public_status["meaning"] = "UNKNOWN_NOT_ZERO"
        return public_rows, public_status

    try:
        session = _post_json(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            {"identifier": identifier, "password": app_password},
        )
        token = str(session.get("accessJwt") or "").strip()
        if not token:
            return [], {
                "provider": "bluesky",
                "status": "AUTH_NO_ACCESS_JWT",
                "public_status": public_status.get("status"),
                "meaning": "UNKNOWN_NOT_ZERO",
            }
    except Exception as exc:
        return [], {
            "provider": "bluesky",
            "status": "AUTH_SESSION_" + _safe_error(exc),
            "public_status": public_status.get("status"),
            "meaning": "UNKNOWN_NOT_ZERO",
        }

    queries = _queries(identity)
    rows: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for query in queries:
        params = urlencode({"q": query, "limit": 15, "sort": "latest"})
        try:
            payload = _get_json(
                "https://bsky.social/xrpc/app.bsky.feed.searchPosts?" + params,
                token,
            )
            rows.extend(_map_posts(payload, seen))
        except Exception as exc:
            errors.append(_safe_error(exc))

    if rows or not errors:
        return rows[:30], {
            "provider": "bluesky",
            "status": "OK_DIRECT_AUTH",
            "count": len(rows),
            "queries": len(queries),
            "query_identity": "EXACT_MINT_PLUS_SYMBOL_OR_NAME_LATEST",
            "public_status": public_status.get("status"),
            "auth_fallback": "USED",
        }
    return [], {
        "provider": "bluesky",
        "status": errors[0],
        "public_status": public_status.get("status"),
        "auth_fallback": "FAILED",
        "meaning": "UNKNOWN_NOT_ZERO",
    }
