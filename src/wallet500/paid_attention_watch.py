from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .revival_1000 import looks_like_solana_address
from .waking_confirmation import (
    _dedupe,
    _get_json,
    _identity,
    _latest_distribution,
    _scan_birdeye,
    _scan_news,
    _scan_reddit,
    _scan_x,
    _scan_youtube,
    confirmation_status,
    score_news,
    score_social,
)

DATA = Path("data")
PAID_LEDGER = DATA / "paid-visibility-ledger.json"
OUTPUT = DATA / "paid-attention-research-watch.json"
STATE = DATA / "paid-attention-research-watch-state.json"

MODE = "RESEARCH_ONLY_PAID_ATTENTION_WATCH_V1"
CONTRACT = "PAID_ATTENTION_WATCH_V1"
NETWORK = "solana"
FRESHNESS_HOURS = 36
MIN_RESEARCH_LIQUIDITY_USD = 50_000.0
EXTREME_THIN_LIQUIDITY_USD = 10_000.0
_LIQ_UNSET = object()

BANNED_SYMBOLS = {
    "USDC", "USDT", "DAI", "USDS", "USD1", "USDE", "PYUSD", "FDUSD", "TUSD",
    "USDP", "GUSD", "FRAX", "LUSD", "CRVUSD", "USDD", "USDB", "USDX", "USD0",
    "USDY", "EURC", "EURS", "WBTC", "CBBTC", "TBTC", "LBTC", "SOLVBTC", "WSOL",
    "BNSOL", "JITOSOL", "JUPSOL", "MSOL", "STSOL", "VSOL", "JLP", "SUSDE",
    "SYRUPUSDC", "USYC", "USTB", "BUILD",
}


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _n(v: Any, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _dt(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _latest_exact_market(event: dict) -> dict | None:
    pair = str(event.get("pair_address") or "")
    rows = []
    for obs in event.get("observations") or []:
        market = obs.get("market") if isinstance(obs, dict) else None
        if isinstance(market, dict) and str(market.get("pair_address") or "") == pair:
            rows.append(market)
    if rows:
        return rows[-1]
    t0 = event.get("t0")
    if isinstance(t0, dict) and str(t0.get("pair_address") or "") == pair:
        return t0
    return None


def _fresh_paid_groups(ledger: dict, reference: datetime) -> list[dict]:
    if (
        ledger.get("mode") != "RESEARCH_ONLY_PAID_VISIBILITY_LAB_V1"
        or ledger.get("contract") != "PAID_VISIBILITY_LAB_V1"
        or ledger.get("production_portfolio_impact") != "NONE"
        or ledger.get("no_hindsight") is not True
    ):
        raise RuntimeError("PAID_ATTENTION_SOURCE_CONTRACT_REJECTED")

    groups: dict[tuple[str, str], dict] = {}
    for event in ledger.get("events") or []:
        if not isinstance(event, dict) or str(event.get("chain") or "").lower() != NETWORK:
            continue
        token = str(event.get("token_address") or "")
        pair = str(event.get("pair_address") or "")
        if not looks_like_solana_address(token) or not looks_like_solana_address(pair):
            continue
        if event.get("pair_identity_locked") is not True:
            continue
        last_seen = _dt(event.get("last_seen_at")) or _dt(event.get("first_seen_at"))
        if last_seen is None:
            continue
        age_h = max(0.0, (reference - last_seen).total_seconds() / 3600.0)
        if age_h > FRESHNESS_HOURS:
            continue
        market = _latest_exact_market(event)
        if market is None:
            continue
        key = (token, pair)
        row = groups.setdefault(key, {
            "token_address": token,
            "pair_address": pair,
            "events": [],
            "first_seen_at": event.get("first_seen_at"),
            "last_seen_at": event.get("last_seen_at"),
            "market": market,
        })
        row["events"].append(event)
        if str(event.get("first_seen_at") or "") < str(row.get("first_seen_at") or "z"):
            row["first_seen_at"] = event.get("first_seen_at")
        if str(event.get("last_seen_at") or "") > str(row.get("last_seen_at") or ""):
            row["last_seen_at"] = event.get("last_seen_at")
            row["market"] = market

    out = []
    for row in groups.values():
        events = row["events"]
        types = sorted({str(x.get("promotion_type") or "UNKNOWN") for x in events})
        boost_total = max([_n(x.get("boost_total_amount_latest"), 0.0) or 0.0 for x in events if x.get("promotion_type") == "BOOST"] or [0.0])
        boost_amount = max([_n(x.get("boost_amount_latest"), 0.0) or 0.0 for x in events if x.get("promotion_type") == "BOOST"] or [0.0])
        ad_boost = "AD" in types and "BOOST" in types
        t0_candidates = [x.get("t0") for x in events if isinstance(x.get("t0"), dict)]
        t0 = t0_candidates[0] if t0_candidates else row["market"]
        row.update({
            "promotion_types": types,
            "boost_total_amount": boost_total,
            "boost_amount": boost_amount,
            "ad_and_boost": ad_boost,
            "t0": t0,
        })
        out.append(row)
    out.sort(key=lambda x: (-(x.get("boost_total_amount") or 0), str(x.get("first_seen_at") or "")))
    return out


def timing_class(group: dict) -> str:
    t0 = group.get("t0") or {}
    h24 = _n(t0.get("price_change_h24_pct"))
    h6 = _n(t0.get("price_change_h6_pct"))
    if (h24 is not None and h24 >= 35) or (h6 is not None and h6 >= 80):
        return "PROMOTION_AFTER_BREAKOUT"
    if h24 is not None and -15 <= h24 <= 20 and (h6 is None or h6 <= 35):
        return "PROMOTION_PRE_BREAKOUT_WINDOW"
    if h24 is not None and 20 < h24 < 35:
        return "PROMOTION_DURING_ADVANCING_MOVE"
    if h24 is not None and h24 <= -40:
        return "PROMOTION_DURING_CAPITULATION"
    return "PROMOTION_TIMING_NEUTRAL"


def liquidity_class(t0_liquidity_usd, live_liquidity_usd, timing: str) -> str:
    t0_liq = _n(t0_liquidity_usd)
    live_liq = _n(live_liquidity_usd)
    if live_liq is None:
        return "LIQUIDITY_UNVERIFIED"
    if live_liq < EXTREME_THIN_LIQUIDITY_USD:
        if t0_liq is not None and t0_liq >= MIN_RESEARCH_LIQUIDITY_USD:
            return "POST_PROMOTION_LIQUIDITY_COLLAPSE"
        return "EXTREME_THIN_LIQUIDITY"
    if live_liq < MIN_RESEARCH_LIQUIDITY_USD:
        if t0_liq is not None and t0_liq >= MIN_RESEARCH_LIQUIDITY_USD:
            return "POST_PROMOTION_LIQUIDITY_DRAIN"
        return "LOW_LIQUIDITY_BELOW_RESEARCH_FLOOR"
    if timing == "PROMOTION_DURING_CAPITULATION" and t0_liq is not None and t0_liq < MIN_RESEARCH_LIQUIDITY_USD:
        return "POST_COLLAPSE_PAID_PROMOTION"
    return "RESEARCH_LIQUIDITY_OK"


def classify_watch(
    timing: str,
    confirmation: str,
    distribution: dict | None,
    t0_liquidity_usd=_LIQ_UNSET,
    live_liquidity_usd=_LIQ_UNSET,
) -> str:
    enforce_liquidity = t0_liquidity_usd is not _LIQ_UNSET or live_liquidity_usd is not _LIQ_UNSET
    if enforce_liquidity:
        t0_value = None if t0_liquidity_usd is _LIQ_UNSET else t0_liquidity_usd
        live_value = None if live_liquidity_usd is _LIQ_UNSET else live_liquidity_usd
        liq_class = liquidity_class(t0_value, live_value, timing)
        if liq_class == "LIQUIDITY_UNVERIFIED":
            return "PAID_ATTENTION_LIQUIDITY_UNVERIFIED"
        if liq_class in {"EXTREME_THIN_LIQUIDITY", "POST_PROMOTION_LIQUIDITY_COLLAPSE", "POST_COLLAPSE_PAID_PROMOTION"}:
            return "PAID_ATTENTION_PUMP_DUMP_LEARNING"
        if liq_class in {"LOW_LIQUIDITY_BELOW_RESEARCH_FLOOR", "POST_PROMOTION_LIQUIDITY_DRAIN"}:
            return "PAID_ATTENTION_LOW_LIQUIDITY_LEARNING"
    risk = _n((distribution or {}).get("risk_score"))
    if risk is not None and risk >= 50:
        return "PAID_ATTENTION_RISK_RESEARCH"
    if timing == "PROMOTION_AFTER_BREAKOUT":
        return "PAID_ATTENTION_LATE_MOVE"
    if timing == "PROMOTION_PRE_BREAKOUT_WINDOW" and confirmation in {
        "WAKING_CONFIRMED_RESEARCH", "WAKING_STRONG_RESEARCH"
    }:
        return "PAID_ATTENTION_EARLY_CONFIRMING"
    return "PAID_ATTENTION_RESEARCH_WATCH"


def _live_pair(group: dict) -> tuple[dict, dict]:
    pair = str(group.get("pair_address") or "")
    token = str(group.get("token_address") or "")
    try:
        payload = _get_json(f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair}")
        pairs = payload.get("pairs") or []
        exact = next((x for x in pairs if str(x.get("pairAddress") or "") == pair), None)
        if not isinstance(exact, dict):
            return group.get("market") or {}, {"provider": "dexscreener_paid_watch", "status": "PAIR_NOT_FOUND"}
        base = exact.get("baseToken") or {}
        if str(base.get("address") or "") != token:
            return group.get("market") or {}, {"provider": "dexscreener_paid_watch", "status": "BASE_TOKEN_MISMATCH"}
        liq = exact.get("liquidity") or {}
        vol = exact.get("volume") or {}
        tx = exact.get("txns") or {}
        pc = exact.get("priceChange") or {}
        h24 = tx.get("h24") or {}
        market = {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "pair_address": pair,
            "price_usd": _n(exact.get("priceUsd")),
            "liquidity_usd": _n(liq.get("usd")),
            "market_cap_usd": _n(exact.get("marketCap")),
            "fdv_usd": _n(exact.get("fdv")),
            "volume_24h_usd": _n(vol.get("h24")),
            "buys_24h": int(_n(h24.get("buys"), 0) or 0),
            "sells_24h": int(_n(h24.get("sells"), 0) or 0),
            "price_change_h1_pct": _n(pc.get("h1")),
            "price_change_h6_pct": _n(pc.get("h6")),
            "price_change_h24_pct": _n(pc.get("h24")),
            "symbol": base.get("symbol"),
            "name": base.get("name"),
            "dex_id": exact.get("dexId"),
        }
        return market, {"provider": "dexscreener_paid_watch", "status": "OK"}
    except Exception as exc:
        return group.get("market") or {}, {"provider": "dexscreener_paid_watch", "status": type(exc).__name__}


def run(output_dir: str = "data") -> dict:
    global DATA, PAID_LEDGER, OUTPUT, STATE
    DATA = Path(output_dir)
    PAID_LEDGER = DATA / "paid-visibility-ledger.json"
    OUTPUT = DATA / "paid-attention-research-watch.json"
    STATE = DATA / "paid-attention-research-watch-state.json"
    DATA.mkdir(parents=True, exist_ok=True)

    observed_at = datetime.now(timezone.utc).isoformat()
    reference = _dt(observed_at) or datetime.now(timezone.utc)
    ledger = _load(PAID_LEDGER, {})
    groups = _fresh_paid_groups(ledger, reference)
    old_state = _load(STATE, {"version": 1, "tokens": {}})
    state_tokens = old_state.setdefault("tokens", {})
    distribution = _latest_distribution()
    rows = []
    provider_counts: dict[str, int] = {}
    banned = 0

    for group in groups:
        token = str(group["token_address"])
        pair = str(group["pair_address"])
        live, live_status = _live_pair(group)
        symbol = str(live.get("symbol") or "").upper()
        name = str(live.get("name") or "")
        if symbol in BANNED_SYMBOLS:
            banned += 1
            continue

        coin = {
            "network": NETWORK,
            "token_address": token,
            "dex_pair_address": pair,
            "symbol": symbol or None,
            "name": name or None,
            "id": None,
        }
        identity, statuses = _identity(coin)
        statuses.append(live_status)
        st = dict(state_tokens.get(token) or {})
        holders, wallets, st, birdeye_status = _scan_birdeye(token, st, observed_at)
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
            "source": "PAID_WATCH_SOCIAL_MULTI_SOURCE_V1" if social_verified else "NOT_CONNECTED",
            "observed_at": observed_at,
            "score": round(social_score, 2) if social_verified else 0.0,
            "signals": social_signals if social_verified else [],
            "metrics": {
                "mentions": len(social_events),
                "sources": len({x.get("source") for x in social_events if x.get("source")}),
                "authors": len({x.get("author") for x in social_events if x.get("author")}),
            },
            "events": social_events[:20],
        }
        news = {
            "available": news_verified,
            "verified": news_verified,
            "source": "GOOGLE_NEWS_RSS_IDENTITY_QUERY" if news_verified else "UNAVAILABLE",
            "observed_at": observed_at,
            "score": round(news_score, 2) if news_verified else 0.0,
            "signals": news_signals if news_verified else [],
            "metrics": {"items": len(news_events), "catalyst_keywords": catalysts},
            "events": news_events[:15],
        }
        channels = {
            "holders": holders or {"available": False, "verified": False, "score": 0.0, "source": "NOT_CONNECTED"},
            "wallets": wallets or {"available": False, "verified": False, "score": 0.0, "source": "NOT_CONNECTED"},
            "social": social,
            "news": news,
        }
        dist = distribution.get(token)
        confirmation, confirmation_score, strong = confirmation_status(channels, dist)
        timing = timing_class(group)
        t0_liquidity_usd = _n((group.get("t0") or {}).get("liquidity_usd"))
        live_liquidity_usd = _n(live.get("liquidity_usd"))
        liq_class = liquidity_class(t0_liquidity_usd, live_liquidity_usd, timing)
        watch_status = classify_watch(timing, confirmation, dist, t0_liquidity_usd, live_liquidity_usd)

        st["identity"] = identity
        st["social_mentions"] = len(social_events)
        st["news_items"] = len(news_events)
        st["last_observed_at"] = observed_at
        state_tokens[token] = st
        for p in statuses:
            key = f"{p.get('provider')}:{p.get('status')}"
            provider_counts[key] = provider_counts.get(key, 0) + 1

        rows.append({
            "network": NETWORK,
            "token_address": token,
            "pair_address": pair,
            "pair_identity_locked": True,
            "symbol": symbol or None,
            "name": name or None,
            "base_watch_status": "PAID_ATTENTION_RESEARCH_WATCH",
            "watch_status": watch_status,
            "promotion": {
                "first_seen_at": group.get("first_seen_at"),
                "last_seen_at": group.get("last_seen_at"),
                "types": group.get("promotion_types"),
                "boost_amount": group.get("boost_amount"),
                "boost_total_amount": group.get("boost_total_amount"),
                "ad_and_boost": group.get("ad_and_boost"),
                "timing_class": timing,
                "t0_price_change_h1_pct": _n((group.get("t0") or {}).get("price_change_h1_pct")),
                "t0_price_change_h6_pct": _n((group.get("t0") or {}).get("price_change_h6_pct")),
                "t0_price_change_h24_pct": _n((group.get("t0") or {}).get("price_change_h24_pct")),
            },
            "market": live,
            "liquidity_evidence": {
                "t0_liquidity_usd": t0_liquidity_usd,
                "live_liquidity_usd": live_liquidity_usd,
                "liquidity_class": liq_class,
                "research_floor_usd": MIN_RESEARCH_LIQUIDITY_USD,
                "extreme_thin_floor_usd": EXTREME_THIN_LIQUIDITY_USD,
            },
            "confirmation_status": confirmation,
            "confirmation_score": confirmation_score,
            "strong_families": strong,
            "identity": identity,
            "channels": channels,
            "distribution_evidence": dist,
            "provider_status": statuses,
            "pre_alpha_eligible": False,
            "verified_buy_signal": False,
            "production_portfolio_impact": "NONE",
        })
        time.sleep(0.05)

    priority = {
        "PAID_ATTENTION_EARLY_CONFIRMING": 0,
        "PAID_ATTENTION_RESEARCH_WATCH": 1,
        "PAID_ATTENTION_RISK_RESEARCH": 2,
        "PAID_ATTENTION_LATE_MOVE": 3,
        "PAID_ATTENTION_LOW_LIQUIDITY_LEARNING": 4,
        "PAID_ATTENTION_PUMP_DUMP_LEARNING": 5,
        "PAID_ATTENTION_LIQUIDITY_UNVERIFIED": 6,
    }
    rows.sort(key=lambda x: (
        priority.get(x.get("watch_status"), 9),
        -float((x.get("promotion") or {}).get("boost_total_amount") or 0),
    ))

    state = {"version": 1, "updated_at": observed_at, "tokens": state_tokens}
    _write(STATE, state)
    counts = {
        "fresh_exact_pair_paid_groups": len(groups),
        "tracked": len(rows),
        "banned_wrapped_stable_pegged": banned,
        "early_confirming": sum(1 for x in rows if x["watch_status"] == "PAID_ATTENTION_EARLY_CONFIRMING"),
        "research_watch": sum(1 for x in rows if x["watch_status"] == "PAID_ATTENTION_RESEARCH_WATCH"),
        "risk": sum(1 for x in rows if x["watch_status"] == "PAID_ATTENTION_RISK_RESEARCH"),
        "late_move": sum(1 for x in rows if x["watch_status"] == "PAID_ATTENTION_LATE_MOVE"),
        "low_liquidity_learning": sum(1 for x in rows if x["watch_status"] == "PAID_ATTENTION_LOW_LIQUIDITY_LEARNING"),
        "pump_dump_learning": sum(1 for x in rows if x["watch_status"] == "PAID_ATTENTION_PUMP_DUMP_LEARNING"),
        "liquidity_unverified": sum(1 for x in rows if x["watch_status"] == "PAID_ATTENTION_LIQUIDITY_UNVERIFIED"),
        "live_liquidity_ge_50k": sum(1 for x in rows if _n((x.get("market") or {}).get("liquidity_usd"), 0.0) >= MIN_RESEARCH_LIQUIDITY_USD),
        "live_liquidity_lt_50k": sum(1 for x in rows if _n((x.get("market") or {}).get("liquidity_usd"), 0.0) < MIN_RESEARCH_LIQUIDITY_USD),
        "live_liquidity_lt_10k": sum(1 for x in rows if _n((x.get("market") or {}).get("liquidity_usd"), 0.0) < EXTREME_THIN_LIQUIDITY_USD),
        "ad_and_boost": sum(1 for x in rows if (x.get("promotion") or {}).get("ad_and_boost") is True),
        "boost_500_plus": sum(1 for x in rows if float((x.get("promotion") or {}).get("boost_total_amount") or 0) >= 500),
    }
    payload = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "network": NETWORK,
        "generated_at": observed_at,
        "source_paid_visibility_updated_at": ledger.get("updated_at"),
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "trigger_policy": "VERIFIED_PAID_VISIBILITY_CREATES_RESEARCH_WATCH_ONLY",
        "rules": [
            "DEX Screener paid visibility is a research trigger, never a buy or PRE-ALPHA trigger by itself.",
            "Every row is exact Solana mint + exact locked pair; pair mixing is forbidden.",
            "Wrapped, stable and pegged symbols are excluded.",
            "Promotion timing is measured from Wallet500 T0 facts only; no later performance is used to classify early vs late.",
            "EARLY_CONFIRMING requires independent Waking confirmation evidence in addition to early promotion timing.",
            "Missing providers remain unavailable and never become positive evidence.",
            "Paid Attention main watch requires verified live exact-pair liquidity >= $50K; thinner or unverified pairs are quarantined for learning only.",
            "T0 liquidity and live liquidity are preserved to distinguish already-thin promotions from post-promotion liquidity collapse.",
        ],
        "counts": counts,
        "provider_status_counts": provider_counts,
        "targets": rows,
    }
    _write(OUTPUT, payload)
    print("PAID_ATTENTION_RESEARCH_WATCH_V1_OK", counts)
    return payload


if __name__ == "__main__":
    run()
