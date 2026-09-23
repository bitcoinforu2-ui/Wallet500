from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPOT = ROOT / "data/spot-market-discovery.json"
CEX_SPOT_IDENTITY = ROOT / "data/cex-spot-identity-radar.json"
ALPHA = ROOT / "data/alpha-caller-candidates.json"
KOL = ROOT / "data/early-kol-candidates.json"
BUY_REGISTRY = ROOT / "data/buy-zone-close-watch-registry.json"
BOOTSTRAP = ROOT / "data/new-chain-bootstrap-radar.json"
OUT = ROOT / "data/unified-dynamic-candidates.json"
EVENTS = ROOT / "data/close-watch-events.json"

EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
ALIASES = {"eth": "ethereum", "bnb": "bsc"}
PUBLIC_ALPHA_LIVE_WINDOW_MINUTES = 180
MULTI_POOL_WATCH_MAX_POOLS = 5
MULTI_POOL_WATCH_MIN_LIQUIDITY_USD = 5000.0
RECENT_GATE_LISTING_WINDOW_SECONDS = 48 * 3600


def now():
    return datetime.now(timezone.utc).isoformat()


def recent_gate_listing(row, current=None):
    """Treat a verified recent Gate buy_start as a discovery trigger, not a BUY signal."""
    try:
        buy_start = int(float(row.get("buy_start") or 0))
    except (TypeError, ValueError):
        return False
    if buy_start <= 0:
        return False
    current = current or datetime.now(timezone.utc)
    age = current.timestamp() - buy_start
    return -300 <= age <= RECENT_GATE_LISTING_WINDOW_SECONDS


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


def asset_ident(row):
    c = chain_name(row.get("network") or row.get("chain"))
    t = norm_addr(c, row.get("contract") or row.get("token_address"))
    return f"{c}:{t}" if c and t else ""


def verified_asset_pools(row):
    """Return bounded exact-token pools for asset-level monitoring.

    Pool discovery is contract-address based. Thin/noisy siblings are ignored unless
    they have meaningful current volume, while the selected execution pool is always
    retained. FINAL BUY still evaluates each exact pair independently.
    """
    chain = chain_name(row.get("chain") or row.get("network"))
    token = norm_addr(chain, row.get("token_address") or row.get("contract"))
    primary_pair = norm_addr(chain, row.get("pair_address") or row.get("pair"))
    candidates = []
    for raw in row.get("dex_liquidity_pools_top5") or []:
        if not isinstance(raw, dict):
            continue
        pool_chain = chain_name(raw.get("chain") or chain)
        pool_token = norm_addr(pool_chain, raw.get("token_address") or token)
        pair = norm_addr(pool_chain, raw.get("pair_address"))
        if not pair or pool_chain != chain or pool_token != token:
            continue
        liq = float(raw.get("liquidity_usd") or 0)
        vol = float(raw.get("volume_h24") or 0)
        if pair != primary_pair and liq < MULTI_POOL_WATCH_MIN_LIQUIDITY_USD and vol < 10000.0:
            continue
        candidates.append({
            "network": chain,
            "contract": token,
            "pair": raw.get("pair_address"),
            "dex_url": raw.get("url") or "",
            "dex": raw.get("dex"),
            "price_usd": raw.get("price_usd"),
            "liquidity_usd": liq,
            "volume_h1": float(raw.get("volume_h1") or 0),
            "volume_h24": vol,
            "pair_created_at": raw.get("pair_created_at"),
            "exact_token_side": raw.get("exact_token_side"),
            "provider": raw.get("provider"),
        })

    if primary_pair and not any(
        norm_addr(chain, x.get("pair")) == primary_pair for x in candidates
    ):
        candidates.append({
            "network": chain,
            "contract": token,
            "pair": row.get("pair_address") or row.get("pair"),
            "dex_url": row.get("dex_url") or row.get("url") or "",
            "dex": row.get("dex"),
            "price_usd": row.get("dex_price_usd"),
            "liquidity_usd": float(
                row.get("execution_pool_liquidity_usd")
                or row.get("dex_pair_liquidity_usd")
                or row.get("dex_liquidity_usd")
                or 0
            ),
            "volume_h1": float(row.get("dex_volume_h1") or 0),
            "volume_h24": float(row.get("dex_volume_h24") or 0),
            "pair_created_at": row.get("pair_created_at"),
            "exact_token_side": row.get("exact_token_side"),
            "provider": row.get("pair_provider"),
        })

    candidates.sort(
        key=lambda x: (float(x.get("liquidity_usd") or 0), float(x.get("volume_h24") or 0)),
        reverse=True,
    )
    return candidates[:MULTI_POOL_WATCH_MAX_POOLS]


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


def proven_gate_market(row, expected_market):
    """Return exact Gate market id only when it is present in the verified CEX row."""
    expected = str(expected_market or "").upper().replace("-", "_").replace("/", "_").strip()
    if not expected:
        return ""
    for market in row.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if str(market.get("exchange") or "").lower().strip() != "gate":
            continue
        if market.get("volume_comparable_usd_like", True) is False:
            continue
        try:
            price = float(market.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            continue
        market_id = str(market.get("market_id") or "").upper().replace("-", "_").replace("/", "_").strip()
        symbol = str(market.get("symbol") or "").upper().replace("-", "").replace("_", "").replace("/", "").strip()
        expected_symbol = expected.replace("_", "")
        if market_id == expected or symbol == expected_symbol:
            return expected
    return ""


def main():
    spot = load(SPOT, {"candidates": []})
    cex_identity = load(CEX_SPOT_IDENTITY, {"candidates": []})
    alpha = load(ALPHA, {"candidates": []})
    kol = load(KOL, {"candidates": []})
    buy_registry = load(BUY_REGISTRY, {"entries": {}})
    bootstrap = load(BOOTSTRAP, {"candidates": []})
    event_doc = load(EVENTS, {"version": 3, "events": []})
    out = []
    seen = set()
    current = datetime.now(timezone.utc)
    stale_alpha_excluded = 0
    invalid_time_alpha_excluded = 0
    canonical_gate_market_suppressed = 0
    cex_market_exact_identity_recovered = 0

    gate_spot_by_identity = {}
    gate_spot_by_market = {}
    gate_spot_by_base = {}
    for gate_row in spot.get("candidates") or []:
        if not isinstance(gate_row, dict):
            continue
        market = str(gate_row.get("currency_pair") or "").upper().strip()
        base = str(gate_row.get("symbol") or "").upper().strip()
        if market:
            gate_spot_by_market[market] = gate_row
        if base:
            gate_spot_by_base[base] = gate_row
        if gate_row.get("identity_status") != "RESOLVED_EXACT":
            continue
        gate_ident = ident(gate_row)
        if gate_ident:
            gate_spot_by_identity[gate_ident[3]] = gate_row

    cex_identity_by_base = {}
    for cex_row in cex_identity.get("candidates") or []:
        if not isinstance(cex_row, dict):
            continue
        base = str(
            cex_row.get("base_symbol")
            or str(cex_row.get("symbol") or "").upper().removesuffix("USDT")
        ).upper().strip()
        if base:
            cex_identity_by_base[base] = cex_row

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
        base = str(
            row.get("base_symbol")
            or str(row.get("symbol") or "").upper().removesuffix("USDT")
        ).upper().strip()
        gate_market = f"{base}_USDT" if base else ""
        # One Gate market must have one canonical actionable candidate. Suppress
        # the multi-venue representation only when the Gate row can itself stay
        # actionable/watchable (resolved exact, >=25% mover, or top-10). Otherwise
        # retain the verified multi-venue DEX identity so weak-but-valid candidates
        # are not lost merely because Gate also lists the ticker.
        gate_row = gate_spot_by_market.get(gate_market) if gate_market else None
        gate_can_own_market = False
        if isinstance(gate_row, dict):
            gate_change = float(
                gate_row.get("discovery_momentum_change_pct")
                or gate_row.get("change_24h_pct")
                or 0
            )
            gate_first_change = float(gate_row.get("first_seen_change_24h_pct") or 0)
            gate_rank = int(gate_row.get("positive_gainer_rank") or 999999)
            gate_can_own_market = bool(
                gate_row.get("identity_status") == "RESOLVED_EXACT"
                or max(gate_change, gate_first_change) >= 25.0
                or gate_rank <= 10
            )
            if gate_can_own_market:
                gate_has_exact_asset = bool(
                    gate_row.get("identity_status") == "RESOLVED_EXACT"
                    and asset_ident(gate_row)
                )
                same_gate_asset = bool(
                    gate_has_exact_asset
                    and asset_ident(row)
                    and asset_ident(gate_row) == asset_ident(row)
                )
                # A Gate ticker/market can suppress another exact identity only when
                # Gate itself has already proven a chain+contract. If Gate is still
                # CEX-only, the independently verified exact identity must survive.
                if gate_has_exact_asset and not same_gate_asset:
                    canonical_gate_market_suppressed += 1
                    continue
                if same_gate_asset:
                    canonical_gate_market_suppressed += 1
        if row.get("identity_status") != "DEX_VERIFIED" or row.get("identity_verified") is not True:
            continue
        if row.get("execution_pair_price_coherent") is not True:
            continue
        if row.get("market_age_verified") is not True:
            continue
        milestone = cex_signal_milestone(row)
        primary_pair = norm_addr(
            chain_name(row.get("chain")),
            row.get("pair_address"),
        )
        gate_has_exact_asset = bool(
            isinstance(gate_row, dict)
            and gate_row.get("identity_status") == "RESOLVED_EXACT"
            and asset_ident(gate_row)
        )
        same_gate_asset = bool(
            gate_has_exact_asset
            and asset_ident(row)
            and asset_ident(gate_row) == asset_ident(row)
        )
        gate_pair = (
            norm_addr(chain_name(gate_row.get("network") or gate_row.get("chain")), gate_row.get("pair"))
            if same_gate_asset
            else ""
        )
        verified_gate_market = proven_gate_market(row, gate_market)
        if not verified_gate_market and same_gate_asset and isinstance(gate_row, dict):
            verified_gate_market = str(gate_row.get("currency_pair") or "").upper().strip()
        if verified_gate_market and isinstance(gate_row, dict) and not gate_has_exact_asset:
            cex_market_exact_identity_recovered += 1
        pools = verified_asset_pools(row)
        for pool_rank, pool in enumerate(pools, start=1):
            i = ident(pool)
            if not i or i[3] in seen:
                continue
            # The Gate-resolved exact pair remains the canonical candidate and is
            # added by the Gate loop below. Keep its sibling pools as independent
            # monitors of the same contract so ignition on WBNB/USDT/etc. is seen.
            if gate_can_own_market and gate_pair and i[2] == gate_pair:
                continue

            exact_gate_exec = gate_spot_by_identity.get(i[3]) or {}
            currency_pair = ""
            if exact_gate_exec.get("currency_pair"):
                currency_pair = str(exact_gate_exec.get("currency_pair") or "").upper().strip()
            elif verified_gate_market:
                currency_pair = verified_gate_market
            seen.add(i[3])
            out.append({
                "candidate_type": "CEX_SPOT_DISCOVERY",
                "symbol": str(row.get("symbol") or "").upper(),
                "network": pool.get("network"),
                "contract": pool.get("contract"),
                "pair": pool.get("pair"),
                "dex_url": pool.get("dex_url") or "",
                "source": (
                    "CEX Spot Multi-Venue Exact Identity"
                    if i[2] == primary_pair
                    else "CEX Spot Asset Multi-Pool Exact Identity"
                ),
                "exchange": "gate" if currency_pair else None,
                "currency_pair": currency_pair or None,
                "execution_identity_scope": (
                    "EXACT_CHAIN_CONTRACT_PAIR_PLUS_CEX_MARKET"
                    if currency_pair
                    else "EXACT_CHAIN_CONTRACT_PAIR"
                ),
                "cex_market_identity_recovered": bool(
                    currency_pair
                    and isinstance(gate_row, dict)
                    and gate_row.get("identity_status") != "RESOLVED_EXACT"
                ),
                "first_seen_at": milestone.get("observed_at") or row.get("identity_attempted_at"),
                "first_seen_price": milestone.get("reference_price") or pool.get("price_usd"),
                "first_seen_change_24h_pct": milestone.get("reference_change_24h_pct"),
                "discovery_price": pool.get("price_usd") or milestone.get("reference_price"),
                "change_24h_pct": row.get("change_24h_max_pct"),
                "quote_volume_24h_usd": max_cex_turnover(row),
                "positive_gainer_rank": row.get("leaderboard_best_rank"),
                "dex_liquidity_usd": pool.get("liquidity_usd"),
                "spot_revival_score": row.get("spot_revival_score"),
                "coherent_confirmations": row.get("coherent_confirmations"),
                "identity_key": i[3],
                "asset_identity_key": asset_ident(pool),
                "multi_pool_watch": True,
                "asset_pool_rank": pool_rank,
                "asset_pool_role": "PRIMARY" if i[2] == primary_pair else "SIBLING",
                "asset_pool_count": int(row.get("dex_pool_count") or len(pools)),
                "asset_total_dex_liquidity_usd": row.get("dex_total_liquidity_usd"),
                "pool_provider": pool.get("provider"),
            })

    for row in spot.get("candidates") or []:
        if row.get("status") != "IDENTITY_RESOLVED" or row.get("identity_status") != "RESOLVED_EXACT":
            continue
        if float(row.get("dex_liquidity_usd") or 0) <= 0:
            continue
        i = ident(row)
        if not i or i[3] in seen:
            continue

        cex_hist = cex_identity_by_base.get(str(row.get("symbol") or "").upper()) or {}
        milestone = cex_signal_milestone(cex_hist) if cex_hist else {}
        gate_first_at = parse_ts(row.get("first_seen_at"))
        cex_first_at = parse_ts(milestone.get("observed_at"))
        use_cex_anchor = bool(
            cex_first_at is not None
            and (gate_first_at is None or cex_first_at < gate_first_at)
            and milestone.get("reference_price") is not None
        )
        merged_first_seen_at = milestone.get("observed_at") if use_cex_anchor else row.get("first_seen_at")
        merged_first_seen_price = milestone.get("reference_price") if use_cex_anchor else row.get("first_seen_price")
        merged_first_seen_change = milestone.get("reference_change_24h_pct") if use_cex_anchor else row.get("first_seen_change_24h_pct")

        seen.add(i[3])
        out.append({
            "candidate_type": "GATE_SPOT_DISCOVERY",
            "symbol": str(row.get("symbol") or "").upper(),
            "network": row.get("network"),
            "contract": row.get("contract"),
            "pair": row.get("pair"),
            "dex_url": row.get("dex_url") or "",
            "source": (
                "Gate New Listing"
                if bool(row.get("new_listing_fast_lane") or recent_gate_listing(row))
                else "Gate Spot"
            ),
            "source_url": row.get("source_url") or "",
            "exchange": "gate",
            "currency_pair": row.get("currency_pair"),
            "execution_identity_scope": "EXACT_CHAIN_CONTRACT_PAIR_PLUS_CEX_MARKET",
            "first_seen_at": merged_first_seen_at,
            "first_seen_price": merged_first_seen_price,
            "first_seen_change_24h_pct": merged_first_seen_change,
            "first_seen_quote_volume_24h_usd": row.get("first_seen_quote_volume_24h_usd"),
            "discovery_price": row.get("discovery_price"),
            "change_24h_pct": row.get("change_24h_pct"),
            "discovery_momentum_change_pct": row.get("discovery_momentum_change_pct"),
            "gain_from_first_seen_pct": row.get("gain_from_first_seen_pct"),
            "quote_volume_24h_usd": row.get("quote_volume_24h_usd"),
            "positive_gainer_rank": row.get("positive_gainer_rank"),
            "dex_liquidity_usd": row.get("dex_liquidity_usd"),
            "identity_key": i[3],
            "asset_identity_key": asset_ident(row),
            "multi_pool_watch": True,
            "asset_pool_role": "CANONICAL_EXECUTION",
            "asset_pool_rank": 1,
            "asset_pool_count": int((cex_hist.get("dex_pool_count") if isinstance(cex_hist, dict) else 0) or 1),
            "asset_total_dex_liquidity_usd": (
                cex_hist.get("dex_total_liquidity_usd")
                if isinstance(cex_hist, dict)
                else None
            ),
            "identity_source": row.get("identity_source"),
            "identity_reason": row.get("identity_reason"),
            "merged_cex_identity_history": bool(use_cex_anchor),
            "merged_cex_history_symbol": cex_hist.get("symbol") if use_cex_anchor else None,
            "native_asset_proxy": bool(row.get("native_asset_proxy")),
            "native_asset_coingecko_id": row.get("native_asset_coingecko_id"),
            "research_only_identity": bool(row.get("research_only_identity")),
            "buy_start": row.get("buy_start"),
            "new_listing_fast_lane": bool(row.get("new_listing_fast_lane") or recent_gate_listing(row)),
            "gate_pair_type": row.get("gate_pair_type"),
            "gate_st_tag": bool(row.get("gate_st_tag")),
            "gate_special_surface": bool(row.get("gate_special_surface")),
        })

    # Strong CEX movers that do not expose a supported on-chain contract still
    # receive an exact venue-market identity. This keeps BRC-20/native/unsupported
    # chain assets observable without pretending they have a DEX identity.
    for row in spot.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        if row.get("identity_status") == "RESOLVED_EXACT":
            continue
        change = float(row.get("discovery_momentum_change_pct") or row.get("change_24h_pct") or 0)
        rank = int(row.get("positive_gainer_rank") or 999999)
        first_change = float(row.get("first_seen_change_24h_pct") or change or 0)
        new_listing_fast_lane = bool(row.get("new_listing_fast_lane") or recent_gate_listing(row))
        if max(change, first_change) < 25.0 and rank > 10 and not new_listing_fast_lane:
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
            "source": "Gate New Listing" if new_listing_fast_lane else "Gate Spot",
            "source_url": row.get("source_url") or "",
            "first_seen_at": row.get("first_seen_at"),
            "first_seen_price": row.get("first_seen_price") or row.get("discovery_price"),
            "first_seen_change_24h_pct": row.get("first_seen_change_24h_pct"),
            "first_seen_quote_volume_24h_usd": row.get("first_seen_quote_volume_24h_usd"),
            "discovery_price": row.get("discovery_price"),
            "change_24h_pct": row.get("change_24h_pct"),
            "discovery_momentum_change_pct": row.get("discovery_momentum_change_pct"),
            "gain_from_first_seen_pct": row.get("gain_from_first_seen_pct"),
            "quote_volume_24h_usd": row.get("quote_volume_24h_usd"),
            "positive_gainer_rank": row.get("positive_gainer_rank"),
            "identity_key": cex_key,
            "identity_reason": row.get("identity_reason"),
            "research_only_identity": False,
            "telegram_policy": "FINAL_BUY_ONLY",
            "buy_start": row.get("buy_start"),
            "new_listing_fast_lane": new_listing_fast_lane,
            "gate_pair_type": row.get("gate_pair_type"),
            "gate_st_tag": bool(row.get("gate_st_tag")),
            "gate_special_surface": bool(row.get("gate_special_surface")),
        })

    for row in kol.get("candidates") or []:
        if not isinstance(row, dict) or row.get("status") != "GATED_RESEARCH_CANDIDATE":
            continue
        i = ident(row)
        if not i:
            continue
        deep = bool(row.get("emergency_deep_scan"))
        kol_evidence = {
            "signal_state": row.get("signal_state"),
            "signal_event_id": row.get("signal_event_id"),
            "independent_groups_15m": row.get("independent_groups_15m"),
            "independent_groups_30m": row.get("independent_groups_30m"),
            "independent_groups_60m": row.get("independent_groups_60m"),
            "independent_groups_under_100k": row.get("independent_groups_under_100k"),
            "wallet_names": row.get("wallet_names") or [],
            "market_cap_usd": row.get("market_cap_usd"),
            "emergency_deep_scan": deep,
            "automatic_buy": False,
            "production_promotion_allowed": False,
        }
        if i[3] in seen:
            existing = next((x for x in out if x.get("identity_key") == i[3]), None)
            if existing is not None:
                existing["early_kol_convergence"] = kol_evidence
                existing["deep_investigation"] = bool(existing.get("deep_investigation") or deep)
                existing["full_intelligence"] = bool(existing.get("full_intelligence") or deep)
                existing["collector_priority"] = min(int(existing.get("collector_priority") or 9), 1 if deep else 2)
                if deep:
                    existing["priority"] = "HIGHEST"
                    existing["close_watch"] = "HIGHEST"
            continue
        seen.add(i[3])
        out.append({
            "candidate_type": "EARLY_KOL_CONVERGENCE",
            "symbol": str(row.get("symbol") or "KOL").upper(),
            "network": row.get("network"),
            "contract": row.get("contract"),
            "pair": row.get("pair"),
            "dex_url": row.get("dex_url") or "",
            "source": row.get("source") or "Wallet500 Early KOL Convergence",
            "source_url": row.get("dex_url") or "",
            "first_seen_at": row.get("first_seen_at") or row.get("observed_at"),
            "discovery_price": row.get("price_usd"),
            "dex_liquidity_usd": row.get("liquidity_usd"),
            "market_cap_usd": row.get("market_cap_usd"),
            "identity_key": i[3],
            "priority": "HIGHEST" if deep else "HIGH",
            "close_watch": "HIGHEST" if deep else "HIGH",
            "collector_priority": 1 if deep else 2,
            "deep_investigation": deep,
            "full_intelligence": deep,
            "research_only": True,
            "automatic_buy": False,
            "production_promotion_allowed": False,
            "requires_full_wallet500_gates": True,
            "early_kol_convergence": kol_evidence,
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
        0 if x["candidate_type"] == "BUY_ZONE" else 1 if x["candidate_type"] == "EARLY_KOL_CONVERGENCE" else 2 if x["candidate_type"] == "NEW_CHAIN_BOOTSTRAP" else 3 if x["candidate_type"] in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY"} else 4,
        (
            x.get("alpha_age_minutes", 999999)
            if x["candidate_type"] == "PUBLIC_ALPHA"
            else (
                -1
                if x.get("new_listing_fast_lane") is True
                else (x.get("positive_gainer_rank") or 999999)
            )
        ),
        -(float(x.get("dex_liquidity_usd") or 0)),
    ))
    doc = {
        "version": 2,
        "generated_at": now(),
        "mode": "EXACT_IDENTITY_ASSET_MULTI_POOL_RESEARCH",
        "counts": {
            "buy_zone": sum(x["candidate_type"] == "BUY_ZONE" for x in out),
            "cex_spot": sum(x["candidate_type"] == "CEX_SPOT_DISCOVERY" for x in out),
            "gate_spot": sum(x["candidate_type"] == "GATE_SPOT_DISCOVERY" for x in out),
            "cex_market": sum(x["candidate_type"] == "CEX_MARKET_DISCOVERY" for x in out),
            "new_chain_bootstrap": sum(x["candidate_type"] == "NEW_CHAIN_BOOTSTRAP" for x in out),
            "public_alpha": sum(x["candidate_type"] == "PUBLIC_ALPHA" for x in out),
            "early_kol_convergence": sum(x["candidate_type"] == "EARLY_KOL_CONVERGENCE" for x in out),
            "early_kol_deep_scan": sum(x["candidate_type"] == "EARLY_KOL_CONVERGENCE" and bool((x.get("early_kol_convergence") or {}).get("emergency_deep_scan")) for x in out),
            "public_alpha_stale_excluded": stale_alpha_excluded,
            "public_alpha_invalid_time_excluded": invalid_time_alpha_excluded,
            "canonical_gate_market_suppressed": canonical_gate_market_suppressed,
            "cex_market_exact_identity_recovered": cex_market_exact_identity_recovered,
            "multi_pool_watch_candidates": sum(bool(x.get("multi_pool_watch")) for x in out),
            "multi_pool_sibling_candidates": sum(x.get("asset_pool_role") == "SIBLING" for x in out),
            "public_alpha_live_window_minutes": PUBLIC_ALPHA_LIVE_WINDOW_MINUTES,
            "total": len(out),
        },
        "candidates": out[:120],
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    events = [e for e in (event_doc.get("events") or []) if isinstance(e, dict)]
    existing = {str(e.get("canonical_event_id") or "") for e in events}
    added = 0
    for candidate in out:
        ctype = candidate["candidate_type"]
        if ctype not in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "NEW_CHAIN_BOOTSTRAP", "EARLY_KOL_CONVERGENCE"}:
            continue
        is_bootstrap = ctype == "NEW_CHAIN_BOOTSTRAP"
        is_kol = ctype == "EARLY_KOL_CONVERGENCE"
        if is_kol:
            kol = candidate.get("early_kol_convergence") or {}
            cid = "early-kol-convergence:" + str(kol.get("signal_event_id") or candidate["identity_key"])
        else:
            cid = ("new-chain-bootstrap:" if is_bootstrap else "cex-spot-discovery:") + candidate["identity_key"]
        if cid in existing:
            continue
        change = max(0.0, float(candidate.get("change_24h_pct") or 0))
        if is_kol:
            kol = candidate.get("early_kol_convergence") or {}
            strength = min(95.0, 45.0 + 12.0 * float(kol.get("independent_groups_60m") or 0))
            confidence = 78 if kol.get("emergency_deep_scan") else 68
            family = "wallet_flow"
            kind = "early_kol_deep_scan" if kol.get("emergency_deep_scan") else "early_kol_convergence_watch"
            subject = (
                f"independent_60m={kol.get('independent_groups_60m')} "
                f"under_100k={kol.get('independent_groups_under_100k')} "
                f"wallets={','.join(kol.get('wallet_names') or [])}"
            )
        else:
            strength = min(85.0, max(25.0, float(candidate.get("bootstrap_score") or 0))) if is_bootstrap else min(75.0, 20.0 + change * 0.35)
            confidence = 72
            family = "catalyst_news" if is_bootstrap else "search_discovery"
            kind = "new_chain_bootstrap" if is_bootstrap else "cex_spot_mover"
            subject = (
                f"bootstrap_score={candidate.get('bootstrap_score')} chain={candidate.get('network')}"
                if is_bootstrap
                else f"rank={candidate.get('positive_gainer_rank')} change24h={candidate.get('change_24h_pct')}"
            )
        events.append({
            "symbol": candidate["symbol"],
            "network": candidate["network"],
            "contract": candidate["contract"],
            "pair": candidate["pair"],
            "identity_key": candidate["identity_key"],
            "family": family,
            "kind": kind,
            "direction": 1,
            "strength": round(strength, 1),
            "confidence": confidence,
            "source": candidate.get("source") or ("Wallet500 Early KOL Convergence" if is_kol else ("New Chain Bootstrap Radar" if is_bootstrap else "CEX Spot")),
            "source_url": candidate.get("source_url") or "",
            "subject": subject,
            "canonical_event_id": cid,
            "event_time": candidate.get("first_seen_at") or now(),
            "observed_at": now(),
            "free_source": True,
            "research_only": True,
            "identity_verified": True,
            "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR",
            "discovery_price": candidate.get("discovery_price"),
            "change_24h_pct": candidate.get("change_24h_pct"),
            "quote_volume_24h_usd": candidate.get("quote_volume_24h_usd"),
            "rank": candidate.get("positive_gainer_rank"),
            "automatic_buy": False if is_kol else None,
            "requires_full_wallet500_gates": True if is_kol else None,
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
