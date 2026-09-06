from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "Wallet500-SocialMesh/1.0"


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


def _csv_env(name: str, limit: int = 50) -> list[str]:
    seen = set()
    out = []
    for raw in (os.getenv(name) or "").replace("\n", ",").split(","):
        item = raw.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _identity_terms(identity: dict) -> dict:
    mint = str(identity.get("token_address") or "").strip()
    pair = str(identity.get("pair_address") or identity.get("dex_pair_address") or "").strip()
    name = str(identity.get("name") or "").strip()
    symbol = str(identity.get("symbol") or "").strip().lstrip("$")
    return {"mint": mint, "pair": pair, "name": name, "symbol": symbol}


def exact_queries(identity: dict) -> list[str]:
    t = _identity_terms(identity)
    return [x for x in (t["mint"], t["pair"]) if x]


def broad_query(identity: dict) -> str:
    t = _identity_terms(identity)
    parts = exact_queries(identity)
    if t["name"]:
        parts.append(f'"{t["name"]}"')
    if t["symbol"] and len(t["symbol"]) >= 3:
        parts.append(f'${t["symbol"]}')
    return " OR ".join(parts)


def provider_config() -> dict:
    return {
        "telegram_mtproto": bool(
            (os.getenv("TELEGRAM_API_ID") or "").strip()
            and (os.getenv("TELEGRAM_API_HASH") or "").strip()
            and (os.getenv("TELEGRAM_SESSION") or "").strip()
        ),
        "farcaster_neynar": bool((os.getenv("NEYNAR_API_KEY") or "").strip()),
        "discord_watch": bool(
            (os.getenv("DISCORD_BOT_TOKEN") or "").strip()
            and (_csv_env("DISCORD_GUILD_IDS") or _csv_env("DISCORD_CHANNEL_IDS"))
        ),
        "threads_keyword": bool((os.getenv("THREADS_ACCESS_TOKEN") or "").strip()),
        "bluesky_public": True,
    }


def _telegram_handle(url: str | None) -> str | None:
    if not url:
        return None
    try:
        path = urlparse(str(url)).path.strip("/")
        handle = path.split("/")[0] if path else ""
        if not handle or handle.startswith("+"):
            return None
        return handle
    except Exception:
        return None


async def _scan_telegram_async(identity: dict, limit_per_query: int) -> tuple[list[dict], dict]:
    api_id = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    session = (os.getenv("TELEGRAM_SESSION") or "").strip()
    if not api_id or not api_hash or not session:
        return [], {"provider": "telegram_mtproto", "status": "NOT_CONFIGURED"}
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except Exception:
        return [], {"provider": "telegram_mtproto", "status": "DEPENDENCY_MISSING_TELETHON"}

    try:
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
    except Exception as exc:
        return [], {"provider": "telegram_mtproto", "status": _safe_error(exc)}

    rows: list[dict] = []
    seen: set[tuple[str, int]] = set()
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return [], {"provider": "telegram_mtproto", "status": "SESSION_NOT_AUTHORIZED"}

        queries = exact_queries(identity)[:2]
        if not queries:
            t = _identity_terms(identity)
            queries = [x for x in (t["name"], t["symbol"]) if x][:1]

        async def add_message(message, query_kind: str):
            if not getattr(message, "message", None):
                return
            chat = await message.get_chat()
            sender = await message.get_sender()
            chat_username = str(getattr(chat, "username", "") or "")
            chat_title = str(getattr(chat, "title", "") or getattr(chat, "first_name", "") or "")
            sender_username = str(getattr(sender, "username", "") or "")
            sender_name = str(
                getattr(sender, "title", "")
                or getattr(sender, "first_name", "")
                or getattr(sender, "last_name", "")
                or sender_username
                or chat_username
                or chat_title
                or "telegram"
            )
            chat_id = str(getattr(message, "chat_id", "") or getattr(chat, "id", "") or "")
            msg_id = int(getattr(message, "id", 0) or 0)
            key = (chat_id, msg_id)
            if msg_id <= 0 or key in seen:
                return
            seen.add(key)
            published = getattr(message, "date", None)
            url = f"https://t.me/{chat_username}/{msg_id}" if chat_username else None
            replies = getattr(getattr(message, "replies", None), "replies", 0) or 0
            rows.append({
                "source": "telegram",
                "id": f"{chat_id}:{msg_id}",
                "author": chat_username or sender_username or sender_name,
                "author_id": str(getattr(sender, "id", "") or ""),
                "channel": chat_title or chat_username or chat_id,
                "channel_id": chat_id,
                "published_at": published.astimezone(timezone.utc).isoformat() if published else None,
                "text": str(getattr(message, "message", "") or "")[:1500],
                "engagement": float(getattr(message, "views", 0) or 0)
                + float(getattr(message, "forwards", 0) or 0)
                + float(replies),
                "url": url,
                "query_kind": query_kind,
                "direct_provider": True,
            })

        for q in queries:
            async for message in client.iter_messages(None, search=q, limit=limit_per_query):
                await add_message(message, "GLOBAL_SEARCH")

        official = _telegram_handle(identity.get("official_telegram"))
        if official:
            async for message in client.iter_messages(official, limit=min(15, limit_per_query)):
                await add_message(message, "OFFICIAL_CHANNEL_HISTORY")
    except Exception as exc:
        return rows, {
            "provider": "telegram_mtproto",
            "status": _safe_error(exc),
            "count": len(rows),
            "meaning": "UNKNOWN_NOT_ZERO",
        }
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    return rows[: max(10, limit_per_query * 3)], {
        "provider": "telegram_mtproto",
        "status": "OK_DIRECT",
        "count": len(rows),
        "query_identity": "GLOBAL_EXACT_MINT_PAIR_PLUS_OFFICIAL_CHANNEL",
    }


def scan_telegram_mtproto(identity: dict):
    limit = max(3, min(25, int(os.getenv("TELEGRAM_RESULTS_PER_QUERY", "8"))))
    try:
        return asyncio.run(_scan_telegram_async(identity, limit))
    except RuntimeError:
        return [], {
            "provider": "telegram_mtproto",
            "status": "EVENT_LOOP_ACTIVE",
            "meaning": "UNKNOWN_NOT_ZERO",
        }


def scan_farcaster(identity: dict):
    key = (os.getenv("NEYNAR_API_KEY") or "").strip()
    if not key:
        return [], {"provider": "farcaster", "status": "NOT_CONFIGURED"}
    query = broad_query(identity).replace(" OR ", " | ")
    if not query:
        return [], {"provider": "farcaster", "status": "NO_QUERY_IDENTITY"}
    params = urlencode({"q": query})
    try:
        payload = _get_json(
            "https://api.neynar.com/v2/farcaster/cast/search/?" + params,
            headers={"x-api-key": key},
        )
        casts = ((payload.get("result") or {}).get("casts")) or []
        rows = []
        for item in casts[:25]:
            if not isinstance(item, dict):
                continue
            author = item.get("author") or {}
            username = str(author.get("username") or author.get("fid") or "")
            h = item.get("hash") or item.get("thread_hash")
            rows.append({
                "source": "farcaster",
                "id": h,
                "author": username,
                "author_id": author.get("fid"),
                "followers": author.get("follower_count"),
                "published_at": item.get("timestamp"),
                "text": str(item.get("text") or "")[:1500],
                "engagement": float(((item.get("replies") or {}).get("count")) or 0)
                + float(((item.get("reactions") or {}).get("recasts_count")) or item.get("recasts_count") or 0)
                + float(((item.get("reactions") or {}).get("likes_count")) or item.get("likes_count") or 0),
                "url": f"https://warpcast.com/{username}/{str(h)[:12]}" if username and h else None,
                "direct_provider": True,
            })
        return rows, {
            "provider": "farcaster",
            "status": "OK_DIRECT",
            "count": len(rows),
            "query_identity": "MINT_PAIR_BROAD",
        }
    except Exception as exc:
        return [], {"provider": "farcaster", "status": _safe_error(exc), "meaning": "UNKNOWN_NOT_ZERO"}


def _discord_message_row(message: dict, guild_id: str | None = None) -> dict:
    author = message.get("author") or {}
    channel_id = str(message.get("channel_id") or "")
    message_id = str(message.get("id") or "")
    return {
        "source": "discord",
        "id": message_id,
        "author": author.get("username") or author.get("global_name") or author.get("id"),
        "author_id": author.get("id"),
        "channel_id": channel_id,
        "guild_id": guild_id,
        "published_at": message.get("timestamp"),
        "text": str(message.get("content") or "")[:1500],
        "engagement": float(len(message.get("reactions") or [])),
        "url": f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        if guild_id and channel_id and message_id else None,
        "direct_provider": True,
    }


def scan_discord(identity: dict):
    token = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()
    guild_ids = _csv_env("DISCORD_GUILD_IDS", limit=12)
    channel_ids = _csv_env("DISCORD_CHANNEL_IDS", limit=20)
    if not token or not (guild_ids or channel_ids):
        return [], {"provider": "discord", "status": "NOT_CONFIGURED"}
    headers = {"Authorization": "Bot " + token}
    queries = exact_queries(identity)
    if not queries:
        t = _identity_terms(identity)
        queries = [x for x in (t["name"], t["symbol"]) if x][:1]
    rows: list[dict] = []
    errors: list[str] = []
    seen = set()
    raw_message_count = 0
    content_message_count = 0

    for guild_id in guild_ids:
        for q in queries[:2]:
            params = urlencode({"content": q, "limit": 25, "sort_by": "timestamp", "sort_order": "desc"})
            try:
                payload = _get_json(
                    f"https://discord.com/api/v10/guilds/{quote(guild_id)}/messages/search?" + params,
                    headers=headers,
                )
                for group in payload.get("messages") or []:
                    candidates = group if isinstance(group, list) else [group]
                    for message in candidates:
                        if not isinstance(message, dict):
                            continue
                        raw_message_count += 1
                        if str(message.get("content") or ""):
                            content_message_count += 1
                        mid = str(message.get("id") or "")
                        if not mid or mid in seen:
                            continue
                        seen.add(mid)
                        rows.append(_discord_message_row(message, guild_id))
            except Exception as exc:
                errors.append(_safe_error(exc))

    exact_terms = [q.lower() for q in queries if q]
    for channel_id in channel_ids:
        try:
            payload = _get_json(
                f"https://discord.com/api/v10/channels/{quote(channel_id)}/messages?limit=50",
                headers=headers,
            )
            if not isinstance(payload, list):
                continue
            for message in payload:
                if not isinstance(message, dict):
                    continue
                raw_message_count += 1
                text = str(message.get("content") or "")
                if text:
                    content_message_count += 1
                if exact_terms and not any(term in text.lower() for term in exact_terms):
                    continue
                mid = str(message.get("id") or "")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                rows.append(_discord_message_row(message))
        except Exception as exc:
            errors.append(_safe_error(exc))

    if raw_message_count > 0 and content_message_count == 0:
        status = "MESSAGE_CONTENT_UNAVAILABLE"
    elif rows or not errors:
        status = "OK_DIRECT"
    else:
        status = errors[0]
    return rows[:60], {
        "provider": "discord",
        "status": status,
        "count": len(rows),
        "errors": sorted(set(errors))[:4],
        "query_identity": "WATCHED_GUILD_SEARCH_AND_CHANNEL_HISTORY",
        "message_content_visible": content_message_count > 0 if raw_message_count else None,
        "meaning": None if status == "OK_DIRECT" else "UNKNOWN_NOT_ZERO",
    }


def scan_threads(identity: dict):
    token = (os.getenv("THREADS_ACCESS_TOKEN") or "").strip()
    if not token:
        return [], {"provider": "threads", "status": "NOT_CONFIGURED"}
    exact = exact_queries(identity)
    query = exact[0] if exact else broad_query(identity)
    if not query:
        return [], {"provider": "threads", "status": "NO_QUERY_IDENTITY"}
    fields = "id,username,text,timestamp,permalink"
    params = urlencode({
        "q": query,
        "search_type": "RECENT",
        "search_mode": "KEYWORD",
        "limit": 25,
        "fields": fields,
        "access_token": token,
    })
    try:
        payload = _get_json("https://graph.threads.net/keyword_search?" + params)
        rows = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            rows.append({
                "source": "threads",
                "id": item.get("id"),
                "author": item.get("username"),
                "published_at": item.get("timestamp"),
                "text": str(item.get("text") or "")[:1500],
                "url": item.get("permalink"),
                "direct_provider": True,
            })
        return rows, {
            "provider": "threads",
            "status": "OK_DIRECT",
            "count": len(rows),
            "query_identity": "MINT_PAIR_BROAD_RECENT",
        }
    except Exception as exc:
        return [], {"provider": "threads", "status": _safe_error(exc), "meaning": "UNKNOWN_NOT_ZERO"}


def scan_bluesky(identity: dict):
    t = _identity_terms(identity)
    queries = exact_queries(identity)[:1]
    if t["symbol"] and len(t["symbol"]) >= 3:
        queries.append(f"${t['symbol']}")
    elif t["name"]:
        queries.append(t["name"])
    queries = list(dict.fromkeys(q for q in queries if q))[:2]
    if not queries:
        return [], {"provider": "bluesky", "status": "NO_QUERY_IDENTITY"}

    rows = []
    seen = set()
    errors = []
    for query in queries:
        params = urlencode({"q": query, "limit": 15, "sort": "latest"})
        try:
            payload = _get_json("https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?" + params)
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
        except Exception as exc:
            errors.append(_safe_error(exc))

    status = "OK_DIRECT_PUBLIC" if rows or not errors else errors[0]
    return rows[:30], {
        "provider": "bluesky",
        "status": status,
        "count": len(rows),
        "queries": len(queries),
        "query_identity": "EXACT_MINT_PLUS_SYMBOL_OR_NAME_LATEST",
        "meaning": None if status.startswith("OK") else "UNKNOWN_NOT_ZERO",
    }


MESH_SCANNERS = {
    "telegram_mtproto": scan_telegram_mtproto,
    "farcaster": scan_farcaster,
    "discord": scan_discord,
    "threads": scan_threads,
    "bluesky": scan_bluesky,
}
