from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    import resilient_http
except ImportError:  # package import in pytest / module mode
    from scripts import resilient_http

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
DYNAMIC = ROOT / "data/unified-dynamic-candidates.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/cross-domain-intelligence-state.json"
UA = "Wallet500-CrossDomain/1.0"

ALIASES = {"eth": "ethereum", "bnb": "bsc"}
EVM = {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
GT_NET = {
    "ethereum": "eth",
    "bsc": "bsc",
    "base": "base",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon_pos",
    "avalanche": "avax",
    "solana": "solana",
    "arc": "arc",
}
BLOCKSCOUT = {
    "ethereum": "https://eth.blockscout.com",
    "base": "https://base.blockscout.com",
    "arbitrum": "https://arbitrum.blockscout.com",
    "optimism": "https://optimism.blockscout.com",
    "polygon": "https://polygon.blockscout.com",
    "bsc": "https://bsc.blockscout.com",
}
NEWS_POSITIVE = re.compile(r"\b(list(?:ed|ing)|launch(?:ed)?|partnership|integrat(?:e|ion)|upgrade|approval|funding|mainnet|buyback|burn)\b", re.I)
NEWS_NEGATIVE = re.compile(r"\b(hack(?:ed)?|exploit|breach|delist(?:ed|ing)|lawsuit|investigation|attack|drain|rug|scam)\b", re.I)
CRYPTO_CONTEXT = re.compile(r"\b(crypto|cryptocurrency|blockchain|token|coin|defi|web3|exchange)\b", re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def get_json(url, timeout=7):
    try:
        return resilient_http.request_json(
            url,
            timeout=timeout,
            attempts=4,
            cache_ttl=45,
            user_agent=UA,
        )
    except Exception:
        return None


def get_text(url, timeout=7):
    try:
        return resilient_http.request_text(
            url,
            timeout=timeout,
            attempts=4,
            cache_ttl=90,
            user_agent=UA,
            accept="application/rss+xml,text/xml,*/*",
        )
    except Exception:
        return None


def post_json(url, payload, timeout=7):
    try:
        return resilient_http.request_json(
            url,
            method="POST",
            payload=payload,
            timeout=timeout,
            attempts=4,
            user_agent=UA,
        )
    except Exception:
        return None


def chain_name(v):
    raw = str(v or "").strip().lower()
    return ALIASES.get(raw, raw)


def norm(chain, v):
    raw = str(v or "").strip()
    return raw.lower() if chain in EVM else raw


def ident(row):
    c = chain_name(row.get("network") or row.get("chain"))
    t = norm(c, row.get("contract") or row.get("token_address"))
    p = norm(c, row.get("pair") or row.get("pair_address"))
    return (c, t, p, f"{c}:{t}:{p}") if c and t and p else None


def ev(t, family, kind, direction, strength, confidence, source, **extra):
    i = ident(t)
    if not i:
        return None
    ts = now()
    e = {
        "symbol": str(t.get("symbol") or "").upper(),
        "network": i[0],
        "contract": i[1],
        "pair": i[2],
        "identity_key": i[3],
        "family": family,
        "kind": kind,
        "direction": direction,
        "strength": round(max(0, min(100, float(strength))), 1),
        "confidence": round(max(0, min(100, float(confidence))), 1),
        "source": source,
        "source_url": extra.pop("source_url", ""),
        "subject": extra.pop("subject", ""),
        "canonical_event_id": extra.pop("canonical_event_id", f"{source}:{i[3]}:{kind}"),
        "event_time": extra.pop("event_time", ts),
        "observed_at": ts,
        "free_source": True,
        "identity_verified": True,
        "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR",
    }
    e.update(extra)
    return e


def targets():
    cfg = load(CONFIG, {"tokens": []})
    dyn = load(DYNAMIC, {"candidates": []})
    dynamic_rows = [x for x in (dyn.get("candidates") or []) if isinstance(x, dict)]
    buy_rows = [x for x in dynamic_rows if str(x.get("candidate_type") or "").upper() == "BUY_ZONE"]

    def hot_cex(x):
        ctype = str(x.get("candidate_type") or "").upper()
        if ctype not in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY"}:
            return False
        try:
            momentum = float(x.get("discovery_momentum_change_pct") or x.get("change_24h_pct") or 0)
            gain = float(x.get("gain_from_first_seen_pct") or 0)
            rank = int(x.get("positive_gainer_rank") or 999999)
            turnover = float(x.get("quote_volume_24h_usd") or 0)
        except (TypeError, ValueError):
            return False
        return momentum >= 25.0 or gain >= 25.0 or (rank <= 15 and turnover >= 20000.0)

    hot_rows = [x for x in dynamic_rows if hot_cex(x)]
    hot_ids = {id(x) for x in hot_rows}
    other_dynamic = [
        x for x in dynamic_rows
        if str(x.get("candidate_type") or "").upper() != "BUY_ZONE" and id(x) not in hot_ids
    ]
    hot_rows.sort(
        key=lambda x: (
            int(x.get("positive_gainer_rank") or 999999),
            -float(x.get("discovery_momentum_change_pct") or x.get("change_24h_pct") or 0),
        )
    )

    # BUY and hot CEX identities are never displaced by the ordinary research cap.
    rows = []
    seen = set()
    ordered = buy_rows + hot_rows + list(cfg.get("tokens") or []) + other_dynamic
    for x in ordered:
        if not isinstance(x, dict):
            continue
        i = ident(x)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        rows.append(x)
    buy_count = len([x for x in rows if str(x.get("candidate_type") or "").upper() == "BUY_ZONE"])
    hot_count = sum(1 for x in rows if hot_cex(x))
    return rows[:max(60, buy_count + hot_count)]


def global_attention_maps(rows=None):
    trending = {}
    networks = {"eth", "bsc", "base", "arbitrum", "solana", "arc"}
    for row in rows or []:
        chain = chain_name((row or {}).get("network") or (row or {}).get("chain"))
        network = GT_NET.get(chain)
        if network:
            networks.add(network)
    for network in sorted(networks)[:10]:
        d = get_json(f"https://api.geckoterminal.com/api/v2/networks/{network}/trending_pools", timeout=6) or {}
        for rank, item in enumerate(d.get("data") or [], 1):
            attrs = item.get("attributes") or {}
            address = str(attrs.get("address") or "").lower()
            if address:
                trending[(network, address)] = rank
    boosts = {}
    for endpoint in ("latest", "top"):
        rows = get_json(f"https://api.dexscreener.com/token-boosts/{endpoint}/v1", timeout=6) or []
        if isinstance(rows, dict):
            rows = [rows]
        for r in rows:
            chain = chain_name(r.get("chainId"))
            token = norm(chain, r.get("tokenAddress"))
            if chain and token:
                boosts[(chain, token)] = max(
                    float(r.get("totalAmount") or r.get("amount") or 0),
                    boosts.get((chain, token), 0),
                )
    return trending, boosts


def blockscout_snapshot(t):
    i = ident(t)
    if not i or i[0] not in BLOCKSCOUT:
        return None
    base = BLOCKSCOUT[i[0]]
    addr = urllib.parse.quote(i[1], safe="")
    info = get_json(f"{base}/api/v2/tokens/{addr}", timeout=6)
    holders = get_json(f"{base}/api/v2/tokens/{addr}/holders", timeout=6)
    if not isinstance(info, dict) or not isinstance(holders, dict):
        return None
    try:
        decimals = int(info.get("decimals") or 0)
        supply_raw = float(info.get("total_supply") or 0)
        supply = supply_raw / (10 ** decimals) if decimals and supply_raw else supply_raw
    except Exception:
        decimals, supply = 0, 0.0
    vals = []
    exchange_units = 0.0
    exchange_names = ("binance", "coinbase", "kraken", "okx", "kucoin", "gate", "bybit", "mexc", "bitget")
    for row in (holders.get("items") or [])[:50]:
        try:
            units = float(row.get("value") or 0) / (10 ** decimals if decimals else 1)
        except Exception:
            units = 0.0
        vals.append(units)
        address_meta = row.get("address") or row.get("address_hash") or {}
        text = json.dumps(address_meta, ensure_ascii=False).lower()
        if any(name in text for name in exchange_names):
            exchange_units += units
    top10 = sum(vals[:10])
    top20 = sum(vals[:20])
    try:
        holders_count = float(info.get("holders_count")) if info.get("holders_count") is not None else None
    except Exception:
        holders_count = None
    return {
        "provider": "Blockscout",
        "holders_count": holders_count,
        "total_supply": supply,
        "top10_pct": (top10 / supply * 100) if supply > 0 else None,
        "top20_pct": (top20 / supply * 100) if supply > 0 else None,
        "exchange_top_units": exchange_units,
        "top_rows": len(vals),
    }


def solana_snapshot(t):
    i = ident(t)
    if not i or i[0] != "solana":
        return None
    url = "https://api.mainnet-beta.solana.com"
    supply = post_json(url, {"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [i[1]]}, timeout=6)
    largest = post_json(url, {"jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts", "params": [i[1]]}, timeout=6)
    try:
        total = float((((supply or {}).get("result") or {}).get("value") or {}).get("uiAmountString") or 0)
        rows = (((largest or {}).get("result") or {}).get("value") or [])
        vals = [float(x.get("uiAmountString") or 0) for x in rows]
    except Exception:
        return None
    if total <= 0:
        return None
    return {
        "provider": "Solana RPC",
        "holders_count": None,
        "total_supply": total,
        "top10_pct": sum(vals[:10]) / total * 100,
        "top20_pct": sum(vals[:20]) / total * 100,
        "exchange_top_units": None,
        "top_rows": len(vals),
    }


def holder_snapshot(t):
    i = ident(t)
    if not i:
        return None
    return solana_snapshot(t) if i[0] == "solana" else blockscout_snapshot(t)


def news_snapshot(t):
    sym = str(t.get("symbol") or "").upper()
    if not sym or len(sym) < 2:
        return None
    q = urllib.parse.quote(f'"{sym}" (crypto OR blockchain OR token)')
    xml = get_text(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en", timeout=6)
    if not xml:
        return None
    nowdt = datetime.now(timezone.utc)
    items = []
    try:
        root = ET.fromstring(xml)
        for item in root.findall(".//item")[:20]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            try:
                dt = parsedate_to_datetime(pub).astimezone(timezone.utc)
            except Exception:
                continue
            age_h = (nowdt - dt).total_seconds() / 3600
            if age_h < 0 or age_h > 24:
                continue
            if not re.search(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])", title.upper()):
                continue
            if not CRYPTO_CONTEXT.search(title):
                continue
            items.append({"title": title[:180], "link": link, "published_at": dt.isoformat()})
    except Exception:
        return None
    if not items:
        return {"count": 0, "direction": 0, "titles": []}
    pos = sum(bool(NEWS_POSITIVE.search(x["title"])) for x in items)
    neg = sum(bool(NEWS_NEGATIVE.search(x["title"])) for x in items)
    direction = 1 if pos > neg and pos else (-1 if neg > pos and neg else 0)
    return {"count": len(items), "direction": direction, "positive": pos, "negative": neg, "titles": items[:5]}


def main():
    event_doc = load(EVENTS, {"version": 3, "events": []})
    old_state = load(STATE, {"version": 1, "tokens": {}})
    old_tokens = old_state.get("tokens") or {}
    rows = targets()
    trending, boosts = global_attention_maps(rows)
    fresh = []
    new_state = {
        "version": 1,
        "updated_at": now(),
        "tokens": {},
        "providers": {"geckoterminal_trending": True, "dexscreener_boosts": True},
    }

    holder_results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(holder_snapshot, t): (ident(t)[3], t) for t in rows if ident(t)}
        for f in as_completed(futs):
            key, _ = futs[f]
            try:
                holder_results[key] = f.result()
            except Exception:
                holder_results[key] = None

    news_results = {}
    news_targets = sorted(
        rows,
        key=lambda x: (
            0 if str(x.get("candidate_type") or "").upper() == "BUY_ZONE"
            else 1 if str(x.get("candidate_type") or "").upper() == "NEW_CHAIN_BOOTSTRAP"
            else 2 if x.get("candidate_type") == "GATE_SPOT_DISCOVERY"
            else 3,
            x.get("positive_gainer_rank") or 999999,
        ),
    )[:12]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(news_snapshot, t): (ident(t)[3], t) for t in news_targets if ident(t)}
        for f in as_completed(futs):
            key, _ = futs[f]
            try:
                news_results[key] = f.result()
            except Exception:
                news_results[key] = None

    for t in rows:
        i = ident(t)
        if not i:
            continue
        key = i[3]
        prev = old_tokens.get(key) or {}
        hs = holder_results.get(key)
        ns = news_results.get(key)
        token_state = {"observed_at": now(), "holder": hs, "news": ns}

        if hs:
            prevh = prev.get("holder") or {}
            hc = hs.get("holders_count")
            phc = prevh.get("holders_count")
            if hc is not None and phc not in (None, 0):
                delta = (float(hc) - float(phc)) / abs(float(phc)) * 100
                if abs(delta) >= 2:
                    fresh.append(ev(
                        t,
                        "holder_network",
                        "holder_growth",
                        1 if delta > 0 else -1,
                        min(100, abs(delta) * 8),
                        88,
                        hs["provider"],
                        holder_count=hc,
                        change_pct=round(delta, 3),
                        contradicts_bullish=delta < 0,
                    ))
            top10 = hs.get("top10_pct")
            ptop10 = prevh.get("top10_pct")
            if top10 is not None:
                if float(top10) >= 70:
                    fresh.append(ev(
                        t,
                        "holder_network",
                        "holder_concentration",
                        -1,
                        min(100, 35 + (float(top10) - 70) * 2),
                        82,
                        hs["provider"],
                        top10_pct=round(float(top10), 2),
                        contradicts_bullish=True,
                    ))
                if ptop10 is not None and abs(float(top10) - float(ptop10)) >= 1.5:
                    dpp = float(top10) - float(ptop10)
                    fresh.append(ev(
                        t,
                        "wallet_flow",
                        "top_holder_balance_change",
                        -1 if dpp > 0 else 1,
                        min(100, abs(dpp) * 12),
                        82,
                        hs["provider"],
                        top10_pct=round(float(top10), 2),
                        change_pp=round(dpp, 2),
                        contradicts_bullish=dpp > 0,
                    ))
            exu = hs.get("exchange_top_units")
            pexu = prevh.get("exchange_top_units")
            if exu is not None and pexu not in (None, 0):
                d = (float(exu) - float(pexu)) / abs(float(pexu)) * 100
                if abs(d) >= 10:
                    fresh.append(ev(
                        t,
                        "wallet_flow",
                        "exchange_netflow",
                        -1 if d > 0 else 1,
                        min(100, abs(d) * 2),
                        78,
                        hs["provider"],
                        exchange_top_units=exu,
                        change_pct=round(d, 2),
                        contradicts_bullish=d > 0,
                    ))

        gt_key = (GT_NET.get(i[0], i[0]), i[2].lower())
        rank = trending.get(gt_key)
        if rank:
            fresh.append(ev(
                t,
                "search_discovery",
                "geckoterminal_trending_pool",
                1,
                max(35, 100 - rank * 5),
                84,
                "GeckoTerminal Trending",
                rank=rank,
                canonical_event_id=f"gt-trending:{key}:{rank}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}",
            ))

        boost = boosts.get((i[0], i[1]))
        if boost and boost > 0:
            fresh.append(ev(
                t,
                "attention_social",
                "paid_attention_boost",
                1,
                min(60, 20 + boost ** 0.5),
                58,
                "DexScreener Boosts",
                boost_amount=boost,
                paid_attention=True,
                canonical_event_id=f"ds-boost:{key}:{int(boost)}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}",
            ))

        if ns and ns.get("count", 0) >= 2:
            direction = int(ns.get("direction") or 0)
            if direction:
                fresh.append(ev(
                    t,
                    "catalyst_news",
                    "news_velocity",
                    direction,
                    min(80, 30 + ns["count"] * 8),
                    62,
                    "Google News RSS",
                    subject=" | ".join(x["title"] for x in ns["titles"][:2]),
                    article_count_24h=ns["count"],
                    positive_hits=ns.get("positive", 0),
                    negative_hits=ns.get("negative", 0),
                    contradicts_bullish=direction < 0,
                    canonical_event_id=f"news-velocity:{key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}",
                ))
            else:
                fresh.append(ev(
                    t,
                    "catalyst_news",
                    "news_velocity",
                    0,
                    0,
                    55,
                    "Google News RSS",
                    subject=" | ".join(x["title"] for x in ns["titles"][:2]),
                    article_count_24h=ns["count"],
                    canonical_event_id=f"news-neutral:{key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}",
                ))

        new_state["tokens"][key] = token_state

    events = [e for e in (event_doc.get("events") or []) if isinstance(e, dict)]
    ded = {}
    for e in events + [x for x in fresh if x]:
        ded[(e.get("identity_key") or "", e.get("canonical_event_id"), e.get("kind"))] = e
    event_doc["version"] = max(3, int(event_doc.get("version") or 0))
    event_doc["generated_at"] = now()
    event_doc["events"] = list(ded.values())[-5000:]
    EVENTS.write_text(json.dumps(event_doc, indent=2, ensure_ascii=False) + "\n")
    STATE.write_text(json.dumps(new_state, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "targets": len(rows),
        "holder_snapshots": sum(v is not None for v in holder_results.values()),
        "news_snapshots": sum(v is not None for v in news_results.values()),
        "new_events": len([x for x in fresh if x]),
        "trending_matches": sum(1 for x in fresh if x and x.get("kind") == "geckoterminal_trending_pool"),
        "holder_events": sum(1 for x in fresh if x and x.get("family") in {"wallet_flow", "holder_network"}),
        "news_events": sum(1 for x in fresh if x and x.get("family") == "catalyst_news"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
