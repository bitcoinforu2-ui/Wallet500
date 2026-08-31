from __future__ import annotations

import json
import math
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from .revival_1000 import looks_like_solana_address

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
HOLDER_EVIDENCE = DATA / "hybrid-external-evidence.json"
LATEST = DATA / "waking-confirmation-latest.json"
STATE = DATA / "waking-confirmation-state.json"

MODE = "RESEARCH_ONLY_WAKING_CONFIRMATION_V1"
CONTRACT = "WAKING_CONFIRMATION_V1"
NETWORK = "solana"
WAKING_STATUS = "WAKING_MARKET_ONLY"

POSITIVE_CATALYSTS = (
    "listing", "listed", "partnership", "partner", "integration", "launch",
    "mainnet", "buyback", "burn", "staking", "upgrade", "release", "airdrop",
    "roadmap", "governance", "exchange", "funding", "adoption",
)
NEGATIVE_CATALYSTS = (
    "hack", "hacked", "exploit", "breach", "delist", "delisting", "lawsuit",
    "investigation", "unlock", "rug", "scam", "shutdown", "migration issue",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _n(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _pct(cur, prev):
    cur = _n(cur)
    prev = _n(prev)
    if cur is None or prev in (None, 0):
        return None
    return (cur / prev - 1.0) * 100.0


def _get_json(url: str, headers: dict | None = None, timeout: int = 18):
    req = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Wallet500-Waking/1.0", **(headers or {})},
    )
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_text(url: str, headers: dict | None = None, timeout: int = 18) -> str:
    req = Request(
        url,
        headers={"Accept": "*/*", "User-Agent": "Wallet500-Waking/1.0", **(headers or {})},
    )
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return "NETWORK_UNAVAILABLE"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _unwrap_data(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _flatten(obj, prefix="") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(_flatten(v, key))
            elif not isinstance(v, list):
                out[key] = v
    return out


def _find_num(flat: dict[str, object], suffixes: list[str]):
    lowered = {str(k).lower(): v for k, v in flat.items()}
    for suffix in [x.lower() for x in suffixes]:
        for key, value in lowered.items():
            if key == suffix or key.endswith("." + suffix) or key.endswith(suffix):
                x = _n(value)
                if x is not None:
                    return x
    return None


def extract_birdeye_overview_metrics(payload: dict) -> dict:
    data = _unwrap_data(payload)
    flat = _flatten(data if isinstance(data, dict) else {})
    out = {
        "holder_count": _find_num(flat, ["holder", "holders", "holderCount", "holder_count"]),
    }
    for frame in ("1h", "4h", "24h"):
        compact = frame.lower()
        out[f"unique_wallet_{frame}"] = _find_num(
            flat,
            [f"uniqueWallet{compact}", f"unique_wallet_{compact}"],
        )
        out[f"unique_wallet_change_{frame}_pct"] = _find_num(
            flat,
            [
                f"uniqueWallet{compact}ChangePercent",
                f"unique_wallet_{compact}_change_percent",
                f"uniqueWallet{compact}ChangePct",
            ],
        )
    return out


def score_holder_growth(current, previous) -> tuple[float, list[str], float | None]:
    change = _pct(current, previous)
    if change is None:
        return 0.0, ["HOLDER_BASELINE_LEARNING"], None
    score = 0.0
    signals = [f"HOLDER_CHANGE_{change:+.3f}PCT"]
    if change >= 0.25:
        score += 30; signals.append("HOLDER_GROWTH_GE_0_25PCT")
    if change >= 1.0:
        score += 25; signals.append("HOLDER_GROWTH_GE_1PCT")
    if change >= 3.0:
        score += 25; signals.append("HOLDER_GROWTH_GE_3PCT")
    if change >= 7.5:
        score += 20; signals.append("HOLDER_GROWTH_GE_7_5PCT")
    if change <= -1.0:
        signals.append("HOLDER_CONTRACTION_GE_1PCT")
    return min(100.0, score), signals, round(change, 4)


def score_wallet_growth(metrics: dict) -> tuple[float, list[str]]:
    score = 0.0
    signals: list[str] = []
    for frame, weight in (("1h", 45.0), ("4h", 30.0), ("24h", 25.0)):
        change = _n(metrics.get(f"unique_wallet_change_{frame}_pct"))
        if change is None:
            continue
        signals.append(f"UNIQUE_WALLET_{frame.upper()}_CHANGE_{change:+.2f}PCT")
        if change >= 10:
            score += weight * 0.45
        if change >= 25:
            score += weight * 0.35
        if change >= 50:
            score += weight * 0.20
    return min(100.0, score), signals


def _scan_birdeye(address: str, state_row: dict, observed_at: str):
    key = (os.getenv("BIRDEYE_API_KEY") or "").strip()
    if not key:
        return None, None, state_row, {"provider": "birdeye", "status": "NOT_CONFIGURED"}
    headers = {"X-API-KEY": key, "x-chain": "solana"}
    q = urlencode({"address": address, "frames": "1h,4h,24h", "ui_amount_mode": "raw"})
    try:
        payload = _get_json("https://public-api.birdeye.so/defi/token_overview?" + q, headers=headers)
        metrics = extract_birdeye_overview_metrics(payload)
    except Exception as exc:
        return None, None, state_row, {"provider": "birdeye", "status": _safe_error(exc)}

    current = metrics.get("holder_count")
    previous = state_row.get("holder_count")
    holder_score, holder_signals, holder_change = score_holder_growth(current, previous)
    holders = None
    if current is not None:
        holders = {
            "available": True,
            "verified": True,
            "source": "BIRDEYE_TOKEN_OVERVIEW_EXACT_MINT",
            "observed_at": observed_at,
            "score": round(holder_score, 2),
            "signals": holder_signals,
            "metrics": {
                "holder_count": int(current),
                "previous_holder_count": int(previous) if _n(previous) is not None else None,
                "holder_change_pct": holder_change,
            },
        }

    wallet_score, wallet_signals = score_wallet_growth(metrics)
    wallet_available = any(metrics.get(f"unique_wallet_{f}") is not None for f in ("1h", "4h", "24h"))
    wallets = None
    if wallet_available:
        wallets = {
            "available": True,
            "verified": True,
            "source": "BIRDEYE_TOKEN_OVERVIEW_EXACT_MINT",
            "observed_at": observed_at,
            "score": round(wallet_score, 2),
            "signals": wallet_signals,
            "metrics": {k: v for k, v in metrics.items() if k.startswith("unique_wallet_")},
        }

    state_row = dict(state_row)
    if current is not None:
        state_row["holder_count"] = int(current)
    for k, v in metrics.items():
        if k.startswith("unique_wallet_") and v is not None:
            state_row[k] = v
    state_row["birdeye_observed_at"] = observed_at
    return holders, wallets, state_row, {"provider": "birdeye", "status": "OK"}


def _identity(coin: dict) -> tuple[dict, list[dict]]:
    pair = str(coin.get("dex_pair_address") or "")
    identity = {
        "token_address": coin.get("token_address"),
        "symbol": coin.get("symbol"),
        "name": coin.get("name"),
        "coingecko_id": coin.get("id"),
        "official_x": None,
        "official_telegram": None,
        "official_discord": None,
        "official_website": None,
        "official_reddit": None,
        "github_repos": [],
    }
    statuses: list[dict] = []

    if looks_like_solana_address(pair):
        try:
            payload = _get_json(f"https://api.dexscreener.com/latest/dex/pairs/solana/{quote(pair)}")
            pairs = payload.get("pairs") or []
            exact = next((x for x in pairs if str(x.get("pairAddress") or "") == pair), pairs[0] if pairs else {})
            info = exact.get("info") or {}
            sites = [str((x or {}).get("url") or "") for x in (info.get("websites") or [])]
            identity["official_website"] = next((x for x in sites if x), None)
            for row in info.get("socials") or []:
                kind = str((row or {}).get("type") or "").lower()
                url = str((row or {}).get("url") or "")
                if kind in {"twitter", "x"} and url:
                    identity["official_x"] = url
                elif kind == "telegram" and url:
                    identity["official_telegram"] = url
                elif kind == "discord" and url:
                    identity["official_discord"] = url
            statuses.append({"provider": "dexscreener_identity", "status": "OK"})
        except Exception as exc:
            statuses.append({"provider": "dexscreener_identity", "status": _safe_error(exc)})

    coin_id = str(coin.get("id") or "")
    if coin_id:
        headers = {}
        cg_key = (os.getenv("COINGECKO_DEMO_API_KEY") or "").strip()
        if cg_key:
            headers["x-cg-demo-api-key"] = cg_key
        try:
            qs = "localization=false&tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false"
            payload = _get_json(f"https://api.coingecko.com/api/v3/coins/{quote(coin_id)}?{qs}", headers=headers)
            links = payload.get("links") or {}
            homes = [x for x in (links.get("homepage") or []) if x]
            if homes and not identity["official_website"]:
                identity["official_website"] = homes[0]
            tw = str(links.get("twitter_screen_name") or "").strip()
            tg = str(links.get("telegram_channel_identifier") or "").strip()
            if tw and not identity["official_x"]:
                identity["official_x"] = "https://x.com/" + tw.lstrip("@")
            if tg and not identity["official_telegram"]:
                identity["official_telegram"] = "https://t.me/" + tg.lstrip("@")
            identity["official_reddit"] = links.get("subreddit_url") or None
            identity["github_repos"] = [
                str(x) for x in (((links.get("repos_url") or {}).get("github")) or []) if x
            ][:5]
            statuses.append({"provider": "coingecko_identity", "status": "OK"})
        except Exception as exc:
            statuses.append({"provider": "coingecko_identity", "status": _safe_error(exc)})
    return identity, statuses


def _x_handle(url: str | None) -> str | None:
    if not url:
        return None
    try:
        path = urlparse(url).path.strip("/")
        return path.split("/")[0] if path else None
    except Exception:
        return None


def _broad_query(identity: dict) -> str:
    name = str(identity.get("name") or "").strip()
    symbol = str(identity.get("symbol") or "").strip().lstrip("$")
    parts = [f'"{name}"'] if name else []
    if symbol and len(symbol) >= 3:
        parts.append(f'"${symbol}"')
    return " OR ".join(parts[:2]) or str(identity.get("token_address") or "")


def _scan_x(identity: dict):
    token = (os.getenv("X_BEARER_TOKEN") or "").strip()
    if not token:
        return [], {"provider": "x", "status": "NOT_CONFIGURED"}
    mint = str(identity.get("token_address") or "")
    handle = _x_handle(identity.get("official_x"))
    parts = [mint]
    if handle:
        parts.append(f"from:{handle}")
    else:
        parts.append(_broad_query(identity))
    params = urlencode({
        "query": "(" + " OR ".join(parts) + ") -is:retweet",
        "max_results": 10,
        "tweet.fields": "created_at,public_metrics,author_id",
    })
    try:
        payload = _get_json(
            "https://api.x.com/2/tweets/search/recent?" + params,
            headers={"Authorization": "Bearer " + token},
        )
        rows = []
        for x in payload.get("data") or []:
            pm = x.get("public_metrics") or {}
            rows.append({
                "source": "x",
                "id": x.get("id"),
                "author": x.get("author_id"),
                "published_at": x.get("created_at"),
                "text": str(x.get("text") or "")[:1000],
                "engagement": sum(_n(pm.get(k), 0) or 0 for k in ("like_count", "retweet_count", "reply_count", "quote_count")),
            })
        return rows, {"provider": "x", "status": "OK", "count": len(rows)}
    except Exception as exc:
        return [], {"provider": "x", "status": _safe_error(exc)}


def _scan_youtube(identity: dict):
    key = (os.getenv("YOUTUBE_API_KEY") or "").strip()
    if not key:
        return [], {"provider": "youtube", "status": "NOT_CONFIGURED"}
    params = urlencode({
        "part": "snippet",
        "type": "video",
        "order": "date",
        "maxResults": 10,
        "q": _broad_query(identity),
        "key": key,
    })
    try:
        payload = _get_json("https://www.googleapis.com/youtube/v3/search?" + params)
        rows = []
        for x in payload.get("items") or []:
            sn = x.get("snippet") or {}
            vid = (x.get("id") or {}).get("videoId")
            rows.append({
                "source": "youtube",
                "id": vid,
                "author": sn.get("channelTitle"),
                "published_at": sn.get("publishedAt"),
                "text": f"{sn.get('title') or ''} {sn.get('description') or ''}"[:1000],
                "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
            })
        return rows, {"provider": "youtube", "status": "OK", "count": len(rows)}
    except Exception as exc:
        return [], {"provider": "youtube", "status": _safe_error(exc)}


def _scan_reddit(identity: dict):
    params = urlencode({"q": _broad_query(identity), "sort": "new", "t": "day", "limit": 15, "raw_json": 1})
    try:
        payload = _get_json("https://www.reddit.com/search.json?" + params)
        rows = []
        for child in (((payload.get("data") or {}).get("children")) or []):
            d = (child or {}).get("data") or {}
            rows.append({
                "source": "reddit",
                "id": d.get("id"),
                "author": d.get("author"),
                "published_at": d.get("created_utc"),
                "text": f"{d.get('title') or ''} {d.get('selftext') or ''}"[:1000],
                "engagement": (_n(d.get("score"), 0) or 0) + (_n(d.get("num_comments"), 0) or 0),
                "url": "https://www.reddit.com" + str(d.get("permalink") or ""),
            })
        return rows, {"provider": "reddit", "status": "OK", "count": len(rows)}
    except Exception as exc:
        return [], {"provider": "reddit", "status": _safe_error(exc)}


def _scan_news(identity: dict):
    name = str(identity.get("name") or "").strip()
    symbol = str(identity.get("symbol") or "").strip().lstrip("$")
    if not name:
        return [], {"provider": "google_news_rss", "status": "NO_NAME"}
    q = f'"{name}" crypto OR token'
    if symbol and len(symbol) >= 3:
        q += f' OR "${symbol}"'
    q += " when:1d"
    url = "https://news.google.com/rss/search?" + urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    try:
        root = ET.fromstring(_get_text(url))
        rows = []
        for item in root.findall(".//item")[:20]:
            src = item.find("source")
            rows.append({
                "source": "news",
                "id": item.findtext("link"),
                "author": src.text if src is not None else None,
                "published_at": item.findtext("pubDate"),
                "text": (item.findtext("title") or "")[:1000],
                "url": item.findtext("link"),
            })
        return rows, {"provider": "google_news_rss", "status": "OK", "count": len(rows)}
    except Exception as exc:
        return [], {"provider": "google_news_rss", "status": _safe_error(exc)}


def _dedupe(rows: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        key = (row.get("source"), row.get("id") or row.get("url") or row.get("text"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def score_social(rows: list[dict], previous_count: int | None) -> tuple[float, list[str]]:
    sources = {str(x.get("source")) for x in rows if x.get("source")}
    authors = {str(x.get("author")) for x in rows if x.get("author")}
    count = len(rows)
    score = min(45.0, len(sources) * 15.0) + min(25.0, len(authors) * 5.0)
    signals = [f"SOCIAL_MENTIONS_{count}", f"SOCIAL_SOURCES_{len(sources)}", f"SOCIAL_AUTHORS_{len(authors)}"]
    if previous_count and previous_count > 0:
        ratio = count / previous_count
        signals.append(f"SOCIAL_COUNT_VS_PREVIOUS_{ratio:.2f}X")
        if ratio >= 2:
            score += 20
        if ratio >= 4:
            score += 10
    elif count:
        signals.append("SOCIAL_BASELINE_LEARNING")
    return min(100.0, score), signals


def score_news(rows: list[dict], previous_count: int | None) -> tuple[float, list[str], list[str]]:
    sources = {str(x.get("author")) for x in rows if x.get("author")}
    catalysts = set()
    for row in rows:
        text = str(row.get("text") or "").lower()
        catalysts.update(x for x in (*POSITIVE_CATALYSTS, *NEGATIVE_CATALYSTS) if x in text)
    score = min(45.0, len(rows) * 8.0) + min(25.0, len(sources) * 8.0)
    if catalysts:
        score += min(30.0, len(catalysts) * 10.0)
    signals = [f"NEWS_ITEMS_{len(rows)}", f"NEWS_SOURCES_{len(sources)}"]
    if catalysts:
        signals.append("CATALYST_KEYWORDS:" + ",".join(sorted(catalysts)[:8]))
    if previous_count and previous_count > 0:
        ratio = len(rows) / previous_count
        signals.append(f"NEWS_COUNT_VS_PREVIOUS_{ratio:.2f}X")
        if ratio >= 2:
            score += 10
    return min(100.0, score), signals, sorted(catalysts)


def _latest_distribution() -> dict[str, dict]:
    payload = _load(HOLDER_EVIDENCE, {})
    out = {}
    for row in payload.get("observations") or []:
        if not isinstance(row, dict):
            continue
        address = str(row.get("token_address") or "")
        holders = row.get("holders") or {}
        if looks_like_solana_address(address) and holders.get("verified") is True:
            out[address] = holders
    return out


def confirmation_status(channels: dict, distribution: dict | None) -> tuple[str, float, list[str]]:
    weights = {"holders": 25.0, "wallets": 25.0, "social": 20.0, "news": 15.0, "distribution": 15.0}
    score = 0.0
    strong = []
    for name in ("holders", "wallets", "social", "news"):
        ch = channels.get(name)
        if isinstance(ch, dict) and ch.get("verified") is True:
            s = max(0.0, min(100.0, _n(ch.get("score"), 0) or 0))
            score += weights[name] * s / 100.0
            if s >= 55:
                strong.append(name)
    risk = _n((distribution or {}).get("risk_score"))
    if risk is not None:
        dist_score = max(0.0, 100.0 - risk)
        score += weights["distribution"] * dist_score / 100.0
        if dist_score >= 70:
            strong.append("distribution")
    if risk is not None and risk >= 50:
        return "WAKING_RISK_RESEARCH", round(score, 2), strong
    if len(set(strong)) >= 3 and score >= 45:
        return "WAKING_STRONG_RESEARCH", round(score, 2), strong
    if len(set(strong)) >= 2 and score >= 30:
        return "WAKING_CONFIRMED_RESEARCH", round(score, 2), strong
    return "WAKING_UNCONFIRMED_RESEARCH", round(score, 2), strong


def run() -> dict:
    observed_at = now_iso()
    source = _load(REVIVAL, {})
    if source.get("network") != NETWORK or source.get("production_portfolio_impact") != "NONE":
        raise RuntimeError("WAKING_SOURCE_TRUTH_CONTRACT_REJECTED")
    targets = [
        x for x in (source.get("coins") or [])
        if isinstance(x, dict)
        and x.get("watch_status") == WAKING_STATUS
        and looks_like_solana_address(str(x.get("token_address") or ""))
    ]
    targets.sort(key=lambda x: _n(x.get("revival_score_verified"), 0) or 0, reverse=True)

    state = _load(STATE, {"version": 1, "tokens": {}})
    token_state = state.setdefault("tokens", {})
    distribution = _latest_distribution()
    rows = []
    provider_counts: dict[str, int] = {}

    for coin in targets:
        address = str(coin.get("token_address"))
        st = dict(token_state.get(address) or {})
        identity, statuses = _identity(coin)
        holders, wallets, st, birdeye_status = _scan_birdeye(address, st, observed_at)
        statuses.append(birdeye_status)

        social_events = []
        for scanner in (_scan_x, _scan_youtube, _scan_reddit):
            events, provider = scanner(identity)
            social_events.extend(events)
            statuses.append(provider)
        news_events, news_provider = _scan_news(identity)
        statuses.append(news_provider)
        social_events = _dedupe(social_events)
        news_events = _dedupe(news_events)

        social_score, social_signals = score_social(social_events, st.get("social_mentions"))
        news_score, news_signals, catalysts = score_news(news_events, st.get("news_items"))
        social_verified = any(
            x.get("status") == "OK" and x.get("provider") in {"x", "youtube", "reddit"}
            for x in statuses
        )
        news_verified = news_provider.get("status") == "OK"

        social = {
            "available": social_verified,
            "verified": social_verified,
            "source": "WAKING_SOCIAL_MULTI_SOURCE_SCAN_V1" if social_verified else "NOT_CONNECTED",
            "observed_at": observed_at,
            "score": round(social_score, 2) if social_verified else 0.0,
            "signals": social_signals if social_verified else [],
            "metrics": {
                "mentions": len(social_events),
                "sources": len({x.get("source") for x in social_events if x.get("source")}),
                "authors": len({x.get("author") for x in social_events if x.get("author")}),
            },
            "events": social_events[:30],
        }
        news = {
            "available": news_verified,
            "verified": news_verified,
            "source": "GOOGLE_NEWS_RSS_IDENTITY_QUERY" if news_verified else "UNAVAILABLE",
            "observed_at": observed_at,
            "score": round(news_score, 2) if news_verified else 0.0,
            "signals": news_signals if news_verified else [],
            "metrics": {"items": len(news_events), "catalyst_keywords": catalysts},
            "events": news_events[:20],
        }

        channels = {
            "holders": holders or {"available": False, "verified": False, "score": 0.0, "source": "NOT_CONNECTED"},
            "wallets": wallets or {"available": False, "verified": False, "score": 0.0, "source": "NOT_CONNECTED"},
            "social": social,
            "news": news,
        }
        status, score, strong = confirmation_status(channels, distribution.get(address))

        st["identity"] = identity
        st["social_mentions"] = len(social_events)
        st["news_items"] = len(news_events)
        st["last_observed_at"] = observed_at
        token_state[address] = st

        for p in statuses:
            key = f"{p.get('provider')}:{p.get('status')}"
            provider_counts[key] = provider_counts.get(key, 0) + 1

        rows.append({
            "network": NETWORK,
            "token_address": address,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "base_watch_status": WAKING_STATUS,
            "revival_score_verified": coin.get("revival_score_verified"),
            "confirmation_status": status,
            "confirmation_score": score,
            "strong_families": strong,
            "identity": identity,
            "channels": channels,
            "distribution_evidence": distribution.get(address),
            "provider_status": statuses,
            "production_portfolio_impact": "NONE",
        })
        time.sleep(0.08)

    state.update({"version": 1, "updated_at": observed_at, "tokens": token_state})
    _write(STATE, state)
    payload = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "network": NETWORK,
        "generated_at": observed_at,
        "source_generated_at": source.get("generated_at"),
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "rules": [
            "WAKING_MARKET_ONLY remains unchanged; this layer only adds confirmation evidence",
            "only exact-mint holder/wallet data may score",
            "unconfigured/failed providers remain unavailable and never become positive evidence",
            "social/news activity measures attention/catalysts and is not directional price proof",
            "confirmation statuses are research-only and cannot promote PRE-ALPHA",
        ],
        "counts": {
            "waking_targets": len(rows),
            "confirmed": sum(1 for x in rows if x["confirmation_status"] == "WAKING_CONFIRMED_RESEARCH"),
            "strong": sum(1 for x in rows if x["confirmation_status"] == "WAKING_STRONG_RESEARCH"),
            "risk": sum(1 for x in rows if x["confirmation_status"] == "WAKING_RISK_RESEARCH"),
            "unconfirmed": sum(1 for x in rows if x["confirmation_status"] == "WAKING_UNCONFIRMED_RESEARCH"),
        },
        "provider_status_counts": provider_counts,
        "targets": rows,
    }
    _write(LATEST, payload)
    print("WAKING_CONFIRMATION_V1_OK", payload["counts"], provider_counts)
    return payload


if __name__ == "__main__":
    run()
