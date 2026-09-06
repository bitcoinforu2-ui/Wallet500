from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "Wallet500-SocialMeshIndex/1.0"

SITE_QUERY = (
    "site:t.me OR site:farcaster.xyz OR site:warpcast.com OR "
    "site:threads.net OR site:bsky.app OR site:discord.com"
)

SOURCE_HINTS = (
    (("t.me", "telegram"), "telegram_index"),
    (("farcaster.xyz", "warpcast.com", "farcaster"), "farcaster_index"),
    (("threads.net", "threads"), "threads_index"),
    (("bsky.app", "bluesky"), "bluesky_index"),
    (("discord.com", "discord.gg", "discord"), "discord_index"),
)


def _identity_terms(identity: dict) -> tuple[str, str]:
    mint = str(identity.get("token_address") or "").strip()
    pair = str(identity.get("pair_address") or identity.get("dex_pair_address") or "").strip()
    return mint, pair


def build_query(identity: dict) -> str | None:
    mint, pair = _identity_terms(identity)
    exact = [f'"{x}"' for x in (mint, pair) if x]
    if not exact:
        return None
    return f"({' OR '.join(exact)}) ({SITE_QUERY}) when:7d"


def _source(title: str, publisher: str) -> str:
    hay = f"{title} {publisher}".lower()
    for hints, source in SOURCE_HINTS:
        if any(h in hay for h in hints):
            return source
    return "mesh_index"


def _attribution(text: str, identity: dict) -> str | None:
    mint, pair = _identity_terms(identity)
    if mint and mint in text:
        return "EXACT_CONTRACT"
    if pair and pair in text:
        return "EXACT_PAIR"
    return None


def scan_mesh_public_index(identity: dict) -> tuple[list[dict], dict]:
    query = build_query(identity)
    if not query:
        return [], {"provider": "social_mesh_public_index", "status": "NO_QUERY_IDENTITY"}

    url = "https://news.google.com/rss/search?" + urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    try:
        req = Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml,text/xml,*/*",
        })
        with urlopen(req, timeout=18) as response:
            raw = response.read()
        root = ET.fromstring(raw)
    except Exception as exc:
        code = getattr(exc, "code", None)
        status = f"HTTP_{code}" if code else type(exc).__name__
        return [], {
            "provider": "social_mesh_public_index",
            "status": f"INDEX_{status}",
            "meaning": "UNKNOWN_NOT_ZERO",
        }

    rows: list[dict] = []
    seen = set()
    for i, item in enumerate(root.findall(".//item")[:30]):
        title = html.unescape(str(item.findtext("title") or "")).strip()
        link = str(item.findtext("link") or "").strip()
        published = str(item.findtext("pubDate") or "").strip() or None
        publisher = str(item.findtext("source") or "").strip()
        attr = _attribution(title, identity)
        if not title or attr is None:
            continue
        key = (title, link)
        if key in seen:
            continue
        seen.add(key)
        source = _source(title, publisher)
        rows.append({
            "source": source,
            "author": publisher or source,
            "published_at": published,
            "text": title[:1200],
            "url": link,
            "id": f"mesh-index:{i}:{title[:80]}",
            "context_only": True,
            "organic_eligible": False,
            "indexed_identity_evidence": True,
            "attribution": attr,
        })

    return rows, {
        "provider": "social_mesh_public_index",
        "status": "INDEX_OK_CONTEXT_ONLY",
        "count": len(rows),
        "organic_eligible": False,
        "query_identity": "EXACT_MINT_OR_PAIR_ONLY",
        "meaning": "PUBLIC_INDEX_CONTEXT_ONLY_NEVER_ORGANIC_PROOF",
    }
