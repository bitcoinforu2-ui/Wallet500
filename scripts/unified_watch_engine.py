from __future__ import annotations

import json
import os
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import resilient_http
except ImportError:  # package import in pytest / module mode
    from scripts import resilient_http

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/unified-watch-config.json"
STATE = ROOT / "data/unified-watch-state.json"
DYNAMIC = ROOT / "data/unified-dynamic-candidates.json"
INTEL = ROOT / "data/close-watch-intelligence.json"
INTEL_REPORT = ROOT / "data/unified-watch-intelligence-report.json"
EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}
ALERTWORTHY_INTEL_FAMILIES = {
    "wallet_flow",
    "holder_network",
    "attention_social",
    "search_discovery",
    "catalyst_news",
    "fundamental_usage",
    "supply_tokenomics",
    "derivatives",
}
QUARTER_WAVE_REVALIDATION_GAIN_PCT = 25.0


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def chain_name(value):
    raw = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(raw, raw)


def norm_addr(chain, value):
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def exact_identity_key(row):
    chain = chain_name(row.get("chain") or row.get("network"))
    token = norm_addr(chain, row.get("token_address") or row.get("contract") or row.get("mint"))
    pair = norm_addr(chain, row.get("pair_address") or row.get("pair"))
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def candidate_identity_key(row):
    if str(row.get("execution_identity_scope") or "").upper() == "EXACT_CEX_MARKET":
        exchange = str(row.get("exchange") or "").lower().strip()
        market = str(row.get("currency_pair") or "").upper().strip()
        return f"cex:{exchange}:{market}" if exchange and market else ""
    return exact_identity_key(row)


def load_intelligence():
    try:
        doc = json.loads(INTEL.read_text()) if INTEL.exists() else {}
    except Exception:
        doc = {}
    rows = [x for x in (doc.get("tokens") or []) if isinstance(x, dict)]
    return {exact_identity_key(x): x for x in rows if exact_identity_key(x)}, doc


def http_json(url):
    return resilient_http.request_json(
        url,
        timeout=20,
        attempts=4,
        cache_ttl=45,
        user_agent="Wallet500-UnifiedWatch/1.5",
    )


def gate_execution_snapshot(currency_pair):
    market = str(currency_pair or "").upper().strip()
    if not market or not market.endswith("_USDT"):
        raise RuntimeError("GATE_EXACT_MARKET_IDENTITY_MISSING")
    meta = http_json(f"https://api.gateio.ws/api/v4/spot/currency_pairs/{market}")
    if str(meta.get("id") or "").upper() != market:
        raise RuntimeError("GATE_MARKET_IDENTITY_MISMATCH")
    if str(meta.get("trade_status") or "tradable").lower() != "tradable":
        raise RuntimeError("GATE_MARKET_NOT_TRADABLE")
    if str(meta.get("type") or "normal").lower() != "normal":
        raise RuntimeError("GATE_MARKET_NOT_NORMAL_SPOT")

    tickers = http_json(f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={market}")
    ticker = tickers[0] if isinstance(tickers, list) and tickers else {}
    if str(ticker.get("currency_pair") or "").upper() != market:
        raise RuntimeError("GATE_TICKER_IDENTITY_MISMATCH")
    last = float(ticker.get("last") or 0)
    turnover = float(ticker.get("quote_volume") or 0)
    change24 = float(ticker.get("change_percentage") or 0)
    if last <= 0:
        raise RuntimeError("GATE_PRICE_MISSING")

    book = http_json(f"https://api.gateio.ws/api/v4/spot/order_book?currency_pair={market}&limit=100")
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    if not bids or not asks:
        raise RuntimeError("GATE_ORDER_BOOK_MISSING")
    best_bid = float(bids[0][0]); best_ask = float(asks[0][0])
    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        raise RuntimeError("GATE_ORDER_BOOK_INVALID")
    mid = (best_bid + best_ask) / 2.0
    spread_pct = ((best_ask - best_bid) / mid) * 100.0 if mid > 0 else 999.0

    bid_floor = mid * 0.99
    ask_ceiling = mid * 1.01
    bid_depth = sum(float(p) * float(q) for p, q in bids if float(p) >= bid_floor)
    ask_depth = sum(float(p) * float(q) for p, q in asks if float(p) <= ask_ceiling)
    total_depth = bid_depth + ask_depth
    imbalance = (bid_depth + 1.0) / (ask_depth + 1.0)

    return {
        "cex_execution_verified": True,
        "cex_execution_scope": "EXACT_CEX_MARKET",
        "cex_exchange": "gate",
        "cex_currency_pair": market,
        "cex_price": last,
        "cex_turnover_24h_usd": turnover,
        "cex_change_24h_pct": change24,
        "cex_orderbook_spread_pct": spread_pct,
        "cex_bid_depth_1pct_usd": bid_depth,
        "cex_ask_depth_1pct_usd": ask_depth,
        "cex_depth_1pct_usd": total_depth,
        "cex_bid_ask_depth_ratio": imbalance,
    }


def live_cex_market(t):
    snap = gate_execution_snapshot(t.get("currency_pair"))
    depth = float(snap.get("cex_depth_1pct_usd") or 0)
    return {
        "price": float(snap["cex_price"]),
        "liquidity": depth,
        "volume_h1": 0.0,
        "volume_h24": float(snap.get("cex_turnover_24h_usd") or 0),
        "buys_h1": 0,
        "sells_h1": 0,
        "change_h1": 0.0,
        "change_h24": float(snap.get("cex_change_24h_pct") or 0),
        "spread_pct": float(snap.get("cex_orderbook_spread_pct") or 999),
        "observed_at": now_iso(),
        **snap,
    }


def live_exact_pair(t, max_spread):
    n = str(t["network"]).strip().lower()
    canonical_chain = chain_name(n)
    pair = norm_addr(canonical_chain, t["pair"])
    ca = norm_addr(canonical_chain, t["contract"])

    gt = http_json(f"https://api.geckoterminal.com/api/v2/networks/{n}/pools/{t['pair']}")
    o = gt.get("data") or {}
    a = o.get("attributes") or {}
    r = o.get("relationships") or {}
    b = (((r.get("base_token") or {}).get("data") or {}).get("id") or "")
    q = (((r.get("quote_token") or {}).get("data") or {}).get("id") or "")
    b_addr = str(b).split("_")[-1]
    q_addr = str(q).split("_")[-1]
    if norm_addr(canonical_chain, b_addr) == ca:
        gp = float(a.get("base_token_price_usd") or 0)
    elif norm_addr(canonical_chain, q_addr) == ca:
        gp = float(a.get("quote_token_price_usd") or 0)
    else:
        raise RuntimeError("EXACT_PAIR_IDENTITY_MISMATCH_GT")
    if gp <= 0:
        raise RuntimeError("GT_PRICE_MISSING")

    vol = a.get("volume_usd") or {}
    tx = a.get("transactions") or {}
    h1 = tx.get("h1") or {}
    ch = a.get("price_change_percentage") or {}
    g = {
        "price": gp,
        "liquidity": float(a.get("reserve_in_usd") or 0),
        "volume_h1": float(vol.get("h1") or 0),
        "volume_h24": float(vol.get("h24") or 0),
        "buys_h1": int(h1.get("buys") or 0),
        "sells_h1": int(h1.get("sells") or 0),
        "change_h1": float(ch.get("h1") or 0),
        "change_h24": float(ch.get("h24") or 0),
    }
    if g["liquidity"] <= 0:
        raise RuntimeError("GT_LIQUIDITY_MISSING")

    dsnet = "ethereum" if n == "eth" else n
    ds = http_json(f"https://api.dexscreener.com/latest/dex/pairs/{dsnet}/{t['pair']}")
    p = next(
        (
            x
            for x in (ds.get("pairs") or [])
            if chain_name(x.get("chainId")) == canonical_chain
            and norm_addr(canonical_chain, x.get("pairAddress")) == pair
        ),
        None,
    )
    if not p:
        raise RuntimeError("EXACT_PAIR_MISSING_DS")
    base = norm_addr(canonical_chain, (p.get("baseToken") or {}).get("address"))
    quote = norm_addr(canonical_chain, (p.get("quoteToken") or {}).get("address"))
    if ca not in {base, quote}:
        raise RuntimeError("DS_TOKEN_NOT_IN_EXACT_PAIR_FAIL_CLOSED")
    dp = float(p.get("priceUsd") or 0)
    if dp <= 0:
        raise RuntimeError("DS_PRICE_MISSING")

    med = statistics.median([gp, dp])
    spread = ((max(gp, dp) - min(gp, dp)) / med) * 100 if med else 999
    if spread > max_spread:
        raise RuntimeError(f"SOURCE_DATA_MISMATCH:{spread:.3f}%")
    return {
        **g,
        "price": med,
        "gt_price": gp,
        "ds_price": dp,
        "spread_pct": spread,
        "observed_at": now_iso(),
    }


def money(v):
    v = float(v)
    if abs(v) >= 1e6:
        return f"${v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.2f}"


def send(msg):
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        raise RuntimeError("TELEGRAM_SECRETS_NOT_CONFIGURED")
    data = urllib.parse.urlencode(
        {"chat_id": chat, "text": msg[:4000], "disable_web_page_preview": "true"}
    ).encode()
    body = json.load(
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{bot}/sendMessage",
                data=data,
                method="POST",
            ),
            timeout=20,
        )
    )
    if not body.get("ok"):
        raise RuntimeError("TELEGRAM_SEND_FAILED")


def dynamic_candidates(persisted_tokens=None):
    if not DYNAMIC.exists():
        return []
    try:
        d = json.loads(DYNAMIC.read_text())
    except Exception:
        return []

    rows = []
    seen = set()
    for c in d.get("candidates") or []:
        ctype = str(c.get("candidate_type") or "").upper()
        if ctype not in {"BUY_ZONE", "PUBLIC_ALPHA", "GATE_SPOT_DISCOVERY", "CEX_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY", "NEW_CHAIN_BOOTSTRAP"}:
            continue
        ca = str(c.get("contract") or "")
        pair = str(c.get("pair") or "")
        network = str(c.get("network") or "")
        if ctype == "CEX_MARKET_DISCOVERY":
            key = candidate_identity_key(c)
        else:
            if not ca or not pair or not network:
                continue
            key = exact_identity_key({"network": network, "contract": ca, "pair": pair})
        if not key or key in seen:
            continue
        seen.add(key)
        row = dict(c)
        row["_identity_key"] = key
        row["_candidate_type"] = ctype
        rows.append(row)

    # Keep exact-identity spot discovery broad, but bound the expensive watcher.
    # Multi-CEX exact identities and legacy Gate exact identities are retained.
    # Public-alpha gets the remaining balanced slice: freshest calls plus the
    # highest-liquidity calls. Final BUY targets are never displaced.
    buy_zone = [x for x in rows if x["_candidate_type"] == "BUY_ZONE"]
    spot = [
        x for x in rows
        if x["_candidate_type"] in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY"}
    ]
    bootstrap = [x for x in rows if x["_candidate_type"] == "NEW_CHAIN_BOOTSTRAP"]
    bootstrap = sorted(
        bootstrap,
        key=lambda x: (float(x.get("bootstrap_score") or 0), float(x.get("dex_liquidity_usd") or 0)),
        reverse=True,
    )[:12]
    alpha = [x for x in rows if x["_candidate_type"] == "PUBLIC_ALPHA"]
    dynamic_cap = 48
    alpha_budget = max(0, dynamic_cap - len(buy_zone) - len(bootstrap) - len(spot))

    def _liq(x):
        try:
            return float(x.get("dex_liquidity_usd") or 0)
        except (TypeError, ValueError):
            return 0.0

    newest = sorted(alpha, key=lambda x: str(x.get("first_seen_at") or ""), reverse=True)
    liquid = sorted(alpha, key=_liq, reverse=True)
    chosen = []
    chosen_ids = set()
    fresh_budget = min(alpha_budget, max(8, (alpha_budget * 2) // 3))
    for bucket, limit in ((newest, fresh_budget), (liquid, alpha_budget)):
        for x in bucket:
            if len(chosen) >= alpha_budget or (bucket is newest and len(chosen) >= limit):
                break
            key = x["_identity_key"]
            if key in chosen_ids:
                continue
            chosen_ids.add(key)
            chosen.append(x)

    selected = buy_zone + bootstrap + spot + chosen
    out = []
    for c in selected:
        ctype = c["_candidate_type"]
        out.append(
            {
                "symbol": str(c.get("symbol") or "DYNAMIC").upper(),
                "network": str(c.get("network") or ""),
                "contract": str(c.get("contract") or ""),
                "pair": str(c.get("pair") or ""),
                "exchange": c.get("exchange"),
                "currency_pair": c.get("currency_pair"),
                "execution_identity_scope": c.get("execution_identity_scope"),
                "dex_url": c.get("dex_url") or "",
                "up_levels": [],
                "down_levels": [],
                "liquidity_drop_pct": 25,
                "volume_acceleration_multiple": 2.0,
                "min_volume_h1_for_momentum": 0,
                "dynamic_buy_candidate": ctype == "BUY_ZONE",
                "dynamic_alpha_candidate": ctype == "PUBLIC_ALPHA",
                "dynamic_bootstrap_candidate": ctype == "NEW_CHAIN_BOOTSTRAP",
                "dynamic_spot_candidate": ctype in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY"},
                "dynamic_cex_market_candidate": ctype == "CEX_MARKET_DISCOVERY",
                "candidate_type": ctype,
                "priority": c.get("priority") or ("HIGHEST" if ctype == "BUY_ZONE" else None),
                "close_watch": c.get("close_watch") or ("HIGHEST" if ctype == "BUY_ZONE" else None),
                "collector_priority": c.get("collector_priority", 0 if ctype == "BUY_ZONE" else None),
                "deep_investigation": bool(c.get("deep_investigation") or ctype in {"BUY_ZONE", "NEW_CHAIN_BOOTSTRAP"}),
                "full_intelligence": bool(c.get("full_intelligence") or ctype in {"BUY_ZONE", "NEW_CHAIN_BOOTSTRAP"}),
                "derivatives_intelligence": bool(c.get("derivatives_intelligence")),
                "derivatives_symbol": c.get("derivatives_symbol"),
                "buy_zone_price_usd": c.get("buy_zone_price_usd"),
                "first_buy_at": c.get("first_buy_at"),
                "last_buy_at": c.get("last_buy_at"),
                "source": c.get("source") or "",
                "source_url": c.get("source_url") or "",
                "first_seen_at": c.get("first_seen_at"),
                "first_seen_price": c.get("first_seen_price"),
                "first_seen_change_24h_pct": c.get("first_seen_change_24h_pct"),
                "first_seen_quote_volume_24h_usd": c.get("first_seen_quote_volume_24h_usd"),
                "discovery_price": c.get("discovery_price"),
                "change_24h_pct": c.get("change_24h_pct"),
                "discovery_momentum_change_pct": c.get("discovery_momentum_change_pct"),
                "gain_from_first_seen_pct": c.get("gain_from_first_seen_pct"),
                "quote_volume_24h_usd": c.get("quote_volume_24h_usd"),
                "positive_gainer_rank": c.get("positive_gainer_rank"),
                "dex_liquidity_usd": c.get("dex_liquidity_usd"),
                "bootstrap_score": c.get("bootstrap_score"),
                "bootstrap_reasons": c.get("bootstrap_reasons") or [],
                "bootstrap_final_buy_lane": bool(c.get("bootstrap_final_buy_lane")),
            }
        )

    # Once a CEX spot candidate crosses the +25% verified-price threshold it must
    # stay watched even if it later drops out of the live mover leaderboard.
    current_ids = {candidate_identity_key(x) for x in out if candidate_identity_key(x)}
    for prev in (persisted_tokens or {}).values():
        if not isinstance(prev, dict):
            continue
        if prev.get("dynamic_spot_candidate") is not True:
            continue
        if prev.get("quarter_wave_revalidation_armed") is not True:
            continue
        key = candidate_identity_key(prev)
        if not key or key in current_ids:
            continue
        ctype = str(prev.get("candidate_type") or "GATE_SPOT_DISCOVERY").upper()
        if ctype not in {"CEX_SPOT_DISCOVERY", "GATE_SPOT_DISCOVERY", "CEX_MARKET_DISCOVERY"}:
            ctype = "GATE_SPOT_DISCOVERY"
        out.append({
            "symbol": str(prev.get("symbol") or "CEX").upper(),
            "network": str(prev.get("network") or ""),
            "contract": str(prev.get("contract") or ""),
            "pair": str(prev.get("pair") or ""),
            "exchange": prev.get("exchange"),
            "currency_pair": prev.get("currency_pair"),
            "execution_identity_scope": prev.get("execution_identity_scope"),
            "dex_url": prev.get("dex_url") or "",
            "up_levels": [],
            "down_levels": [],
            "liquidity_drop_pct": 25,
            "volume_acceleration_multiple": 2.0,
            "min_volume_h1_for_momentum": 0,
            "dynamic_buy_candidate": False,
            "dynamic_alpha_candidate": False,
            "dynamic_bootstrap_candidate": False,
            "dynamic_spot_candidate": True,
            "dynamic_cex_market_candidate": ctype == "CEX_MARKET_DISCOVERY",
            "candidate_type": ctype,
            "priority": "HIGH",
            "close_watch": "HIGHEST",
            "collector_priority": 1,
            "deep_investigation": True,
            "full_intelligence": True,
            "source": prev.get("source") or "Persisted +25% CEX Revalidation",
            "source_url": prev.get("source_url") or "",
            "first_seen_at": prev.get("first_seen_at"),
            "first_seen_price": prev.get("first_seen_price") or prev.get("quarter_wave_anchor_price"),
            "first_seen_change_24h_pct": prev.get("first_seen_change_24h_pct"),
            "first_seen_quote_volume_24h_usd": prev.get("first_seen_quote_volume_24h_usd"),
            "discovery_price": prev.get("discovery_price"),
            "change_24h_pct": prev.get("change_24h_pct"),
            "discovery_momentum_change_pct": prev.get("discovery_momentum_change_pct"),
            "gain_from_first_seen_pct": prev.get("gain_from_first_seen_pct"),
            "quote_volume_24h_usd": prev.get("cex_quote_volume_24h_usd"),
            "positive_gainer_rank": prev.get("positive_gainer_rank"),
            "dex_liquidity_usd": prev.get("liquidity"),
            "quarter_wave_persisted": True,
        })
        current_ids.add(key)
    return out

def fusion_summary(row, notable_min_raw=0.30):
    if not row:
        return {
            "status": "NOT_AVAILABLE",
            "score": None,
            "label": "NOT_AVAILABLE",
            "families": 0,
            "hard_risks": [],
            "family_scores": {},
            "notable_evidence": [],
            "updated_at": None,
            "evidence_age_minutes": None,
            "current_evidence_count": 0,
        }

    notable = set()
    for e in row.get("evidence") or []:
        if not isinstance(e, dict) or not e.get("current"):
            continue
        direction = int(e.get("direction") or 0)
        raw = abs(float(e.get("raw") or 0))
        fam = str(e.get("family") or "")
        kind = str(e.get("kind") or "")
        if direction and fam and kind and raw >= notable_min_raw:
            notable.add(f"{fam}:{kind}:{direction}")

    return {
        "status": row.get("status") or "UNKNOWN",
        "score": row.get("score"),
        "label": row.get("label") or "WATCH",
        "families": int(row.get("independent_positive_families") or 0),
        "hard_risks": sorted(set(row.get("hard_risks") or [])),
        "family_scores": dict(row.get("family_scores") or {}),
        "notable_evidence": sorted(notable),
        "updated_at": row.get("updated_at"),
        "freshest_event_at": row.get("freshest_event_at"),
        "evidence_age_minutes": row.get("evidence_age_minutes"),
        "current_evidence_count": int(row.get("current_evidence_count") or 0),
    }


def pct_delta(current, previous):
    try:
        c = float(current)
        p = float(previous)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return (c - p) / abs(p) * 100.0


def order_flow_ratio(snapshot):
    try:
        return (float(snapshot.get("buys_h1") or 0) + 1.0) / (float(snapshot.get("sells_h1") or 0) + 1.0)
    except Exception:
        return 1.0


def alpha_telegram_confirmations(live, fusion, triggers, reasons, policy):
    confirmations = []
    score = fusion.get("score")
    families = int(fusion.get("families") or 0)

    if families >= int(policy.get("alpha_min_positive_families_for_telegram", 2)):
        confirmations.append(f"MULTI_FAMILY_{families}")

    if score is not None and float(score) >= float(policy.get("alpha_min_fusion_score_for_telegram", 12.0)):
        confirmations.append(f"FUSION_SCORE_{float(score):.1f}")

    family_scores = fusion.get("family_scores") or {}
    wallet_holder_min = float(policy.get("alpha_wallet_holder_score_for_telegram", 3.0))
    for fam in ("wallet_flow", "holder_network"):
        fam_score = float(family_scores.get(fam) or 0)
        if fam_score >= wallet_holder_min:
            confirmations.append(f"{fam.upper()}_{fam_score:.1f}")

    for item in fusion.get("notable_evidence") or []:
        fam = str(item).split(":", 1)[0]
        if fam in ALERTWORTHY_INTEL_FAMILIES:
            confirmations.append(f"INTEL_{fam.upper()}")

    min_volume = float(policy.get("alpha_min_volume_h1_for_telegram", 5000.0))
    if "PRICE_PLUS_VOLUME_ACCELERATION" in triggers and float(live.get("volume_h1") or 0) >= min_volume:
        confirmations.append("STRONG_VOLUME_ACCELERATION")

    buys = int(live.get("buys_h1") or 0)
    sells = int(live.get("sells_h1") or 0)
    min_buys = int(policy.get("alpha_min_buys_h1_for_telegram", 15))
    min_ratio = float(policy.get("alpha_min_buy_sell_ratio_for_telegram", 2.0))
    ratio = (buys + 1.0) / (sells + 1.0)
    if buys >= min_buys and ratio >= min_ratio:
        confirmations.append(f"STRONG_BUY_IMBALANCE_{ratio:.1f}X")

    for reason in reasons or []:
        r = str(reason)
        if r.startswith("NEW_INTELLIGENCE:"):
            confirmations.append("NEW_MATERIAL_INTELLIGENCE")
        elif r.startswith("WALLET_FLOW_SHIFT_+"):
            confirmations.append("WALLET_FLOW_SHIFT")
        elif r.startswith("HOLDER_NETWORK_SHIFT_+"):
            confirmations.append("HOLDER_NETWORK_SHIFT")
        elif r.startswith("INTELLIGENCE_SCORE_+"):
            confirmations.append("INTELLIGENCE_SCORE_RISE")

    if "ALPHA_CALL_PLUS_BUY_IMBALANCE" in triggers:
        confirmations.append("ALPHA_PLUS_BUY_IMBALANCE")

    return list(dict.fromkeys(confirmations))


def alpha_telegram_gate(live, fusion, triggers, reasons, risk, policy):
    if risk:
        return True, ["RISK_BYPASS"]
    if not bool(policy.get("alpha_close_watch_require_confirmation", True)):
        return True, ["CONFIRMATION_GATE_DISABLED"]
    confirmations = alpha_telegram_confirmations(live, fusion, triggers, reasons, policy)
    required = max(1, int(policy.get("alpha_min_confirmations_for_telegram", 1)))
    return len(confirmations) >= required, confirmations


def material_change_reasons(last_alert, live, fusion, triggers, policy):
    last_alert = last_alert or {}
    last_fusion = last_alert.get("fusion") or {}
    reasons = []

    current_hard = set(fusion.get("hard_risks") or [])
    previous_hard = set(last_fusion.get("hard_risks") or [])
    new_hard = sorted(current_hard - previous_hard)
    if new_hard:
        reasons.append("NEW_HARD_RISK:" + ",".join(new_hard[:3]))

    current_notable = set(fusion.get("notable_evidence") or [])
    previous_notable = set(last_fusion.get("notable_evidence") or [])
    new_notable = sorted(current_notable - previous_notable)
    high_value_new_notable = [
        x for x in new_notable if x.split(":", 1)[0] in ALERTWORTHY_INTEL_FAMILIES
    ]

    if not last_alert:
        if triggers:
            reasons.append("FIRST_MATERIAL_TRIGGER")
        if high_value_new_notable:
            reasons.append("NEW_INTELLIGENCE:" + ",".join(high_value_new_notable[:3]))
        score = fusion.get("score")
        if score is not None and float(score) >= 55 and int(fusion.get("families") or 0) >= 3:
            reasons.append("INTELLIGENCE_CONFLUENCE")
        return list(dict.fromkeys(reasons))

    previous_triggers = set(last_alert.get("triggers") or [])
    new_triggers = [x for x in triggers if x not in previous_triggers]
    if new_triggers:
        reasons.append("NEW_TRIGGER:" + ",".join(new_triggers[:3]))

    price_change = pct_delta(live.get("price"), last_alert.get("price"))
    if price_change is not None and abs(price_change) >= float(policy.get("price_change_from_last_alert_pct", 8.0)):
        reasons.append(f"PRICE_CHANGE_{price_change:+.1f}%")

    liquidity_change = pct_delta(live.get("liquidity"), last_alert.get("liquidity"))
    if liquidity_change is not None and abs(liquidity_change) >= float(policy.get("liquidity_change_from_last_alert_pct", 20.0)):
        reasons.append(f"LIQUIDITY_CHANGE_{liquidity_change:+.1f}%")

    current_volume = float(live.get("volume_h1") or 0)
    previous_volume = float(last_alert.get("volume_h1") or 0)
    min_volume = float(policy.get("minimum_volume_usd_for_volume_delta", 1000.0))
    multiple = float(policy.get("volume_multiple_from_last_alert", 2.0))
    if previous_volume > 0 and max(current_volume, previous_volume) >= min_volume:
        ratio = current_volume / previous_volume
        if ratio >= multiple:
            reasons.append(f"VOLUME_EXPANSION_{ratio:.1f}X")
        elif ratio <= 1.0 / max(multiple, 1.01):
            reasons.append(f"VOLUME_CONTRACTION_{ratio:.2f}X")

    current_score = fusion.get("score")
    previous_score = last_fusion.get("score")
    if current_score is not None and previous_score is not None:
        score_delta = float(current_score) - float(previous_score)
        if abs(score_delta) >= float(policy.get("intelligence_score_delta", 12.0)):
            reasons.append(f"INTELLIGENCE_SCORE_{score_delta:+.1f}")

    current_label = str(fusion.get("label") or "")
    previous_label = str(last_fusion.get("label") or "")
    if current_label and previous_label and current_label != previous_label:
        if max(float(current_score or 0), float(previous_score or 0)) >= 30:
            reasons.append(f"INTELLIGENCE_LABEL_{previous_label}_TO_{current_label}")

    family_threshold = float(policy.get("wallet_holder_family_score_delta", 3.0))
    current_family_scores = fusion.get("family_scores") or {}
    previous_family_scores = last_fusion.get("family_scores") or {}
    for fam in ("wallet_flow", "holder_network"):
        cur = float(current_family_scores.get(fam) or 0)
        prev = float(previous_family_scores.get(fam) or 0)
        delta = cur - prev
        if abs(delta) >= family_threshold:
            reasons.append(f"{fam.upper()}_SHIFT_{delta:+.1f}")

    if high_value_new_notable:
        reasons.append("NEW_INTELLIGENCE:" + ",".join(high_value_new_notable[:3]))

    current_ratio = order_flow_ratio(live)
    previous_ratio = order_flow_ratio(last_alert)
    if current_ratio >= 2.5 and current_ratio >= previous_ratio * 1.8:
        reasons.append(f"BUY_PRESSURE_SHIFT_{current_ratio:.1f}X")
    elif current_ratio <= 0.4 and current_ratio <= previous_ratio / 1.8:
        reasons.append(f"SELL_PRESSURE_SHIFT_{current_ratio:.2f}X")

    return list(dict.fromkeys(reasons))


def alert_snapshot(live, fusion, triggers):
    return {
        "sent_at": now_iso(),
        "price": live.get("price"),
        "liquidity": live.get("liquidity"),
        "volume_h1": live.get("volume_h1"),
        "buys_h1": live.get("buys_h1"),
        "sells_h1": live.get("sells_h1"),
        "triggers": list(triggers),
        "fusion": {
            "score": fusion.get("score"),
            "label": fusion.get("label"),
            "families": fusion.get("families"),
            "hard_risks": list(fusion.get("hard_risks") or []),
            "family_scores": dict(fusion.get("family_scores") or {}),
            "notable_evidence": list(fusion.get("notable_evidence") or []),
        },
    }


def spot_cex_sensor(t, prev):
    """Bridge CEX discovery telemetry into the exact-pair close-watch lane.

    The baseline is frozen on first observation so a small-cap volume expansion
    is judged relative to its own pre-wave state instead of a fixed $100K bar.
    """
    if not t.get("dynamic_spot_candidate"):
        return {
            "triggers": [],
            "cex_led": False,
            "current_volume_usd": 0.0,
            "baseline_volume_usd": 0.0,
            "baseline_multiple": 0.0,
            "scan_multiple": 0.0,
            "current_rank": None,
        }

    def fnum(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def irank(value):
        try:
            rank = int(float(value))
            return rank if rank > 0 else 999
        except (TypeError, ValueError):
            return 999

    current_volume = fnum(t.get("quote_volume_24h_usd") or t.get("cex_turnover_usd"))
    previous_volume = fnum(prev.get("cex_quote_volume_24h_usd"))
    baseline = fnum(prev.get("cex_quote_volume_baseline_usd"))
    first_seen_volume = fnum(t.get("first_seen_quote_volume_24h_usd"))
    if baseline <= 0:
        baseline = (
            previous_volume
            if previous_volume > 0
            else first_seen_volume
            if first_seen_volume > 0
            else current_volume
        )

    current_rank = irank(t.get("positive_gainer_rank"))
    previous_rank = irank(prev.get("positive_gainer_rank"))
    baseline_multiple = current_volume / baseline if current_volume > 0 and baseline > 0 else 0.0
    scan_multiple = current_volume / previous_volume if current_volume > 0 and previous_volume > 0 else 0.0

    triggers = []
    if current_volume >= 1000 and baseline_multiple >= 4.0 and current_rank <= 15:
        triggers.append("CEX_RELATIVE_VOLUME_SHOCK")
    if current_volume >= 1000 and scan_multiple >= 2.5:
        triggers.append("CEX_VOLUME_ACCELERATION")
    if current_rank <= 10 and previous_rank > 10:
        triggers.append("CEX_TOP10_ENTRY")
    if current_rank <= 3 and previous_rank > 3:
        triggers.append("CEX_TOP3_BREAKOUT")
    if current_rank <= 25 and previous_rank < 999 and current_rank + 5 <= previous_rank:
        triggers.append("CEX_RANK_ACCELERATION")

    return {
        "triggers": list(dict.fromkeys(triggers)),
        "cex_led": bool(triggers),
        "current_volume_usd": current_volume,
        "baseline_volume_usd": baseline,
        "baseline_multiple": round(baseline_multiple, 4),
        "scan_multiple": round(scan_multiple, 4),
        "current_rank": None if current_rank >= 999 else current_rank,
    }


def quarter_wave_revalidation(
    prev,
    live_price,
    observed_at=None,
    threshold_pct=QUARTER_WAVE_REVALIDATION_GAIN_PCT,
    *,
    anchor_price=None,
    anchor_change_24h_pct=None,
    anchor_at=None,
):
    """Arm strict revalidation after a real +25% wave without losing late discoveries."""
    prev = prev if isinstance(prev, dict) else {}

    def fnum(value, default=0.0):
        try:
            return float(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    price = fnum(live_price)
    threshold = float(threshold_pct)
    supplied_anchor = fnum(anchor_price)
    persisted_anchor = fnum(prev.get("quarter_wave_anchor_price"))
    legacy_anchor = fnum(prev.get("first_verified_price") or prev.get("price"))
    # Repository first-seen evidence is the canonical anchor and may repair
    # a bad legacy anchor that was created after the move had already started.
    anchor = supplied_anchor or persisted_anchor or legacy_anchor
    if anchor <= 0 and price > 0:
        anchor = price

    first_change = fnum(
        prev.get("first_seen_change_24h_pct")
        if prev.get("first_seen_change_24h_pct") is not None
        else anchor_change_24h_pct
    )
    gain_pct = ((price / anchor) - 1.0) * 100.0 if price > 0 and anchor > 0 else 0.0
    late_discovery = first_change >= threshold
    gain_trigger = gain_pct >= threshold
    already_armed = bool(prev.get("quarter_wave_revalidation_armed"))
    armed = bool(already_armed or late_discovery or gain_trigger)
    stamp = str(observed_at or now_iso())

    if already_armed:
        basis = str(prev.get("quarter_wave_revalidation_basis") or "PERSISTED")
    elif late_discovery:
        basis = "FIRST_DISCOVERY_ALREADY_GE_25PCT_24H"
    elif gain_trigger:
        basis = "GAIN_GE_25PCT_FROM_IMMUTABLE_FIRST_SEEN_PRICE"
    else:
        basis = "WAITING_FOR_25PCT_REVALIDATION"

    out = {
        "quarter_wave_anchor_price": anchor if anchor > 0 else None,
        "quarter_wave_anchor_at": prev.get("quarter_wave_anchor_at") or anchor_at or observed_at,
        "first_verified_price": anchor if anchor > 0 else None,
        "first_verified_at": prev.get("first_verified_at") or anchor_at or (stamp if anchor > 0 else None),
        "first_seen_change_24h_pct": first_change,
        "gain_from_first_verified_pct": round(gain_pct, 4),
        "quarter_wave_revalidation_threshold_pct": threshold,
        "quarter_wave_revalidation_armed": armed,
        "quarter_wave_revalidation_basis": basis,
        "quarter_wave_late_discovery": late_discovery,
    }
    if armed:
        out["quarter_wave_revalidation_armed_at"] = prev.get("quarter_wave_revalidation_armed_at") or stamp
        out["quarter_wave_revalidation_trigger_price"] = prev.get("quarter_wave_revalidation_trigger_price") or price
    return out

def main():
    cfg = json.loads(CONFIG.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {"version": 3, "tokens": {}}
    state["version"] = 4
    st = state.setdefault("tokens", {})
    spread = float((cfg.get("data_integrity") or {}).get("max_price_source_spread_pct", 2))
    alert_policy = dict(cfg.get("alert_policy") or {})
    notable_min_raw = float(alert_policy.get("notable_evidence_min_raw", 0.30))

    static_tokens = list(cfg.get("tokens") or [])
    dynamic_all = dynamic_candidates(st)
    static_by_identity = {exact_identity_key(x): x for x in static_tokens if exact_identity_key(x)}
    tokens = []
    used = set()

    # Final BUY targets always run first at HIGHEST priority. If the identity is
    # already statically configured, preserve its tuned watch parameters while
    # upgrading it to the durable BUY close-watch semantics.
    for buy in [x for x in dynamic_all if x.get("dynamic_buy_candidate")]:
        identity = exact_identity_key(buy)
        if not identity or identity in used:
            continue
        base = dict(static_by_identity.get(identity) or {})
        if base:
            for field in (
                "candidate_type", "dynamic_buy_candidate", "priority", "close_watch",
                "collector_priority", "deep_investigation", "full_intelligence",
                "buy_zone_price_usd", "first_buy_at", "last_buy_at",
            ):
                base[field] = buy.get(field)
            if buy.get("first_seen_at"):
                base["first_seen_at"] = buy.get("first_seen_at")
            if buy.get("discovery_price") is not None:
                base["discovery_price"] = buy.get("discovery_price")
            target = base
        else:
            target = buy
        tokens.append(target)
        used.add(identity)

    for item in static_tokens:
        identity = exact_identity_key(item)
        if identity and identity not in used:
            tokens.append(item)
            used.add(identity)

    for item in dynamic_all:
        identity = candidate_identity_key(item)
        if identity and identity not in used:
            tokens.append(item)
            used.add(identity)

    dynamic = dynamic_all
    intel_index, intel_doc = load_intelligence()
    intel_rows = []
    sent_alerts = 0
    internal_spot_escalations = 0
    suppressed_alerts = 0
    suppressed_low_confirmation_alerts = 0

    for t in tokens:
        sym = t["symbol"].upper()
        identity_key = candidate_identity_key(t)
        chain_identity_key = exact_identity_key(t)
        if t.get("dynamic_buy_candidate"):
            key = f"BUY:{identity_key}"
        elif t.get("dynamic_alpha_candidate"):
            key = f"ALPHA:{identity_key}"
        elif t.get("dynamic_spot_candidate"):
            key = f"SPOT:{identity_key}"
        else:
            key = sym
        prev = st.get(key) or {}
        last_alert = prev.get("last_alert") or {}
        fusion = fusion_summary(intel_index.get(chain_identity_key), notable_min_raw=notable_min_raw)

        try:
            if t.get("dynamic_cex_market_candidate"):
                live = live_cex_market(t)
            else:
                live = live_exact_pair(t, spread)
                if str(t.get("exchange") or "").lower() == "gate" and t.get("currency_pair"):
                    try:
                        live.update(gate_execution_snapshot(t.get("currency_pair")))
                    except Exception as cex_exc:
                        live["cex_execution_verified"] = False
                        live["cex_execution_error"] = f"{type(cex_exc).__name__}:{str(cex_exc)[:160]}"
        except Exception as e:
            print(key, "UNVERIFIED", str(e), "INTELLIGENCE", fusion)
            intel_rows.append({
                "symbol": sym,
                "identity_key": identity_key,
                "candidate_type": t.get("candidate_type") or "CONFIGURED",
                "market_verified": False,
                "intelligence": fusion,
                "error": str(e)[:240],
            })
            continue

        pp = float(prev.get("price") or 0)
        pl = float(prev.get("liquidity") or 0)
        pv = float(prev.get("volume_h1") or 0)
        cex_sensor = spot_cex_sensor(t, prev)
        tr = list(cex_sensor["triggers"])
        if pp > 0:
            for lv in t.get("up_levels") or []:
                if pp < float(lv) <= live["price"]:
                    tr.append(f"BREAK_ABOVE_{float(lv):g}")
            for lv in t.get("down_levels") or []:
                if pp >= float(lv) > live["price"]:
                    tr.append(f"LOSS_BELOW_{float(lv):g}")
            drop = float(t.get("liquidity_drop_pct") or 25)
            if pl > 0 and live["liquidity"] < pl * (1 - drop / 100):
                tr.append(f"LIQUIDITY_DROP_GT_{drop:g}PCT")
            mult = float(t.get("volume_acceleration_multiple") or 2)
            minv = float(t.get("min_volume_h1_for_momentum") or 0)
            if pv > 0 and live["volume_h1"] >= max(minv, pv * mult) and live["price"] > pp:
                tr.append("PRICE_PLUS_VOLUME_ACCELERATION")
            if (
                t.get("dynamic_alpha_candidate")
                and live["buys_h1"] >= 10
                and live["buys_h1"] >= max(2 * live["sells_h1"], 10)
            ):
                tr.append("ALPHA_CALL_PLUS_BUY_IMBALANCE")

        first_change_for_revalidation = t.get("first_seen_change_24h_pct")
        if t.get("dynamic_spot_candidate"):
            try:
                current_discovery_momentum = float(t.get("discovery_momentum_change_pct") or 0)
                first_change_numeric = float(first_change_for_revalidation or 0)
                if current_discovery_momentum > first_change_numeric:
                    first_change_for_revalidation = current_discovery_momentum
            except (TypeError, ValueError):
                pass

        quarter_wave = (
            quarter_wave_revalidation(
                prev,
                live["price"],
                live["observed_at"],
                anchor_price=t.get("first_seen_price") or t.get("discovery_price"),
                anchor_change_24h_pct=first_change_for_revalidation,
                anchor_at=t.get("first_seen_at"),
            )
            if t.get("dynamic_spot_candidate")
            else {}
        )

        current_state = {
            "symbol": sym,
            "network": t.get("network") or "",
            "contract": t.get("contract") or "",
            "pair": t.get("pair") or "",
            "exchange": t.get("exchange"),
            "currency_pair": t.get("currency_pair"),
            "execution_identity_scope": t.get("execution_identity_scope"),
            "dex_url": t.get("dex_url") or prev.get("dex_url") or "",
            "source": t.get("source") or prev.get("source") or "",
            "source_url": t.get("source_url") or prev.get("source_url") or "",
            "identity_key": identity_key,
            "price": live["price"],
            "liquidity": live["liquidity"],
            "volume_h1": live["volume_h1"],
            "volume_h24": live["volume_h24"],
            "buys_h1": live["buys_h1"],
            "sells_h1": live["sells_h1"],
            "spread_pct": live["spread_pct"],
            "observed_at": live["observed_at"],
            "cex_execution_verified": live.get("cex_execution_verified"),
            "cex_execution_scope": live.get("cex_execution_scope"),
            "cex_orderbook_spread_pct": live.get("cex_orderbook_spread_pct"),
            "cex_bid_depth_1pct_usd": live.get("cex_bid_depth_1pct_usd"),
            "cex_ask_depth_1pct_usd": live.get("cex_ask_depth_1pct_usd"),
            "cex_depth_1pct_usd": live.get("cex_depth_1pct_usd"),
            "cex_bid_ask_depth_ratio": live.get("cex_bid_ask_depth_ratio"),
            "candidate_type": t.get("candidate_type") or "CONFIGURED",
            "dynamic_buy_candidate": bool(t.get("dynamic_buy_candidate")),
            "dynamic_alpha_candidate": bool(t.get("dynamic_alpha_candidate")),
            "dynamic_spot_candidate": bool(t.get("dynamic_spot_candidate")),
            "first_seen_at": prev.get("first_seen_at") or t.get("first_seen_at"),
            "first_seen_price": prev.get("first_seen_price") if prev.get("first_seen_price") is not None else t.get("first_seen_price"),
            "first_seen_change_24h_pct": prev.get("first_seen_change_24h_pct") if prev.get("first_seen_change_24h_pct") is not None else t.get("first_seen_change_24h_pct"),
            "first_seen_quote_volume_24h_usd": prev.get("first_seen_quote_volume_24h_usd") if prev.get("first_seen_quote_volume_24h_usd") is not None else t.get("first_seen_quote_volume_24h_usd"),
            "discovery_price": prev.get("discovery_price") if prev.get("discovery_price") is not None else t.get("discovery_price"),
            "change_24h_pct": t.get("change_24h_pct") if t.get("change_24h_pct") is not None else prev.get("change_24h_pct"),
            "discovery_momentum_change_pct": t.get("discovery_momentum_change_pct") if t.get("discovery_momentum_change_pct") is not None else prev.get("discovery_momentum_change_pct"),
            "gain_from_first_seen_pct": t.get("gain_from_first_seen_pct") if t.get("gain_from_first_seen_pct") is not None else prev.get("gain_from_first_seen_pct"),
            "cex_quote_volume_24h_usd": cex_sensor["current_volume_usd"],
            "cex_quote_volume_baseline_usd": cex_sensor["baseline_volume_usd"],
            "cex_relative_volume_multiple": cex_sensor["baseline_multiple"],
            "cex_scan_volume_multiple": cex_sensor["scan_multiple"],
            "positive_gainer_rank": cex_sensor["current_rank"],
            "cex_led_revival": cex_sensor["cex_led"],
            "intelligence_fusion": fusion,
            "last_alert": last_alert,
            "last_internal_escalation": prev.get("last_internal_escalation") or {},
            **quarter_wave,
        }
        st[key] = current_state
        intel_rows.append({
            "symbol": sym,
            "identity_key": identity_key,
            "candidate_type": current_state["candidate_type"],
            "market_verified": True,
            "discovery_price": current_state.get("discovery_price"),
            "first_seen_at": current_state.get("first_seen_at"),
            "cex_sensor": {
                "volume_24h_usd": current_state.get("cex_quote_volume_24h_usd"),
                "baseline_volume_usd": current_state.get("cex_quote_volume_baseline_usd"),
                "relative_volume_multiple": current_state.get("cex_relative_volume_multiple"),
                "scan_volume_multiple": current_state.get("cex_scan_volume_multiple"),
                "positive_gainer_rank": current_state.get("positive_gainer_rank"),
                "cex_led_revival": current_state.get("cex_led_revival"),
            },
            "quarter_wave_revalidation": {
                "armed": bool(current_state.get("quarter_wave_revalidation_armed")),
                "threshold_pct": current_state.get("quarter_wave_revalidation_threshold_pct"),
                "first_verified_price": current_state.get("first_verified_price"),
                "first_verified_at": current_state.get("first_verified_at"),
                "gain_from_first_verified_pct": current_state.get("gain_from_first_verified_pct"),
                "armed_at": current_state.get("quarter_wave_revalidation_armed_at"),
                "trigger_price": current_state.get("quarter_wave_revalidation_trigger_price"),
                "basis": current_state.get("quarter_wave_revalidation_basis"),
                "late_discovery": current_state.get("quarter_wave_late_discovery"),
                "anchor_price": current_state.get("quarter_wave_anchor_price"),
            } if t.get("dynamic_spot_candidate") else None,
            "intelligence": fusion,
        })

        comparison_snapshot = last_alert
        if t.get("dynamic_spot_candidate"):
            comparison_snapshot = prev.get("last_internal_escalation") or last_alert
        reasons = material_change_reasons(comparison_snapshot, live, fusion, tr, alert_policy)
        print(key, "VERIFIED", current_state, "TRIGGERS", tr, "ALERT_REASONS", reasons)

        if not reasons:
            if tr:
                suppressed_alerts += 1
                print(key, "ALERT_SUPPRESSED_NO_MATERIAL_CHANGE", tr)
            continue

        hard_risk = bool(fusion.get("hard_risks"))
        risk = hard_risk or any(x.startswith("LOSS_") or "LIQUIDITY_DROP" in x for x in tr)

        alpha_confirmations = []
        if t.get("dynamic_alpha_candidate"):
            alpha_ok, alpha_confirmations = alpha_telegram_gate(
                live, fusion, tr, reasons, risk, alert_policy
            )
            if not alpha_ok:
                suppressed_low_confirmation_alerts += 1
                st[key]["last_suppressed_alert"] = {
                    "observed_at": live.get("observed_at"),
                    "reasons": list(reasons),
                    "triggers": list(tr),
                    "fusion_score": fusion.get("score"),
                    "families": fusion.get("families"),
                    "volume_h1": live.get("volume_h1"),
                    "buys_h1": live.get("buys_h1"),
                    "sells_h1": live.get("sells_h1"),
                    "reason": "LOW_ALPHA_CONFIRMATION",
                }
                print(
                    key,
                    "ALERT_SUPPRESSED_LOW_ALPHA_CONFIRMATION",
                    {"reasons": reasons, "triggers": tr, "confirmations": alpha_confirmations},
                )
                continue

        if risk:
            label = "RISK"
        elif t.get("dynamic_buy_candidate"):
            label = "BUY_ZONE_CLOSE_WATCH"
        elif t.get("dynamic_alpha_candidate"):
            label = "ALPHA_CLOSE_WATCH"
        elif t.get("dynamic_spot_candidate") and cex_sensor["cex_led"]:
            label = "CEX_LED_REVIVAL_CLOSE_WATCH"
        elif t.get("dynamic_spot_candidate"):
            label = "SPOT_CLOSE_WATCH"
        elif tr:
            label = "REVIVAL_BUILDING"
        else:
            label = "INTELLIGENCE_MATERIAL_CHANGE"
        icon = "⚠️" if risk else "🔥"
        score_text = "n/a" if fusion.get("score") is None else f"{float(fusion['score']):.1f}/100"
        intel_line = (
            f"Intelligence Fusion: {score_text} · {fusion.get('label')} · "
            f"{fusion.get('families')} independent positive families · {fusion.get('status')}"
        )
        if fusion.get("hard_risks"):
            intel_line += " · HARD RISK: " + ", ".join(map(str, fusion["hard_risks"]))

        lines = [
            f"{icon} {sym} | WALLET500 UNIFIED WATCH | {label}",
            "WHY THIS ALERT: " + " | ".join(reasons[:6]),
        ]
        if t.get("dynamic_alpha_candidate") and alpha_confirmations:
            lines.append("CONFIRMATION: " + " | ".join(alpha_confirmations[:4]))
        if current_state.get("discovery_price") is not None:
            lines.append(f"DISCOVERY PRICE: ${float(current_state['discovery_price']):.8f}")
        lines.extend([
            f"CURRENT VERIFIED PRICE: ${live['price']:.8f}",
            f"SOURCE: GeckoTerminal exact pair + DexScreener exact pair | spread {live['spread_pct']:.2f}%",
            f"OBSERVED: {live['observed_at']}",
            f"Previous scan: ${pp:.8f}",
            f"1H {live['change_h1']:+.2f}% | 24H {live['change_h24']:+.2f}%",
            f"Liquidity {money(live['liquidity'])} | Vol 1H {money(live['volume_h1'])}",
            f"Buys/Sells 1H: {live['buys_h1']}/{live['sells_h1']}",
            intel_line,
            "TRIGGERS: " + (", ".join(tr) if tr else "INTELLIGENCE_MATERIAL_CHANGE"),
            "No repeat alert unless a new material change is detected.",
            f"CA: {t['contract']}",
            f"Pair: {t['pair']}",
            str(t.get("dex_url") or ""),
        ])
        if t.get("dynamic_spot_candidate"):
            snap = alert_snapshot(live, fusion, tr)
            snap.update({
                "cex_quote_volume_24h_usd": cex_sensor["current_volume_usd"],
                "cex_quote_volume_baseline_usd": cex_sensor["baseline_volume_usd"],
                "cex_relative_volume_multiple": cex_sensor["baseline_multiple"],
                "cex_scan_volume_multiple": cex_sensor["scan_multiple"],
                "positive_gainer_rank": cex_sensor["current_rank"],
                "internal_only": True,
                "telegram_suppressed_by_policy": "FINAL_BUY_ONLY_CANONICAL_DECISION_ENGINE",
            })
            st[key]["last_internal_escalation"] = snap
            st[key]["close_watch_mode"] = "CEX_LED_REVIVAL" if cex_sensor["cex_led"] else "SPOT_CLOSE_WATCH"
            internal_spot_escalations += 1
            print(key, "INTERNAL_SPOT_ESCALATION", {"label": label, "triggers": tr, "reasons": reasons})
            continue

        send("\n".join(lines))
        st[key].pop("last_suppressed_alert", None)
        st[key]["last_alert"] = alert_snapshot(live, fusion, tr)
        sent_alerts += 1

    state["updated_at"] = now_iso()
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    report = {
        "version": 4,
        "updated_at": now_iso(),
        "mode": "CEX_SENSOR_HANDOFF_INTERNAL_SPOT_PLUS_FINAL_ALERTS",
        "alert_policy": alert_policy,
        "fusion_snapshot_generated_at": intel_doc.get("generated_at") if isinstance(intel_doc, dict) else None,
        "sent_alerts": sent_alerts,
        "internal_spot_escalations": internal_spot_escalations,
        "spot_telegram_policy": "INTERNAL_ONLY_UNTIL_CANONICAL_BUY",
        "suppressed_repeated_alerts": suppressed_alerts,
        "suppressed_low_confirmation_alerts": suppressed_low_confirmation_alerts,
        "configured_targets": len(static_tokens),
        "dynamic_buy_targets": sum(bool(x.get("dynamic_buy_candidate")) for x in dynamic),
        "dynamic_alpha_targets": sum(bool(x.get("dynamic_alpha_candidate")) for x in dynamic),
        "dynamic_bootstrap_targets": sum(bool(x.get("dynamic_bootstrap_candidate")) for x in dynamic),
        "dynamic_spot_targets": sum(bool(x.get("dynamic_spot_candidate")) for x in dynamic),
        "targets": intel_rows,
    }
    INTEL_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "configured": len(static_tokens),
        "dynamic_buy": sum(bool(x.get("dynamic_buy_candidate")) for x in dynamic),
        "dynamic_alpha": sum(bool(x.get("dynamic_alpha_candidate")) for x in dynamic),
        "dynamic_bootstrap": sum(bool(x.get("dynamic_bootstrap_candidate")) for x in dynamic),
        "dynamic_spot": sum(bool(x.get("dynamic_spot_candidate")) for x in dynamic),
        "intelligence_targets": len(intel_rows),
        "sent_alerts": sent_alerts,
        "internal_spot_escalations": internal_spot_escalations,
        "suppressed_repeated_alerts": suppressed_alerts,
        "suppressed_low_confirmation_alerts": suppressed_low_confirmation_alerts,
        "alert_mode": "MATERIAL_CHANGE_PLUS_ALPHA_CONFIRMATION_GATE",
    }, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
