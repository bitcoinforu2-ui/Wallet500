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
HORIZONS_MIN = (0, 5, 15, 60, 360, 1440, 4320)
BOOST_REUSE_GAP_MIN = 36 * 60
MAX_EVENTS = 2500

PROVIDERS = [
    {
        "priority": 1,
        "provider": "coinmarketcap",
        "display_name": "CoinMarketCap",
        "promotion": "Boost (12–24h) + ads/sponsorship",
        "audience_metric": "30M+ monthly active users; 1B+ monthly page views",
        "detectability": "PUBLIC_UI_NO_STABLE_FEED",
    },
    {
        "priority": 2,
        "provider": "dexscreener",
        "display_name": "DEX Screener",
        "promotion": "Token Boosts (12–24h), token ads, trending-bar ads",
        "audience_metric": "Millions of users (official marketplace wording; no exact MAU published)",
        "detectability": "AUTOMATED_OFFICIAL_API",
    },
    {
        "priority": 3,
        "provider": "dextools",
        "display_name": "DEXTools",
        "promotion": "NITRO 24h boosts + token race + banners",
        "audience_metric": "20M visitors/month (official site)",
        "detectability": "PUBLIC_UI_NO_STABLE_FEED",
    },
    {
        "priority": 4,
        "provider": "coingecko",
        "display_name": "CoinGecko",
        "promotion": "Boosted Coin + self-serve/managed token ads",
        "audience_metric": "10M+ average monthly users; 200M+ monthly page views",
        "detectability": "PUBLIC_UI_NO_STABLE_FEED",
    },
    {
        "priority": 5,
        "provider": "geckoterminal",
        "display_name": "GeckoTerminal",
        "promotion": "Boosted token ads / pool-page ads",
        "audience_metric": "Millions of active traders (official ads page; standalone MAU not published)",
        "detectability": "PUBLIC_UI_NO_STABLE_FEED",
    },
    {
        "priority": 6,
        "provider": "coinsniper",
        "display_name": "CoinSniper",
        "promotion": "Listing boosts + promoted positions + banner ads",
        "audience_metric": "1.5M active monthly users; 300K views/day",
        "detectability": "PUBLIC_PROMOTED_LIST_NO_API",
    },
    {
        "priority": 7,
        "provider": "coinscope",
        "display_name": "Coinscope",
        "promotion": "Promotion list + banners + popup",
        "audience_metric": "50K daily users; 2.6M registered users",
        "detectability": "PUBLIC_PROMOTED_LIST_NO_API",
    },
    {
        "priority": 8,
        "provider": "coinranking",
        "display_name": "Coinranking",
        "promotion": "Native top-ranking spots + banners",
        "audience_metric": "500K+ high-intent crypto users",
        "detectability": "PUBLIC_UI_NO_STABLE_FEED",
    },
    {
        "priority": 9,
        "provider": "coincodex",
        "display_name": "CoinCodex",
        "promotion": "Display ads + newsletter/mailings",
        "audience_metric": "10M+ monthly page views; 750K+ subscribers",
        "detectability": "PUBLIC_UI_NO_STABLE_FEED",
    },
    {
        "priority": 10,
        "provider": "coincheckup",
        "display_name": "CoinCheckup",
        "promotion": "Banner/display + sponsored content/newsletter",
        "audience_metric": "300K+ monthly users",
        "detectability": "PUBLIC_UI_NO_STABLE_FEED",
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _n(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _pct(cur, base):
    cur = _n(cur)
    base = _n(base)
    if cur is None or base in (None, 0):
        return None
    return (cur / base - 1.0) * 100.0


def _norm_token(chain: str, address: str) -> str:
    chain = (chain or "").lower()
    address = str(address or "").strip()
    return address.lower() if address.startswith("0x") or chain not in {"solana"} else address


def _same_token(chain: str, a: str, b: str) -> bool:
    return _norm_token(chain, a) == _norm_token(chain, b)


def _get_json(url: str, timeout: int = 20):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Wallet500-PaidVisibility/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return "NETWORK_UNAVAILABLE"
    return f"{type(exc).__name__}:{str(exc)[:160]}"


def _fetch_list(url: str, errors: list[dict], label: str) -> list[dict]:
    try:
        payload = _get_json(url)
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []
    except Exception as exc:
        errors.append({"source": label, "error": _safe_error(exc)})
        return []


def _market_from_pair(chain: str, token_address: str, pair: dict, observed_at: str) -> dict | None:
    base = pair.get("baseToken") or {}
    if not _same_token(chain, str(base.get("address") or ""), token_address):
        return None
    liq = pair.get("liquidity") or {}
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    pc = pair.get("priceChange") or {}
    h24 = txns.get("h24") or {}
    return {
        "observed_at": observed_at,
        "chain": chain,
        "token_address": token_address,
        "pair_address": pair.get("pairAddress"),
        "dex_id": pair.get("dexId"),
        "price_usd": _n(pair.get("priceUsd")),
        "liquidity_usd": _n(liq.get("usd")),
        "market_cap_usd": _n(pair.get("marketCap")),
        "fdv_usd": _n(pair.get("fdv")),
        "pair_volume_24h_usd": _n(volume.get("h24")),
        "buys_24h": int(_n(h24.get("buys"), 0) or 0),
        "sells_24h": int(_n(h24.get("sells"), 0) or 0),
        "price_change_m5_pct": _n(pc.get("m5")),
        "price_change_h1_pct": _n(pc.get("h1")),
        "price_change_h6_pct": _n(pc.get("h6")),
        "price_change_h24_pct": _n(pc.get("h24")),
        "pair_created_at_ms": pair.get("pairCreatedAt"),
        "boosts_active": int(_n((pair.get("boosts") or {}).get("active"), 0) or 0),
    }


def fetch_token_market(chain: str, token_address: str, observed_at: str, errors: list[dict]) -> dict | None:
    url = f"https://api.dexscreener.com/token-pairs/v1/{quote(chain)}/{quote(token_address)}"
    try:
        rows = _get_json(url)
        if not isinstance(rows, list):
            return None
        exact = []
        for pair in rows:
            if not isinstance(pair, dict):
                continue
            m = _market_from_pair(chain, token_address, pair, observed_at)
            if m:
                exact.append(m)
        if not exact:
            return None
        exact.sort(key=lambda x: (_n(x.get("liquidity_usd"), -1) or -1), reverse=True)
        return exact[0]
    except Exception as exc:
        errors.append({"source": "dexscreener_token_pairs", "chain": chain, "token_address": token_address, "error": _safe_error(exc)})
        return None


def fetch_exact_pair_market(chain: str, token_address: str, pair_address: str, observed_at: str, errors: list[dict]) -> dict | None:
    url = f"https://api.dexscreener.com/latest/dex/pairs/{quote(chain)}/{quote(pair_address)}"
    try:
        payload = _get_json(url)
        rows = payload.get("pairs") or [] if isinstance(payload, dict) else []
        for pair in rows:
            if isinstance(pair, dict) and str(pair.get("pairAddress") or "") == pair_address:
                return _market_from_pair(chain, token_address, pair, observed_at)
        return None
    except Exception as exc:
        errors.append({"source": "dexscreener_exact_pair", "chain": chain, "pair_address": pair_address, "error": _safe_error(exc)})
        return None


def _market_impact(cur: dict | None, base: dict | None) -> dict:
    if not cur or not base:
        return {}
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
    def logdiff(a, b, missing=4.0):
        a, b = _n(a), _n(b)
        if a is None or b is None or a <= 0 or b <= 0:
            return missing
        return abs(math.log(a) - math.log(b))

    target_mc = target.get("market_cap_usd") or target.get("fdv_usd")
    coin_mc = coin.get("market_cap_usd") or coin.get("fdv_usd")
    price24 = _n(target.get("price_change_h24_pct"))
    coin24 = _n(coin.get("change_24h_pct"))
    momentum = abs((price24 or 0.0) - (coin24 or 0.0)) / 20.0
    return (
        0.40 * logdiff(target_mc, coin_mc)
        + 0.30 * logdiff(target.get("liquidity_usd"), coin.get("dex_pair_liquidity_usd"))
        + 0.20 * logdiff(target.get("pair_volume_24h_usd"), coin.get("dex_pair_volume_24h_usd"))
        + 0.10 * momentum
    )


def select_solana_controls(target: dict, promoted_tokens: set[str], revival: dict, observed_at: str, errors: list[dict], limit: int = 3) -> list[dict]:
    if target.get("chain") != "solana":
        return []
    candidates = []
    for coin in revival.get("coins") or []:
        if not isinstance(coin, dict):
            continue
        address = str(coin.get("token_address") or "")
        if not address or address in promoted_tokens:
            continue
        pair = str(coin.get("dex_pair_address") or "")
        if coin.get("network") != "solana" or coin.get("dex_link_type") != "DEXSCREENER_VERIFIED_PAIR" or not pair:
            continue
        candidates.append((_control_distance(target, coin), coin))
    candidates.sort(key=lambda x: x[0])

    controls = []
    for distance, coin in candidates[: max(8, limit * 3)]:
        address = str(coin.get("token_address") or "")
        pair = str(coin.get("dex_pair_address") or "")
        live = fetch_exact_pair_market("solana", address, pair, observed_at, errors)
        if not live:
            continue
        controls.append(
            {
                "token_address": address,
                "symbol": coin.get("symbol"),
                "name": coin.get("name"),
                "pair_address": pair,
                "match_distance": round(distance, 5),
                "t0": live,
                "observations": [{"horizon_min": 0, "market": live}],
            }
        )
        if len(controls) >= limit:
            break
    return controls


def _promotion_key(row: dict, source_type: str) -> tuple[str, str, str]:
    return (
        str(row.get("chainId") or "").lower(),
        _norm_token(str(row.get("chainId") or ""), str(row.get("tokenAddress") or "")),
        source_type,
    )


def collect_dexscreener_promotions(errors: list[dict]) -> list[dict]:
    top = _fetch_list("https://api.dexscreener.com/token-boosts/top/v1", errors, "dexscreener_boost_top")
    latest = _fetch_list("https://api.dexscreener.com/token-boosts/latest/v1", errors, "dexscreener_boost_latest")
    ads = _fetch_list("https://api.dexscreener.com/ads/latest/v1", errors, "dexscreener_ads_latest")

    merged: dict[tuple[str, str, str], dict] = {}
    for source_name, rows, source_type in (
        ("TOKEN_BOOST_TOP", top, "BOOST"),
        ("TOKEN_BOOST_LATEST", latest, "BOOST"),
        ("ADS_LATEST", ads, "AD"),
    ):
        for row in rows:
            chain = str(row.get("chainId") or "").lower()
            token = str(row.get("tokenAddress") or "")
            if not chain or not token:
                continue
            key = _promotion_key(row, source_type)
            item = merged.setdefault(
                key,
                {
                    "provider": "dexscreener",
                    "promotion_type": source_type,
                    "chain": chain,
                    "token_address": token,
                    "source_surfaces": [],
                    "platform_url": row.get("url"),
                    "platform_date": row.get("date"),
                    "duration_hours": _n(row.get("durationHours")),
                    "impressions": _n(row.get("impressions")),
                    "boost_amount": _n(row.get("amount")),
                    "boost_total_amount": _n(row.get("totalAmount")),
                },
            )
            if source_name not in item["source_surfaces"]:
                item["source_surfaces"].append(source_name)
            if _n(row.get("totalAmount")) is not None:
                item["boost_total_amount"] = max(_n(item.get("boost_total_amount"), 0) or 0, _n(row.get("totalAmount"), 0) or 0)
            if _n(row.get("amount")) is not None:
                item["boost_amount"] = max(_n(item.get("boost_amount"), 0) or 0, _n(row.get("amount"), 0) or 0)
            if row.get("date"):
                item["platform_date"] = row.get("date")
            if _n(row.get("durationHours")) is not None:
                item["duration_hours"] = _n(row.get("durationHours"))
            if _n(row.get("impressions")) is not None:
                item["impressions"] = _n(row.get("impressions"))
    return list(merged.values())


def _event_id(promo: dict, first_seen: str) -> str:
    platform_date = str(promo.get("platform_date") or "")
    raw = "|".join(
        [
            str(promo.get("provider") or ""),
            str(promo.get("promotion_type") or ""),
            str(promo.get("chain") or ""),
            _norm_token(str(promo.get("chain") or ""), str(promo.get("token_address") or "")),
            platform_date or first_seen[:13],
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _find_reusable_event(events: list[dict], promo: dict, now_dt: datetime) -> dict | None:
    chain = str(promo.get("chain") or "")
    token = _norm_token(chain, str(promo.get("token_address") or ""))
    ptype = str(promo.get("promotion_type") or "")
    platform_date = str(promo.get("platform_date") or "")
    for event in reversed(events):
        if event.get("provider") != "dexscreener" or event.get("promotion_type") != ptype:
            continue
        if str(event.get("chain") or "") != chain or _norm_token(chain, str(event.get("token_address") or "")) != token:
            continue
        if platform_date and str(event.get("platform_date") or "") == platform_date:
            return event
        last = _dt(event.get("last_seen_at"))
        if not platform_date and last and (now_dt - last).total_seconds() <= BOOST_REUSE_GAP_MIN * 60:
            return event
    return None


def _due_horizons(event: dict, now_dt: datetime) -> list[int]:
    first = _dt(event.get("first_seen_at"))
    if not first:
        return []
    elapsed = (now_dt - first).total_seconds() / 60.0
    done = {int(x.get("horizon_min")) for x in event.get("observations") or [] if x.get("horizon_min") is not None}
    return [h for h in HORIZONS_MIN if h not in done and elapsed >= h]


def _append_control_horizon(control: dict, horizon: int, observed_at: str, errors: list[dict]) -> None:
    pair = str(control.get("pair_address") or "")
    token = str(control.get("token_address") or "")
    if not pair or not token:
        return
    market = fetch_exact_pair_market("solana", token, pair, observed_at, errors)
    if market:
        control.setdefault("observations", []).append({"horizon_min": horizon, "market": market})


def _event_horizon_summary(event: dict, horizon: int) -> dict | None:
    obs = next((x for x in event.get("observations") or [] if int(x.get("horizon_min", -1)) == horizon), None)
    if not obs:
        return None
    promoted = obs.get("impact") or {}
    control_price = []
    control_liq = []
    control_vol = []
    for c in event.get("controls") or []:
        row = next((x for x in c.get("observations") or [] if int(x.get("horizon_min", -1)) == horizon), None)
        if not row:
            continue
        impact = _market_impact((row or {}).get("market"), c.get("t0"))
        control_price.append(impact.get("price_change_pct"))
        control_liq.append(impact.get("liquidity_change_pct"))
        control_vol.append(impact.get("pair_volume_24h_change_pct"))
    med_price = _median(control_price)
    med_liq = _median(control_liq)
    med_vol = _median(control_vol)
    return {
        "horizon_min": horizon,
        "promoted_price_change_pct": promoted.get("price_change_pct"),
        "control_median_price_change_pct": med_price,
        "excess_price_change_pct": (
            promoted.get("price_change_pct") - med_price
            if promoted.get("price_change_pct") is not None and med_price is not None
            else None
        ),
        "promoted_liquidity_change_pct": promoted.get("liquidity_change_pct"),
        "control_median_liquidity_change_pct": med_liq,
        "excess_liquidity_change_pct": (
            promoted.get("liquidity_change_pct") - med_liq
            if promoted.get("liquidity_change_pct") is not None and med_liq is not None
            else None
        ),
        "promoted_pair_volume_24h_change_pct": promoted.get("pair_volume_24h_change_pct"),
        "control_median_pair_volume_24h_change_pct": med_vol,
        "excess_pair_volume_24h_change_pct": (
            promoted.get("pair_volume_24h_change_pct") - med_vol
            if promoted.get("pair_volume_24h_change_pct") is not None and med_vol is not None
            else None
        ),
        "control_count": len([x for x in control_price if x is not None]),
    }


def _cohort_stats(events: list[dict], horizon: int) -> dict:
    rows = []
    for event in events:
        h = _event_horizon_summary(event, horizon)
        if h:
            rows.append(h)
    return {
        "horizon_min": horizon,
        "events_with_snapshot": len(rows),
        "events_with_matched_control": sum(1 for x in rows if x.get("control_count", 0) > 0),
        "median_price_change_pct": _median([x.get("promoted_price_change_pct") for x in rows]),
        "median_excess_price_change_pct": _median([x.get("excess_price_change_pct") for x in rows]),
        "median_liquidity_change_pct": _median([x.get("promoted_liquidity_change_pct") for x in rows]),
        "median_excess_liquidity_change_pct": _median([x.get("excess_liquidity_change_pct") for x in rows]),
        "median_pair_volume_24h_change_pct": _median([x.get("promoted_pair_volume_24h_change_pct") for x in rows]),
        "median_excess_pair_volume_24h_change_pct": _median([x.get("excess_pair_volume_24h_change_pct") for x in rows]),
    }


def run() -> dict:
    observed_at = now_iso()
    now_dt = _dt(observed_at) or datetime.now(timezone.utc)
    errors: list[dict] = []
    revival = _load(REVIVAL, {})
    old = _load(LEDGER, {})
    events = [x for x in (old.get("events") or []) if isinstance(x, dict)]
    promotions = collect_dexscreener_promotions(errors)

    promoted_solana = {
        str(x.get("token_address") or "")
        for x in promotions
        if x.get("chain") == "solana"
    }
    seen_event_ids = set()

    for promo in promotions:
        event = _find_reusable_event(events, promo, now_dt)
        if event is None:
            market = fetch_token_market(str(promo.get("chain")), str(promo.get("token_address")), observed_at, errors)
            event = {
                "event_id": _event_id(promo, observed_at),
                "provider": promo.get("provider"),
                "promotion_type": promo.get("promotion_type"),
                "chain": promo.get("chain"),
                "token_address": promo.get("token_address"),
                "platform_url": promo.get("platform_url"),
                "platform_date": promo.get("platform_date"),
                "duration_hours": promo.get("duration_hours"),
                "impressions": promo.get("impressions"),
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
                "source_surfaces": promo.get("source_surfaces") or [],
                "boost_amount_latest": promo.get("boost_amount"),
                "boost_total_amount_latest": promo.get("boost_total_amount"),
                "pair_identity_locked": bool(market and market.get("pair_address")),
                "pair_address": (market or {}).get("pair_address"),
                "t0": market,
                "observations": [],
                "controls": [],
                "production_portfolio_impact": "NONE",
                "truth_notes": [
                    "T0 is Wallet500 first observation; no historical price is reconstructed.",
                    "Pair identity is locked at T0 and reused for all impact horizons.",
                    "Paid visibility is a confounder/research event, never a positive alpha signal by itself.",
                ],
            }
            if market:
                event["observations"].append({"horizon_min": 0, "market": market, "impact": _market_impact(market, market)})
                event["controls"] = select_solana_controls(market, promoted_solana, revival, observed_at, errors)
            events.append(event)
        else:
            event["last_seen_at"] = observed_at
            event["source_surfaces"] = sorted(set((event.get("source_surfaces") or []) + (promo.get("source_surfaces") or [])))
            if _n(promo.get("boost_amount")) is not None:
                event["boost_amount_latest"] = promo.get("boost_amount")
            if _n(promo.get("boost_total_amount")) is not None:
                event["boost_total_amount_latest"] = promo.get("boost_total_amount")
            if promo.get("impressions") is not None:
                event["impressions"] = promo.get("impressions")
            if promo.get("duration_hours") is not None:
                event["duration_hours"] = promo.get("duration_hours")
        seen_event_ids.add(event["event_id"])

    for event in events:
        first = _dt(event.get("first_seen_at"))
        if not first or (now_dt - first).total_seconds() > 4 * 24 * 3600:
            continue
        pair = str(event.get("pair_address") or "")
        token = str(event.get("token_address") or "")
        chain = str(event.get("chain") or "")
        if not pair or not token or not chain:
            continue
        due = [h for h in _due_horizons(event, now_dt) if h != 0]
        for horizon in due:
            market = fetch_exact_pair_market(chain, token, pair, observed_at, errors)
            if not market:
                continue
            event.setdefault("observations", []).append(
                {"horizon_min": horizon, "market": market, "impact": _market_impact(market, event.get("t0"))}
            )
            for control in event.get("controls") or []:
                _append_control_horizon(control, horizon, observed_at, errors)

    events.sort(key=lambda x: str(x.get("first_seen_at") or ""))
    if len(events) > MAX_EVENTS:
        events = events[-MAX_EVENTS:]

    for event in events:
        event["impact_by_horizon"] = [
            x for h in HORIZONS_MIN if (x := _event_horizon_summary(event, h)) is not None
        ]

    active_ids = set(seen_event_ids)
    latest_active = [x for x in events if x.get("event_id") in active_ids]
    latest_active.sort(key=lambda x: (_n(x.get("boost_total_amount_latest"), 0) or 0), reverse=True)

    ledger = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "updated_at": observed_at,
        "production_portfolio_impact": PRODUCTION_IMPACT,
        "no_hindsight": True,
        "providers": PROVIDERS,
        "automated_collectors": ["dexscreener"],
        "rules": [
            "Paid promotion is recorded as an external exposure event, not as organic demand.",
            "No paid event can promote a token to Qualified/PRE-ALPHA.",
            "T0 equals Wallet500 first observation unless the platform provides an explicit campaign timestamp; market data is never reconstructed backward.",
            "Exact pair identity is locked at T0 for outcome measurement.",
            "Solana events receive matched non-promoted controls when Wallet500 has suitable exact-pair candidates.",
            "Missing provider feeds remain NOT_CONNECTED rather than being inferred.",
        ],
        "source_errors": errors[:80],
        "events": events,
    }
    _write(LEDGER, ledger)

    summary = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "generated_at": observed_at,
        "production_portfolio_impact": PRODUCTION_IMPACT,
        "providers_tracked": len(PROVIDERS),
        "providers_automated": 1,
        "active_paid_events_now": len(latest_active),
        "active_solana_paid_events_now": sum(1 for x in latest_active if x.get("chain") == "solana"),
        "total_events_observed": len(events),
        "active_events": [
            {
                "event_id": x.get("event_id"),
                "provider": x.get("provider"),
                "promotion_type": x.get("promotion_type"),
                "chain": x.get("chain"),
                "token_address": x.get("token_address"),
                "pair_address": x.get("pair_address"),
                "first_seen_at": x.get("first_seen_at"),
                "boost_amount_latest": x.get("boost_amount_latest"),
                "boost_total_amount_latest": x.get("boost_total_amount_latest"),
                "impressions": x.get("impressions"),
                "controls": len(x.get("controls") or []),
                "latest_market": (x.get("observations") or [{}])[-1].get("market"),
            }
            for x in latest_active[:100]
        ],
        "cohort_impact": [_cohort_stats(events, h) for h in HORIZONS_MIN if h != 0],
        "interpretation_contract": (
            "A positive post-promotion return is not attributed to promotion unless it also exceeds the matched control cohort; "
            "small samples remain descriptive only."
        ),
        "source_errors": errors[:30],
    }
    _write(SUMMARY, summary)
    print(
        "PAID_VISIBILITY_LAB_V1_OK",
        {
            "active": summary["active_paid_events_now"],
            "active_solana": summary["active_solana_paid_events_now"],
            "events": summary["total_events_observed"],
            "errors": len(errors),
        },
    )
    return summary


if __name__ == "__main__":
    run()
