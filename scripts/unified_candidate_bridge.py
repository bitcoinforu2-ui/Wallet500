from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPOT = ROOT / "data/spot-market-discovery.json"
CEX_SPOT_IDENTITY = ROOT / "data/cex-spot-identity-radar.json"
ALPHA = ROOT / "data/alpha-caller-candidates.json"
BUY_REGISTRY = ROOT / "data/buy-zone-close-watch-registry.json"
OUT = ROOT / "data/unified-dynamic-candidates.json"
EVENTS = ROOT / "data/close-watch-events.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
PUBLIC_ALPHA_LIVE_WINDOW_MINUTES = 180


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


def parse_ts(value):
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def alpha_age_minutes(row, current=None):
    current = current or datetime.now(timezone.utc)
    ts = parse_ts(row.get("called_at") or row.get("observed_at"))
    if ts is None:
        return None
    return max(0.0, (current - ts).total_seconds() / 60.0)


def alpha_asset_key(row):
    chain = chain_name(row.get("network") or row.get("chain"))
    contract = norm_addr(chain, row.get("contract") or row.get("token_address"))
    return f"{chain}:{contract}" if chain and contract else None


def independent_caller_name(row):
    caller = str(row.get("origin_caller") or row.get("caller") or "").strip()
    source = str(row.get("source") or "").strip()
    source_class = str(row.get("source_class") or "")
    lowered = caller.lower()
    if not caller:
        return None
    if source_class == "caller_aggregator" and (
        lowered in {"call analyser", "call analyser sol"}
        or lowered == source.lower()
    ):
        return None
    return caller


def alpha_convergence_metrics(rows, current=None):
    current = current or datetime.now(timezone.utc)
    grouped = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "GATED_RESEARCH_CANDIDATE":
            continue
        age = alpha_age_minutes(row, current=current)
        if age is None or age > PUBLIC_ALPHA_LIVE_WINDOW_MINUTES:
            continue
        asset = alpha_asset_key(row)
        caller = independent_caller_name(row)
        called = parse_ts(row.get("called_at") or row.get("observed_at"))
        if not asset or not caller or called is None:
            continue
        grouped.setdefault(asset, []).append(
            {
                "caller": caller,
                "called_at": called,
                "source": row.get("source"),
                "fingerprint": str(row.get("source_content_fingerprint") or ""),
            }
        )

    result = {}
    for asset, items in grouped.items():
        items.sort(key=lambda x: x["called_at"])
        # Collapse exact copied posts first, then collapse repeated surfaces from
        # the same underlying caller. This is intentionally conservative.
        fingerprints = {}
        for item in items:
            fp = item["fingerprint"]
            if fp:
                fingerprints.setdefault(fp, item)
            else:
                fingerprints[f"nofp:{item['caller'].lower()}:{item['called_at'].isoformat()}"] = item
        first_by_caller = {}
        for item in sorted(fingerprints.values(), key=lambda x: x["called_at"]):
            first_by_caller.setdefault(item["caller"].strip().lower(), item)
        independent = sorted(first_by_caller.values(), key=lambda x: x["called_at"])
        if not independent:
            continue
        first = independent[0]
        def within(minutes):
            return [
                item for item in independent
                if (item["called_at"] - first["called_at"]).total_seconds() <= minutes * 60
            ]
        c15, c30, c60 = len(within(15)), len(within(30)), len(within(60))
        if c30 >= 3:
            tier = "MULTI_SOURCE_CONVERGENCE"
        elif c30 >= 2:
            tier = "DOUBLE_SOURCE_CONVERGENCE"
        elif c60 >= 2:
            tier = "SLOW_DOUBLE_SOURCE"
        else:
            tier = "SINGLE_SOURCE"
        last_60 = within(60)[-1]["called_at"]
        result[asset] = {
            "alpha_first_caller": first["caller"],
            "alpha_first_source": first.get("source"),
            "alpha_first_called_at": first["called_at"].isoformat(),
            "alpha_independent_callers_15m": c15,
            "alpha_independent_callers_30m": c30,
            "alpha_independent_callers_60m": c60,
            "alpha_independent_callers_60m_list": [x["caller"] for x in within(60)[:12]],
            "alpha_convergence_span_minutes": round(
                max(0.0, (last_60 - first["called_at"]).total_seconds() / 60.0), 2
            ),
            "alpha_convergence_tier": tier,
            "alpha_convergence_research_only": True,
            "alpha_independence_mode": "DISTINCT_ORIGIN_CALLER_PLUS_EXACT_CONTENT_COPY_COLLAPSE",
        }
    return result


def candidate_sort_key(row):
    liquidity = -float(row.get("dex_liquidity_usd") or 0)
    kind = row.get("candidate_type")
    if kind == "BUY_ZONE":
        return (0, 0, 0, liquidity)
    if kind in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY"}:
        return (1, int(row.get("positive_gainer_rank") or 999999), 0, liquidity)
    return (
        2,
        -int(row.get("alpha_independent_callers_30m") or 1),
        float(row.get("alpha_age_minutes") or 999999),
        liquidity,
    )


def cex_signal_milestone(row):
    """Prefer the freshest valid CEX milestone so old alerts cannot mask reactivation."""
    milestones = row.get("milestones") if isinstance(row.get("milestones"), dict) else {}
    names = (
        "first_cross_venue_slow_ignition",
        "first_shadow_watch",
        "first_alert",
        "first_watch",
        "first_anomaly",
        "first_seen",
    )
    candidates = []
    for priority, name in enumerate(names):
        item = milestones.get(name)
        if not isinstance(item, dict) or not item.get("observed_at"):
            continue
        ts = parse_ts(item.get("observed_at"))
        if ts is not None:
            candidates.append((ts, -priority, item))
    return max(candidates, key=lambda x: (x[0], x[1]))[2] if candidates else {}


def max_cex_turnover(row):
    values = []
    for market in row.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if market.get("volume_comparable_usd_like", True) is False:
            continue
        try:
            values.append(float(market.get("volume_24h") or 0.0))
        except (TypeError, ValueError):
            pass
    return max(values, default=0.0)


def main():
    spot = load(SPOT, {"candidates": []})
    cex_identity = load(CEX_SPOT_IDENTITY, {"candidates": []})
    alpha = load(ALPHA, {"candidates": []})
    alpha_rows = [x for x in (alpha.get("candidates") or []) if isinstance(x, dict)]
    buy_registry = load(BUY_REGISTRY, {"entries": {}})
    event_doc = load(EVENTS, {"version": 3, "events": []})
    out = []
    seen = set()
    current = datetime.now(timezone.utc)
    stale_alpha_excluded = 0
    invalid_time_alpha_excluded = 0
    convergence = alpha_convergence_metrics(alpha_rows, current=current)

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

    for row in cex_identity.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        if row.get("identity_status") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
            continue
        if row.get("execution_pair_price_coherent") is not True:
            continue
        if row.get("market_age_verified") is not True:
            continue
        i = ident(row)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        milestone = cex_signal_milestone(row)
        out.append({
            "candidate_type": "CEX_SPOT_DISCOVERY",
            "symbol": str(row.get("symbol") or "").upper(),
            "network": row.get("chain"),
            "contract": row.get("token_address"),
            "pair": row.get("pair_address"),
            "dex_url": row.get("dex_url") or row.get("url") or "",
            "source": "CEX Spot Multi-Venue Exact Identity",
            "first_seen_at": milestone.get("observed_at") or row.get("identity_attempted_at"),
            "discovery_price": milestone.get("reference_price"),
            "change_24h_pct": row.get("change_24h_max_pct"),
            "quote_volume_24h_usd": max_cex_turnover(row),
            "positive_gainer_rank": row.get("leaderboard_best_rank"),
            "dex_liquidity_usd": (
                row.get("execution_pool_liquidity_usd")
                or row.get("dex_pair_liquidity_usd")
                or row.get("dex_liquidity_usd")
            ),
            "spot_revival_score": row.get("spot_revival_score"),
            "coherent_confirmations": row.get("coherent_confirmations"),
            "identity_key": i[3],
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

    for row in alpha_rows:
        if row.get("status") != "GATED_RESEARCH_CANDIDATE":
            continue
        age_minutes = alpha_age_minutes(row, current=current)
        if age_minutes is None:
            invalid_time_alpha_excluded += 1
            continue
        if age_minutes > PUBLIC_ALPHA_LIVE_WINDOW_MINUTES:
            stale_alpha_excluded += 1
            continue
        i = ident(row)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        conv = convergence.get(alpha_asset_key(row), {})
        out.append({
            "candidate_type": "PUBLIC_ALPHA",
            "symbol": str(row.get("symbol") or "ALPHA").upper(),
            "network": row.get("network"),
            "contract": row.get("contract"),
            "pair": row.get("pair"),
            "dex_url": row.get("dex_url") or "",
            "source": row.get("source") or "Public Alpha",
            "first_seen_at": row.get("called_at") or row.get("observed_at"),
            "alpha_age_minutes": round(age_minutes, 2),
            "dex_liquidity_usd": row.get("liquidity_usd"),
            "price_usd_at_intake": row.get("price_usd"),
            "market_cap_usd_at_intake": row.get("market_cap_usd"),
            "pair_age_minutes_at_intake": row.get("pair_age_minutes_at_intake"),
            "volume_h1_usd_at_intake": row.get("volume_h1_usd"),
            "buys_h1_at_intake": row.get("buys_h1"),
            "sells_h1_at_intake": row.get("sells_h1"),
            "identity_key": i[3],
            "priority": (
                "ALPHA_MULTI_CONVERGENCE"
                if int(conv.get("alpha_independent_callers_30m") or 0) >= 3
                else "ALPHA_DOUBLE_CONVERGENCE"
                if int(conv.get("alpha_independent_callers_30m") or 0) >= 2
                else "ALPHA_FIRST_CALL"
            ),
            "collector_priority": (
                1 if int(conv.get("alpha_independent_callers_30m") or 0) >= 2 else 3
            ),
            "deep_investigation": int(conv.get("alpha_independent_callers_30m") or 0) >= 2,
            "full_intelligence": int(conv.get("alpha_independent_callers_30m") or 0) >= 3,
            **conv,
        })

    out.sort(key=candidate_sort_key)
    doc = {
        "version": 1,
        "generated_at": now(),
        "mode": "EXACT_IDENTITY_DYNAMIC_RESEARCH",
        "counts": {
            "buy_zone": sum(x["candidate_type"] == "BUY_ZONE" for x in out),
            "cex_spot": sum(x["candidate_type"] == "CEX_SPOT_DISCOVERY" for x in out),
            "gate_spot": sum(x["candidate_type"] == "GATE_SPOT_DISCOVERY" for x in out),
            "public_alpha": sum(x["candidate_type"] == "PUBLIC_ALPHA" for x in out),
            "public_alpha_double_source_or_better": sum(
                x["candidate_type"] == "PUBLIC_ALPHA"
                and int(x.get("alpha_independent_callers_30m") or 0) >= 2
                for x in out
            ),
            "public_alpha_multi_source": sum(
                x["candidate_type"] == "PUBLIC_ALPHA"
                and int(x.get("alpha_independent_callers_30m") or 0) >= 3
                for x in out
            ),
            "public_alpha_stale_excluded": stale_alpha_excluded,
            "public_alpha_invalid_time_excluded": invalid_time_alpha_excluded,
            "public_alpha_live_window_minutes": PUBLIC_ALPHA_LIVE_WINDOW_MINUTES,
            "total": len(out),
        },
        "candidates": out[:120],
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    events = [e for e in (event_doc.get("events") or []) if isinstance(e, dict)]
    existing = {str(e.get("canonical_event_id") or "") for e in events}
    added = 0
    for c in out:
        if c["candidate_type"] not in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY"}:
            continue
        cid = "cex-spot-discovery:" + c["identity_key"]
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
            "source": c.get("source") or "CEX Spot",
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
    print(json.dumps({"status": "OK", **doc["counts"], "cex_discovery_events_added": added}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
