from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "Wallet500-SocialDirect/3.1"


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return "NETWORK_UNAVAILABLE"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _get_json(url: str, headers: dict | None = None, timeout: int = 18):
    req = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT, **(headers or {})},
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_form_json(url: str, data: dict, headers: dict | None = None, timeout: int = 18):
    body = urlencode(data).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
            **(headers or {}),
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _x_handle(url: str | None) -> str | None:
    if not url:
        return None
    try:
        path = urlparse(str(url)).path.strip("/")
        return path.split("/")[0] if path else None
    except Exception:
        return None


def _identity_terms(identity: dict) -> dict:
    mint = str(identity.get("token_address") or "").strip()
    pair = str(identity.get("pair_address") or identity.get("dex_pair_address") or "").strip()
    name = str(identity.get("name") or "").strip()
    symbol = str(identity.get("symbol") or "").strip().lstrip("$")
    handle = _x_handle(identity.get("official_x"))
    return {"mint": mint, "pair": pair, "name": name, "symbol": symbol, "handle": handle}


def direct_query(identity: dict, provider: str = "generic") -> str:
    t = _identity_terms(identity)
    exact = [x for x in (t["mint"], t["pair"]) if x]
    broad = []
    if t["name"]:
        broad.append(f'"{t["name"]}"')
    if t["symbol"] and len(t["symbol"]) >= 3:
        broad.append(f'"${t["symbol"]}"')

    if provider == "youtube":
        return " | ".join(exact + broad[:2])
    if provider == "x":
        parts = exact + broad[:2]
        if t["handle"]:
            parts.append(f"from:{t['handle']}")
        return "(" + " OR ".join(parts) + ") -is:retweet"
    return " OR ".join(exact + broad[:2])


def provider_config() -> dict:
    return {
        "x": bool((os.getenv("X_BEARER_TOKEN") or "").strip()),
        "youtube": bool((os.getenv("YOUTUBE_API_KEY") or "").strip()),
        "reddit_oauth": bool(
            (os.getenv("REDDIT_CLIENT_ID") or "").strip()
            and (os.getenv("REDDIT_CLIENT_SECRET") or "").strip()
        ),
        "reddit_public": True,
        "telegram_public_direct": True,
    }


def _iso_from_epoch(value):
    try:
        if value in (None, ""):
            return None
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return value


def scan_x(identity: dict):
    token = (os.getenv("X_BEARER_TOKEN") or "").strip()
    if not token:
        return [], {"provider": "x", "status": "NOT_CONFIGURED"}
    query = direct_query(identity, "x")
    if not query or query == "() -is:retweet":
        return [], {"provider": "x", "status": "NO_QUERY_IDENTITY"}
    params = urlencode({
        "query": query,
        "max_results": 10,
        "tweet.fields": "created_at,public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "username,name,verified",
    })
    try:
        payload = _get_json(
            "https://api.x.com/2/tweets/search/recent?" + params,
            headers={"Authorization": "Bearer " + token},
        )
        users = {
            str(x.get("id") or ""): x
            for x in (((payload.get("includes") or {}).get("users")) or [])
            if isinstance(x, dict)
        }
        rows = []
        for item in payload.get("data") or []:
            pm = item.get("public_metrics") or {}
            user = users.get(str(item.get("author_id") or ""), {})
            username = str(user.get("username") or item.get("author_id") or "")
            tid = item.get("id")
            rows.append({
                "source": "x",
                "id": tid,
                "author": username,
                "author_id": item.get("author_id"),
                "author_verified": user.get("verified"),
                "published_at": item.get("created_at"),
                "text": str(item.get("text") or "")[:1500],
                "engagement": sum(float(pm.get(k) or 0) for k in ("like_count", "retweet_count", "reply_count", "quote_count")),
                "url": f"https://x.com/{username}/status/{tid}" if username and tid else None,
                "direct_provider": True,
            })
        return rows, {"provider": "x", "status": "OK_DIRECT", "count": len(rows), "query_identity": "MINT_PAIR_OFFICIAL_BROAD"}
    except Exception as exc:
        return [], {"provider": "x", "status": _safe_error(exc), "direct": True}


def scan_youtube(identity: dict):
    key = (os.getenv("YOUTUBE_API_KEY") or "").strip()
    if not key:
        return [], {"provider": "youtube", "status": "NOT_CONFIGURED"}
    query = direct_query(identity, "youtube")
    if not query:
        return [], {"provider": "youtube", "status": "NO_QUERY_IDENTITY"}
    published_after = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    params = urlencode({
        "part": "snippet",
        "type": "video",
        "order": "date",
        "maxResults": 10,
        "publishedAfter": published_after,
        "q": query,
        "key": key,
    })
    try:
        payload = _get_json("https://www.googleapis.com/youtube/v3/search?" + params)
        rows = []
        for item in payload.get("items") or []:
            snippet = item.get("snippet") or {}
            vid = (item.get("id") or {}).get("videoId")
            rows.append({
                "source": "youtube",
                "id": vid,
                "author": snippet.get("channelTitle"),
                "channel_id": snippet.get("channelId"),
                "published_at": snippet.get("publishedAt"),
                "text": f"{snippet.get('title') or ''} {snippet.get('description') or ''}"[:1500],
                "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
                "direct_provider": True,
            })
        return rows, {"provider": "youtube", "status": "OK_DIRECT", "count": len(rows), "query_identity": "MINT_PAIR_BROAD"}
    except Exception as exc:
        return [], {"provider": "youtube", "status": _safe_error(exc), "direct": True}


def _reddit_access_token() -> tuple[str | None, str | None]:
    client_id = (os.getenv("REDDIT_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("REDDIT_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return None, "NOT_CONFIGURED"
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    try:
        payload = _post_form_json(
            "https://www.reddit.com/api/v1/access_token",
            {"grant_type": "client_credentials"},
            headers={
                "Authorization": "Basic " + basic,
                "User-Agent": (os.getenv("REDDIT_USER_AGENT") or "Wallet500/3.1 by bitcoinforu2-ui").strip(),
            },
        )
        token = str(payload.get("access_token") or "").strip()
        return (token, None) if token else (None, "OAUTH_NO_TOKEN")
    except Exception as exc:
        return None, _safe_error(exc)


def _reddit_rows(payload: dict) -> list[dict]:
    rows = []
    for child in (((payload.get("data") or {}).get("children")) or []):
        data = (child or {}).get("data") or {}
        permalink = str(data.get("permalink") or "")
        rows.append({
            "source": "reddit",
            "id": data.get("id"),
            "author": data.get("author"),
            "subreddit": data.get("subreddit"),
            "published_at": _iso_from_epoch(data.get("created_utc")),
            "text": f"{data.get('title') or ''} {data.get('selftext') or ''}"[:1500],
            "engagement": float(data.get("score") or 0) + float(data.get("num_comments") or 0),
            "url": "https://www.reddit.com" + permalink if permalink else None,
            "direct_provider": True,
        })
    return rows


def scan_reddit(identity: dict):
    query = direct_query(identity, "reddit")
    if not query:
        return [], {"provider": "reddit", "status": "NO_QUERY_IDENTITY", "direct": True}

    user_agent = (os.getenv("REDDIT_USER_AGENT") or "Wallet500/3.1 by bitcoinforu2-ui").strip()
    token, token_error = _reddit_access_token()
    oauth_error = token_error
    if token:
        params = urlencode({"q": query, "sort": "new", "t": "day", "limit": 25, "raw_json": 1})
        try:
            payload = _get_json(
                "https://oauth.reddit.com/search?" + params,
                headers={"Authorization": "Bearer " + token, "User-Agent": user_agent},
            )
            rows = _reddit_rows(payload)
            return rows, {
                "provider": "reddit",
                "status": "OK_DIRECT_OAUTH",
                "count": len(rows),
                "query_identity": "MINT_PAIR_BROAD",
            }
        except Exception as exc:
            oauth_error = _safe_error(exc)

    # Reddit's public JSON search is a useful no-secret fallback. It remains a direct
    # source because the post payload comes from reddit.com itself, not a search index.
    params = urlencode({"q": query, "sort": "new", "t": "day", "limit": 25, "raw_json": 1})
    try:
        payload = _get_json(
            "https://www.reddit.com/search.json?" + params,
            headers={"User-Agent": user_agent},
        )
        rows = _reddit_rows(payload)
        return rows, {
            "provider": "reddit",
            "status": "OK_DIRECT_PUBLIC",
            "count": len(rows),
            "query_identity": "MINT_PAIR_BROAD",
            "oauth_status": oauth_error,
        }
    except Exception as exc:
        return [], {
            "provider": "reddit",
            "status": _safe_error(exc),
            "direct": True,
            "oauth_status": oauth_error,
        }
