from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPOT = ROOT / "data/spot-market-discovery.json"
ALPHA = ROOT / "data/alpha-caller-candidates.json"
BUY_REGISTRY = ROOT / "data/buy-zone-close-watch-registry.json"
OUT = ROOT / "data/unified-dynamic-candidates.json"
EVENTS = ROOT / "data/close-watch-events.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def now():
    return datetime.now(timezone.utc).isoformat()


def chain_name(v):
    raw = str(v or "").strip().lower()
    return ALIASES.get(raw, raw)


def norm_addr(chain, v):
    raw = str(v or "").strip()
    return raw.lower() if chain in EVM else raw


def ident(row):
    c = chain_name(row.get("network") or row.get("chain"))
    t = norm_addr(c, row.get("contract") or row.get("token_address"))
    p = norm_addr(c, row.get("pair") or row.get("pair_address"))
    return (c, t, p, f"{c}:{t}:{p}") if c and t and p else None


def load(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def main():
    spot = load(SPOT, {"candidates": []})
    alpha = load(ALPHA, {"candidates": []})
    buy_registry = load(BUY_REGISTRY, {"entries": {}})
    event_doc = load(EVENTS, {"version": 3, "events": []})
    out = []
    seen = set()

    buy_entries = buy_registry.get("entries") if isinstance(buy_registry, dict) and isinstance(buy_registry.get("entries"), dict) else {}
    for row in buy_entries.values():
        if not isinstance(row, dict) or row.get("active") is not True:
            continue
        i = ident(row)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        out.append({
            "candidate_type": "BUY_ZONE",
            "symbol": str(row.get("symbol") or "BUY").upper(),
            "network": row.get("network") or row.get("chain"),
            "contract": row.get("contract") or row.get("token_address"),
            "pair": row.get("pair") or row.get("pair_address"),
            "dex_url": row.get("dex_url") or "",
            "source": "Decision Engine BUY_ZONE",
            "first_seen_at": row.get("first_buy_at") or row.get("last_buy_at"),
            "discovery_price": row.get("first_buy_price_usd") or row.get("buy_zone_price_usd"),
            "dex_liquidity_usd": row.get("dex_liquidity_usd"),
            "identity_key": i[3],
            "priority": "HIGHEST",
            "close_watch": "HIGHEST",
            "collector_priority": 0,
            "deep_investigation": True,
            "full_intelligence": True,
            "wallet_holder_intelligence": True,
            "attention_social_intelligence": True,
            "search_news_intelligence": True,
            "market_microstructure_intelligence": True,
            "derivatives_intelligence": bool(row.get("derivatives_intelligence")),
            "derivatives_symbol": row.get("derivatives_symbol"),
            "buy_zone_price_usd": row.get("buy_zone_price_usd"),
            "first_buy_at": row.get("first_buy_at"),
            "last_buy_at": row.get("last_buy_at"),
        })

    for row in spot.get("candidates") or []:
        if row.get("status") != "IDENTITY_RESOLVED" or row.get("identity_status") != "RESOLVED_EXACT":
            continue
        if float(row.get("dex_liquidity_usd") or 0) <= 0:
            continue
        i = ident(row)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        out.append({
            "candidate_type": "GATE_SPOT_DISCOVERY",
            "symbol": str(row.get("symbol") or "").upper(),
            "network": row.get("network"),
            "contract": row.get("contract"),
            "pair": row.get("pair"),
            "dex_url": row.get("dex_url") or "",
            "source": "Gate Spot",
            "source_url": row.get("source_url") or "",
            "first_seen_at": row.get("first_seen_at"),
            "discovery_price": row.get("discovery_price"),
            "change_24h_pct": row.get("change_24h_pct"),
            "quote_volume_24h_usd": row.get("quote_volume_24h_usd"),
            "positive_gainer_rank": row.get("positive_gainer_rank"),
            "dex_liquidity_usd": row.get("dex_liquidity_usd"),
            "identity_key": i[3],
        })

    for row in alpha.get("candidates") or []:
        if row.get("status") != "GATED_RESEARCH_CANDIDATE":
            continue
        i = ident(row)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        out.append({
            "candidate_type": "PUBLIC_ALPHA",
            "symbol": str(row.get("symbol") or "ALPHA").upper(),
            "network": row.get("network"),
            "contract": row.get("contract"),
            "pair": row.get("pair"),
            "dex_url": row.get("dex_url") or "",
            "source": row.get("source") or "Public Alpha",
            "first_seen_at": row.get("called_at") or row.get("observed_at"),
            "dex_liquidity_usd": row.get("liquidity_usd"),
            "identity_key": i[3],
        })

    out.sort(key=lambda x: (
        0 if x["candidate_type"] == "BUY_ZONE" else 1 if x["candidate_type"] == "GATE_SPOT_DISCOVERY" else 2,
        x.get("positive_gainer_rank") or 999999,
        -(float(x.get("dex_liquidity_usd") or 0)),
    ))
    doc = {
        "version": 1,
        "generated_at": now(),
        "mode": "EXACT_IDENTITY_DYNAMIC_RESEARCH",
        "counts": {
            "buy_zone": sum(x["candidate_type"] == "BUY_ZONE" for x in out),
            "gate_spot": sum(x["candidate_type"] == "GATE_SPOT_DISCOVERY" for x in out),
            "public_alpha": sum(x["candidate_type"] == "PUBLIC_ALPHA" for x in out),
            "total": len(out),
        },
        "candidates": out[:120],
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    events = [e for e in (event_doc.get("events") or []) if isinstance(e, dict)]
    existing = {str(e.get("canonical_event_id") or "") for e in events}
    added = 0
    for c in out:
        if c["candidate_type"] != "GATE_SPOT_DISCOVERY":
            continue
        cid = "gate-spot-discovery:" + c["identity_key"]
        if cid in existing:
            continue
        change = max(0.0, float(c.get("change_24h_pct") or 0))
        strength = min(75.0, 20.0 + change * 0.35)
        events.append({
            "symbol": c["symbol"],
            "network": c["network"],
            "contract": c["contract"],
            "pair": c["pair"],
            "identity_key": c["identity_key"],
            "family": "search_discovery",
            "kind": "cex_spot_mover",
            "direction": 1,
            "strength": round(strength, 1),
            "confidence": 72,
            "source": "Gate Spot",
            "source_url": c.get("source_url") or "",
            "subject": f"rank={c.get('positive_gainer_rank')} change24h={c.get('change_24h_pct')}",
            "canonical_event_id": cid,
            "event_time": c.get("first_seen_at") or now(),
            "observed_at": now(),
            "free_source": True,
            "research_only": True,
            "identity_verified": True,
            "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR",
            "discovery_price": c.get("discovery_price"),
            "change_24h_pct": c.get("change_24h_pct"),
            "quote_volume_24h_usd": c.get("quote_volume_24h_usd"),
            "rank": c.get("positive_gainer_rank"),
        })
        existing.add(cid)
        added += 1

    event_doc["version"] = max(3, int(event_doc.get("version") or 0))
    event_doc["generated_at"] = now()
    event_doc["events"] = events[-5000:]
    EVENTS.write_text(json.dumps(event_doc, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "OK", **doc["counts"], "gate_discovery_events_added": added}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
