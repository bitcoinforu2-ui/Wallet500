"""Wallet500 Moonshot future-listing intelligence.

Detects exact-contract future-listing announcements published by Moonshot's official
account, keeps them visible as persistent dashboard intelligence, and sends a
special Telegram alert only after the exact same asset is present in Wallet500's
canonical REAL ALERT feed.

This lane never creates a REAL ALERT and never weakens any production gate.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

from . import moonshot_verification_watch as mv

MODE = "MOONSHOT_FUTURE_LISTING_INTELLIGENCE_V1"
NETWORK = "solana"
OFFICIAL_X_HANDLE = "moonshot"
PRIORITY_SCORE = 100
MAX_LEDGER_EVENTS = 2_000
MAX_ACTIVE_FUTURE_DAYS = 14

DATA = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
LEDGER_PATH = DATA / "moonshot-future-listing-ledger.json"
LATEST_PATH = DATA / "moonshot-future-listing-latest.json"
STATE_PATH = DATA / "moonshot-future-listing-state.json"
REAL_ALERTS_PATH = DATA / "real-alerts.json"
VERIFICATION_LEDGER_PATH = DATA / "moonshot-verification-ledger.json"
EXTERNAL_ALPHA_PATH = DATA / "external-alpha-events.json"

UA = {
    "User-Agent": "Wallet500-MoonshotFutureListing/1.0 (+https://github.com/bitcoinforu2-ui/Wallet500)",
    "Accept": "application/json,text/html,*/*",
}

# Explicit future tense + Moonshot context. Current "is now verified" notices do not
# match unless they separately contain future-listing language.
FUTURE_RE = re.compile(
    r"(?:"
    r"\b(?:coming|arriving|launching|listing)\s+(?:very\s+)?soon\s+(?:to|on)\s+moonshot\b|"
    r"\bcoming\s+(?:to|on)\s+moonshot\b|"
    r"\b(?:will|set\s+to|scheduled\s+to)\s+(?:be\s+)?(?:list(?:ed)?|launch(?:ed)?|available|verified)\s+(?:soon\s+)?(?:to|on)\s+moonshot\b|"
    r"\bmoonshot\b.{0,80}\b(?:coming\s+soon|future\s+listing|listing\s+soon|launching\s+soon|will\s+list|will\s+launch)\b|"
    r"\b(?:future\s+listing|listing\s+soon|launching\s+soon|will\s+list|will\s+launch)\b.{0,80}\bmoonshot\b"
    r")",
    re.I | re.S,
)
SYMBOL_RE = re.compile(r"\$([A-Za-z0-9_]{1,20})")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _load(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_error(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code:
        return f"HTTP_{code}"
    return f"{type(exc).__name__}:{str(exc)[:140]}"


def _get(url: str, headers: dict | None = None, timeout: int = 15) -> tuple[str, Any]:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        ctype = str(response.headers.get("content-type") or "").lower()
    if "json" in ctype or raw.lstrip().startswith(("{", "[")):
        return "json", json.loads(raw)
    return "html", raw


def _dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        d = parsedate_to_datetime(text)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_future_listing_text(text: object) -> bool:
    return bool(FUTURE_RE.search(str(text or "")))


def _symbol(text: object) -> str | None:
    match = SYMBOL_RE.search(str(text or ""))
    return match.group(1).upper() if match else None


def _event_key(token: str) -> str:
    return hashlib.sha256(f"moonshot-future-listing|{NETWORK}|{token}".encode()).hexdigest()[:24]


def _observation(
    *,
    token: str,
    text: str,
    post_id: str,
    published_at: datetime,
    surface: str,
    source_url: str,
) -> dict:
    return {
        "event_id": _event_key(token),
        "event_type": "MOONSHOT_FUTURE_LISTING",
        "chain": NETWORK,
        "token": token,
        "symbol": _symbol(text),
        "source_owner": "moonshot",
        "source_kind": "OFFICIAL_MOONSHOT_FUTURE_LISTING",
        "source_category": "launchpad_discovery_platform",
        "surface": surface,
        "post_id": str(post_id),
        "published_at": _iso(published_at),
        "source_url": source_url,
        "text": str(text)[:3000],
        "catalyst_priority_score": PRIORITY_SCORE,
        "strong_catalyst": True,
        "special_alert": True,
        "dashboard_visible": True,
        "automatic_buy": False,
        "production_trade_impact": "NONE",
    }


def collect_official_x_api(reference: datetime | None = None) -> tuple[list[dict], list[dict], dict]:
    """Use the official X API when configured. Exact mint in the same post is mandatory."""
    reference = reference or _now()
    bearer = str(os.getenv("X_BEARER_TOKEN") or "").strip()
    if not bearer:
        return [], [], {"provider": "x_api", "status": "NOT_CONFIGURED", "exact_rows": 0, "unresolved_rows": 0}
    query = (
        f'from:{OFFICIAL_X_HANDLE} '
        '("coming to Moonshot" OR "coming on Moonshot" OR "coming soon" OR '
        '"will be listed" OR "will be available" OR "will be verified" OR "launching soon") -is:retweet'
    )
    params = urllib.parse.urlencode({
        "query": query,
        "max_results": 100,
        "tweet.fields": "created_at,author_id",
        "expansions": "author_id",
        "user.fields": "username,verified",
    })
    try:
        _, payload = _get(
            "https://api.x.com/2/tweets/search/recent?" + params,
            headers={"Authorization": "Bearer " + bearer},
        )
        users = {
            str(u.get("id") or ""): u
            for u in (((payload.get("includes") or {}).get("users")) or [])
            if isinstance(u, dict)
        }
        exact: list[dict] = []
        unresolved: list[dict] = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            user = users.get(str(item.get("author_id") or ""), {})
            if str(user.get("username") or "").lower() != OFFICIAL_X_HANDLE:
                continue
            published = _dt(item.get("created_at"))
            text = str(item.get("text") or "")
            if published is None or published < reference - timedelta(days=MAX_ACTIVE_FUTURE_DAYS):
                continue
            if not is_future_listing_text(text):
                continue
            addresses = mv.extract_solana_addresses(text)
            if not addresses:
                unresolved.append({
                    "surface": "official_x_api",
                    "post_id": str(item.get("id") or ""),
                    "published_at": _iso(published),
                    "symbol": _symbol(text),
                    "text": text[:3000],
                    "source_url": f"https://x.com/{OFFICIAL_X_HANDLE}/status/{item.get('id')}",
                    "reason": "SYMBOL_ONLY_OR_EXACT_MINT_MISSING",
                })
                continue
            for token in addresses:
                exact.append(_observation(
                    token=token,
                    text=text,
                    post_id=str(item.get("id") or ""),
                    published_at=published,
                    surface="official_x_api",
                    source_url=f"https://x.com/{OFFICIAL_X_HANDLE}/status/{item.get('id')}",
                ))
        return exact, unresolved, {
            "provider": "x_api",
            "status": "OK_DIRECT",
            "exact_rows": len(exact),
            "unresolved_rows": len(unresolved),
        }
    except Exception as exc:
        return [], [], {"provider": "x_api", "status": _safe_error(exc), "exact_rows": 0, "unresolved_rows": 0}


def _walk(obj: Any) -> Iterable[dict]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk(value)


def _profile_ids(payload: Any) -> set[str]:
    ids: set[str] = set()
    for obj in _walk(payload):
        handle = str(obj.get("screen_name") or obj.get("username") or "").lower()
        if handle != OFFICIAL_X_HANDLE:
            continue
        for key in ("id_str", "id", "rest_id", "user_id_str"):
            if obj.get(key) is not None:
                ids.add(str(obj.get(key)))
    return ids


def _authored_by_moonshot(obj: dict, profile_ids: set[str]) -> bool:
    for child in _walk(obj):
        if str(child.get("screen_name") or child.get("username") or "").lower() == OFFICIAL_X_HANDLE:
            return True
        for key in ("author_id", "user_id_str", "user_id"):
            if child.get(key) is not None and str(child.get(key)) in profile_ids:
                return True
    return False


def parse_x_syndication(page: str, reference: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Parse X's public profile syndication page as a paid-API fallback.

    This is a redundant transport for the same Moonshot source owner; it never
    counts as an independent confirmation source.
    """
    reference = reference or _now()
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        page or "",
        flags=re.I | re.S,
    )
    if not match:
        return [], []
    try:
        payload = json.loads(html.unescape(match.group(1)))
    except Exception:
        return [], []

    profile_ids = _profile_ids(payload)
    exact: dict[tuple[str, str], dict] = {}
    unresolved: dict[str, dict] = {}
    for obj in _walk(payload):
        text = obj.get("full_text") or obj.get("text")
        post_id = obj.get("id_str") or obj.get("rest_id") or obj.get("id")
        if not isinstance(text, str) or post_id is None:
            continue
        if not is_future_listing_text(text) or not _authored_by_moonshot(obj, profile_ids):
            continue
        published = _dt(obj.get("created_at") or obj.get("createdAt") or obj.get("date"))
        if published is None or published < reference - timedelta(days=MAX_ACTIVE_FUTURE_DAYS):
            continue
        source_url = f"https://x.com/{OFFICIAL_X_HANDLE}/status/{post_id}"
        addresses = mv.extract_solana_addresses(text)
        if not addresses:
            unresolved[str(post_id)] = {
                "surface": "official_x_public_syndication",
                "post_id": str(post_id),
                "published_at": _iso(published),
                "symbol": _symbol(text),
                "text": text[:3000],
                "source_url": source_url,
                "reason": "SYMBOL_ONLY_OR_EXACT_MINT_MISSING",
            }
            continue
        for token in addresses:
            exact[(str(post_id), token)] = _observation(
                token=token,
                text=text,
                post_id=str(post_id),
                published_at=published,
                surface="official_x_public_syndication",
                source_url=source_url,
            )
    return list(exact.values()), list(unresolved.values())


def collect_official_x_syndication(reference: datetime | None = None) -> tuple[list[dict], list[dict], dict]:
    reference = reference or _now()
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{OFFICIAL_X_HANDLE}"
    try:
        _, page = _get(url)
        exact, unresolved = parse_x_syndication(str(page), reference)
        return exact, unresolved, {
            "provider": "x_public_syndication",
            "status": "OK_FALLBACK",
            "exact_rows": len(exact),
            "unresolved_rows": len(unresolved),
        }
    except Exception as exc:
        return [], [], {"provider": "x_public_syndication", "status": _safe_error(exc), "exact_rows": 0, "unresolved_rows": 0}


def collect_official_sources(reference: datetime | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect both transports and dedupe them to one Moonshot source owner."""
    reference = reference or _now()
    api_exact, api_unresolved, api_health = collect_official_x_api(reference)
    fallback_exact, fallback_unresolved, fallback_health = collect_official_x_syndication(reference)
    combined = api_exact + fallback_exact
    dedup: dict[tuple[str, str], dict] = {}
    for row in combined:
        key = (str(row.get("post_id") or ""), str(row.get("token") or ""))
        old = dedup.get(key)
        if old is None or str(row.get("surface")) == "official_x_api":
            dedup[key] = row
    unresolved = {
        str(row.get("post_id") or hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]): row
        for row in api_unresolved + fallback_unresolved
    }
    return list(dedup.values()), list(unresolved.values()), [api_health, fallback_health]


def _canonical_real_alert(token: str) -> tuple[bool, dict | None, dict]:
    """Re-use the canonical producer truth instead of duplicating thresholds here."""
    payload = _load(REAL_ALERTS_PATH, {})
    truth = payload.get("truth_contract") if isinstance(payload, dict) and isinstance(payload.get("truth_contract"), dict) else {}
    rows = payload.get("alerts") if isinstance(payload, dict) and isinstance(payload.get("alerts"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_token = str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()
        chain = str(row.get("chain") or "").strip().lower()
        if row_token != token or chain != NETWORK:
            continue
        ok = bool(
            row.get("status") == "REAL_ALERT"
            and row.get("actionable_research_alert") is True
            and row.get("exact_identity_verified") is True
            and row.get("exact_pair_verified") is True
            and bool(row.get("pair_address"))
            and not list(row.get("blockers") or [])
        )
        return ok, row, truth
    return False, None, truth


def _already_verified(token: str) -> bool:
    payload = _load(VERIFICATION_LEDGER_PATH, {})
    events = payload.get("events") if isinstance(payload, dict) and isinstance(payload.get("events"), dict) else {}
    for event in events.values():
        if not isinstance(event, dict):
            continue
        if str(event.get("event_type") or "") != "MOONSHOT_VERIFIED":
            continue
        if str(event.get("token") or "") == token and str(event.get("source_owner") or "") == "moonshot":
            return True
    return False


def _market(token: str) -> tuple[dict, str]:
    market, status = mv._market(token)
    return market or {}, status


def _telegram_send(text: str) -> tuple[bool, str]:
    bot = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = str(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not bot or not chat:
        return False, "TELEGRAM_SECRETS_MISSING"
    try:
        body = urllib.parse.urlencode({
            "chat_id": chat,
            "text": text,
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA["User-Agent"]},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw.strip() else {"ok": int(getattr(response, "status", 200)) < 300}
        return bool(payload.get("ok")), "SENT" if payload.get("ok") else "API_OK_FALSE"
    except Exception as exc:
        return False, _safe_error(exc)


def _message(event: dict) -> str:
    market = event.get("market") if isinstance(event.get("market"), dict) else {}
    gate = event.get("wallet500_gate") if isinstance(event.get("wallet500_gate"), dict) else {}
    canonical = gate.get("canonical_alert") if isinstance(gate.get("canonical_alert"), dict) else {}
    liq = market.get("liquidity_usd")
    price = market.get("price_usd")
    lines = [
        "🚀🔥 MOONSHOT FUTURE LISTING · WALLET500 PASS",
        f"{event.get('symbol') or market.get('symbol') or '?'} | SOLANA | catalyst {PRIORITY_SCORE}/100",
        "✅ Official Moonshot future-listing announcement",
        "✅ Canonical Wallet500 REAL ALERT: PASS",
        f"CA: {event.get('token')}",
        f"Pair: {market.get('pair_address') or canonical.get('pair_address') or 'unknown'}",
        f"Liquidity: ${float(liq):,.0f}" if liq is not None else "Liquidity: unknown",
        f"Price: ${float(price):.12g}" if price is not None else "Price: unknown",
        f"Wallet500 score: {canonical.get('score') if canonical.get('score') is not None else 'n/a'}",
        "⚠️ MANUAL DECISION ONLY — NO AUTOMATIC TRADE",
    ]
    if event.get("source_url"):
        lines.append(f"🔗 Moonshot source: {event.get('source_url')}")
    if market.get("dex_url") or canonical.get("dex_url"):
        lines.append(f"🔗 DEX: {market.get('dex_url') or canonical.get('dex_url')}")
    return "\n".join(lines)


def _merge_external_alpha(events: list[dict]) -> int:
    payload = _load(EXTERNAL_ALPHA_PATH, {"version": 1, "events": []})
    if isinstance(payload, list):
        payload = {"version": 1, "events": payload}
    if not isinstance(payload, dict):
        payload = {"version": 1, "events": []}
    existing = payload.get("events") if isinstance(payload.get("events"), list) else []
    kept = [
        row for row in existing
        if not (isinstance(row, dict) and str(row.get("event_type") or "") == "MOONSHOT_FUTURE_LISTING")
    ]
    rows = []
    for event in events:
        if not event.get("token"):
            continue
        market = event.get("market") if isinstance(event.get("market"), dict) else {}
        rows.append({
            "event_id": event.get("event_id"),
            "event_type": "MOONSHOT_FUTURE_LISTING",
            "source_owner": "moonshot",
            "source_kind": "OFFICIAL_MOONSHOT_FUTURE_LISTING",
            "source_url": event.get("source_url"),
            "chain": NETWORK,
            "token": event.get("token"),
            "symbol": event.get("symbol") or market.get("symbol"),
            "observed_at": event.get("first_seen_at") or event.get("published_at"),
            "last_seen_at": event.get("last_seen_at"),
            "catalyst_priority_score": PRIORITY_SCORE,
            "moonshot_future_listing": True,
            "phase": event.get("phase"),
            "pair_address": market.get("pair_address"),
            "liquidity_usd": market.get("liquidity_usd"),
            "wallet500_real_alert_pass": bool((event.get("wallet500_gate") or {}).get("pass")),
            "research_only_until_wallet500_gates_pass": True,
            "automatic_buy": False,
        })
    payload.update({
        "version": max(1, int(payload.get("version") or 1)),
        "updated_at": _iso(_now()),
        "events": (kept + rows)[-10_000:],
    })
    _write(EXTERNAL_ALPHA_PATH, payload)
    return len(rows)


def run(reference: datetime | None = None) -> dict:
    reference = reference or _now()
    DATA.mkdir(parents=True, exist_ok=True)
    previous = _load(LEDGER_PATH, {"version": 1, "events": {}})
    previous_events = previous.get("events") if isinstance(previous, dict) and isinstance(previous.get("events"), dict) else {}
    state = _load(STATE_PATH, {"version": 1, "alerted": {}})
    if not isinstance(state, dict):
        state = {"version": 1, "alerted": {}}
    alerted = state.get("alerted") if isinstance(state.get("alerted"), dict) else {}

    observations, unresolved, source_health = collect_official_sources(reference)
    now = _iso(reference)

    # Refresh or add official evidence. A token remains in the persistent ledger
    # even if the original social post later falls out of the recent timeline.
    for obs in observations:
        key = str(obs.get("event_id") or "")
        if not key:
            continue
        rec = previous_events.get(key) if isinstance(previous_events.get(key), dict) else {}
        evidence = rec.get("evidence") if isinstance(rec.get("evidence"), list) else []
        identity = (str(obs.get("post_id") or ""), str(obs.get("surface") or ""))
        known = {(str(x.get("post_id") or ""), str(x.get("surface") or "")) for x in evidence if isinstance(x, dict)}
        if identity not in known:
            evidence.append({
                "post_id": obs.get("post_id"),
                "surface": obs.get("surface"),
                "published_at": obs.get("published_at"),
                "source_url": obs.get("source_url"),
                "text": obs.get("text"),
            })
        rec.update(obs)
        rec["first_seen_at"] = rec.get("first_seen_at") or obs.get("published_at") or now
        rec["last_seen_at"] = now
        rec["evidence"] = evidence[-30:]
        previous_events[key] = rec

    decorated: list[dict] = []
    telegram: list[dict] = []
    for key, raw in list(previous_events.items()):
        if not isinstance(raw, dict) or str(raw.get("token") or "") == "":
            continue
        event = dict(raw)
        token = str(event.get("token"))
        verified = _already_verified(token)
        market, market_status = _market(token)
        passed, canonical, truth = _canonical_real_alert(token)
        published = _dt(event.get("published_at") or event.get("first_seen_at"))
        age = (reference - published) if published else timedelta.max
        active_window = age <= timedelta(days=MAX_ACTIVE_FUTURE_DAYS)

        event["phase"] = "LISTED_OR_VERIFIED_ON_MOONSHOT" if verified else "FUTURE_LISTING_PENDING"
        event["market"] = market
        event["market_status"] = market_status
        event["wallet500_gate"] = {
            "pass": passed,
            "source": "data/real-alerts.json",
            "canonical_alert": canonical,
            "truth_contract": truth,
            "rule": "exact same Solana mint must be a current canonical actionable REAL_ALERT; this lane duplicates no thresholds",
        }
        event["telegram_eligible"] = bool(
            event["phase"] == "FUTURE_LISTING_PENDING"
            and active_window
            and passed
            and event.get("source_owner") == "moonshot"
            and event.get("token")
            and event.get("source_url")
        )
        event["dashboard_visible"] = True
        event["special_alert"] = True
        event["automatic_buy"] = False
        event["production_trade_impact"] = "NONE"

        if event["telegram_eligible"] and key not in alerted:
            ok, status = _telegram_send(_message(event))
            telegram.append({"event_id": key, "ok": ok, "status": status})
            if ok:
                alerted[key] = {
                    "sent_at": now,
                    "token": token,
                    "symbol": event.get("symbol") or market.get("symbol"),
                    "source_url": event.get("source_url"),
                    "canonical_real_alert_first_alert_at": (canonical or {}).get("first_alert_at"),
                }

        previous_events[key] = event
        decorated.append(event)

    decorated.sort(
        key=lambda e: (
            e.get("phase") == "FUTURE_LISTING_PENDING",
            bool((e.get("wallet500_gate") or {}).get("pass")),
            str(e.get("published_at") or e.get("first_seen_at") or ""),
        ),
        reverse=True,
    )
    if len(decorated) > MAX_LEDGER_EVENTS:
        decorated = decorated[:MAX_LEDGER_EVENTS]
    event_map = {str(e.get("event_id")): e for e in decorated if e.get("event_id")}

    ledger = {
        "version": 1,
        "mode": MODE,
        "updated_at": now,
        "network": NETWORK,
        "policy": {
            "source_owner": "moonshot",
            "future_listing_priority": PRIORITY_SCORE,
            "exact_contract_in_same_official_announcement_required": True,
            "symbol_only_never_coin_level_actionable": True,
            "dashboard_persistence": "ledger retained; pending events are re-evaluated every scan",
            "telegram_gate": "current canonical REAL_ALERT for exact same Solana mint",
            "telegram_does_not_duplicate_thresholds": True,
            "automatic_buy": False,
            "moonshot_future_listing_never_bypasses_wallet500_gates": True,
        },
        "source_health": source_health,
        "unresolved_symbol_only": unresolved[-200:],
        "events": event_map,
        "alerted": alerted,
    }
    _write(LEDGER_PATH, ledger)
    _write(STATE_PATH, {"version": 1, "updated_at": now, "alerted": alerted})
    alpha_count = _merge_external_alpha(decorated)

    latest = {
        "version": 1,
        "mode": MODE,
        "updated_at": now,
        "status": "OK" if any(str(h.get("status") or "").startswith("OK") for h in source_health) else "DEGRADED",
        "counts": {
            "official_exact_future_observations": len(observations),
            "unresolved_symbol_only": len(unresolved),
            "persistent_events": len(decorated),
            "pending_future_listings": sum(1 for e in decorated if e.get("phase") == "FUTURE_LISTING_PENDING"),
            "wallet500_pass": sum(1 for e in decorated if (e.get("wallet500_gate") or {}).get("pass")),
            "telegram_eligible": sum(1 for e in decorated if e.get("telegram_eligible")),
            "telegram_attempts": len(telegram),
            "telegram_delivered": sum(1 for x in telegram if x.get("ok")),
            "external_alpha_events": alpha_count,
        },
        "events": decorated[:100],
        "unresolved_symbol_only": unresolved[-50:],
        "source_health": source_health,
        "telegram": telegram,
        "automatic_buy": False,
        "production_trade_impact": "NONE",
    }
    _write(LATEST_PATH, latest)
    print("MOONSHOT FUTURE LISTING", json.dumps(latest["counts"], separators=(",", ":")))
    return latest


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
