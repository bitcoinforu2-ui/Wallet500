"""Wallet500 Catalyst Wire — official-event-first intelligence.

This lane is deliberately independent from momentum scoring. For a listing,
pre-listing, exchange roadmap, pre-market/call-auction event, or another verified
official catalyst, volume/liquidity/holder growth are normally consequences of
the announcement and therefore have ZERO weight in this lane.

An event can alert only when its token already passes Wallet500's preliminary
identity/safety/veteran filter. Alerts are research-only/manual; no trade is ever
executed by this module.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
OUT = DATA / "catalyst-wire-live.json"
LEDGER = DATA / "catalyst-wire-ledger.json"
STATE = DATA / "catalyst-wire-state.json"
MIN_VETERAN_AGE_DAYS = 180
MAX_WORKERS = 10

UA = {
    "User-Agent": "Wallet500-CatalystWire/1.1 (+https://github.com/bitcoinforu2-ui/Wallet500)",
    "Accept": "application/json,text/html,*/*",
}
BLOCKED_SYMBOLS = {
    "USDT", "USDC", "USDBC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD",
    "WETH", "WBNB", "WBTC", "WSOL", "STETH", "WSTETH", "CBBTC", "CBETH",
}

PAGE_SOURCES = [
    ("MEXC_SPOT_LISTINGS", "mexc", "https://www.mexc.com/announcements/new-listings/spot-18"),
    ("MEXC_FUTURES_LISTINGS", "mexc", "https://www.mexc.com/announcements/new-listings/futures-19"),
    ("MEXC_TELEGRAM", "mexc", "https://t.me/s/MEXC_OfficialAnnouncements"),
    ("BINANCE_NEW_LISTINGS", "binance", "https://www.binance.com/en/support/announcement/list/48"),
    ("BINANCE_TELEGRAM", "binance", "https://t.me/s/binance_announcements"),
    ("KRAKEN_ROADMAP", "kraken", "https://www.kraken.com/listings"),
    ("BITGET_SPOT_LISTINGS", "bitget", "https://www.bitget.com/support/sections/5955813039257"),
    ("BITGET_FUTURES_LISTINGS", "bitget", "https://www.bitget.com/support/sections/12508313405000"),
    ("BITHUMB_MARKET_ADDITIONS", "bithumb", "https://feed.bithumb.com/notice?category=9&page=1"),
    ("COINEX_NEW_LISTINGS", "coinex", "https://www.coinex.com/en/announcements"),
    ("HTX_NEW_LISTINGS", "htx", "https://www.htx.com/en-us/support/list/360000039942/"),
    ("LBANK_ANNOUNCEMENTS", "lbank", "https://www.lbank.com/support/announcement"),
    ("BINGX_LISTINGS", "bingx", "https://bingx.com/en/support/"),
    ("BITMART_LISTINGS", "bitmart", "https://www.bitmart.com/en-US/support/sections/7923014477723/360000908874"),
    ("WEEX_LISTINGS", "weex", "https://www.weex.com/help/categories/360000459153"),
    ("CRYPTOCOM_PRODUCT_NEWS", "crypto.com", "https://crypto.com/product-news"),
    ("UPBIT_PUBLIC_NOTICES", "upbit", "https://upbit.com/service_center/notice"),
]

API_SOURCES = [
    ("GATE_SPOT_INSTRUMENTS", "gate", "https://api.gateio.ws/api/v4/spot/currency_pairs"),
    ("OKX_SPOT_INSTRUMENTS", "okx", "https://www.okx.com/api/v5/public/instruments?instType=SPOT"),
    ("OKX_SWAP_INSTRUMENTS", "okx", "https://www.okx.com/api/v5/public/instruments?instType=SWAP"),
    ("KUCOIN_SPOT_INSTRUMENTS", "kucoin", "https://api.kucoin.com/api/v2/symbols"),
    ("BYBIT_SPOT_INSTRUMENTS", "bybit", "https://api.bybit.com/v5/market/instruments-info?category=spot&limit=1000"),
    ("BITGET_SPOT_INSTRUMENTS", "bitget", "https://api.bitget.com/api/v2/spot/public/symbols"),
    ("COINBASE_PRODUCTS", "coinbase", "https://api.exchange.coinbase.com/products"),
    ("LBANK_SPOT_INSTRUMENTS", "lbank", "https://api.lbank.info/v2/currencyPairs.do"),
    ("WEEX_SPOT_INSTRUMENTS", "weex", "https://api-spot.weex.com/api/v3/exchangeInfo"),
]
ANNOUNCEMENT_API_SOURCES = [
    ("BITGET_ANNOUNCEMENT_API", "bitget", "https://api.bitget.com/api/v2/public/annoucements?language=en_US&annType=coin_listings&limit=10"),
]

EVENT_RULES = [
    ("SPOT_LISTING_EXPECTED", 100, re.compile(r"\b(will\s+(?:be\s+)?list|to\s+list|listing\s+on|gets?\s+listed|market\s+addition|마켓\s*추가|거래지원\s*개시|coming\s+soon)\b", re.I)),
    ("EXCHANGE_ROADMAP", 96, re.compile(r"\b(listing\s+roadmap|roadmap|tokens?\s+launching\s+soon)\b", re.I)),
    ("PREMARKET_OR_AUCTION", 94, re.compile(r"\b(pre[- ]?market|preopen|call\s+auction|auction\s+mode|pendingopen|prelaunch)\b", re.I)),
    ("FUTURES_LISTING", 86, re.compile(r"\b(perpetual|futures?|swap)\b.{0,100}\b(list|launch|available|add)|\b(list|launch|available|add)\b.{0,100}\b(perpetual|futures?|swap)\b", re.I)),
    ("LAUNCHPOOL_ALPHA_AIRDROP", 82, re.compile(r"\b(launchpool|hodler\s+airdrop|binance\s+alpha|megadrop|token\s+generation\s+event|\bTGE\b)\b", re.I)),
    ("OFFICIAL_CATALYST", 76, re.compile(r"\b(partnership|partnered|integration|integrated|mainnet|buyback|token\s+burn|burned|migration|hard\s+fork|rebrand|contract\s+swap)\b", re.I)),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _get(url: str, timeout: int = 15) -> tuple[str, Any]:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
        ctype = (r.headers.get("content-type") or "").lower()
    if "json" in ctype or raw.lstrip().startswith(("{", "[")):
        return "json", json.loads(raw)
    return "html", raw


def _plain(raw: str) -> str:
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw or "", flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _anchors(raw: str, base_url: str) -> list[tuple[str, str]]:
    out = []
    for href, body in re.findall(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", raw or "", flags=re.I | re.S):
        label = _plain(body)
        if label:
            out.append((label, urllib.parse.urljoin(base_url, html.unescape(href))))
    return out[:5000]


def _norm_symbol(value: object) -> str:
    s = re.sub(r"[^A-Z0-9]", "", str(value or "").upper().strip())
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH", "KRW", "EUR"):
        if s.endswith(quote) and len(s) > len(quote) + 1:
            return s[:-len(quote)]
    return s


def _norm_chain(value: object) -> str:
    x = str(value or "").lower().strip()
    return {"eth": "ethereum", "bnb": "bsc", "binance-smart-chain": "bsc", "arbitrum-one": "arbitrum"}.get(x, x)


def _finite(value: object) -> float | None:
    try:
        v = float(value)
        return v if v == v and abs(v) != float("inf") else None
    except Exception:
        return None


def _walk_rows(obj: Any, depth: int = 0):
    if depth > 6:
        return
    if isinstance(obj, list):
        for item in obj[:5000]:
            if isinstance(item, dict):
                yield item
                yield from _walk_rows(item, depth + 1)
    elif isinstance(obj, dict):
        for key, value in list(obj.items())[:5000]:
            if isinstance(value, dict):
                if any(k in value for k in ("token", "token_address", "mint", "chain", "market_age_days")):
                    row = dict(value)
                    row.setdefault("symbol", key)
                    yield row
                yield from _walk_rows(value, depth + 1)
            elif isinstance(value, list):
                yield from _walk_rows(value, depth + 1)


def _candidate_universe() -> dict[str, dict]:
    sources = [
        "active-qualified-candidates.json", "multichain-veteran-revival.json",
        "manual-watchlist.json", "revival-1000-latest.json", "cex-identity-registry.json",
        "real-alerts.json", "candidate-evidence-envelope.json",
    ]
    by_symbol: dict[str, dict] = {}
    for filename in sources:
        for row in _walk_rows(_load(DATA / filename, {})):
            symbol = _norm_symbol(row.get("symbol") or row.get("ticker"))
            token = str(row.get("token") or row.get("token_address") or row.get("mint") or row.get("contract") or "").strip()
            chain = _norm_chain(row.get("chain") or row.get("network"))
            if not symbol or symbol in BLOCKED_SYMBOLS:
                continue
            dst = by_symbol.setdefault(symbol, {"symbol": symbol, "sources": []})
            if filename not in dst["sources"]:
                dst["sources"].append(filename)
            if token and not dst.get("token"):
                dst["token"] = token
            if chain and not dst.get("chain"):
                dst["chain"] = chain
            for key in ("dex_url", "url", "pair_address", "name"):
                if row.get(key) and not dst.get(key):
                    dst[key] = row.get(key)
            age = _finite(row.get("market_age_days") or row.get("market_age_min_days") or row.get("age_days"))
            if age is not None:
                dst["market_age_days"] = max(age, _finite(dst.get("market_age_days")) or 0.0)
            risk = str(row.get("pump_dump_risk_level") or row.get("risk_level") or "").upper()
            if risk in {"HIGH", "CRITICAL"} or row.get("pump_dump_blocked") is True:
                dst["hard_risk_block"] = True
            if row.get("market_age_verified") is True or row.get("registry_identity_verified") is True:
                dst["identity_or_age_verified"] = True
            if row.get("qualification") in {"QUALIFIED", "REVIVAL_QUALIFIED"} or row.get("actionable_research_alert") is True:
                dst["existing_engine_pass"] = True

    current_names = {"active-qualified-candidates.json", "multichain-veteran-revival.json", "manual-watchlist.json", "revival-1000-latest.json", "real-alerts.json"}
    for row in by_symbol.values():
        age = _finite(row.get("market_age_days"))
        exact_identity = bool(row.get("token") and row.get("chain"))
        current = bool(set(row.get("sources") or []) & current_names)
        row["preliminary_filter_pass"] = bool(
            exact_identity and not row.get("hard_risk_block")
            and (age is None or age >= MIN_VETERAN_AGE_DAYS)
            and (current or row.get("existing_engine_pass") or row.get("identity_or_age_verified"))
        )
        row["filter_policy"] = "IDENTITY_SAFETY_AGE_ONLY_NO_VOLUME_LIQUIDITY_HOLDER_GROWTH_WEIGHT"
    return by_symbol


def _classify(text: str, source_id: str) -> tuple[str | None, int]:
    if source_id == "KRAKEN_ROADMAP":
        return "EXCHANGE_ROADMAP", 96
    for event_type, score, rx in EVENT_RULES:
        if rx.search(text or ""):
            return event_type, score
    return None, 0


def _event_id(source_id: str, symbol: str, event_type: str, text: str) -> str:
    canonical = re.sub(r"\s+", " ", text.lower()).strip()[:500]
    return hashlib.sha256(f"{source_id}|{symbol}|{event_type}|{canonical}".encode()).hexdigest()[:24]


def _best_anchor(symbol: str, anchors: list[tuple[str, str]], broad_url: str) -> str:
    rx = re.compile(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", re.I)
    ranked = []
    for label, href in anchors:
        if not rx.search(label):
            continue
        low = (label + " " + href).lower()
        score = (3 if _classify(label, "ANCHOR")[0] else 0) + (2 if any(k in low for k in ("list", "announcement", "support", "notice", "article", "help")) else 0)
        ranked.append((score, href))
    return max(ranked, default=(0, broad_url))[1]


def _page_events(source_id: str, owner: str, url: str, universe: dict[str, dict]) -> tuple[list[dict], dict]:
    try:
        kind, payload = _get(url)
        raw = payload if kind == "html" else json.dumps(payload, ensure_ascii=False)
        text = _plain(raw) if kind == "html" else raw
        links = _anchors(raw, url) if kind == "html" else []
    except Exception as exc:
        return [], {"source": source_id, "owner": owner, "kind": "page", "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    events = []
    upper = text.upper()
    for symbol, candidate in universe.items():
        if len(symbol) < 3:
            continue
        for m in list(re.finditer(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", upper))[:4]:
            a, b = max(0, m.start() - 240), min(len(text), m.end() + 420)
            snippet = text[a:b]
            event_type, impact = _classify(snippet, source_id)
            if not event_type:
                continue
            direct = _best_anchor(symbol, links, url)
            events.append({
                "event_id": _event_id(source_id, symbol, event_type, snippet), "observed_at": _now(),
                "source_id": source_id, "source_owner": owner, "source_kind": "OFFICIAL_PAGE_OR_SOCIAL",
                "source_url": direct, "source_surface_url": url, "symbol": symbol,
                "event_type": event_type, "impact_score": impact, "excerpt": snippet[:520], "candidate": candidate,
            })
            break
    return events, {"source": source_id, "owner": owner, "kind": "page", "ok": True, "bytes": len(text), "events": len(events)}


def _announcement_api_events(source_id: str, owner: str, url: str, universe: dict[str, dict]) -> tuple[list[dict], dict]:
    try:
        _, payload = _get(url)
    except Exception as exc:
        return [], {"source": source_id, "owner": owner, "kind": "announcement_api", "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    rows = payload.get("data") or [] if isinstance(payload, dict) else []
    events = []
    for item in rows[:100] if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(k) or "") for k in ("annTitle", "annDesc", "title", "description"))
        for symbol, candidate in universe.items():
            if len(symbol) < 3 or not re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", text, re.I):
                continue
            event_type, impact = _classify(text, source_id)
            if not event_type:
                continue
            direct = str(item.get("annUrl") or item.get("url") or url)
            events.append({
                "event_id": _event_id(source_id, symbol, event_type, text), "observed_at": _now(),
                "source_id": source_id, "source_owner": owner, "source_kind": "OFFICIAL_ANNOUNCEMENT_API",
                "source_url": direct, "source_surface_url": url, "symbol": symbol, "event_type": event_type,
                "impact_score": impact, "excerpt": text[:520], "candidate": candidate,
            })
    return events, {"source": source_id, "owner": owner, "kind": "announcement_api", "ok": True, "rows": len(rows) if isinstance(rows, list) else 0, "events": len(events)}


def _rows_from_api(source_id: str, payload: Any) -> list[dict]:
    if source_id.startswith("GATE_") and isinstance(payload, list):
        return [{"symbol": x.get("id"), "state": x.get("trade_status"), "start": x.get("buy_start"), "type": x.get("type"), "raw": x} for x in payload if isinstance(x, dict)]
    if source_id.startswith("OKX_") and isinstance(payload, dict):
        return [{"symbol": x.get("instId"), "state": x.get("state"), "start": x.get("listTime"), "type": x.get("instType"), "raw": x} for x in payload.get("data") or [] if isinstance(x, dict)]
    if source_id.startswith("KUCOIN_") and isinstance(payload, dict):
        return [{"symbol": x.get("symbol"), "state": "enable" if x.get("enableTrading") else "preopen", "start": x.get("tradingStartTime"), "type": "call_auction" if x.get("callauctionIsEnabled") else "spot", "raw": x} for x in payload.get("data") or [] if isinstance(x, dict)]
    if source_id.startswith("BYBIT_") and isinstance(payload, dict):
        return [{"symbol": x.get("symbol"), "state": x.get("status"), "start": x.get("launchTime"), "type": "spot", "raw": x} for x in ((payload.get("result") or {}).get("list") or []) if isinstance(x, dict)]
    if source_id.startswith("BITGET_") and isinstance(payload, dict):
        return [{"symbol": x.get("symbol"), "state": x.get("status"), "start": x.get("openTime") or x.get("launchTime"), "type": "spot", "raw": x} for x in payload.get("data") or [] if isinstance(x, dict)]
    if source_id == "COINBASE_PRODUCTS" and isinstance(payload, list):
        return [{"symbol": x.get("id"), "state": x.get("status"), "start": None, "type": "spot", "raw": x} for x in payload if isinstance(x, dict)]
    if source_id == "LBANK_SPOT_INSTRUMENTS" and isinstance(payload, dict):
        return [{"symbol": x, "state": "listed", "start": None, "type": "spot", "raw": x} for x in (payload.get("data") or [])]
    if source_id == "WEEX_SPOT_INSTRUMENTS" and isinstance(payload, dict):
        block = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        return [{"symbol": x.get("symbol"), "state": x.get("status"), "start": None, "type": "spot", "raw": x} for x in (block.get("symbols") or []) if isinstance(x, dict)]
    return []


def _api_events(source_id: str, owner: str, url: str, universe: dict[str, dict], source_state: dict) -> tuple[list[dict], dict, dict]:
    try:
        _, payload = _get(url)
        rows = _rows_from_api(source_id, payload)
    except Exception as exc:
        return [], {"source": source_id, "owner": owner, "kind": "api", "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}, source_state
    snapshot = {}
    for row in rows:
        base = _norm_symbol(row.get("symbol"))
        if base:
            snapshot[base] = {"state": row.get("state"), "start": row.get("start"), "type": row.get("type")}
    previous = source_state.get("snapshot") if isinstance(source_state.get("snapshot"), dict) else None
    if previous is None:
        return [], {"source": source_id, "owner": owner, "kind": "api", "ok": True, "rows": len(rows), "baseline": True, "events": 0}, {"snapshot": snapshot, "baseline_at": _now()}
    events = []
    for symbol, cur in snapshot.items():
        candidate, prev = universe.get(symbol), previous.get(symbol)
        if not candidate or (prev is not None and prev == cur):
            continue
        state, typ, start = str(cur.get("state") or "").lower(), str(cur.get("type") or "").lower(), cur.get("start")
        if typ in {"premarket", "call_auction"} or state in {"preopen", "pendingopen", "prelaunch", "init"}:
            event_type, impact = "PREMARKET_OR_AUCTION", 94
        elif "swap" in typ or "future" in typ:
            event_type, impact = "FUTURES_LISTING", 86
        else:
            event_type, impact = "SPOT_LISTING_EXPECTED", 100
        text = f"{source_id} instrument change {symbol} state={state} type={typ} start={start}"
        events.append({
            "event_id": _event_id(source_id, symbol, event_type, text), "observed_at": _now(),
            "source_id": source_id, "source_owner": owner, "source_kind": "OFFICIAL_MACHINE_STATE",
            "source_url": url, "symbol": symbol, "event_type": event_type, "impact_score": impact,
            "excerpt": text, "candidate": candidate, "machine_state": cur,
        })
    return events, {"source": source_id, "owner": owner, "kind": "api", "ok": True, "rows": len(rows), "events": len(events)}, {"snapshot": snapshot, "updated_at": _now()}


def _social_catalyst_events(universe: dict[str, dict]) -> tuple[list[dict], dict]:
    payload = _load(DATA / "social-intelligence-v2.json", {})
    events = []
    for row in payload.get("tokens") or [] if isinstance(payload, dict) else []:
        if not isinstance(row, dict):
            continue
        symbol = _norm_symbol(row.get("symbol"))
        candidate = universe.get(symbol)
        if not candidate:
            continue
        cats = row.get("catalysts") if isinstance(row.get("catalysts"), dict) else {}
        for item in (cats.get("positive") or [])[:10]:
            text = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
            event_type, impact = _classify(text, "PROJECT_OFFICIAL_SOCIAL")
            if not event_type:
                continue
            direct = item.get("url") if isinstance(item, dict) else None
            events.append({
                "event_id": _event_id("PROJECT_OFFICIAL_SOCIAL", symbol, event_type, text), "observed_at": _now(),
                "source_id": "PROJECT_OFFICIAL_SOCIAL", "source_owner": symbol,
                "source_kind": "EXISTING_VERIFIED_SOCIAL_ENGINE", "source_url": direct, "symbol": symbol,
                "event_type": event_type, "impact_score": impact, "excerpt": text[:520], "candidate": candidate,
            })
    return events, {"source": "PROJECT_OFFICIAL_SOCIAL", "kind": "internal", "ok": True, "events": len(events)}


def _decorate(event: dict) -> dict:
    c = event.get("candidate") if isinstance(event.get("candidate"), dict) else {}
    e = dict(event)
    e["preliminary_filter_pass"] = c.get("preliminary_filter_pass") is True
    e["contract"] = c.get("token")
    e["chain"] = c.get("chain")
    e["dex_url"] = c.get("dex_url") or c.get("url")
    e["market_age_days"] = c.get("market_age_days")
    e["ignored_for_event_lane"] = ["volume_acceleration", "liquidity_growth", "holder_growth", "wallet_growth"]
    e.pop("candidate", None)
    return e


def _telegram_send(text: str) -> tuple[bool, str]:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "TELEGRAM_SECRETS_MISSING"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8"))
        return bool(payload.get("ok")), "OK" if payload.get("ok") else "API_OK_FALSE"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:220]


def _message(e: dict) -> str:
    lines = [
        "⚡ WALLET500 · CATALYST WIRE", "🆕 OFFICIAL EVENT ALERT",
        f"Token: {e.get('symbol')} | {str(e.get('chain') or 'unknown').upper()}",
        f"Event: {e.get('event_type')} · impact {e.get('impact_score')}/100",
        f"Source: {e.get('source_owner')} / {e.get('source_id')}",
        f"Detected UTC: {e.get('observed_at') or _now()}",
        "✅ Preliminary filter: PASS (identity / safety / veteran-age lane)",
        "⏭ Volume, liquidity growth, holder growth, wallet growth: ZERO WEIGHT",
        "⚠️ Intelligence alert only — manual decision, no automatic trade",
    ]
    if e.get("contract"):
        lines.append(f"Contract: {e.get('contract')}")
    if e.get("source_url"):
        lines.append(f"🔗 Official source: {e.get('source_url')}")
    if e.get("dex_url"):
        lines.append(f"🔗 DEX: {e.get('dex_url')}")
    return "\n".join(lines)


def run() -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    universe = _candidate_universe()
    state = _load(STATE, {"version": 1, "sources": {}, "alerted": {}})
    if not isinstance(state, dict):
        state = {"version": 1, "sources": {}, "alerted": {}}
    source_states = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    alerted = state.get("alerted") if isinstance(state.get("alerted"), dict) else {}
    seen_before = state.get("seen_event_ids") if isinstance(state.get("seen_event_ids"), dict) else None
    first_global_baseline = seen_before is None
    seen_before = seen_before or {}

    events, health = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for sid, owner, url in PAGE_SOURCES:
            futures[pool.submit(_page_events, sid, owner, url, universe)] = ("page", sid)
        for sid, owner, url in ANNOUNCEMENT_API_SOURCES:
            futures[pool.submit(_announcement_api_events, sid, owner, url, universe)] = ("announcement_api", sid)
        for fut in as_completed(futures):
            try:
                got, h = fut.result()
                events.extend(got)
                health.append(h)
            except Exception as exc:
                kind, sid = futures[fut]
                health.append({"source": sid, "kind": kind, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_meta = {}
        for sid, owner, url in API_SOURCES:
            f = pool.submit(_api_events, sid, owner, url, universe, source_states.get(sid) or {})
            future_meta[f] = (sid, owner)
        for fut in as_completed(future_meta):
            sid, owner = future_meta[fut]
            try:
                got, h, new_state = fut.result()
                events.extend(got)
                health.append(h)
                source_states[sid] = new_state
            except Exception as exc:
                health.append({"source": sid, "owner": owner, "kind": "api", "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})

    got, h = _social_catalyst_events(universe)
    events.extend(got)
    health.append(h)
    health.append({
        "source": "UPBIT_ANNOUNCEMENT_WEBSOCKET", "owner": "upbit", "kind": "realtime_websocket",
        "ok": False, "status": "NEEDS_PERSISTENT_AUTHENTICATED_RUNTIME",
        "endpoint_class": "wss://{region}-api.upbit.com/websocket/v1/private", "category": "trade",
    })

    dedup = {}
    for raw in events:
        e = _decorate(raw)
        old = dedup.get(e["event_id"])
        if old is None or int(e.get("impact_score") or 0) > int(old.get("impact_score") or 0):
            dedup[e["event_id"]] = e
    events = sorted(dedup.values(), key=lambda x: int(x.get("impact_score") or 0), reverse=True)

    now = _now()
    for e in events:
        e["forward_new"] = (not first_global_baseline) and e["event_id"] not in seen_before
        e["alert_eligible"] = bool(e.get("preliminary_filter_pass") and e.get("source_url") and e.get("forward_new"))

    delivered, delivery_errors = [], []
    for e in events:
        if not e.get("alert_eligible") or e["event_id"] in alerted:
            continue
        ok, detail = _telegram_send(_message(e))
        if ok:
            alerted[e["event_id"]] = {"sent_at": now, "symbol": e.get("symbol"), "event_type": e.get("event_type"), "source_url": e.get("source_url")}
            delivered.append(e["event_id"])
        elif detail != "TELEGRAM_SECRETS_MISSING":
            delivery_errors.append({"event_id": e["event_id"], "error": detail})

    records = (_load(LEDGER, {"events": {}}).get("events") or {})
    for e in events:
        rec = records.get(e["event_id"]) or {"first_seen_at": now}
        rec["last_seen_at"] = now
        rec["event"] = e
        records[e["event_id"]] = rec
    if len(records) > 5000:
        records = dict(sorted(records.items(), key=lambda kv: kv[1].get("last_seen_at") or "", reverse=True)[:5000])
    _write(LEDGER, {"version": 1, "updated_at": now, "mode": "FORWARD_ONLY_OFFICIAL_CATALYST_LEDGER", "events": records})

    all_seen = dict(seen_before)
    for e in events:
        all_seen[e["event_id"]] = all_seen.get(e["event_id"]) or now
    if len(all_seen) > 10000:
        all_seen = dict(list(all_seen.items())[-10000:])

    health.sort(key=lambda x: (not bool(x.get("ok")), str(x.get("source"))))
    payload = {
        "version": 2, "updated_at": now, "mode": "CATALYST_WIRE_EVENT_FIRST_NO_MOMENTUM_WEIGHT",
        "automatic_trade": False,
        "policy": {
            "preliminary_filter": "exact identity + current Wallet500 universe + no hard risk block + veteran age when known",
            "event_lane_zero_weight": ["volume_acceleration", "liquidity_growth", "holder_growth", "wallet_growth"],
            "official_source_required": True, "source_link_required_for_telegram": True,
            "first_run_is_baseline_no_historical_telegram": True, "trade_execution": "MANUAL_ONLY",
        },
        "counts": {
            "candidate_universe": len(universe), "preliminary_pass": sum(1 for x in universe.values() if x.get("preliminary_filter_pass")),
            "sources": len(health), "sources_healthy": sum(1 for x in health if x.get("ok")), "events_visible": len(events),
            "forward_new": sum(1 for x in events if x.get("forward_new")), "alert_eligible": sum(1 for x in events if x.get("alert_eligible")),
            "telegram_delivered_this_run": len(delivered),
        },
        "source_health": health, "events": events[:300], "telegram": {"delivered": delivered, "errors": delivery_errors},
        "research_source_classes": [
            "exchange machine state / instrument provisioning", "pre-market and call-auction state",
            "official exchange announcement APIs/pages", "official exchange Telegram surfaces",
            "exchange listing roadmaps", "existing Wallet500 verified project social catalysts",
        ],
    }
    _write(OUT, payload)
    state.update({"version": 2, "updated_at": now, "sources": source_states, "alerted": alerted, "seen_event_ids": all_seen})
    _write(STATE, state)
    print("CATALYST_WIRE", json.dumps(payload["counts"], separators=(",", ":")))
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
