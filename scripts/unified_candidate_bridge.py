from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPOT = ROOT / "data/spot-market-discovery.json"
CEX_SPOT_IDENTITY = ROOT / "data/cex-spot-identity-radar.json"
ALPHA = ROOT / "data/alpha-caller-candidates.json"
BUY_REGISTRY = ROOT / "data/buy-zone-close-watch-registry.json"
BOOTSTRAP = ROOT / "data/new-chain-bootstrap-radar.json"
OUT = ROOT / "data/unified-dynamic-candidates.json"
EVENTS = ROOT / "data/close-watch-events.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
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
    buy_registry = load(BUY_REGISTRY, {"entries": {}})
    bootstrap = load(BOOTSTRAP, {"candidates": []})
    event_doc = load(EVENTS, {"version": 3, "events": []})
    out = []
    seen = set()
    current = datetime.now(timezone.utc)
    stale_alpha_excluded = 0
    invalid_time_alpha_excluded = 0

    gate_spot_by_identity = {}
    for gate_row in spot.get("candidates") or []:
        if not isinstance(gate_row, dict) or gate_row.get("identity_status") != "RESOLVED_EXACT":
            continue
        gate_ident = ident(gate_row)
        if gate_ident:
            gate_spot_by_identity[gate_ident[3]] = gate_row

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
        gate_exec = gate_spot_by_identity.get(i[3]) or {}
        out.append({
            "candidate_type": "CEX_SPOT_DISCOVERY",
            "symbol": str(row.get("symbol") or "").upper(),
            "network": row.get("chain"),
            "contract": row.get("token_address"),
            "pair": row.get("pair_address"),
            "dex_url": row.get("dex_url") or row.get("url") or "",
            "source": "CEX Spot Multi-Venue Exact Identity",
            "exchange": "gate" if gate_exec.get("currency_pair") else None,
            "currency_pair": gate_exec.get("currency_pair"),
            "execution_identity_scope": (
                "EXACT_CHAIN_CONTRACT_PAIR_PLUS_CEX_MARKET"
                if gate_exec.get("currency_pair")
                else "EXACT_CHAIN_CONTRACT_PAIR"
            ),
            "first_seen_at": milestone.get("observed_at") or row.get("identity_attempted_at"),
            "first_seen_price": milestone.get("reference_price"),
            "first_seen_change_24h_pct": milestone.get("reference_change_24h_pct"),
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
            "exchange": "gate",
            "currency_pair": row.get("currency_pair"),
            "execution_identity_scope": "EXACT_CHAIN_CONTRACT_PAIR_PLUS_CEX_MARKET",
            "first_seen_at": row.get("first_seen_at"),
            "first_seen_price": row.get("first_seen_price"),
            "first_seen_change_24h_pct": row.get("first_seen_change_24h_pct"),
            "first_seen_quote_volume_24h_usd": row.get("first_seen_quote_volume_24h_usd"),
            "discovery_price": row.get("discovery_price"),
            "change_24h_pct": row.get("change_24h_pct"),
            "quote_volume_24h_usd": row.get("quote_volume_24h_usd"),
            "positive_gainer_rank": row.get("positive_gainer_rank"),
            "dex_liquidity_usd": row.get("dex_liquidity_usd"),
            "identity_key": i[3],
            "identity_source": row.get("identity_source"),
            "identity_reason": row.get("identity_reason"),
            "native_asset_proxy": bool(row.get("native_asset_proxy")),
            "native_asset_coingecko_id": row.get("native_asset_coingecko_id"),
            "research_only_identity": bool(row.get("research_only_identity")),
        })

    # Strong CEX movers that do not expose a supported on-chain contract still
    # receive an exact venue-market identity. This keeps BRC-20/native/unsupported
    # chain assets observable without pretending they have a DEX identity.
    for row in spot.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        if row.get("identity_status") == "RESOLVED_EXACT":
            continue
        change = float(row.get("change_24h_pct") or 0)
        rank = int(row.get("positive_gainer_rank") or 999999)
        first_change = float(row.get("first_seen_change_24h_pct") or change or 0)
        if max(change, first_change) < 25.0 and rank > 10:
            continue
        currency_pair = str(row.get("currency_pair") or "").upper().strip()
        if not currency_pair:
            continue
        cex_key = f"cex:gate:{currency_pair}"
        if cex_key in seen:
            continue
        seen.add(cex_key)
        out.append({
            "candidate_type": "CEX_MARKET_DISCOVERY",
            "symbol": str(row.get("symbol") or "").upper(),
            "exchange": "gate",
            "currency_pair": currency_pair,
            "execution_identity_scope": "EXACT_CEX_MARKET",
            "source": "Gate Spot",
            "source_url": row.get("source_url") or "",
            "first_seen_at": row.get("first_seen_at"),
            "first_seen_price": row.get("first_seen_price") or row.get("discovery_price"),
            "first_seen_change_24h_pct": row.get("first_seen_change_24h_pct"),
            "first_seen_quote_volume_24h_usd": row.get("first_seen_quote_volume_24h_usd"),
            "discovery_price": row.get("discovery_price"),
            "change_24h_pct": row.get("change_24h_pct"),
            "quote_volume_24h_usd": row.get("quote_volume_24h_usd"),
            "positive_gainer_rank": row.get("positive_gainer_rank"),
            "identity_key": cex_key,
            "identity_reason": row.get("identity_reason"),
            "research_only_identity": False,
            "telegram_policy": "FINAL_BUY_ONLY",
        })

    for row in bootstrap.get("candidates") or []:
        if not isinstance(row, dict) or row.get("bootstrap_actionable_watch") is not True:
            continue
        if float(row.get("liquidity_usd") or 0) <= 0:
            continue
        i = ident(row)
        if not i or i[3] in seen:
            continue
        seen.add(i[3])
        score = float(row.get("bootstrap_score") or 0)
        out.append({
            "candidate_type": "NEW_CHAIN_BOOTSTRAP",
            "symbol": str(row.get("symbol") or "BOOTSTRAP").upper(),
            "network": row.get("network") or row.get("chain"),
            "contract": row.get("contract") or row.get("token_address"),
            "pair": row.get("pair") or row.get("pair_address"),
            "dex_url": row.get("dex_url") or "",
            "source": "New Chain Bootstrap Radar",
            "source_url": row.get("dex_url") or "",
            "first_seen_at": row.get("first_seen_at") or row.get("pair_created_at"),
            "discovery_price": row.get("price_usd"),
            "change_24h_pct": row.get("price_change_h24"),
            "quote_volume_24h_usd": row.get("volume_h24"),
            "dex_liquidity_usd": row.get("liquidity_usd"),
            "bootstrap_score": score,
            "bootstrap_reasons": row.get("bootstrap_reasons") or [],
            "bootstrap_final_buy_lane": True,
            "exact_identity_required": True,
            "exact_pair_required": True,
            "telegram_policy": "FINAL_BUY_ONLY",
            "priority": "HIGHEST" if score >= 70 else "HIGH",
            "close_watch": "HIGHEST",
            "collector_priority": 1,
            "deep_investigation": True,
            "full_intelligence": True,
            "identity_key": i[3],
        })

    for row in alpha.get("candidates") or []:
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
            "identity_key": i[3],
        })

    out.sort(key=lambda x: (
        0 if x["candidate_type"] == "BUY_ZONE" else 1 if x["candidate_type"] == "NEW_CHAIN_BOOTSTRAP" else 2 if x["candidate_type"] in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY"} else 3,
        (
            x.get("alpha_age_minutes", 999999)
            if x["candidate_type"] == "PUBLIC_ALPHA"
            else (x.get("positive_gainer_rank") or 999999)
        ),
        -(float(x.get("dex_liquidity_usd") or 0)),
    ))
    doc = {
        "version": 1,
        "generated_at": now(),
        "mode": "EXACT_IDENTITY_DYNAMIC_RESEARCH",
        "counts": {
            "buy_zone": sum(x["candidate_type"] == "BUY_ZONE" for x in out),
            "cex_spot": sum(x["candidate_type"] == "CEX_SPOT_DISCOVERY" for x in out),
            "gate_spot": sum(x["candidate_type"] == "GATE_SPOT_DISCOVERY" for x in out),
            "cex_market": sum(x["candidate_type"] == "CEX_MARKET_DISCOVERY" for x in out),
            "new_chain_bootstrap": sum(x["candidate_type"] == "NEW_CHAIN_BOOTSTRAP" for x in out),
            "public_alpha": sum(x["candidate_type"] == "PUBLIC_ALPHA" for x in out),
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
        if c["candidate_type"] not in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "NEW_CHAIN_BOOTSTRAP"}:
            continue
        is_bootstrap = c["candidate_type"] == "NEW_CHAIN_BOOTSTRAP"
        cid = ("new-chain-bootstrap:" if is_bootstrap else "cex-spot-discovery:") + c["identity_key"]
        if cid in existing:
            continue
        change = max(0.0, float(c.get("change_24h_pct") or 0))
        strength = min(85.0, max(25.0, float(c.get("bootstrap_score") or 0))) if is_bootstrap else min(75.0, 20.0 + change * 0.35)
        events.append({
            "symbol": c["symbol"],
            "network": c["network"],
            "contract": c["contract"],
            "pair": c["pair"],
            "identity_key": c["identity_key"],
            "family": "catalyst_news" if is_bootstrap else "search_discovery",
            "kind": "new_chain_bootstrap" if is_bootstrap else "cex_spot_mover",
            "direction": 1,
            "strength": round(strength, 1),
            "confidence": 72,
            "source": c.get("source") or ("New Chain Bootstrap Radar" if is_bootstrap else "CEX Spot"),
            "source_url": c.get("source_url") or "",
            "subject": (f"bootstrap_score={c.get('bootstrap_score')} chain={c.get('network')}" if is_bootstrap else f"rank={c.get('positive_gainer_rank')} change24h={c.get('change_24h_pct')}"),
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
