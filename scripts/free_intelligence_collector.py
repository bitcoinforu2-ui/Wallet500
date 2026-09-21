from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import resilient_http
except ImportError:  # package import in pytest / module mode
    from scripts import resilient_http

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "data/unified-watch-config.json"
DYNAMIC = ROOT / "data/unified-dynamic-candidates.json"
SPOT = ROOT / "data/spot-market-discovery.json"
BOOTSTRAP = ROOT / "data/new-chain-bootstrap-radar.json"
BUY_REGISTRY = ROOT / "data/buy-zone-close-watch-registry.json"
PROTOCOL_BUYBACK_REGISTRY = ROOT / "data/protocol-buyback-registry.json"
EVENTS = ROOT / "data/close-watch-events.json"
STATE = ROOT / "data/free-intelligence-collector-state.json"
UA = "Wallet500-FreeIntel/2.1"
EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}
HONEYPOT_CHAIN_IDS = {
    "ethereum": 1,
    "bsc": 56,
    "base": 8453,
    "arbitrum": 42161,
    "optimism": 10,
    "polygon": 137,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def chain_name(value: object) -> str:
    raw = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(raw, raw)


def norm_addr(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def identity(t: dict) -> tuple[str, str, str, str]:
    chain = chain_name(t.get("network") or t.get("chain"))
    contract = norm_addr(chain, t.get("contract") or t.get("token_address"))
    pair = norm_addr(chain, t.get("pair") or t.get("pair_address"))
    return chain, contract, pair, f"{chain}:{contract}:{pair}"


def same_addr(chain: str, left: object, right: object) -> bool:
    return norm_addr(chain, left) == norm_addr(chain, right)


def get_json(url: str, headers=None, timeout: int = 12):
    try:
        return resilient_http.request_json(
            url,
            headers=headers or {},
            timeout=timeout,
            attempts=4,
            cache_ttl=45,
            user_agent=UA,
        )
    except Exception:
        return None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def event(t, fam, kind, direction, strength, confidence, source, subject="", url="", cid="", extra=None):
    chain, contract, pair, identity_key = identity(t)
    ts = now()
    e = {
        "symbol": str(t.get("symbol") or "").upper(),
        "network": chain,
        "contract": contract,
        "pair": pair,
        "identity_key": identity_key,
        "family": fam,
        "kind": kind,
        "direction": direction,
        "strength": round(max(0, min(100, float(strength))), 1),
        "confidence": round(max(0, min(100, float(confidence))), 1),
        "source": source,
        "source_url": url,
        "subject": subject,
        "canonical_event_id": cid or f"{source}:{identity_key}:{kind}",
        "event_time": ts,
        "observed_at": ts,
        "free_source": True,
    }
    if extra:
        e.update(extra)
    return e


def ds_collect(t, prev):
    chain, contract, pair, identity_key = identity(t)
    data = get_json("https://api.dexscreener.com/latest/dex/tokens/" + contract)
    out = []
    if not data:
        return out, {}
    pairs = data.get("pairs") or []
    exact = next((p for p in pairs if chain_name(p.get("chainId")) == chain and same_addr(chain, p.get("pairAddress"), pair)), None)
    if not exact:
        return [event(t, "market_microstructure", "identity_mismatch", -1, 100, 95, "DexScreener", extra={"hard_risk": True, "identity_verified": False})], {}

    base = (exact.get("baseToken") or {}).get("address")
    if not same_addr(chain, base, contract):
        return [event(t, "market_microstructure", "price_source_mismatch", -1, 100, 98, "DexScreener", extra={"hard_risk": True, "identity_verified": False, "reason": "TRACKED_TOKEN_NOT_DEXSCREENER_BASE_TOKEN"})], {}

    liq = num((exact.get("liquidity") or {}).get("usd"))
    vol = num((exact.get("volume") or {}).get("h1"))
    tx = (exact.get("txns") or {}).get("h1") or {}
    buys = num(tx.get("buys"))
    sells = num(tx.get("sells"))
    price = num(exact.get("priceUsd"))
    market_cap = num(exact.get("marketCap"))
    fdv = num(exact.get("fdv"))
    price_change = exact.get("priceChange") or {}
    price_change_h1 = num(price_change.get("h1"))
    price_change_h24 = num(price_change.get("h24"))
    snap = {
        "price": price,
        "liquidity": liq,
        "volume_h1": vol,
        "buys_h1": buys,
        "sells_h1": sells,
        "market_cap": market_cap,
        "fdv": fdv,
        "price_change_h1": price_change_h1,
        "price_change_h24": price_change_h24,
    }

    out.append(event(t, "market_microstructure", "verified_market_snapshot", 0, 0, 100, "DexScreener", url=str(exact.get("url") or ""), cid=f"dexsnapshot:{identity_key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "price_usd": price, "liquidity_usd": liq, "volume_h1_usd": vol, "buys_h1": buys, "sells_h1": sells, "market_cap_usd": market_cap, "fdv_usd": fdv, "price_change_h1_pct": price_change_h1, "price_change_h24_pct": price_change_h24}))

    if buys is not None and sells is not None and buys + sells >= 20:
        ratio = (buys + 1) / (sells + 1)
        strength = min(100, abs(ratio - 1) * 90)
        if ratio >= 1.25:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", 1, strength, 82, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "value": ratio}))
        elif ratio <= 0.8:
            out.append(event(t, "market_microstructure", "buy_sell_imbalance", -1, strength, 82, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "value": ratio, "contradicts_bullish": True}))

    pv = num(prev.get("volume_h1"))
    pl = num(prev.get("liquidity"))
    if vol is not None and pv and pv > 0:
        multiple = vol / pv
        if multiple >= 1.5:
            out.append(event(t, "market_microstructure", "volume_acceleration", 1, min(100, (multiple - 1) * 55), 78, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "multiple": round(multiple, 3)}))
    if liq is not None and pl and pl > 0:
        change = (liq - pl) / pl * 100
        if change <= -20:
            out.append(event(t, "market_microstructure", "liquidity_change", -1, min(100, abs(change) * 2), 88, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "change_pct": round(change, 2), "contradicts_bullish": True, "hard_risk": change <= -45}))
        elif change >= 15:
            out.append(event(t, "market_microstructure", "liquidity_change", 1, min(100, change * 1.5), 80, "DexScreener", extra={"identity_verified": True, "identity_scope": "EXACT_CHAIN_CONTRACT_PAIR", "change_pct": round(change, 2)}))
    return out, snap


def trending(tokens):
    eligible = []
    for t in tokens:
        cg_id = str(t.get("coingecko_id") or (t.get("free_intel") or {}).get("coingecko_id") or "").strip().lower()
        if cg_id:
            eligible.append((t, cg_id))
    if not eligible:
        return []
    data = get_json("https://api.coingecko.com/api/v3/search/trending") or {}
    coins = data.get("coins") or []
    out = []
    for rank, row in enumerate(coins, 1):
        item = row.get("item") or {}
        item_id = str(item.get("id") or "").strip().lower()
        for t, cg_id in eligible:
            if item_id == cg_id:
                out.append(event(t, "search_discovery", "coingecko_trending_rank", 1, max(35, 100 - rank * 7), 82, "CoinGecko Trending", url="https://www.coingecko.com/", cid=f"coingecko-trending:{identity(t)[3]}:{cg_id}:{datetime.now(timezone.utc).date()}", extra={"identity_verified": True, "identity_scope": "EXPLICIT_COINGECKO_ID_TO_CONFIGURED_EXACT_PAIR", "coingecko_id": cg_id, "rank": rank}))
    return out


def honeypot(t, prev=None, with_snapshot=False, market_snapshot=None):
    """Require corroboration before a provider honeypot flag becomes HARD_RISK.

    Consecutive provider flags are normally enough, but verified real sell flow on
    the exact pair with low simulated sell tax is contradictory execution evidence.
    In that case keep a negative warning and force recheck instead of hard-blocking.
    """
    chain, contract, _, _ = identity(t)
    chain_id = HONEYPOT_CHAIN_IDS.get(chain)
    empty = {"is_honeypot": None, "buy_tax": None, "sell_tax": None, "confirmed_hard_risk": False}
    if not chain_id or not contract:
        return ([], empty) if with_snapshot else []

    d = get_json(
        "https://api.honeypot.is/v2/IsHoneypot?address="
        + contract
        + "&chainID="
        + str(chain_id)
    )
    if not d:
        return ([], empty) if with_snapshot else []

    out = []
    hp = (d.get("honeypotResult") or {}).get("isHoneypot")
    sim = d.get("simulationResult") or {}
    bt = num(sim.get("buyTax"))
    st = num(sim.get("sellTax"))
    previous = prev if isinstance(prev, dict) else {}
    market = market_snapshot if isinstance(market_snapshot, dict) else {}
    real_buys = int(num(market.get("buys_h1")) or 0)
    real_sells = int(num(market.get("sells_h1")) or 0)
    real_volume = num(market.get("volume_h1")) or 0.0
    real_liquidity = num(market.get("liquidity")) or 0.0
    low_sell_tax = st is not None and st <= 5
    contradictory_real_sell_flow = bool(
        hp is True
        and low_sell_tax
        and real_buys >= 20
        and real_sells >= 20
        and real_volume >= 5000
        and real_liquidity >= 50000
    )
    consecutive_honeypot = bool(
        hp is True
        and previous.get("is_honeypot") is True
        and not contradictory_real_sell_flow
    )

    if hp is True:
        kind = (
            "honeypot_provider_conflict_real_sells"
            if contradictory_real_sell_flow
            else "honeypot_or_transfer_block"
            if consecutive_honeypot
            else "honeypot_or_transfer_block_unconfirmed"
        )
        out.append(event(
            t,
            "supply_tokenomics",
            kind,
            -1,
            100 if consecutive_honeypot else 55,
            95 if consecutive_honeypot else 70,
            "Honeypot.is",
            extra={
                "identity_verified": True,
                "identity_scope": "EXACT_CONTRACT_CONFIGURED_PAIR_CONTEXT",
                "hard_risk": consecutive_honeypot,
                "security_confirmation": (
                    "PROVIDER_CONFLICT_WITH_VERIFIED_REAL_SELL_FLOW"
                    if contradictory_real_sell_flow
                    else "CONSECUTIVE_PROVIDER_CONFIRMATION"
                    if consecutive_honeypot
                    else "FIRST_OBSERVATION_REQUIRES_RECHECK"
                ),
                "chain_id": chain_id,
                "real_buys_h1": real_buys,
                "real_sells_h1": real_sells,
                "real_volume_h1_usd": real_volume,
                "real_liquidity_usd": real_liquidity,
                "supersedes_hard_risk_kinds": (
                    ["honeypot_or_transfer_block"]
                    if contradictory_real_sell_flow
                    else []
                ),
            },
        ))

    tax = max([x for x in (bt, st) if x is not None], default=None)
    consecutive_extreme_tax = bool(
        tax is not None
        and tax >= 30
        and previous.get("extreme_tax") is True
    )
    if tax is not None and tax >= 15:
        out.append(event(
            t,
            "supply_tokenomics",
            "extreme_tax",
            -1,
            min(100, tax * 3),
            90,
            "Honeypot.is",
            extra={
                "identity_verified": True,
                "identity_scope": "EXACT_CONTRACT_CONFIGURED_PAIR_CONTEXT",
                "buy_tax": bt,
                "sell_tax": st,
                "hard_risk": consecutive_extreme_tax,
                "security_confirmation": "CONSECUTIVE_PROVIDER_CONFIRMATION" if consecutive_extreme_tax else "FIRST_OBSERVATION_REQUIRES_RECHECK",
                "chain_id": chain_id,
            },
        ))

    snap = {
        "observed_at": now(),
        "chain_id": chain_id,
        "is_honeypot": hp is True,
        "buy_tax": bt,
        "sell_tax": st,
        "extreme_tax": bool(tax is not None and tax >= 30),
        "confirmed_hard_risk": bool(consecutive_honeypot or consecutive_extreme_tax),
        "provider_conflict_with_real_sell_flow": contradictory_real_sell_flow,
        "real_buys_h1": real_buys,
        "real_sells_h1": real_sells,
        "real_volume_h1_usd": real_volume,
        "real_liquidity_usd": real_liquidity,
    }
    return (out, snap) if with_snapshot else out


def github_collect(t, prev):
    repo = (t.get("free_intel") or {}).get("github_repo")
    if not repo:
        return [], {}
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Authorization": "Bearer " + token} if token else {}
    d = get_json("https://api.github.com/repos/" + repo, headers=headers)
    rel = get_json("https://api.github.com/repos/" + repo + "/releases/latest", headers=headers)
    if not d:
        return [], {}
    snap = {"pushed_at": d.get("pushed_at"), "updated_at": d.get("updated_at"), "release": (rel or {}).get("tag_name")}
    out = []
    if snap["pushed_at"] and snap["pushed_at"] != prev.get("pushed_at"):
        out.append(event(t, "developer_project", "repo_activity", 1, 45, 65, "GitHub", subject=repo, url="https://github.com/" + repo, cid=f"github-push:{identity(t)[3]}:{repo}:{snap['pushed_at']}", extra={"identity_verified": True, "identity_scope": "EXPLICIT_CONFIG_PROJECT_MAPPING"}))
    if snap["release"] and snap["release"] != prev.get("release"):
        out.append(event(t, "developer_project", "github_release", 1, 65, 80, "GitHub", subject=snap["release"], url="https://github.com/" + repo + "/releases", cid=f"github-release:{identity(t)[3]}:{repo}:{snap['release']}", extra={"identity_verified": True, "identity_scope": "EXPLICIT_CONFIG_PROJECT_MAPPING"}))
    return out, snap


def defillama(t, prev):
    slug = (t.get("free_intel") or {}).get("defillama_slug")
    if not slug:
        return [], {}
    d = get_json("https://api.llama.fi/protocol/" + slug)
    if not d:
        return [], {}
    tvl = num(d.get("tvl"))
    snap = {"tvl": tvl}
    out = []
    old = num(prev.get("tvl"))
    if tvl is not None and old and old > 0:
        change = (tvl - old) / old * 100
        if abs(change) >= 5:
            out.append(event(t, "fundamental_usage", "tvl_change", 1 if change > 0 else -1, min(100, abs(change) * 5), 80, "DefiLlama", url="https://defillama.com/protocol/" + slug, extra={"identity_verified": True, "identity_scope": "EXPLICIT_CONFIG_PROTOCOL_MAPPING", "change_pct": round(change, 2), "contradicts_bullish": change < 0}))
    return out, snap


def _series_number(value):
    if isinstance(value, dict):
        for key in (
            "buybackUsd",
            "buyback_usd",
            "usd",
            "amountUsd",
            "amount_usd",
            "value",
            "amount",
            "total",
        ):
            if key in value:
                parsed = num(value.get(key))
                if parsed is not None:
                    return parsed
        return None
    return num(value)


def _series_date(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        try:
            ts = float(raw)
            if ts > 10_000_000_000:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    return raw[:10] if len(raw) >= 10 else raw


def _path_value(payload, path):
    current = payload
    parts = path if isinstance(path, (list, tuple)) else str(path or "").split(".")
    for part in parts:
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return None
        current = current.get(part)
    return current


def daily_value_series(payload, series_paths=None, value_keys=None, date_keys=None):
    """Normalize arbitrary public daily-value APIs into [(YYYY-MM-DD, usd)].

    Each protocol can declare data-only adapters in protocol-buyback-registry.json.
    Unknown shapes fail closed; missing values are never converted to zero.
    """
    if not isinstance(payload, dict):
        return []

    paths = list(series_paths or ())
    if not paths:
        paths = ["dailyBuybacks", "daily_buybacks", "totalDataChart", "daily", "data"]

    raw = None
    for path in paths:
        candidate = _path_value(payload, path)
        if isinstance(candidate, (dict, list)):
            raw = candidate
            break
    if raw is None:
        return []

    value_keys = list(value_keys or (
        "buybackUsd", "buyback_usd", "usd", "amountUsd", "amount_usd",
        "value", "amount", "total",
    ))
    date_keys = list(date_keys or ("date", "timestamp", "time", "day"))

    def parse_amount(value):
        if isinstance(value, dict):
            for key in value_keys:
                if key in value:
                    parsed = num(value.get(key))
                    if parsed is not None:
                        return parsed
            return None
        return num(value)

    points = {}
    if isinstance(raw, dict):
        iterator = list(raw.items())
    else:
        iterator = []
        for row in raw:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                iterator.append((row[0], row[1]))
            elif isinstance(row, dict):
                date_value = next((row.get(k) for k in date_keys if row.get(k) is not None), None)
                iterator.append((date_value, row))

    for date_value, value in iterator:
        day = _series_date(date_value)
        amount = parse_amount(value)
        if not day or amount is None or amount < 0:
            continue
        points[day] = float(amount)
    return sorted(points.items())


def _buyback_source_series(source, fallback_slug=""):
    if not isinstance(source, dict):
        return None
    adapter = str(source.get("adapter") or "json_daily_series").strip().lower()
    payload = None
    url = str(source.get("url") or "").strip()
    slug = str(source.get("slug") or fallback_slug or "").strip()

    if adapter == "json_daily_series":
        if not url:
            return None
        payload = get_json(url)
    elif adapter == "defillama_holders_revenue":
        if not slug:
            return None
        url = "https://api.llama.fi/summary/fees/" + slug + "?dataType=dailyHoldersRevenue"
        payload = get_json(url)
    elif adapter == "defillama_revenue":
        if not slug:
            return None
        url = "https://api.llama.fi/summary/fees/" + slug + "?dataType=dailyRevenue"
        payload = get_json(url)
    else:
        return None

    series = daily_value_series(
        payload,
        series_paths=source.get("series_paths"),
        value_keys=source.get("value_keys"),
        date_keys=source.get("date_keys"),
    )
    return {
        "adapter": adapter,
        "name": str(source.get("name") or adapter),
        "url": url,
        "semantics": str(source.get("semantics") or ""),
        "execution_proof": source.get("execution_proof") is True,
        "corroboration_only": source.get("corroboration_only") is True,
        "payload_available": isinstance(payload, dict),
        "series": series,
    }


def _trailing_average(series, latest_date, days):
    previous = [v for d, v in series if d < latest_date]
    if not previous:
        return None
    sample = previous[-max(1, int(days)):]
    return statistics.fmean(sample) if sample else None


def _today_utc():
    return datetime.now(timezone.utc).date().isoformat()


def protocol_buyback_collect(t, prev, market_snapshot):
    """Collect exact-token protocol buyback pressure without creating a BUY itself.

    The sensor only runs for an explicit exact-identity config mapping. Actual
    buyback execution comes from a configured public buyback endpoint, with
    DefiLlama dailyHoldersRevenue as a corroborating/fallback source. Revenue
    acceleration is a separate fundamental family so fusion can require market
    confirmation and independent evidence before FINAL BUY.
    """
    cfg = (t.get("free_intel") or {}).get("buyback_sensor")
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        return [], {}

    endpoint = str(cfg.get("buyback_endpoint") or "").strip()
    slug = str(cfg.get("defillama_fees_slug") or "").strip()

    declared_sources = cfg.get("execution_sources")
    source_records = []
    if isinstance(declared_sources, list) and declared_sources:
        for declared in declared_sources:
            record = _buyback_source_series(declared, fallback_slug=slug)
            if record is not None:
                source_records.append(record)
    else:
        # Backward-compatible adapter for existing configured tokens.
        if endpoint:
            record = _buyback_source_series({
                "adapter": "json_daily_series",
                "name": cfg.get("buyback_source_name") or "Protocol Buyback API",
                "url": endpoint,
                "execution_proof": True,
                "semantics": cfg.get("source_semantics") or "VERIFIED_PROTOCOL_TOKEN_BUYBACK",
            })
            if record is not None:
                source_records.append(record)
        if slug:
            record = _buyback_source_series({
                "adapter": "defillama_holders_revenue",
                "name": "DefiLlama Holders Revenue",
                "slug": slug,
                # Legacy behavior treated this as a fallback execution series.
                # New generic registry entries must explicitly choose semantics.
                "execution_proof": True,
                "semantics": "LEGACY_HOLDERS_REVENUE_BUYBACK_FALLBACK",
            })
            if record is not None:
                source_records.append(record)

    execution_records = [
        r for r in source_records
        if r.get("execution_proof") is True
        and r.get("corroboration_only") is not True
        and r.get("series")
    ]
    if not execution_records:
        return [], {
            "status": "SOURCE_UNAVAILABLE",
            "observed_at": now(),
            "declared_source_count": len(source_records),
            "available_series_count": sum(bool(r.get("series")) for r in source_records),
            "execution_proof_series_count": 0,
        }

    primary = execution_records[0]
    series = primary["series"]
    source = primary["name"]
    source_url = primary["url"]
    source_mode = "GENERIC_" + str(primary.get("adapter") or "SOURCE").upper()
    primary_series = series

    corroboration_records = [
        r for r in source_records
        if r is not primary and r.get("series")
    ]

    latest_date, latest_usd = series[-1]
    avg7 = _trailing_average(series, latest_date, 7)
    avg30 = _trailing_average(series, latest_date, 30)
    multiple7 = (latest_usd / avg7) if avg7 and avg7 > 0 else None
    multiple30 = (latest_usd / avg30) if avg30 and avg30 > 0 else None

    market = market_snapshot if isinstance(market_snapshot, dict) else {}
    market_cap = num(market.get("market_cap")) or num(market.get("fdv"))
    liquidity = num(market.get("liquidity"))
    pressure_bps_mcap = (
        latest_usd / market_cap * 10000.0
        if market_cap is not None and market_cap > 0
        else None
    )
    buyback_to_liquidity_pct = (
        latest_usd / liquidity * 100.0
        if liquidity is not None and liquidity > 0
        else None
    )

    previous_date = str(prev.get("latest_date") or "")
    previous_usd = num(prev.get("latest_buyback_usd"))
    observed_delta = 0.0
    delta_mode = "BASELINE_ONLY"
    if previous_date and previous_usd is not None:
        if latest_date == previous_date:
            observed_delta = max(0.0, latest_usd - previous_usd)
            delta_mode = "SAME_DAY_INCREMENT"
        elif latest_date > previous_date:
            observed_delta = max(0.0, latest_usd)
            delta_mode = "NEW_DAY_EXECUTION"

    corroborated = False
    corroboration_ratio = None
    corroboration_source = None
    if primary_series:
        p_day, p_val = primary_series[-1]
        ratios = []
        for record in corroboration_records:
            other_series = record.get("series") or []
            if not other_series:
                continue
            h_day, h_val = other_series[-1]
            if p_day != h_day or max(p_val, h_val) <= 0:
                continue
            ratio = min(p_val, h_val) / max(p_val, h_val)
            ratios.append((ratio, record.get("name")))
        if ratios:
            corroboration_ratio, corroboration_source = max(ratios, key=lambda x: x[0])
            corroborated = corroboration_ratio >= float(
                cfg.get("corroboration_min_ratio") or 0.70
            )

    min_delta = float(cfg.get("min_execution_delta_usd") or 25000)
    bootstrap_min = float(cfg.get("bootstrap_current_day_min_usd") or 1000000)
    spike_multiple = float(cfg.get("spike_multiple_7d") or 1.5)
    pressure_bps_trigger = float(cfg.get("pressure_bps_mcap_trigger") or 2.0)

    first_observation_current_day = bool(
        not previous_date
        and latest_date == _today_utc()
        and latest_usd >= bootstrap_min
    )
    execution_amount = latest_usd if first_observation_current_day else observed_delta

    strength = 30.0
    if execution_amount >= 250000:
        strength += 10
    if execution_amount >= 1000000:
        strength += 15
    if execution_amount >= 2000000:
        strength += 10
    if multiple7 is not None and multiple7 >= 1.25:
        strength += min(20.0, (multiple7 - 1.0) * 20.0)
    if pressure_bps_mcap is not None and pressure_bps_mcap >= pressure_bps_trigger:
        strength += min(15.0, pressure_bps_mcap * 1.5)
    strength = min(100.0, strength)

    out = []
    if execution_amount >= min_delta:
        confidence = 80.0 if first_observation_current_day else 94.0
        if corroborated:
            # Cross-source agreement raises source confidence, but a first
            # observation still has DAY (not scan-delta) temporal precision.
            confidence = 85.0 if first_observation_current_day else 97.0
        out.append(
            event(
                t,
                "supply_tokenomics",
                "buyback_execution",
                1,
                strength,
                confidence,
                source,
                subject=str(cfg.get("protocol_name") or t.get("symbol") or "protocol"),
                url=source_url,
                cid=(
                    f"buyback:{identity(t)[3]}:{latest_date}:"
                    f"{int(latest_usd // max(1.0, min_delta))}"
                ),
                extra={
                    "identity_verified": True,
                    "identity_scope": "EXPLICIT_PROTOCOL_TOKEN_TO_EXACT_PAIR_MAPPING",
                    "source_mode": source_mode,
                    "source_semantics": str(
                        primary.get("semantics")
                        or cfg.get("source_semantics")
                        or "VERIFIED_PROTOCOL_TOKEN_BUYBACK"
                    ),
                    "latest_buyback_date": latest_date,
                    "latest_buyback_usd": round(latest_usd, 2),
                    "observed_execution_delta_usd": round(execution_amount, 2),
                    "delta_mode": (
                        "CURRENT_DAY_FIRST_OBSERVATION"
                        if first_observation_current_day
                        else delta_mode
                    ),
                    "temporal_precision": (
                        "DAY"
                        if first_observation_current_day
                        else "SCAN_DELTA"
                    ),
                    "avg7_buyback_usd": round(avg7, 2) if avg7 is not None else None,
                    "avg30_buyback_usd": round(avg30, 2) if avg30 is not None else None,
                    "multiple_vs_7d": round(multiple7, 3) if multiple7 is not None else None,
                    "multiple_vs_30d": round(multiple30, 3) if multiple30 is not None else None,
                    "buyback_pressure_bps_mcap": (
                        round(pressure_bps_mcap, 3)
                        if pressure_bps_mcap is not None
                        else None
                    ),
                    "buyback_to_liquidity_pct": (
                        round(buyback_to_liquidity_pct, 3)
                        if buyback_to_liquidity_pct is not None
                        else None
                    ),
                    "cross_source_corroborated": corroborated,
                    "corroboration_source": corroboration_source,
                    "corroboration_ratio": (
                        round(corroboration_ratio, 3)
                        if corroboration_ratio is not None
                        else None
                    ),
                    "first_observation": not bool(previous_date),
                },
            )
        )

    # Do not refresh a historical daily acceleration signal on every scan.
    # It is current only when this scan observed a material execution (or the
    # guarded first-observation bootstrap proved a large current-day total).
    if (
        execution_amount >= min_delta
        and multiple7 is not None
        and multiple7 >= spike_multiple
    ):
        out.append(
            event(
                t,
                "supply_tokenomics",
                "buyback_acceleration",
                1,
                min(100.0, 45.0 + (multiple7 - 1.0) * 30.0),
                (82.0 if first_observation_current_day else 90.0)
                if primary_series
                else (78.0 if first_observation_current_day else 84.0),
                source,
                subject="buyback acceleration",
                url=source_url,
                cid=f"buyback-accel:{identity(t)[3]}:{latest_date}",
                extra={
                    "identity_verified": True,
                    "identity_scope": "EXPLICIT_PROTOCOL_TOKEN_TO_EXACT_PAIR_MAPPING",
                    "latest_buyback_usd": round(latest_usd, 2),
                    "multiple_vs_7d": round(multiple7, 3),
                    "multiple_vs_30d": round(multiple30, 3) if multiple30 is not None else None,
                    "cross_source_corroborated": corroborated,
                },
            )
        )

    revenue_snapshot = {}
    funding_cfg = cfg.get("funding_source") if isinstance(cfg.get("funding_source"), dict) else {}
    funding_slug = str(funding_cfg.get("slug") or slug or "").strip()
    share_pct = num(
        funding_cfg.get("buyback_share_pct")
        if funding_cfg
        else cfg.get("revenue_buyback_share_pct")
    )
    if (funding_slug or str(funding_cfg.get("url") or "").strip()) and share_pct is not None and share_pct > 0:
        funding_record = _buyback_source_series({
            "adapter": funding_cfg.get("adapter") or "defillama_revenue",
            "name": funding_cfg.get("name") or "DefiLlama Revenue",
            "slug": funding_slug,
            "url": funding_cfg.get("url"),
            "series_paths": funding_cfg.get("series_paths"),
            "value_keys": funding_cfg.get("value_keys"),
            "date_keys": funding_cfg.get("date_keys"),
        }, fallback_slug=funding_slug)
        revenue_series = (funding_record or {}).get("series") or []
        if revenue_series:
            rev_date, rev_usd = revenue_series[-1]
            rev_avg7 = _trailing_average(revenue_series, rev_date, 7)
            rev_multiple7 = (
                rev_usd / rev_avg7 if rev_avg7 and rev_avg7 > 0 else None
            )
            expected_buyback = rev_usd * (share_pct / 100.0)
            previous_revenue = prev.get("revenue") if isinstance(prev.get("revenue"), dict) else {}
            prev_rev_date = str(previous_revenue.get("latest_date") or "")
            prev_rev_usd = num(previous_revenue.get("latest_revenue_usd"))
            revenue_delta_usd = 0.0
            revenue_delta_mode = "BASELINE_ONLY"
            if prev_rev_date and prev_rev_usd is not None:
                if rev_date == prev_rev_date:
                    revenue_delta_usd = max(0.0, rev_usd - prev_rev_usd)
                    revenue_delta_mode = "SAME_DAY_INCREMENT"
                elif rev_date > prev_rev_date:
                    revenue_delta_usd = max(0.0, rev_usd)
                    revenue_delta_mode = "NEW_DAY_REVENUE"
            first_revenue_current_day = bool(
                not prev_rev_date
                and rev_date == _today_utc()
                and expected_buyback >= min_delta
            )
            funding_delta_usd = (
                expected_buyback
                if first_revenue_current_day
                else revenue_delta_usd * (share_pct / 100.0)
            )
            revenue_snapshot = {
                "latest_date": rev_date,
                "latest_revenue_usd": rev_usd,
                "avg7_revenue_usd": rev_avg7,
                "multiple_vs_7d": rev_multiple7,
                "expected_buyback_funding_usd": expected_buyback,
                "observed_funding_delta_usd": funding_delta_usd,
                "funding_delta_mode": (
                    "CURRENT_DAY_FIRST_OBSERVATION"
                    if first_revenue_current_day
                    else revenue_delta_mode
                ),
                "buyback_share_pct": share_pct,
            }
            min_rev_multiple = float(
                cfg.get("revenue_acceleration_multiple_7d") or 1.35
            )
            if (
                rev_date == _today_utc()
                and rev_date >= latest_date
                and rev_multiple7 is not None
                and rev_multiple7 >= min_rev_multiple
                and funding_delta_usd >= min_delta
            ):
                out.append(
                    event(
                        t,
                        "fundamental_usage",
                        "revenue_change",
                        1,
                        min(100.0, 40.0 + (rev_multiple7 - 1.0) * 35.0),
                        82.0 if first_revenue_current_day else 90.0,
                        str((funding_record or {}).get("name") or "Buyback Funding Source"),
                        subject="buyback funding pressure",
                        url=((funding_record or {}).get("url") or ("https://defillama.com/protocol/" + funding_slug)),
                        cid=(
                            f"buyback-revenue:{identity(t)[3]}:{rev_date}:"
                            f"{int(expected_buyback // max(1.0, min_delta))}"
                        ),
                        extra={
                            "identity_verified": True,
                            "identity_scope": "EXPLICIT_CONFIG_PROTOCOL_MAPPING",
                            "latest_revenue_usd": round(rev_usd, 2),
                            "revenue_multiple_vs_7d": round(rev_multiple7, 3),
                            "configured_buyback_share_pct": share_pct,
                            "expected_buyback_funding_usd": round(expected_buyback, 2),
                            "observed_funding_delta_usd": round(funding_delta_usd, 2),
                            "funding_delta_mode": (
                                "CURRENT_DAY_FIRST_OBSERVATION"
                                if first_revenue_current_day
                                else revenue_delta_mode
                            ),
                            "lead_signal": True,
                            "does_not_prove_execution": True,
                        },
                    )
                )

    snap = {
        "status": "OK",
        "observed_at": now(),
        "source_mode": source_mode,
        "latest_date": latest_date,
        "latest_buyback_usd": latest_usd,
        "avg7_buyback_usd": avg7,
        "avg30_buyback_usd": avg30,
        "multiple_vs_7d": multiple7,
        "multiple_vs_30d": multiple30,
        "observed_delta_usd": execution_amount,
        "delta_mode": (
            "CURRENT_DAY_FIRST_OBSERVATION"
            if first_observation_current_day
            else delta_mode
        ),
        "market_cap_usd": market_cap,
        "liquidity_usd": liquidity,
        "buyback_pressure_bps_mcap": pressure_bps_mcap,
        "buyback_to_liquidity_pct": buyback_to_liquidity_pct,
        "cross_source_corroborated": corroborated,
        "corroboration_source": corroboration_source,
        "corroboration_ratio": corroboration_ratio,
        "source_semantics": primary.get("semantics"),
        "revenue": revenue_snapshot,
    }
    return out, snap


def targets():
    cfg = json.loads(CFG.read_text())
    try:
        dyn = json.loads(DYNAMIC.read_text()) if DYNAMIC.exists() else {"candidates": []}
    except Exception:
        dyn = {"candidates": []}
    # Keep test/workspace overrides isolated: when DYNAMIC is redirected to a
    # temporary directory, use the matching sibling spot snapshot rather than
    # leaking candidates from the repository's production data directory.
    spot_path = SPOT if SPOT.parent == DYNAMIC.parent else DYNAMIC.with_name("spot-market-discovery.json")
    try:
        spot = json.loads(spot_path.read_text()) if spot_path.exists() else {"candidates": []}
    except Exception:
        spot = {"candidates": []}
    try:
        registry = json.loads(BUY_REGISTRY.read_text()) if BUY_REGISTRY.exists() else {"entries": {}}
    except Exception:
        registry = {"entries": {}}
    try:
        bootstrap = json.loads(BOOTSTRAP.read_text()) if BOOTSTRAP.exists() else {"candidates": []}
    except Exception:
        bootstrap = {"candidates": []}
    # Keep test/workspace overrides isolated just like the spot snapshot.
    # A temporary DYNAMIC path must never pull production registry targets into
    # that isolated run.
    protocol_registry_path = (
        PROTOCOL_BUYBACK_REGISTRY
        if PROTOCOL_BUYBACK_REGISTRY.parent == DYNAMIC.parent
        else DYNAMIC.with_name("protocol-buyback-registry.json")
    )
    try:
        protocol_registry = (
            json.loads(protocol_registry_path.read_text())
            if protocol_registry_path.exists()
            else {"entries": []}
        )
    except Exception:
        protocol_registry = {"entries": []}

    # Read the durable BUY registry directly so a newly persisted BUY gets full
    # intelligence in this same workflow even before the dynamic bridge refresh.
    registry_entries = registry.get("entries") if isinstance(registry, dict) and isinstance(registry.get("entries"), dict) else {}
    registry_buy_targets = [
        t for t in registry_entries.values()
        if isinstance(t, dict) and t.get("active") is True
    ]
    dynamic_buy_targets = [
        t for t in (dyn.get("candidates") or [])
        if isinstance(t, dict) and str(t.get("candidate_type") or "").upper() == "BUY_ZONE"
    ]
    bootstrap_targets = [
        t for t in (bootstrap.get("candidates") or [])
        if isinstance(t, dict) and t.get("bootstrap_actionable_watch") is True
    ]
    # Same-run CEX movers must receive fresh microstructure/security intelligence.
    # Reading Spot Discovery directly avoids the one-workflow lag caused by the
    # dynamic bridge running later in the pipeline.
    spot_hot_targets = []
    for t in (spot.get("resolved_candidates") or []):
        if not isinstance(t, dict):
            continue
        momentum = num(t.get("discovery_momentum_change_pct") or t.get("change_24h_pct")) or 0.0
        gain = num(t.get("gain_from_first_seen_pct")) or 0.0
        rank = int(num(t.get("positive_gainer_rank")) or 999999)
        turnover = num(t.get("quote_volume_24h_usd")) or 0.0
        if momentum >= 25.0 or gain >= 25.0 or (rank <= 15 and turnover >= 20000.0):
            spot_hot_targets.append(t)

    protocol_buyback_targets = []
    for entry in protocol_registry.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("active") is not True:
            continue
        sensor = entry.get("buyback_sensor")
        if not isinstance(sensor, dict) or sensor.get("enabled") is not True:
            continue
        row = dict(entry)
        normalized_sensor = dict(sensor)
        normalized_sensor.setdefault("protocol_name", row.get("protocol_name") or row.get("symbol"))
        normalized_sensor.setdefault("defillama_fees_slug", row.get("defillama_slug"))
        row["free_intel"] = {
            **(row.get("free_intel") if isinstance(row.get("free_intel"), dict) else {}),
            "defillama_slug": row.get("defillama_slug"),
            "buyback_sensor": normalized_sensor,
        }
        protocol_buyback_targets.append(row)

    raw_targets = (
        registry_buy_targets
        + dynamic_buy_targets
        + spot_hot_targets
        + bootstrap_targets
        + [t for t in (cfg.get("tokens") or []) if isinstance(t, dict)]
        + protocol_buyback_targets
    )
    by_key = {}
    order = []
    for t in raw_targets:
        if not isinstance(t, dict) or not all(identity(t)[:3]):
            continue
        key = identity(t)[3]
        if key not in by_key:
            by_key[key] = dict(t)
            order.append(key)
            continue
        merged = dict(by_key[key])
        incoming = dict(t)
        old_free = merged.get("free_intel") if isinstance(merged.get("free_intel"), dict) else {}
        new_free = incoming.get("free_intel") if isinstance(incoming.get("free_intel"), dict) else {}
        merged.update(incoming)
        merged["free_intel"] = {**old_free, **new_free}
        by_key[key] = merged
    return [by_key[key] for key in order]


def main():
    tokens = targets()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"tokens": {}}
    old_events = (json.loads(EVENTS.read_text()).get("events") or []) if EVENTS.exists() else []
    fresh = []
    newstate = {"version": 3, "updated_at": now(), "tokens": {}}
    fresh += trending(tokens)

    for t in tokens:
        _, _, _, key = identity(t)
        p = state.get("tokens", {}).get(key, {})
        de, ds = ds_collect(t, p.get("dexscreener", {}))
        fresh += de
        he, hs = honeypot(
            t,
            p.get("honeypot", {}),
            with_snapshot=True,
            market_snapshot=ds,
        )
        fresh += he
        ge, gs = github_collect(t, p.get("github", {}))
        fresh += ge
        le, ls = defillama(t, p.get("defillama", {}))
        fresh += le
        be, bs = protocol_buyback_collect(t, p.get("buyback", {}), ds)
        fresh += be
        newstate["tokens"][key] = {
            "dexscreener": ds,
            "honeypot": hs,
            "github": gs,
            "defillama": ls,
            "buyback": bs,
            "observed_at": now(),
        }
        time.sleep(0.15)

    cutoff = time.time() - 24 * 3600

    def recent(e):
        try:
            return datetime.fromisoformat(str(e.get("event_time")).replace("Z", "+00:00")).timestamp() >= cutoff
        except Exception:
            return False

    merged = [e for e in old_events if isinstance(e, dict) and recent(e)] + fresh
    ded = {}
    for e in merged:
        chain = chain_name(e.get("network") or e.get("chain"))
        contract = norm_addr(chain, e.get("contract") or e.get("token_address"))
        pair = norm_addr(chain, e.get("pair") or e.get("pair_address"))
        key = f"{chain}:{contract}:{pair}"
        ded[(key, e.get("canonical_event_id"), e.get("kind"))] = e

    EVENTS.write_text(json.dumps({"version": 3, "generated_at": now(), "identity_mode": "EXACT_CHAIN_CONTRACT_PAIR", "events": list(ded.values())}, indent=2, ensure_ascii=False) + "\n")
    STATE.write_text(json.dumps(newstate, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "OK",
        "tokens": len(tokens),
        "new_events": len(fresh),
        "retained_events": len(ded),
        "neutral_verified_snapshots": sum(1 for e in fresh if e.get("kind") == "verified_market_snapshot"),
        "buyback_events": sum(1 for e in fresh if e.get("kind") in {"buyback_execution", "buyback_acceleration"}),
        "buyback_lead_events": sum(1 for e in fresh if e.get("lead_signal") is True),
        "free_only": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
