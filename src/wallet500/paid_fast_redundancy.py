from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MODE = "RESEARCH_ONLY_PAID_FAST_REDUNDANCY_V1"
CONTRACT = "PAID_FAST_REDUNDANCY_V1"
NETWORK = "solana"
PRODUCTION_IMPACT = "NONE"
REUSE_GAP_HOURS = 36
MAX_EVENTS = 10000
X_POLL_EVERY_RUNS = 6

TELEGRAM_SOURCES = [
    {"handle": "dexssignal", "name": "DEX PAID signals", "role": "DEXSCREENER_PAID"},
    {"handle": "dexpaidads", "name": "DEX PAID ADS", "role": "DEXSCREENER_PAID_ADS"},
    {"handle": "mevxpfdexpaid", "name": "MevX - PF - Dex Paid", "role": "DEXSCREENER_PAID_PLUS_HOLDERS"},
    {"handle": "dexpaid_solana", "name": "Solana DEX PAID and BOOSTS Alerts", "role": "DEXSCREENER_PAID_AND_BOOST"},
    {"handle": "dexscreeneronline", "name": "DEX Screener Online / Dex Events", "role": "BOOST_DEXTOOLS_KOL_EVENT_MESH"},
]

X_SOURCES = [
    {"handle": "dex_kolwatcher", "name": "DEX Signals", "role": "PAID_DEXSCREENER"},
    {"handle": "dexsignals", "name": "Dex signals", "role": "PAID_AND_BOOST_DEXSCREENER"},
    {"handle": "KolXscanner", "name": "KOL X Scanner", "role": "PAID_DEXSCREENER_AND_KOL"},
    {"handle": "DexSignalRadar", "name": "DexSignalRadar / Alpha Radar", "role": "PAID_DEXSCREENER_AND_CTO"},
    {"handle": "0x_gemss", "name": "tsak", "role": "PAID_DEXSCREENER"},
    {"handle": "OnChainTrending", "name": "OnChain Trend Signals", "role": "PAID_DEXSCREENER_AND_CTO"},
]

SOL_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")
URL_RE = re.compile(r"https?://\S+", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value):
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _n(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _err(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return "NETWORK_UNAVAILABLE"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _get_json(url: str, headers: dict | None = None, timeout: int = 15):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Wallet500-PaidFast/1.0", **(headers or {})})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_text(url: str, timeout: int = 15) -> str:
    req = Request(url, headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0 Wallet500-PaidFast/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def looks_like_solana_address(value: str) -> bool:
    value = str(value or "").strip()
    return 32 <= len(value) <= 44 and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", value) is not None


def extract_solana_addresses(text: str) -> list[str]:
    body = URL_RE.sub(" ", str(text or ""))
    out = []
    for value in SOL_RE.findall(body):
        if looks_like_solana_address(value) and any(c.isdigit() for c in value) and value not in out:
            out.append(value)
    return out


def classify_text(text: str) -> list[str]:
    low = str(text or "").lower()
    kinds = []
    if "paid ads dexscreener" in low or "paid ad dexscreener" in low:
        kinds.append("DEXSCREENER_PAID_AD")
    elif "paid dexscreener" in low:
        kinds.append("DEXSCREENER_PAID")
    if "dexscreener boost" in low or ("detect boost" in low and "dexscreener" in low):
        kinds.append("DEXSCREENER_BOOST")
    if "dextools trend" in low:
        kinds.append("DEXTOOLS_TREND")
    if "influencer post" in low or "kol signal" in low:
        kinds.append("INFLUENCER_SIGNAL")
    if "new cto detected" in low or "dexscreener cto" in low:
        kinds.append("CTO_SIGNAL")
    return kinds


def _strip_tags(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_telegram_messages(page: str, handle: str, reference: datetime | None = None) -> list[dict]:
    reference = reference or datetime.now(timezone.utc)
    matches = list(re.finditer(r'data-post="([^"]+)"', page, flags=re.I))
    rows = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(page), match.start() + 40000)
        block = page[match.start():end]
        tm = re.search(r'<time[^>]+datetime="([^"]+)"', block, flags=re.I)
        if not tm:
            continue
        published = _dt(tm.group(1))
        if published is None or published < reference - timedelta(hours=24) or published > reference + timedelta(minutes=5):
            continue
        txt = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        post_id = match.group(1)
        rows.append({"source": "telegram", "source_handle": handle, "id": post_id, "published_at": published.isoformat(), "text": _strip_tags(txt.group(1))[:2500] if txt else "", "url": f"https://t.me/{post_id}"})
    return list({r["id"]: r for r in rows}.values())


def collect_telegram(reference: datetime):
    rows, statuses = [], []
    for src in TELEGRAM_SOURCES:
        handle = src["handle"]
        try:
            posts = parse_telegram_messages(_get_text(f"https://t.me/s/{quote(handle)}"), handle, reference)
            relevant = 0
            for post in posts:
                kinds = classify_text(post["text"])
                addresses = extract_solana_addresses(post["text"])
                if not kinds or not addresses:
                    continue
                relevant += 1
                for token in addresses:
                    rows.append({**post, "event_types": kinds, "token_address": token, "source_role": src["role"]})
            statuses.append({"provider": "telegram", "handle": handle, "status": "OK", "posts_24h": len(posts), "relevant_events": relevant})
        except Exception as exc:
            statuses.append({"provider": "telegram", "handle": handle, "status": _err(exc), "posts_24h": 0, "relevant_events": 0})
    return rows, statuses


def collect_x(reference: datetime, enabled: bool):
    token = (os.getenv("X_BEARER_TOKEN") or "").strip()
    if not enabled:
        return [], {"provider": "x", "status": "SKIPPED_BUDGET_GUARD"}
    if not token:
        return [], {"provider": "x", "status": "NOT_CONFIGURED"}
    handles = [x["handle"] for x in X_SOURCES]
    query = "(" + " OR ".join(f"from:{h}" for h in handles) + ") (DEXScreener OR DEXTools OR PAID OR Boost OR CTO) -is:retweet"
    params = urlencode({"query": query, "max_results": 100, "tweet.fields": "created_at,author_id", "expansions": "author_id", "user.fields": "username"})
    try:
        payload = _get_json("https://api.x.com/2/tweets/search/recent?" + params, {"Authorization": "Bearer " + token})
        users = {str(x.get("id")): x for x in (((payload.get("includes") or {}).get("users")) or []) if isinstance(x, dict)}
        allowed = {h.lower() for h in handles}
        rows = []
        for item in payload.get("data") or []:
            username = str(users.get(str(item.get("author_id")), {}).get("username") or "")
            published = _dt(item.get("created_at"))
            if username.lower() not in allowed or published is None or published < reference - timedelta(hours=24):
                continue
            text = str(item.get("text") or "")
            kinds = classify_text(text)
            for address in extract_solana_addresses(text) if kinds else []:
                rows.append({"source": "x", "source_handle": username, "id": item.get("id"), "published_at": published.isoformat(), "text": text[:2500], "url": f"https://x.com/{username}/status/{item.get('id')}", "event_types": kinds, "token_address": address})
        return rows, {"provider": "x", "status": "OK", "count": len(rows), "accounts": len(handles)}
    except Exception as exc:
        return [], {"provider": "x", "status": _err(exc), "accounts": len(handles)}


def collect_official_dexscreener():
    specs = [
        ("TOKEN_BOOST_TOP", "DEXSCREENER_BOOST", "https://api.dexscreener.com/token-boosts/top/v1"),
        ("TOKEN_BOOST_LATEST", "DEXSCREENER_BOOST", "https://api.dexscreener.com/token-boosts/latest/v1"),
        ("ADS_LATEST", "DEXSCREENER_PAID_AD", "https://api.dexscreener.com/ads/latest/v1"),
    ]
    rows, statuses = [], []
    for surface, kind, url in specs:
        try:
            payload = _get_json(url)
            values = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
            count = 0
            for item in values:
                token = str(item.get("tokenAddress") or "") if isinstance(item, dict) else ""
                if str(item.get("chainId") or "").lower() != NETWORK or not looks_like_solana_address(token):
                    continue
                count += 1
                rows.append({"source": "dexscreener_official", "source_handle": surface, "id": str(item.get("url") or f"{surface}:{token}"), "published_at": item.get("date"), "url": item.get("url"), "event_types": [kind], "token_address": token, "official_surface": surface, "boost_amount": _n(item.get("amount")), "boost_total_amount": _n(item.get("totalAmount"))})
            statuses.append({"provider": "dexscreener_official", "surface": surface, "status": "OK", "solana_count": count})
        except Exception as exc:
            statuses.append({"provider": "dexscreener_official", "surface": surface, "status": _err(exc), "solana_count": 0})
    return rows, statuses


def exact_pair_market(token: str, observed_at: str):
    try:
        payload = _get_json(f"https://api.dexscreener.com/token-pairs/v1/solana/{quote(token)}")
        candidates = []
        for pair in payload if isinstance(payload, list) else []:
            if not isinstance(pair, dict) or str((pair.get("baseToken") or {}).get("address") or "") != token:
                continue
            candidates.append((_n((pair.get("liquidity") or {}).get("usd"), 0) or 0, pair))
        if not candidates:
            return None, "PAIR_NOT_FOUND"
        pair = max(candidates, key=lambda x: x[0])[1]
        vol, pc = pair.get("volume") or {}, pair.get("priceChange") or {}
        return {"observed_at": observed_at, "token_address": token, "pair_address": pair.get("pairAddress"), "dex_id": pair.get("dexId"), "symbol": (pair.get("baseToken") or {}).get("symbol"), "name": (pair.get("baseToken") or {}).get("name"), "price_usd": _n(pair.get("priceUsd")), "liquidity_usd": _n((pair.get("liquidity") or {}).get("usd")), "market_cap_usd": _n(pair.get("marketCap")), "volume_24h_usd": _n(vol.get("h24")), "price_change_h1_pct": _n(pc.get("h1")), "price_change_h24_pct": _n(pc.get("h24")), "boosts_active": int(_n((pair.get("boosts") or {}).get("active"), 0) or 0)}, "OK"
    except Exception as exc:
        return None, _err(exc)


def main_paid_tokens(payload: dict) -> set[str]:
    return {str(e.get("token_address")) for e in payload.get("events") or [] if isinstance(e, dict) and str(e.get("chain") or "").lower() == NETWORK and e.get("token_address")}


def _find_reusable(events: list[dict], token: str, reference: datetime):
    for event in reversed(events):
        last = _dt(event.get("last_seen_at") or event.get("first_seen_at"))
        if event.get("token_address") == token and last and reference - last <= timedelta(hours=REUSE_GAP_HOURS):
            return event
    return None


def merge_observation(events: list[dict], obs: dict, observed_at: str, market: dict | None, in_main: bool):
    reference = _dt(observed_at) or datetime.now(timezone.utc)
    token = str(obs["token_address"])
    event = _find_reusable(events, token, reference)
    if event is None:
        first_seen = str(obs.get("published_at") or observed_at)
        event = {"event_id": hashlib.sha256(f"{NETWORK}|{token}|{first_seen[:10]}".encode()).hexdigest()[:24], "network": NETWORK, "token_address": token, "pair_address": (market or {}).get("pair_address"), "pair_identity_locked": bool((market or {}).get("pair_address")), "first_seen_at": first_seen, "last_seen_at": observed_at, "event_types": [], "official_dexscreener_seen": False, "external_confirmation_handles": [], "source_evidence": [], "first_market": market, "latest_market": market, "main_paid_ledger_covered": bool(in_main), "production_portfolio_impact": PRODUCTION_IMPACT}
        events.append(event)
    event["last_seen_at"] = observed_at
    event["main_paid_ledger_covered"] = bool(event.get("main_paid_ledger_covered") or in_main)
    event["event_types"] = sorted(set([*(event.get("event_types") or []), *(obs.get("event_types") or [])]))
    if obs.get("source") == "dexscreener_official":
        event["official_dexscreener_seen"] = True
    else:
        handle = str(obs.get("source_handle") or "")
        if handle and handle not in event["external_confirmation_handles"]:
            event["external_confirmation_handles"].append(handle)
    key = f"{obs.get('source')}:{obs.get('source_handle')}:{obs.get('id')}:{token}"
    if key not in {x.get("evidence_key") for x in event["source_evidence"]}:
        event["source_evidence"].append({"evidence_key": key, "source": obs.get("source"), "source_handle": obs.get("source_handle"), "source_role": obs.get("source_role"), "post_id": obs.get("id"), "published_at": obs.get("published_at"), "observed_at": observed_at, "url": obs.get("url"), "event_types": obs.get("event_types"), "official_surface": obs.get("official_surface"), "boost_amount": obs.get("boost_amount"), "boost_total_amount": obs.get("boost_total_amount")})
    event["source_evidence"] = event["source_evidence"][-100:]
    if market and (not event.get("pair_address") or event.get("pair_address") == market.get("pair_address")):
        event["pair_address"] = market.get("pair_address")
        event["pair_identity_locked"] = bool(market.get("pair_address"))
        event["latest_market"] = market
    return event


def run(output_dir: str = "data") -> dict:
    data = Path(output_dir)
    ledger_path = data / "paid-fast-redundancy-ledger.json"
    summary_path = data / "paid-fast-redundancy-summary.json"
    old = _load(ledger_path, {})
    if old and (old.get("mode") != MODE or old.get("contract") != CONTRACT or old.get("production_portfolio_impact") != PRODUCTION_IMPACT):
        raise RuntimeError("PAID_FAST_REDUNDANCY_SOURCE_CONTRACT_REJECTED")
    observed_at = now_iso()
    reference = _dt(observed_at) or datetime.now(timezone.utc)
    events = [e for e in old.get("events") or [] if isinstance(e, dict)]
    run_count = int(old.get("run_count") or 0) + 1
    main_tokens = main_paid_tokens(_load(data / "paid-visibility-ledger.json", {}))

    official, official_status = collect_official_dexscreener()
    telegram, telegram_status = collect_telegram(reference)
    every = max(1, int(os.getenv("PAID_FAST_X_POLL_EVERY_RUNS", str(X_POLL_EVERY_RUNS))))
    x_rows, x_status = collect_x(reference, run_count <= 1 or run_count % every == 0)
    observations = [*official, *telegram, *x_rows]

    cache, pair_status = {}, {}
    for obs in observations:
        token = str(obs.get("token_address") or "")
        if not looks_like_solana_address(token):
            continue
        if token not in cache:
            cache[token], status = exact_pair_market(token, observed_at)
            pair_status[status] = pair_status.get(status, 0) + 1
        merge_observation(events, obs, observed_at, cache[token], token in main_tokens)

    cutoff = reference - timedelta(days=14)
    events = [e for e in events if (_dt(e.get("last_seen_at")) or reference) >= cutoff][-MAX_EVENTS:]
    active_cutoff = reference - timedelta(hours=36)
    active = [e for e in events if (_dt(e.get("last_seen_at")) or reference) >= active_cutoff]
    for e in events:
        e["external_confirmation_handles"] = sorted(set(e.get("external_confirmation_handles") or []), key=str.lower)
        if e.get("main_paid_ledger_covered"):
            e["coverage_status"] = "COVERED_BY_MAIN_PAID_LEDGER"
        elif e.get("official_dexscreener_seen"):
            e["coverage_status"] = "FAST_OFFICIAL_BACKUP_NOT_YET_IN_MAIN_LEDGER"
        elif e.get("external_confirmation_handles"):
            e["coverage_status"] = "EXTERNAL_ONLY_RESEARCH_UNCONFIRMED_BY_OFFICIAL_FEED"
        else:
            e["coverage_status"] = "RESEARCH_UNKNOWN"

    counts = {"observations_this_run": len(observations), "official_observations_this_run": len(official), "telegram_observations_this_run": len(telegram), "x_observations_this_run": len(x_rows), "unique_tokens_looked_up_this_run": len(cache), "events_retained_14d": len(events), "active_events_36h": len(active), "active_main_covered": sum(e.get("coverage_status") == "COVERED_BY_MAIN_PAID_LEDGER" for e in active), "active_fast_official_backup": sum(e.get("coverage_status") == "FAST_OFFICIAL_BACKUP_NOT_YET_IN_MAIN_LEDGER" for e in active), "active_external_only": sum(e.get("coverage_status") == "EXTERNAL_ONLY_RESEARCH_UNCONFIRMED_BY_OFFICIAL_FEED" for e in active), "active_with_external_confirmation": sum(bool(e.get("external_confirmation_handles")) for e in active), "telegram_sources_configured": len(TELEGRAM_SOURCES), "x_sources_registered": len(X_SOURCES)}
    base = {"version": 1, "mode": MODE, "contract": CONTRACT, "network": NETWORK, "generated_at": observed_at, "run_count": run_count, "production_portfolio_impact": PRODUCTION_IMPACT, "no_hindsight": True}
    ledger = {**base, "source_policy": "DIRECT_DEXSCREENER_PLUS_REDUNDANT_PUBLIC_SIGNAL_ACCOUNTS; EXTERNAL SOURCES NEVER CREATE BUY/PRE-ALPHA STATUS", "telegram_sources": TELEGRAM_SOURCES, "x_sources": X_SOURCES, "counts": counts, "events": events}
    summary = {**base, "counts": counts, "provider_status": {"dexscreener": official_status, "telegram": telegram_status, "x": x_status, "exact_pair_status_counts": pair_status}, "active_fast_official_backup": [{k: e.get(k) for k in ("event_id", "token_address", "pair_address", "first_seen_at", "last_seen_at", "event_types", "external_confirmation_handles", "coverage_status")} for e in active if e.get("coverage_status") == "FAST_OFFICIAL_BACKUP_NOT_YET_IN_MAIN_LEDGER"][:100], "active_external_only": [{k: e.get(k) for k in ("event_id", "token_address", "pair_address", "first_seen_at", "last_seen_at", "event_types", "external_confirmation_handles", "coverage_status")} for e in active if e.get("coverage_status") == "EXTERNAL_ONLY_RESEARCH_UNCONFIRMED_BY_OFFICIAL_FEED"][:100], "rule": "Redundancy findings are research/audit evidence only. External accounts never create a buy or production signal."}
    _write(ledger_path, ledger)
    _write(summary_path, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
