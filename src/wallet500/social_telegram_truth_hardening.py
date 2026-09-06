from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _official_handle(url: str | None) -> str | None:
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


def attribution_v2(event: dict, identity: dict) -> str:
    text = str(event.get("text") or "")
    mint = str(identity.get("token_address") or "")
    pair = str(identity.get("pair_address") or identity.get("dex_pair_address") or "")
    if mint and mint in text:
        return "EXACT_CONTRACT"
    if pair and pair in text:
        return "EXACT_PAIR"

    source = str(event.get("source") or "").lower()
    author = str(event.get("author") or "").lower().lstrip("@")
    x_handle = _official_handle(identity.get("official_x"))
    if source == "x" and x_handle and author == x_handle:
        return "OFFICIAL_CHANNEL_CONTEXT"

    telegram_handle = _official_handle(identity.get("official_telegram"))
    if source == "telegram" and telegram_handle and author == telegram_handle:
        return "OFFICIAL_CHANNEL_CONTEXT"
    return "NAME_SYMBOL_CONTEXT"


def _clean_message_text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html_lib.unescape(fragment)
    fragment = re.sub(r"[ \t\r\f\v]+", " ", fragment)
    fragment = re.sub(r"\n\s*", "\n", fragment)
    return fragment.strip()


def parse_public_telegram_html(page_html: str, handle: str, limit: int = 15) -> tuple[list[dict], int]:
    # Telegram public web pages expose a stable data-post="channel/message_id" marker
    # and a <time datetime="..."> element inside each message block. We intentionally
    # require that original timestamp; an un-timestamped historical message must never
    # inherit Wallet500's current scan time and look artificially fresh.
    parts = re.split(r'data-post=["\']([^"\']+)["\']', page_html, flags=re.I)
    parsed: list[dict] = []
    dropped_untimestamped = 0
    expected = handle.lower().lstrip("@") + "/"

    for i in range(1, len(parts), 2):
        post_ref = str(parts[i] or "").strip()
        fragment = parts[i + 1] if i + 1 < len(parts) else ""
        if not post_ref.lower().startswith(expected):
            continue
        message_id = post_ref.rsplit("/", 1)[-1]
        text_match = re.search(
            r'<div class=["\'][^"\']*tgme_widget_message_text[^"\']*["\'][^>]*>(.*?)</div>',
            fragment,
            flags=re.S | re.I,
        )
        if not text_match:
            continue
        text = _clean_message_text(text_match.group(1))
        if not text:
            continue
        time_match = re.search(r'<time\b[^>]*\bdatetime=["\']([^"\']+)["\']', fragment, flags=re.I)
        if not time_match:
            dropped_untimestamped += 1
            continue
        published_at = html_lib.unescape(time_match.group(1)).strip()
        if not published_at:
            dropped_untimestamped += 1
            continue
        parsed.append({
            "source": "telegram",
            "author": handle,
            "published_at": published_at,
            "text": text[:1500],
            "id": f"{handle}:{message_id}",
            "url": f"https://t.me/{handle}/{message_id}",
            "direct_provider": True,
            "timestamp_provenance": "TELEGRAM_ORIGINAL_DATETIME",
        })

    return parsed[-max(1, limit):], dropped_untimestamped


def scan_public_telegram(identity: dict) -> tuple[list[dict], dict]:
    url = str(identity.get("official_telegram") or "")
    if not url:
        return [], {"provider": "telegram_official", "status": "NO_OFFICIAL_PUBLIC_CHANNEL"}
    handle = _official_handle(url)
    if not handle:
        return [], {"provider": "telegram_official", "status": "PRIVATE_OR_INVITE_CHANNEL"}

    try:
        req = Request(
            f"https://t.me/s/{handle}",
            headers={"User-Agent": "Wallet500-Social/3.0", "Accept": "text/html,*/*"},
        )
        with urlopen(req, timeout=18) as response:
            page_html = response.read().decode("utf-8", errors="replace")
        rows, dropped = parse_public_telegram_html(page_html, handle, limit=15)
        times = [str(x.get("published_at")) for x in rows if x.get("published_at")]
        return rows, {
            "provider": "telegram_official",
            "status": "OK",
            "count": len(rows),
            "timestamped_count": len(times),
            "dropped_untimestamped": dropped,
            "timestamp_required": True,
            "freshness_source": "TELEGRAM_ORIGINAL_DATETIME",
            "oldest_at": min(times) if times else None,
            "latest_at": max(times) if times else None,
        }
    except Exception as exc:
        code = getattr(exc, "code", None)
        status = f"HTTP_{code}" if code else type(exc).__name__
        return [], {"provider": "telegram_official", "status": status, "meaning": "UNKNOWN_NOT_ZERO"}
