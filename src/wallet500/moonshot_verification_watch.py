"""Moonshot verification intelligence lane.

Purpose
-------
Detect the *current* Moonshot app verification event (not the legacy Moonshot
launchpad new/rising/finalized feed), attach exact Solana identity and market
context, and promote it as a high-priority catalyst for Wallet500 research.

Truth/safety contract
---------------------
* Official Moonshot X evidence with an exact contract is authoritative.
* When X is unavailable, two public verification mirrors may provide a
  redundant detection path. A single mirror is provisional and cannot alert or
  enter the cross-source evidence feed.
* Mirror surfaces never count as independent Moonshot sources.
* Moonshot verification is a discovery/catalyst signal, never an endorsement,
  buy instruction, or bypass around identity, liquidity, survival, holder,
  cluster, risk, age, or execution gates.
* Young (<90d) assets may be surfaced in this dedicated research lane so we can
  learn from cases such as STONK without silently weakening the core veteran
  policy. They remain explicitly AGE_EXCEPTION_RESEARCH_ONLY.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MODE = "MOONSHOT_VERIFICATION_INTELLIGENCE_V1"
NETWORK = "solana"
OFFICIAL_X_HANDLE = "moonshot"
MIRROR_CHANNELS = (
    ("moonshotlistings", "Moonshot & Fomo Listings"),
    ("moonshotnews", "Moonshot Listings by 0xYupa"),
    ("moonshot_listings", "Moonshot Listings"),
)
OFFICIAL_PRIORITY_SCORE = 98
MIRROR_CONSENSUS_PRIORITY_SCORE = 94
PROVISIONAL_PRIORITY_SCORE = 70
MIN_RESEARCH_LIQUIDITY_USD = 15_000.0
MIN_ALERT_LIQUIDITY_USD = 50_000.0
CORE_VETERAN_AGE_DAYS = 90.0
MIRROR_WINDOW_HOURS = 36
MAX_LEDGER_EVENTS = 2_000

DATA = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
LEDGER_PATH = DATA / "moonshot-verification-ledger.json"
LATEST_PATH = DATA / "moonshot-verification-latest.json"
EXTERNAL_ALPHA_PATH = DATA / "external-alpha-events.json"

UA = {
    "User-Agent": "Wallet500-MoonshotVerification/1.0 (+https://github.com/bitcoinforu2-ui/Wallet500)",
    "Accept": "application/json,text/html,*/*",
}
SOL_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")
VERIFY_RE = re.compile(r"\b(?:is\s+now\s+)?verified\s+on\s+moonshot\b|\bnew\s+(?:coin\s+)?verification\b", re.I)
CONTRACT_RE = re.compile(r"contract\s+address\s*:\s*([1-9A-HJ-NP-Za-km-z]{32,44})", re.I)
SYMBOL_RE = re.compile(r"\$([A-Za-z0-9_]{1,20})")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _dt(value: object) -> datetime | None:
    try:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        d = datetime.fromisoformat(text)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _n(value: object, default: float | None = None) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _load(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _get(url: str, headers: dict | None = None, timeout: int = 15) -> tuple[str, Any]:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        ctype = str(response.headers.get("content-type") or "").lower()
    if "json" in ctype or raw.lstrip().startswith(("{", "[")):
        return "json", json.loads(raw)
    return "html", raw


def _safe_error(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code:
        return f"HTTP_{code}"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def looks_like_solana_address(value: object) -> bool:
    text = str(value or "").strip()
    return 32 <= len(text) <= 44 and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", text) is not None


def extract_solana_addresses(text: object) -> list[str]:
    body = str(text or "")
    out: list[str] = []
    direct = CONTRACT_RE.search(body)
    if direct and looks_like_solana_address(direct.group(1)):
        out.append(direct.group(1))
    for address in SOL_RE.findall(body):
        if looks_like_solana_address(address) and address not in out and any(c.isdigit() for c in address):
            out.append(address)
    return out


def _strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_telegram_verifications(page: str, handle: str, reference: datetime | None = None) -> list[dict]:
    """Parse verification posts from a public Telegram preview page."""
    reference = reference or _now()
    matches = list(re.finditer(r'data-post="([^"]+)"', page or "", flags=re.I))
    rows: list[dict] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(page), match.start() + 45_000)
        block = page[match.start():end]
        tm = re.search(r'<time[^>]+datetime="([^"]+)"', block, flags=re.I)
        text_match = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        if not tm or not text_match:
            continue
        published = _dt(tm.group(1))
        text = _strip_tags(text_match.group(1))
        if published is None or published < reference - timedelta(hours=MIRROR_WINDOW_HOURS + 12):
            continue
        if not VERIFY_RE.search(text):
            continue
        addresses = extract_solana_addresses(text)
        symbol_match = SYMBOL_RE.search(text)
        for token in addresses:
            rows.append({
                "surface": "telegram_public_mirror",
                "source_handle": handle,
                "post_id": match.group(1),
                "published_at": _iso(published),
                "text": text[:2500],
                "token": token,
                "symbol": symbol_match.group(1).upper() if symbol_match else None,
                "url": f"https://t.me/{match.group(1)}",
            })
    return rows


def collect_mirrors(reference: datetime | None = None) -> tuple[list[dict], list[dict]]:
    reference = reference or _now()
    rows: list[dict] = []
    health: list[dict] = []
    for handle, label in MIRROR_CHANNELS:
        try:
            _, page = _get(f"https://t.me/s/{urllib.parse.quote(handle)}")
            parsed = parse_telegram_verifications(str(page), handle, reference)
            rows.extend(parsed)
            health.append({"provider": "telegram_public_mirror", "handle": handle, "label": label, "status": "OK", "verification_rows": len(parsed)})
        except Exception as exc:
            health.append({"provider": "telegram_public_mirror", "handle": handle, "label": label, "status": _safe_error(exc), "verification_rows": 0})
    return rows, health


def collect_official_x(reference: datetime | None = None) -> tuple[list[dict], dict]:
    """Collect exact-contract Moonshot verification posts from official X.

    Exact contract + Moonshot's standard verification disclaimer is sufficient
    to identify the verification event even when the paired symbol announcement
    is a separate post. Symbol-only posts are deliberately ignored.
    """
    reference = reference or _now()
    bearer = str(os.getenv("X_BEARER_TOKEN") or "").strip()
    if not bearer:
        return [], {"provider": "x", "handle": OFFICIAL_X_HANDLE, "status": "NOT_CONFIGURED", "exact_contract_rows": 0}
    query = f"from:{OFFICIAL_X_HANDLE} (\"Verification is neither an endorsement\" OR \"verified on Moonshot\" OR \"Contract Address\") -is:retweet"
    params = urllib.parse.urlencode({
        "query": query,
        "max_results": 100,
        "tweet.fields": "created_at,author_id,public_metrics",
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
        rows: list[dict] = []
        for item in payload.get("data") or []:
            user = users.get(str(item.get("author_id") or ""), {})
            username = str(user.get("username") or "")
            if username.lower() != OFFICIAL_X_HANDLE:
                continue
            published = _dt(item.get("created_at"))
            if published is None or published < reference - timedelta(days=7):
                continue
            text = str(item.get("text") or "")
            verification_context = bool(VERIFY_RE.search(text) or re.search(r"verification\s+is\s+neither\s+an\s+endorsement", text, re.I))
            addresses = extract_solana_addresses(text) if verification_context else []
            symbol_match = SYMBOL_RE.search(text)
            for token in addresses:
                rows.append({
                    "surface": "official_x",
                    "source_handle": OFFICIAL_X_HANDLE,
                    "post_id": str(item.get("id") or ""),
                    "published_at": _iso(published),
                    "text": text[:2500],
                    "token": token,
                    "symbol": symbol_match.group(1).upper() if symbol_match else None,
                    "url": f"https://x.com/{OFFICIAL_X_HANDLE}/status/{item.get('id')}",
                    "author_verified": user.get("verified"),
                })
        return rows, {"provider": "x", "handle": OFFICIAL_X_HANDLE, "status": "OK_DIRECT", "exact_contract_rows": len(rows)}
    except Exception as exc:
        return [], {"provider": "x", "handle": OFFICIAL_X_HANDLE, "status": _safe_error(exc), "exact_contract_rows": 0}


def _market(token: str) -> tuple[dict | None, str]:
    try:
        _, payload = _get(f"https://api.dexscreener.com/token-pairs/v1/solana/{urllib.parse.quote(token)}")
        pairs = payload if isinstance(payload, list) else []
        exact: list[tuple[float, dict]] = []
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            base = pair.get("baseToken") or {}
            if str(base.get("address") or "") != token:
                continue
            liq = _n((pair.get("liquidity") or {}).get("usd"), 0.0) or 0.0
            exact.append((liq, pair))
        if not exact:
            return None, "EXACT_BASE_PAIR_NOT_FOUND"
        pair = max(exact, key=lambda x: x[0])[1]
        created_ms = _n(pair.get("pairCreatedAt"))
        created = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc) if created_ms else None
        now = _now()
        age_days = (now - created).total_seconds() / 86400.0 if created else None
        return {
            "token": token,
            "chain": NETWORK,
            "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"),
            "symbol": (pair.get("baseToken") or {}).get("symbol"),
            "name": (pair.get("baseToken") or {}).get("name"),
            "price_usd": _n(pair.get("priceUsd")),
            "liquidity_usd": _n((pair.get("liquidity") or {}).get("usd")),
            "market_cap_usd": _n(pair.get("marketCap")),
            "volume_h24_usd": _n((pair.get("volume") or {}).get("h24")),
            "price_change_h24_pct": _n((pair.get("priceChange") or {}).get("h24")),
            "pair_created_at": _iso(created) if created else None,
            "market_age_days": round(age_days, 3) if age_days is not None else None,
            "dex_url": pair.get("url") or (f"https://dexscreener.com/solana/{pair.get('pairAddress')}" if pair.get("pairAddress") else None),
            "pair_identity_locked": bool(pair.get("pairAddress")),
        }, "OK"
    except Exception as exc:
        return None, _safe_error(exc)


def _event_key(token: str) -> str:
    return hashlib.sha256(f"moonshot-verification|{NETWORK}|{token}".encode()).hexdigest()[:24]


def correlate_observations(official: list[dict], mirrors: list[dict], reference: datetime | None = None) -> list[dict]:
    reference = reference or _now()
    by_token: dict[str, dict] = {}
    for row in official:
        token = str(row.get("token") or "").strip()
        if not looks_like_solana_address(token):
            continue
        rec = by_token.setdefault(token, {"official": [], "mirrors": []})
        rec["official"].append(row)
    for row in mirrors:
        token = str(row.get("token") or "").strip()
        if not looks_like_solana_address(token):
            continue
        rec = by_token.setdefault(token, {"official": [], "mirrors": []})
        rec["mirrors"].append(row)

    out: list[dict] = []
    for token, grouped in by_token.items():
        official_rows = grouped["official"]
        mirror_rows = grouped["mirrors"]
        mirror_handles = sorted({str(x.get("source_handle") or "") for x in mirror_rows if x.get("source_handle")})
        times = [d for d in (_dt(x.get("published_at")) for x in official_rows + mirror_rows) if d]
        first_seen = min(times) if times else reference
        recent_mirrors = {
            str(x.get("source_handle") or "")
            for x in mirror_rows
            if (_dt(x.get("published_at")) and abs((reference - _dt(x.get("published_at"))).total_seconds()) <= MIRROR_WINDOW_HOURS * 3600)
        }
        if official_rows:
            confidence = "OFFICIAL_X_EXACT_CONTRACT"
            score = OFFICIAL_PRIORITY_SCORE
            evidence_directness = "DIRECT_OFFICIAL"
            eligible_for_alpha = True
            source_owner = "moonshot"
        elif len(recent_mirrors) >= 2:
            confidence = "DOUBLE_MIRROR_CONSENSUS"
            score = MIRROR_CONSENSUS_PRIORITY_SCORE
            evidence_directness = "REDUNDANT_PUBLIC_MIRRORS"
            eligible_for_alpha = True
            source_owner = "moonshot"
        else:
            confidence = "SINGLE_MIRROR_PROVISIONAL"
            score = PROVISIONAL_PRIORITY_SCORE
            evidence_directness = "PROVISIONAL_MIRROR_ONLY"
            eligible_for_alpha = False
            source_owner = "moonshot_unconfirmed"
        symbol = next((x.get("symbol") for x in official_rows + mirror_rows if x.get("symbol")), None)
        out.append({
            "event_id": _event_key(token),
            "event_type": "MOONSHOT_VERIFIED",
            "chain": NETWORK,
            "token": token,
            "symbol": symbol,
            "source_owner": source_owner,
            "source_kind": "OFFICIAL_MOONSHOT_VERIFICATION" if official_rows else "MOONSHOT_VERIFICATION_MIRROR",
            "source_category": "launchpad_discovery_platform",
            "verification_confidence": confidence,
            "evidence_directness": evidence_directness,
            "official_evidence_count": len(official_rows),
            "mirror_surface_count": len(mirror_handles),
            "mirror_surfaces": mirror_handles,
            "catalyst_priority_score": score,
            "strong_catalyst": score >= 94,
            "eligible_for_external_alpha": eligible_for_alpha,
            "first_seen_at": _iso(first_seen),
            "last_seen_at": _iso(max(times) if times else first_seen),
            "source_url": next((x.get("url") for x in official_rows if x.get("url")), None) or next((x.get("url") for x in mirror_rows if x.get("url")), None),
            "evidence": (official_rows + mirror_rows)[-20:],
            "automatic_buy": False,
            "production_trade_impact": "NONE",
        })
    return sorted(out, key=lambda x: x.get("first_seen_at") or "", reverse=True)


def _merge_external_alpha(events: list[dict]) -> int:
    payload = _load(EXTERNAL_ALPHA_PATH, {"version": 1, "events": []})
    if isinstance(payload, list):
        payload = {"version": 1, "events": payload}
    if not isinstance(payload, dict):
        payload = {"version": 1, "events": []}
    existing = payload.get("events") if isinstance(payload.get("events"), list) else []
    kept = [x for x in existing if not (isinstance(x, dict) and str(x.get("event_type") or "") == "MOONSHOT_VERIFIED")]
    alpha_rows = []
    for event in events:
        if event.get("eligible_for_external_alpha") is not True:
            continue
        market = event.get("market") or {}
        if market.get("pair_identity_locked") is not True:
            continue
        if (_n(market.get("liquidity_usd"), 0.0) or 0.0) < MIN_RESEARCH_LIQUIDITY_USD:
            continue
        alpha_rows.append({
            "event_id": event["event_id"],
            "event_type": "MOONSHOT_VERIFIED",
            "source_owner": "moonshot",
            "source_kind": event.get("source_kind"),
            "source_url": event.get("source_url"),
            "chain": NETWORK,
            "token": event.get("token"),
            "symbol": event.get("symbol") or market.get("symbol"),
            "observed_at": event.get("first_seen_at"),
            "last_seen_at": event.get("last_seen_at"),
            "verification_confidence": event.get("verification_confidence"),
            "catalyst_priority_score": event.get("catalyst_priority_score"),
            "moonshot_verified": True,
            "pair_address": market.get("pair_address"),
            "liquidity_usd": market.get("liquidity_usd"),
            "market_age_days": market.get("market_age_days"),
            "age_policy": event.get("age_policy"),
            "research_only_until_wallet500_gates_pass": True,
            "automatic_buy": False,
        })
    payload.update({
        "version": max(1, int(payload.get("version") or 1)),
        "updated_at": _iso(_now()),
        "events": (kept + alpha_rows)[-10_000:],
    })
    _write(EXTERNAL_ALPHA_PATH, payload)
    return len(alpha_rows)


def _telegram_send(text: str) -> tuple[bool, str]:
    bot = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = str(os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not bot or not chat:
        return False, "TELEGRAM_SECRETS_MISSING"
    try:
        body = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA["User-Agent"]},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if int(getattr(response, "status", 200)) >= 300:
                return False, f"HTTP_{response.status}"
        return True, "SENT"
    except Exception as exc:
        return False, _safe_error(exc)


def _message(event: dict) -> str:
    m = event.get("market") or {}
    liq = _n(m.get("liquidity_usd"))
    age = _n(m.get("market_age_days"))
    lines = [
        "🔥🔥🔥 MOONSHOT VERIFIED — HIGH PRIORITY",
        f"{event.get('symbol') or m.get('symbol') or '?'} | catalyst {event.get('catalyst_priority_score')}/100",
        f"Confidence: {event.get('verification_confidence')}",
        f"CA: {event.get('token')}",
        f"Liquidity: ${liq:,.0f}" if liq is not None else "Liquidity: unknown",
        f"Age: {age:.1f}d | {event.get('age_policy')}" if age is not None else f"Age: unknown | {event.get('age_policy')}",
        "Research catalyst only — NOT a buy instruction. Core Wallet500 risk/execution gates still apply.",
    ]
    if m.get("dex_url"):
        lines.append(f"DEX: {m.get('dex_url')}")
    if event.get("source_url"):
        lines.append(f"Source: {event.get('source_url')}")
    return "\n".join(lines)


def _decorate_market(event: dict) -> dict:
    out = dict(event)
    market, status = _market(str(event.get("token") or ""))
    out["market_status"] = status
    out["market"] = market or {}
    age = _n((market or {}).get("market_age_days"))
    if age is not None and age >= CORE_VETERAN_AGE_DAYS:
        out["age_policy"] = "CORE_VETERAN_90D_PASS"
        out["veteran_gate_pass"] = True
    else:
        out["age_policy"] = "AGE_EXCEPTION_RESEARCH_ONLY"
        out["veteran_gate_pass"] = False
    liq = _n((market or {}).get("liquidity_usd"), 0.0) or 0.0
    out["research_liquidity_pass"] = bool(market and market.get("pair_identity_locked") is True and liq >= MIN_RESEARCH_LIQUIDITY_USD)
    out["alert_liquidity_pass"] = bool(market and market.get("pair_identity_locked") is True and liq >= MIN_ALERT_LIQUIDITY_USD)
    out["alert_eligible"] = bool(out.get("eligible_for_external_alpha") is True and out["alert_liquidity_pass"])
    out["automatic_buy"] = False
    out["never_bypass_wallet500_gates"] = True
    return out


def run(reference: datetime | None = None) -> dict:
    reference = reference or _now()
    DATA.mkdir(parents=True, exist_ok=True)
    previous = _load(LEDGER_PATH, {"version": 1, "events": {}, "alerted": {}})
    if not isinstance(previous, dict):
        previous = {"version": 1, "events": {}, "alerted": {}}
    previous_events = previous.get("events") if isinstance(previous.get("events"), dict) else {}
    alerted = previous.get("alerted") if isinstance(previous.get("alerted"), dict) else {}

    official, x_health = collect_official_x(reference)
    mirrors, mirror_health = collect_mirrors(reference)
    detected = correlate_observations(official, mirrors, reference)

    decorated: list[dict] = []
    telegram: list[dict] = []
    for event in detected:
        e = _decorate_market(event)
        key = str(e.get("event_id"))
        old = previous_events.get(key) if isinstance(previous_events.get(key), dict) else None
        is_new = old is None
        if old:
            e["first_seen_at"] = old.get("first_seen_at") or e.get("first_seen_at")
        e["detected_new_this_run"] = is_new
        if is_new and e.get("alert_eligible") and key not in alerted:
            published = _dt(e.get("first_seen_at"))
            # Do not blast historical backlog on first deployment. A fresh event
            # remains alertable even on the first run.
            fresh = published is not None and reference - published <= timedelta(minutes=30)
            if fresh:
                ok, status = _telegram_send(_message(e))
                telegram.append({"event_id": key, "ok": ok, "status": status})
                if ok:
                    alerted[key] = _iso(reference)
        previous_events[key] = e
        decorated.append(e)

    # Preserve historical truth while bounding storage.
    ordered = sorted(previous_events.values(), key=lambda x: str(x.get("first_seen_at") or ""), reverse=True)[:MAX_LEDGER_EVENTS]
    event_map = {str(x.get("event_id")): x for x in ordered if x.get("event_id")}
    ledger = {
        "version": 1,
        "mode": MODE,
        "updated_at": _iso(reference),
        "network": NETWORK,
        "policy": {
            "official_x_exact_contract_priority": OFFICIAL_PRIORITY_SCORE,
            "double_mirror_consensus_priority": MIRROR_CONSENSUS_PRIORITY_SCORE,
            "single_mirror_priority": PROVISIONAL_PRIORITY_SCORE,
            "single_mirror_can_alert": False,
            "single_mirror_can_enter_external_alpha": False,
            "min_research_liquidity_usd": MIN_RESEARCH_LIQUIDITY_USD,
            "min_alert_liquidity_usd": MIN_ALERT_LIQUIDITY_USD,
            "core_veteran_age_days": CORE_VETERAN_AGE_DAYS,
            "young_assets": "AGE_EXCEPTION_RESEARCH_ONLY",
            "automatic_buy": False,
            "moonshot_verification_never_bypasses_wallet500_gates": True,
        },
        "source_health": {"official_x": x_health, "mirrors": mirror_health},
        "events": event_map,
        "alerted": alerted,
    }
    _write(LEDGER_PATH, ledger)
    alpha_count = _merge_external_alpha(decorated)
    latest = {
        "version": 1,
        "mode": MODE,
        "updated_at": _iso(reference),
        "status": "OK" if (str(x_health.get("status") or "").startswith("OK") or sum(1 for h in mirror_health if h.get("status") == "OK") >= 2) else "DEGRADED",
        "official_x": x_health,
        "mirror_health": mirror_health,
        "counts": {
            "official_exact_contract_observations": len(official),
            "mirror_observations": len(mirrors),
            "tokens_detected": len(detected),
            "high_priority_events": sum(1 for e in decorated if e.get("strong_catalyst")),
            "research_ready_events": sum(1 for e in decorated if e.get("research_liquidity_pass")),
            "external_alpha_events": alpha_count,
            "telegram_attempts": len(telegram),
            "telegram_delivered": sum(1 for x in telegram if x.get("ok")),
        },
        "new_events": [e for e in decorated if e.get("detected_new_this_run")],
        "telegram": telegram,
        "automatic_buy": False,
        "production_trade_impact": "NONE",
    }
    _write(LATEST_PATH, latest)
    return latest


if __name__ == "__main__":
    result = run()
    print(json.dumps({"mode": result["mode"], "status": result["status"], "counts": result["counts"]}, ensure_ascii=False))
