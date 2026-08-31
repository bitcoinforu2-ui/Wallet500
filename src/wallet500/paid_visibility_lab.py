from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
LEDGER = DATA / "paid-visibility-ledger.json"
SUMMARY = DATA / "paid-visibility-summary.json"
MODE = "RESEARCH_ONLY_PAID_VISIBILITY_LAB_V1"
CONTRACT = "PAID_VISIBILITY_LAB_V1"
PRODUCTION_IMPACT = "NONE"
# Revival runs every ~30 minutes. These checkpoints are intentionally coarse enough
# that the label remains truthful despite scheduler jitter.
HORIZONS_MIN = (0, 60, 360, 1440, 4320)
BOOST_REUSE_GAP_MIN = 36 * 60
MAX_EVENTS = 2500

PROVIDERS = [
    {"priority": 1, "provider": "coinmarketcap", "display_name": "CoinMarketCap", "promotion": "Boost (12–24h) + ads/sponsorship", "audience_metric": "large global crypto audience; exact comparable MAU not used for scoring", "detectability": "PUBLIC_UI_NO_STABLE_FEED"},
    {"priority": 2, "provider": "dexscreener", "display_name": "DEX Screener", "promotion": "Token Boosts (12–24h), token ads, trending-bar ads", "audience_metric": "millions of users (official marketplace wording; no exact MAU used)", "detectability": "AUTOMATED_OFFICIAL_API"},
    {"priority": 3, "provider": "dextools", "display_name": "DEXTools", "promotion": "NITRO 24h boosts + Token Race + banners", "audience_metric": "20M visitors/month (official site)", "detectability": "PUBLIC_UI_NO_STABLE_FEED"},
    {"priority": 4, "provider": "coingecko", "display_name": "CoinGecko", "promotion": "Boosted Coin + self-serve/managed token ads", "audience_metric": "10M+ average monthly users; 200M+ monthly page views", "detectability": "PUBLIC_UI_NO_STABLE_FEED"},
    {"priority": 5, "provider": "geckoterminal", "display_name": "GeckoTerminal", "promotion": "Boosted token ads / pool-page ads", "audience_metric": "millions of active traders (official ads wording)", "detectability": "PUBLIC_UI_NO_STABLE_FEED"},
    {"priority": 6, "provider": "coinsniper", "display_name": "CoinSniper", "promotion": "Listing boosts + promoted positions + banners", "audience_metric": "1.5M active monthly users; 300K views/day", "detectability": "PUBLIC_PROMOTED_LIST_NO_API"},
    {"priority": 7, "provider": "coinscope", "display_name": "Coinscope", "promotion": "Promotion list + banners + popup", "audience_metric": "50K daily users; 2.6M registered users", "detectability": "PUBLIC_PROMOTED_LIST_NO_API"},
    {"priority": 8, "provider": "coinranking", "display_name": "Coinranking", "promotion": "Native top-ranking spots + banners", "audience_metric": "500K+ high-intent crypto users", "detectability": "PUBLIC_UI_NO_STABLE_FEED"},
    {"priority": 9, "provider": "coincodex", "display_name": "CoinCodex", "promotion": "Display ads + newsletter/mailings", "audience_metric": "10M+ monthly page views; 750K+ subscribers", "detectability": "PUBLIC_UI_NO_STABLE_FEED"},
    {"priority": 10, "provider": "coincheckup", "display_name": "CoinCheckup", "promotion": "Banner/display + sponsored content/newsletter", "audience_metric": "300K+ monthly users", "detectability": "PUBLIC_UI_NO_STABLE_FEED"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _n(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _pct(cur, base):
    cur, base = _n(cur), _n(base)
    return None if cur is None or base in (None, 0) else (cur / base - 1.0) * 100.0


def _norm_token(chain: str, address: str) -> str:
    chain, address = (chain or "").lower(), str(address or "").strip()
    return address if chain == "solana" else address.lower()


def _same_token(chain: str, a: str, b: str) -> bool:
    return _norm_token(chain, a) == _norm_token(chain, b)


def _get_json(url: str, timeout: int = 20):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Wallet500-PaidVisibility/1.1"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _err(exc: BaseException) -> str:
    if isinstance(exc, HTTPError): return f"HTTP_{exc.code}"
    if isinstance(exc, URLError): return "NETWORK_UNAVAILABLE"
    return f"{type(exc).__name__}:{str(exc)[:150]}"


def _fetch_list(url: str, errors: list[dict], source: str) -> list[dict]:
    try:
        value = _get_json(url)
        if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
        return [value] if isinstance(value, dict) else []
    except Exception as exc:
        errors.append({"source": source, "error": _err(exc)})
        return []


def _market_from_pair(chain: str, token_address: str, pair: dict, observed_at: str) -> dict | None:
    if not _same_token(chain, str((pair.get("baseToken") or {}).get("address") or ""), token_address):
        return None
    liq, vol, tx, pc = pair.get("liquidity") or {}, pair.get("volume") or {}, pair.get("txns") or {}, pair.get("priceChange") or {}
    h24 = tx.get("h24") or {}
    return {
        "observed_at": observed_at, "chain": chain, "token_address": token_address,
        "pair_address": pair.get("pairAddress"), "dex_id": pair.get("dexId"),
        "price_usd": _n(pair.get("priceUsd")), "liquidity_usd": _n(liq.get("usd")),
        "market_cap_usd": _n(pair.get("marketCap")), "fdv_usd": _n(pair.get("fdv")),
        "pair_volume_24h_usd": _n(vol.get("h24")),
        "buys_24h": int(_n(h24.get("buys"), 0) or 0), "sells_24h": int(_n(h24.get("sells"), 0) or 0),
        "price_change_m5_pct": _n(pc.get("m5")), "price_change_h1_pct": _n(pc.get("h1")),
        "price_change_h6_pct": _n(pc.get("h6")), "price_change_h24_pct": _n(pc.get("h24")),
        "pair_created_at_ms": pair.get("pairCreatedAt"),
        "boosts_active": int(_n((pair.get("boosts") or {}).get("active"), 0) or 0),
    }


def fetch_token_market(chain: str, token: str, observed_at: str, errors: list[dict]) -> dict | None:
    try:
        rows = _get_json(f"https://api.dexscreener.com/token-pairs/v1/{quote(chain)}/{quote(token)}")
        exact = [_market_from_pair(chain, token, x, observed_at) for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
        exact = [x for x in exact if x]
        exact.sort(key=lambda x: _n(x.get("liquidity_usd"), -1) or -1, reverse=True)
        return exact[0] if exact else None
    except Exception as exc:
        errors.append({"source": "dexscreener_token_pairs", "chain": chain, "token_address": token, "error": _err(exc)})
        return None


def fetch_exact_pair_market(chain: str, token: str, pair_address: str, observed_at: str, errors: list[dict]) -> dict | None:
    try:
        value = _get_json(f"https://api.dexscreener.com/latest/dex/pairs/{quote(chain)}/{quote(pair_address)}")
        for pair in (value.get("pairs") or []) if isinstance(value, dict) else []:
            if isinstance(pair, dict) and str(pair.get("pairAddress") or "") == pair_address:
                return _market_from_pair(chain, token, pair, observed_at)
    except Exception as exc:
        errors.append({"source": "dexscreener_exact_pair", "chain": chain, "pair_address": pair_address, "error": _err(exc)})
    return None


def _market_impact(cur: dict | None, base: dict | None) -> dict:
    if not cur or not base: return {}
    return {
        "price_change_pct": _pct(cur.get("price_usd"), base.get("price_usd")),
        "liquidity_change_pct": _pct(cur.get("liquidity_usd"), base.get("liquidity_usd")),
        "pair_volume_24h_change_pct": _pct(cur.get("pair_volume_24h_usd"), base.get("pair_volume_24h_usd")),
        "market_cap_change_pct": _pct(cur.get("market_cap_usd"), base.get("market_cap_usd")),
    }


def _median(values):
    clean = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return statistics.median(clean) if clean else None


def _control_distance(target: dict, coin: dict) -> float:
    def ld(a, b):
        a, b = _n(a), _n(b)
        return 4.0 if a is None or b is None or a <= 0 or b <= 0 else abs(math.log(a) - math.log(b))
    tmc, cmc = target.get("market_cap_usd") or target.get("fdv_usd"), coin.get("market_cap_usd") or coin.get("fdv_usd")
    mom = abs((_n(target.get("price_change_h24_pct"), 0) or 0) - (_n(coin.get("change_24h_pct"), 0) or 0)) / 20
    return .4*ld(tmc, cmc) + .3*ld(target.get("liquidity_usd"), coin.get("dex_pair_liquidity_usd")) + .2*ld(target.get("pair_volume_24h_usd"), coin.get("dex_pair_volume_24h_usd")) + .1*mom


def select_solana_controls(target: dict, promoted: set[str], revival: dict, observed_at: str, errors: list[dict], limit: int = 3) -> list[dict]:
    if target.get("chain") != "solana": return []
    candidates = []
    for coin in revival.get("coins") or []:
        if not isinstance(coin, dict): continue
        token, pair = str(coin.get("token_address") or ""), str(coin.get("dex_pair_address") or "")
        if not token or token in promoted or coin.get("network") != "solana" or coin.get("dex_link_type") != "DEXSCREENER_VERIFIED_PAIR" or not pair: continue
        candidates.append((_control_distance(target, coin), coin))
    candidates.sort(key=lambda x: x[0])
    out = []
    for distance, coin in candidates[:max(10, limit*4)]:
        token, pair = str(coin.get("token_address")), str(coin.get("dex_pair_address"))
        live = fetch_exact_pair_market("solana", token, pair, observed_at, errors)
        if live:
            out.append({"token_address": token, "symbol": coin.get("symbol"), "name": coin.get("name"), "pair_address": pair, "match_distance": round(distance, 5), "t0": live, "observations": [{"horizon_min": 0, "actual_elapsed_min": 0.0, "market": live}]})
        if len(out) >= limit: break
    return out


def collect_dexscreener_promotions(errors: list[dict]) -> list[dict]:
    sources = [
        ("TOKEN_BOOST_TOP", "BOOST", _fetch_list("https://api.dexscreener.com/token-boosts/top/v1", errors, "dexscreener_boost_top")),
        ("TOKEN_BOOST_LATEST", "BOOST", _fetch_list("https://api.dexscreener.com/token-boosts/latest/v1", errors, "dexscreener_boost_latest")),
        ("ADS_LATEST", "AD", _fetch_list("https://api.dexscreener.com/ads/latest/v1", errors, "dexscreener_ads_latest")),
    ]
    merged = {}
    for surface, kind, rows in sources:
        for row in rows:
            chain, token = str(row.get("chainId") or "").lower(), str(row.get("tokenAddress") or "")
            if not chain or not token: continue
            key = (chain, _norm_token(chain, token), kind)
            x = merged.setdefault(key, {"provider": "dexscreener", "promotion_type": kind, "chain": chain, "token_address": token, "source_surfaces": [], "platform_url": row.get("url"), "platform_date": row.get("date"), "duration_hours": _n(row.get("durationHours")), "impressions": _n(row.get("impressions")), "boost_amount": _n(row.get("amount")), "boost_total_amount": _n(row.get("totalAmount"))})
            if surface not in x["source_surfaces"]: x["source_surfaces"].append(surface)
            for field in ("boost_amount", "boost_total_amount"):
                val = _n(row.get("amount" if field == "boost_amount" else "totalAmount"))
                if val is not None: x[field] = max(_n(x.get(field), 0) or 0, val)
            if row.get("date"): x["platform_date"] = row.get("date")
            if _n(row.get("durationHours")) is not None: x["duration_hours"] = _n(row.get("durationHours"))
            if _n(row.get("impressions")) is not None: x["impressions"] = _n(row.get("impressions"))
    return list(merged.values())


def _event_id(promo: dict, first_seen: str) -> str:
    raw = "|".join([str(promo.get(k) or "") for k in ("provider", "promotion_type", "chain", "token_address")] + [str(promo.get("platform_date") or first_seen[:13])])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _find_reusable(events: list[dict], promo: dict, now: datetime) -> dict | None:
    chain, token, kind, pdate = str(promo.get("chain") or ""), _norm_token(str(promo.get("chain") or ""), str(promo.get("token_address") or "")), str(promo.get("promotion_type") or ""), str(promo.get("platform_date") or "")
    for e in reversed(events):
        if e.get("provider") != "dexscreener" or e.get("promotion_type") != kind or str(e.get("chain") or "") != chain or _norm_token(chain, str(e.get("token_address") or "")) != token: continue
        if pdate and str(e.get("platform_date") or "") == pdate: return e
        last = _dt(e.get("last_seen_at"))
        if not pdate and last and (now-last).total_seconds() <= BOOST_REUSE_GAP_MIN*60: return e
    return None


def _due_horizons(event: dict, now: datetime) -> list[int]:
    first = _dt(event.get("first_seen_at"))
    if not first: return []
    elapsed = (now-first).total_seconds()/60
    done = {int(x.get("horizon_min")) for x in event.get("observations") or [] if x.get("horizon_min") is not None}
    return [h for h in HORIZONS_MIN if h not in done and elapsed >= h]


def _append_control(control: dict, horizon: int, actual_elapsed: float, observed_at: str, errors: list[dict]) -> None:
    live = fetch_exact_pair_market("solana", str(control.get("token_address") or ""), str(control.get("pair_address") or ""), observed_at, errors)
    if live: control.setdefault("observations", []).append({"horizon_min": horizon, "actual_elapsed_min": round(actual_elapsed, 2), "market": live})


def _event_horizon_summary(event: dict, horizon: int) -> dict | None:
    obs = next((x for x in event.get("observations") or [] if int(x.get("horizon_min", -1)) == horizon), None)
    if not obs: return None
    promoted = obs.get("impact") or {}
    cp, cl, cv = [], [], []
    for c in event.get("controls") or []:
        row = next((x for x in c.get("observations") or [] if int(x.get("horizon_min", -1)) == horizon), None)
        if not row: continue
        imp = _market_impact(row.get("market"), c.get("t0")); cp.append(imp.get("price_change_pct")); cl.append(imp.get("liquidity_change_pct")); cv.append(imp.get("pair_volume_24h_change_pct"))
    mp, ml, mv = _median(cp), _median(cl), _median(cv)
    def excess(v, m): return v-m if v is not None and m is not None else None
    return {"horizon_min": horizon, "actual_elapsed_min": obs.get("actual_elapsed_min"), "promoted_price_change_pct": promoted.get("price_change_pct"), "control_median_price_change_pct": mp, "excess_price_change_pct": excess(promoted.get("price_change_pct"), mp), "promoted_liquidity_change_pct": promoted.get("liquidity_change_pct"), "control_median_liquidity_change_pct": ml, "excess_liquidity_change_pct": excess(promoted.get("liquidity_change_pct"), ml), "promoted_pair_volume_24h_change_pct": promoted.get("pair_volume_24h_change_pct"), "control_median_pair_volume_24h_change_pct": mv, "excess_pair_volume_24h_change_pct": excess(promoted.get("pair_volume_24h_change_pct"), mv), "control_count": len([x for x in cp if x is not None])}


def _cohort(events: list[dict], horizon: int) -> dict:
    rows = [x for e in events if (x := _event_horizon_summary(e, horizon))]
    return {"horizon_min": horizon, "events_with_snapshot": len(rows), "events_with_matched_control": sum(1 for x in rows if x.get("control_count", 0)>0), "median_price_change_pct": _median([x.get("promoted_price_change_pct") for x in rows]), "median_excess_price_change_pct": _median([x.get("excess_price_change_pct") for x in rows]), "median_liquidity_change_pct": _median([x.get("promoted_liquidity_change_pct") for x in rows]), "median_excess_liquidity_change_pct": _median([x.get("excess_liquidity_change_pct") for x in rows]), "median_pair_volume_24h_change_pct": _median([x.get("promoted_pair_volume_24h_change_pct") for x in rows]), "median_excess_pair_volume_24h_change_pct": _median([x.get("excess_pair_volume_24h_change_pct") for x in rows])}


def run() -> dict:
    observed_at, errors = now_iso(), []
    now = _dt(observed_at) or datetime.now(timezone.utc)
    revival, old = _load(REVIVAL, {}), _load(LEDGER, {})
    events = [x for x in old.get("events") or [] if isinstance(x, dict)]
    promotions = collect_dexscreener_promotions(errors)
    promoted_solana = {str(x.get("token_address") or "") for x in promotions if x.get("chain") == "solana"}
    active_ids = set()

    for promo in promotions:
        event = _find_reusable(events, promo, now)
        if event is None:
            market = fetch_token_market(str(promo.get("chain")), str(promo.get("token_address")), observed_at, errors)
            event = {"event_id": _event_id(promo, observed_at), "provider": "dexscreener", "promotion_type": promo.get("promotion_type"), "chain": promo.get("chain"), "token_address": promo.get("token_address"), "platform_url": promo.get("platform_url"), "platform_date": promo.get("platform_date"), "duration_hours": promo.get("duration_hours"), "impressions": promo.get("impressions"), "first_seen_at": observed_at, "last_seen_at": observed_at, "source_surfaces": promo.get("source_surfaces") or [], "boost_amount_latest": promo.get("boost_amount"), "boost_total_amount_latest": promo.get("boost_total_amount"), "pair_identity_locked": bool(market and market.get("pair_address")), "pair_address": (market or {}).get("pair_address"), "t0": market, "observations": [], "controls": [], "production_portfolio_impact": "NONE", "truth_notes": ["T0 is Wallet500 first observation; no historical market price is reconstructed.", "Pair identity is locked at T0 for every later checkpoint.", "Paid visibility is a research confounder and never a positive alpha signal by itself."]}
            if market:
                event["observations"].append({"horizon_min": 0, "actual_elapsed_min": 0.0, "market": market, "impact": _market_impact(market, market)})
                event["controls"] = select_solana_controls(market, promoted_solana, revival, observed_at, errors)
            events.append(event)
        else:
            event["last_seen_at"] = observed_at
            event["source_surfaces"] = sorted(set((event.get("source_surfaces") or []) + (promo.get("source_surfaces") or [])))
            for field in ("boost_amount_latest", "boost_total_amount_latest", "impressions", "duration_hours"):
                src = {"boost_amount_latest":"boost_amount", "boost_total_amount_latest":"boost_total_amount", "impressions":"impressions", "duration_hours":"duration_hours"}[field]
                if promo.get(src) is not None: event[field] = promo.get(src)
        active_ids.add(event["event_id"])

    for event in events:
        first = _dt(event.get("first_seen_at"))
        if not first or (now-first).total_seconds() > 4*24*3600: continue
        pair, token, chain = str(event.get("pair_address") or ""), str(event.get("token_address") or ""), str(event.get("chain") or "")
        if not pair or not token or not chain: continue
        elapsed = (now-first).total_seconds()/60
        for horizon in [h for h in _due_horizons(event, now) if h != 0]:
            market = fetch_exact_pair_market(chain, token, pair, observed_at, errors)
            if not market: continue
            event.setdefault("observations", []).append({"horizon_min": horizon, "actual_elapsed_min": round(elapsed, 2), "market": market, "impact": _market_impact(market, event.get("t0"))})
            for control in event.get("controls") or []: _append_control(control, horizon, elapsed, observed_at, errors)

    events.sort(key=lambda x: str(x.get("first_seen_at") or "")); events = events[-MAX_EVENTS:]
    for event in events: event["impact_by_horizon"] = [x for h in HORIZONS_MIN if (x := _event_horizon_summary(event, h))]
    active = [x for x in events if x.get("event_id") in active_ids]
    active.sort(key=lambda x: _n(x.get("boost_total_amount_latest"), 0) or 0, reverse=True)

    _write(LEDGER, {"version":1, "mode":MODE, "contract":CONTRACT, "updated_at":observed_at, "production_portfolio_impact":PRODUCTION_IMPACT, "no_hindsight":True, "providers":PROVIDERS, "automated_collectors":["dexscreener"], "rules":["Paid promotion is an external exposure event, not organic demand.", "No paid event can promote a token to Qualified/PRE-ALPHA.", "T0 is Wallet500 first observation; no market data is reconstructed backward.", "Exact pair identity is locked at T0.", "Solana events get matched non-promoted exact-pair controls when available.", "Missing platform feeds remain NOT_CONNECTED rather than inferred."], "source_errors":errors[:80], "events":events})
    summary = {"version":1, "mode":MODE, "contract":CONTRACT, "generated_at":observed_at, "production_portfolio_impact":PRODUCTION_IMPACT, "providers_tracked":len(PROVIDERS), "providers_automated":1, "active_paid_events_now":len(active), "active_solana_paid_events_now":sum(1 for x in active if x.get("chain")=="solana"), "total_events_observed":len(events), "active_events":[{"event_id":x.get("event_id"), "provider":x.get("provider"), "promotion_type":x.get("promotion_type"), "chain":x.get("chain"), "token_address":x.get("token_address"), "pair_address":x.get("pair_address"), "first_seen_at":x.get("first_seen_at"), "boost_amount_latest":x.get("boost_amount_latest"), "boost_total_amount_latest":x.get("boost_total_amount_latest"), "impressions":x.get("impressions"), "controls":len(x.get("controls") or []), "latest_market":(x.get("observations") or [{}])[-1].get("market")} for x in active[:100]], "cohort_impact":[_cohort(events,h) for h in HORIZONS_MIN if h], "interpretation_contract":"A post-promotion rise is not attributed to promotion unless it also beats matched controls; small samples are descriptive only.", "source_errors":errors[:30]}
    _write(SUMMARY, summary)
    print("PAID_VISIBILITY_LAB_V1_OK", {"active":len(active), "active_solana":summary["active_solana_paid_events_now"], "events":len(events), "errors":len(errors)})
    return summary


if __name__ == "__main__":
    run()
