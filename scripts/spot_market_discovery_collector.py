from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import resilient_http
except ImportError:  # package import in pytest / module mode
    from scripts import resilient_http

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/spot-market-discovery.json"
STATE = ROOT / "data/spot-market-discovery-state.json"
CONFIG = ROOT / "data/unified-watch-config.json"
NATIVE_IDENTITY = ROOT / "data/native-asset-identity-registry.json"
GATE = "https://api.gateio.ws/api/v4"
UA = "Wallet500-SpotDiscovery/1.1-EvidenceRecovery"
COINGECKO = "https://api.coingecko.com/api/v3"
IDENTITY_RECOVERY_MAX_PRICE_DIVERGENCE_PCT = 20.0
COINGECKO_PLATFORM_MAP = {
    "ethereum": ("eth", "ethereum"),
    "binance-smart-chain": ("bsc", "bsc"),
    "base": ("base", "base"),
    "arbitrum-one": ("arbitrum", "arbitrum"),
    "optimistic-ethereum": ("optimism", "optimism"),
    "polygon-pos": ("polygon", "polygon"),
    "avalanche": ("avalanche", "avalanche"),
    "solana": ("solana", "solana"),
}

# Gate leveraged ETF products use suffixes such as 3L/3S/5L/5S. We also
# honor Gate's explicit etf_leverage field so a leveraged product can never
# be promoted merely because its symbol format changes.
LEVERAGED_SUFFIX = re.compile(r"(?:3|5)(?:L|S)$", re.IGNORECASE)

# Engine network slug, DexScreener chain id.
CHAIN_MAP = {
    "ETH": ("eth", "ethereum"),
    "ERC20": ("eth", "ethereum"),
    "ETHEREUM": ("eth", "ethereum"),
    "BSC": ("bsc", "bsc"),
    "BEP20": ("bsc", "bsc"),
    "BNB": ("bsc", "bsc"),
    "SOL": ("solana", "solana"),
    "SOLANA": ("solana", "solana"),
    "BASE": ("base", "base"),
    "ARBITRUM": ("arbitrum", "arbitrum"),
    "ARBITRUMONE": ("arbitrum", "arbitrum"),
    "ARBONE": ("arbitrum", "arbitrum"),
    "OP": ("optimism", "optimism"),
    "OPTIMISM": ("optimism", "optimism"),
    "POLYGON": ("polygon", "polygon"),
    "MATIC": ("polygon", "polygon"),
    "AVAXC": ("avalanche", "avalanche"),
    "AVALANCHE": ("avalanche", "avalanche"),
    "HARMONY": ("harmony", "harmony"),
    "ONE": ("harmony", "harmony"),
}


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now() -> str:
    return now_dt().isoformat()


def get_json(url: str, timeout: int = 12):
    try:
        return resilient_http.request_json(
            url,
            timeout=timeout,
            attempts=4,
            cache_ttl=45,
            user_agent=UA,
        )
    except Exception as exc:
        print("SPOT_DISCOVERY_FETCH_ERROR", url.split("?")[0], type(exc).__name__)
        return None


def coingecko_get_json(url: str, timeout: int = 12):
    headers = {}
    key = os.environ.get("COINGECKO_DEMO_API_KEY", "").strip()
    if key:
        headers["x-cg-demo-api-key"] = key
    try:
        return resilient_http.request_json(
            url,
            headers=headers,
            timeout=timeout,
            attempts=3,
            cache_ttl=90,
            min_interval=1.25,
            user_agent=UA,
        )
    except Exception as exc:
        print("SPOT_IDENTITY_RECOVERY_FETCH_ERROR", url.split("?")[0], type(exc).__name__)
        return None


def num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_leveraged(base: str, ticker: dict) -> bool:
    if LEVERAGED_SUFFIX.search(base or ""):
        return True
    lev = num(ticker.get("etf_leverage"))
    return lev is not None and abs(lev) > 0


def chain_ids(raw: object):
    value = str(raw or "").upper().replace("-", "").replace("_", "").replace(" ", "")
    if value in CHAIN_MAP:
        return CHAIN_MAP[value]
    if "ERC20" in value or value.startswith("ETH"):
        return CHAIN_MAP["ETH"]
    if "BEP20" in value or value.startswith("BSC"):
        return CHAIN_MAP["BSC"]
    if value.startswith("SOL"):
        return CHAIN_MAP["SOL"]
    if "ARBITRUM" in value:
        return CHAIN_MAP["ARBITRUM"]
    if value.startswith("BASE"):
        return CHAIN_MAP["BASE"]
    return None


def same_addr(chain: str, left: object, right: object) -> bool:
    a, b = str(left or "").strip(), str(right or "").strip()
    return a.lower() == b.lower() if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "harmony"} else a == b


def load_native_discovery_registry(path: Path = NATIVE_IDENTITY) -> dict[str, dict]:
    """Return explicit discovery-enabled native wrappers keyed by exact symbol.

    This is a curated research-only bridge for native assets whose CEX metadata has
    no contract address. It never infers by symbol from the open internet: an asset
    must be explicitly opted in with discovery_symbol_lookup=true in the repository.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}
    by_symbol: dict[str, dict] = {}
    ambiguous: set[str] = set()
    for coin_id, row in (raw.get("assets") or {}).items():
        if not isinstance(row, dict) or row.get("discovery_symbol_lookup") is not True:
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        if symbol in by_symbol:
            ambiguous.add(symbol)
            continue
        by_symbol[symbol] = {"coingecko_id": str(coin_id), **row}
    for symbol in ambiguous:
        by_symbol.pop(symbol, None)
    return by_symbol


def _native_proxy_possibilities(symbol: str, registry: dict[str, dict]) -> list[dict]:
    row = registry.get(str(symbol or "").upper().strip()) if isinstance(registry, dict) else None
    if not isinstance(row, dict):
        return []
    if str(row.get("representation_type") or "") != "CANONICAL_WRAPPED_NATIVE":
        return []
    chain = str(row.get("chain") or "").lower().strip()
    contract = str(row.get("token_address") or "").strip()
    if not chain or not contract:
        return []
    ds = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{urllib.parse.quote(contract, safe='')}")
    out = []
    for pair in (ds or {}).get("pairs") or []:
        if str(pair.get("chainId") or "").lower() != chain:
            continue
        base_addr = (pair.get("baseToken") or {}).get("address")
        quote_addr = (pair.get("quoteToken") or {}).get("address")
        if not (same_addr(chain, base_addr, contract) or same_addr(chain, quote_addr, contract)):
            continue
        pair_addr = str(pair.get("pairAddress") or "").strip()
        if not pair_addr:
            continue
        liq = num((pair.get("liquidity") or {}).get("usd"), 0.0) or 0.0
        out.append({
            "network": chain,
            "contract": contract,
            "pair": pair_addr,
            "dex_url": str(pair.get("url") or ""),
            "dex_liquidity_usd": round(liq, 2),
            "identity_source": "Curated native wrapper registry + DexScreener exact token pair",
            "native_asset_proxy": True,
            "native_asset_coingecko_id": row.get("coingecko_id"),
            "native_asset_representation": row.get("representation_type"),
            "native_asset_evidence_source": row.get("evidence_source"),
            "research_only_identity": True,
            "actionable": False,
        })
    return out


def _coingecko_identity_recovery(symbol: str, cex_price: float | None) -> dict:
    """Recover exact identity when Gate omits contract metadata, fail-closed."""
    base = str(symbol or "").upper().strip()
    cex_price = num(cex_price, 0.0) or 0.0
    if not base or cex_price <= 0:
        return {
            "identity_recovery_attempted": False,
            "identity_recovery_blocker": "CEX_PRICE_OR_SYMBOL_MISSING",
        }

    q = urllib.parse.urlencode({
        "vs_currency": "usd",
        "symbols": base.lower(),
        "include_tokens": "all",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
    })
    markets = coingecko_get_json(f"{COINGECKO}/coins/markets?{q}")
    matches = [
        x for x in (markets or [])
        if isinstance(x, dict) and str(x.get("symbol") or "").upper() == base
    ]
    if not matches:
        return {
            "identity_recovery_attempted": True,
            "identity_recovery_blocker": "COINGECKO_SYMBOL_NOT_FOUND",
        }

    chosen = None
    method = None
    if len(matches) == 1:
        chosen = matches[0]
        method = "UNIQUE_COINGECKO_SYMBOL"
    else:
        ranked = []
        for row in matches:
            px = num(row.get("current_price"), 0.0) or 0.0
            if px <= 0:
                continue
            err = abs(px - cex_price) / max(px, cex_price) * 100.0
            ranked.append((err, row))
        ranked.sort(key=lambda x: x[0])
        if ranked:
            best_err = ranked[0][0]
            second_err = ranked[1][0] if len(ranked) > 1 else 999.0
            if best_err <= 12.0 and second_err >= max(20.0, best_err * 2.0):
                chosen = ranked[0][1]
                method = "COINGECKO_SYMBOL_PLUS_PRICE_COHERENCE"
    if not chosen:
        return {
            "identity_recovery_attempted": True,
            "identity_recovery_blocker": "COINGECKO_SYMBOL_AMBIGUOUS_FAIL_CLOSED",
            "identity_recovery_candidate_count": len(matches),
        }

    coin_id = str(chosen.get("id") or "").strip()
    if not coin_id:
        return {
            "identity_recovery_attempted": True,
            "identity_recovery_blocker": "COINGECKO_ID_MISSING",
        }
    detail = coingecko_get_json(
        f"{COINGECKO}/coins/{urllib.parse.quote(coin_id, safe='')}"
        "?localization=false&tickers=false&market_data=false"
        "&community_data=false&developer_data=false&sparkline=false"
    )
    platforms = (detail or {}).get("platforms") if isinstance(detail, dict) else {}
    possibilities = []
    for platform, contract_value in (platforms or {}).items():
        mapped = COINGECKO_PLATFORM_MAP.get(str(platform or "").lower().strip())
        contract = str(contract_value or "").strip()
        if not mapped or not contract:
            continue
        engine_network, ds_chain = mapped
        ds = get_json(
            f"https://api.dexscreener.com/latest/dex/tokens/"
            f"{urllib.parse.quote(contract, safe='')}"
        )
        for pair in (ds or {}).get("pairs") or []:
            if str(pair.get("chainId") or "").lower() != ds_chain:
                continue
            base_addr = (pair.get("baseToken") or {}).get("address")
            quote_addr = (pair.get("quoteToken") or {}).get("address")
            if not (
                same_addr(ds_chain, base_addr, contract)
                or same_addr(ds_chain, quote_addr, contract)
            ):
                continue
            pair_addr = str(pair.get("pairAddress") or "").strip()
            dex_price = num(pair.get("priceUsd"), 0.0) or 0.0
            if not pair_addr or dex_price <= 0:
                continue
            price_divergence = abs(dex_price - cex_price) / max(dex_price, cex_price) * 100.0
            if price_divergence > IDENTITY_RECOVERY_MAX_PRICE_DIVERGENCE_PCT:
                continue
            liq = num((pair.get("liquidity") or {}).get("usd"), 0.0) or 0.0
            possibilities.append({
                "network": engine_network,
                "contract": contract,
                "pair": pair_addr,
                "dex_url": str(pair.get("url") or ""),
                "dex_liquidity_usd": round(liq, 2),
                "dex_price_usd": dex_price,
                "identity_source": (
                    f"CoinGecko {method} + exact platform contract + "
                    "DexScreener exact token pair + Gate price coherence"
                ),
                "identity_recovery_method": method,
                "identity_recovery_attempted": True,
                "identity_recovery_price_divergence_pct": round(price_divergence, 4),
                "coingecko_id": coin_id,
            })

    if not possibilities:
        return {
            "identity_recovery_attempted": True,
            "identity_recovery_method": method,
            "identity_recovery_blocker": "NO_PRICE_COHERENT_EXACT_DEX_PAIR_FROM_COINGECKO_PLATFORM",
            "coingecko_id": coin_id,
        }

    best = max(
        possibilities,
        key=lambda x: (
            x.get("dex_liquidity_usd") or 0,
            -(x.get("identity_recovery_price_divergence_pct") or 999),
        ),
    )
    return {
        "identity_status": "RESOLVED_EXACT",
        "identity_reason": "EXACT_IDENTITY_RECOVERED_FROM_COINGECKO_PLATFORM",
        **best,
    }


def resolve_identity(
    symbol: str,
    native_registry: dict[str, dict] | None = None,
    *,
    cex_price: float | None = None,
) -> dict:
    q = urllib.parse.urlencode({"currency": symbol})
    chains = get_json(f"{GATE}/wallet/currency_chains?{q}")
    gate_currency_chains_available = isinstance(chains, list)
    if not gate_currency_chains_available:
        chains = []

    possibilities = []
    supported_contracts = 0
    native_registry = native_registry if isinstance(native_registry, dict) else load_native_discovery_registry()
    for row in chains:
        if not isinstance(row, dict):
            continue
        contract = str(row.get("contract_address") or "").strip()
        mapped = chain_ids(row.get("chain") or row.get("name_en"))
        if not contract or not mapped:
            continue
        supported_contracts += 1
        engine_network, ds_chain = mapped
        ds = get_json(f"https://api.dexscreener.com/latest/dex/tokens/{urllib.parse.quote(contract, safe='')}")
        for pair in (ds or {}).get("pairs") or []:
            if str(pair.get("chainId") or "").lower() != ds_chain:
                continue
            base_addr = (pair.get("baseToken") or {}).get("address")
            quote_addr = (pair.get("quoteToken") or {}).get("address")
            if not (same_addr(ds_chain, base_addr, contract) or same_addr(ds_chain, quote_addr, contract)):
                continue
            pair_addr = str(pair.get("pairAddress") or "").strip()
            if not pair_addr:
                continue
            liq = num((pair.get("liquidity") or {}).get("usd"), 0.0) or 0.0
            possibilities.append({
                "network": engine_network,
                "contract": contract,
                "pair": pair_addr,
                "dex_url": str(pair.get("url") or ""),
                "dex_liquidity_usd": round(liq, 2),
                "identity_source": "Gate currency_chains contract + DexScreener exact token pair",
            })
        time.sleep(0.04)

    if not possibilities:
        possibilities.extend(_native_proxy_possibilities(symbol, native_registry))

    if not possibilities:
        recovery = _coingecko_identity_recovery(symbol, cex_price)
        if recovery.get("identity_status") == "RESOLVED_EXACT":
            return recovery
        if not gate_currency_chains_available:
            reason = "GATE_CURRENCY_CHAINS_UNAVAILABLE_AND_NO_CURATED_NATIVE_PAIR"
        else:
            reason = "NO_SUPPORTED_CONTRACT_ADDRESS" if supported_contracts == 0 else "NO_EXACT_LIQUID_DEX_PAIR"
        return {
            "identity_status": "UNRESOLVED",
            "identity_reason": reason,
            **recovery,
        }
    best = max(possibilities, key=lambda x: x.get("dex_liquidity_usd") or 0)
    reason = "EXACT_CURATED_NATIVE_PROXY_PAIR_RESEARCH_ONLY" if best.get("native_asset_proxy") else "EXACT_CHAIN_CONTRACT_PAIR"
    return {"identity_status": "RESOLVED_EXACT", "identity_reason": reason, **best}


def configured_cex_watch_pairs() -> set[str]:
    try:
        doc = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    except Exception:
        return set()
    out = set()
    for row in doc.get("cex_research_watch_targets") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("exchange") or "").strip().lower() != "gate":
            continue
        pair = str(row.get("currency_pair") or "").strip().upper()
        if pair:
            out.add(pair)
    return out


def load_state() -> dict:
    if not STATE.exists():
        return {"version": 1, "pairs": {}}
    try:
        doc = json.loads(STATE.read_text())
        return doc if isinstance(doc, dict) else {"version": 1, "pairs": {}}
    except Exception:
        return {"version": 1, "pairs": {}}


def run() -> dict:
    # Request all Gate change windows. A single timezone-selected percentage can
    # collapse around a reference-window boundary while the app still shows a
    # large 24h move; discovery must not lose the asset at that boundary.
    tickers = get_json(f"{GATE}/spot/tickers?timezone=all")
    pairs = get_json(f"{GATE}/spot/currency_pairs")
    if not isinstance(tickers, list) or not isinstance(pairs, list):
        raise RuntimeError("GATE_SPOT_MARKET_DATA_UNAVAILABLE")

    pair_map = {str(p.get("id") or ""): p for p in pairs if isinstance(p, dict)}
    configured_watch = configured_cex_watch_pairs()
    native_registry = load_native_discovery_registry()
    eligible = []
    ignored_leveraged = []
    for t in tickers:
        if not isinstance(t, dict):
            continue
        pair_id = str(t.get("currency_pair") or "")
        p = pair_map.get(pair_id) or {}
        base = str(p.get("base") or (pair_id.rsplit("_", 1)[0] if "_" in pair_id else "")).upper()
        quote = str(p.get("quote") or (pair_id.rsplit("_", 1)[-1] if "_" in pair_id else "")).upper()
        if quote != "USDT" or not base:
            continue
        if p.get("trade_status") not in (None, "tradable"):
            continue
        if str(p.get("type") or "normal").lower() != "normal":
            continue
        if bool(p.get("st_tag")):
            continue
        if is_leveraged(base, t):
            ignored_leveraged.append(pair_id)
            continue
        last = num(t.get("last"))
        change = num(t.get("change_percentage"))
        change_utc0 = num(t.get("change_utc0"))
        change_utc8 = num(t.get("change_utc8"))
        change_windows = [x for x in (change, change_utc0, change_utc8) if x is not None]
        quote_volume = num(t.get("quote_volume"), 0.0) or 0.0
        if last is None or last <= 0 or not change_windows:
            continue
        discovery_change = max(change_windows)
        buy_start = int(num(p.get("buy_start"), 0) or 0)
        eligible.append({
            "symbol": base,
            "currency_pair": pair_id,
            "source": "Gate Spot",
            "source_url": str(p.get("trade_url") or f"https://www.gate.com/trade/{pair_id}"),
            "discovery_price": last,
            "change_24h_pct": change if change is not None else discovery_change,
            "discovery_momentum_change_pct": discovery_change,
            "change_percentage_raw": change,
            "change_utc0_pct": change_utc0,
            "change_utc8_pct": change_utc8,
            "quote_volume_24h_usd": round(quote_volume, 2),
            "high_24h": num(t.get("high_24h")),
            "low_24h": num(t.get("low_24h")),
            "buy_start": buy_start or None,
            "gate_pair_type": str(p.get("type") or "normal"),
            "leveraged": False,
        })

    eligible_by_pair = {r["currency_pair"]: r for r in eligible}
    state = load_state()
    old_pairs = state.get("pairs") or {}
    positive = sorted(
        (r for r in eligible if float(r.get("discovery_momentum_change_pct") or 0) > 0),
        key=lambda r: (float(r.get("discovery_momentum_change_pct") or 0), r["quote_volume_24h_usd"]),
        reverse=True,
    )
    rank = {r["currency_pair"]: i for i, r in enumerate(positive, 1)}
    ts = now_dt()
    recent_cutoff = int(ts.timestamp()) - 14 * 86400

    # Broad discovery is intentionally permissive because it does not alert or trade.
    # Exact identity and the existing fusion/risk gates remain downstream.
    selected = []
    seen = set()
    for row in positive[:100]:
        if float(row.get("discovery_momentum_change_pct") or 0) < 3.0:
            continue
        selected.append(row)
        seen.add(row["currency_pair"])
    for row in eligible:
        if row["currency_pair"] in seen:
            continue
        if row.get("buy_start") and int(row["buy_start"]) >= recent_cutoff:
            selected.append(row)
            seen.add(row["currency_pair"])

    # Keep recently hot markets in the candidate set across Gate percentage-window
    # boundaries. This is discovery/state only; FINAL BUY safety gates still apply.
    for pair_id, old in old_pairs.items():
        if pair_id in seen or not isinstance(old, dict):
            continue
        row = eligible_by_pair.get(pair_id)
        if not row:
            continue
        hot_until_raw = str(old.get("hot_until") or "")
        try:
            hot_until = datetime.fromisoformat(hot_until_raw.replace("Z", "+00:00")) if hot_until_raw else None
            if hot_until is not None and hot_until.tzinfo is None:
                hot_until = hot_until.replace(tzinfo=timezone.utc)
        except Exception:
            hot_until = None
        peak_change = num(old.get("peak_discovery_momentum_change_pct"), old.get("peak_change_24h_pct", 0)) or 0.0
        peak_gain = num(old.get("peak_gain_from_first_seen_pct"), 0) or 0.0
        if (hot_until and hot_until >= ts) or peak_change >= 25.0 or peak_gain >= 25.0:
            row = dict(row)
            row["forced_hot_watch"] = True
            selected.append(row)
            seen.add(pair_id)

    # Configured CEX research watches are sticky: keep observing the exact Gate
    # market every run even if momentum fades or the pair leaves the top gainers.
    # This is state/research only. Exact on-chain identity is still mandatory
    # before promotion into the actionable Unified Watch path or Telegram.
    for pair_id in sorted(configured_watch):
        row = eligible_by_pair.get(pair_id)
        if row and pair_id not in seen:
            selected.append(row)
            seen.add(pair_id)

    # Retain historical state even when a market temporarily leaves discovery.
    # Without this, first-seen anchors reset and +25% revalidation can never be trusted.
    retention_cutoff = ts - timedelta(days=7)
    new_pairs = {}
    for pair_id, old in old_pairs.items():
        if not isinstance(old, dict):
            continue
        raw = str(old.get("last_seen_at") or old.get("first_seen_at") or "")
        try:
            last_seen_dt = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
            if last_seen_dt is not None and last_seen_dt.tzinfo is None:
                last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
        except Exception:
            last_seen_dt = None
        if last_seen_dt is None or last_seen_dt >= retention_cutoff or old.get("forced_cex_watch"):
            new_pairs[pair_id] = dict(old)

    selected.sort(
        key=lambda r: (
            0 if r["currency_pair"] in configured_watch else 1,
            0 if r.get("forced_hot_watch") else 1,
            rank.get(r["currency_pair"], 999999),
            -float(r.get("discovery_momentum_change_pct") or r.get("change_24h_pct") or 0),
        )
    )

    # Resolve the strongest movers/new listings first. Unresolved rows are still
    # retained as CEX discoveries so the engine can never silently miss them.
    resolution_budget = 30
    for idx, row in enumerate(selected):
        key = row["currency_pair"]
        old = old_pairs.get(key) or {}
        first_seen = str(old.get("first_seen_at") or ts.isoformat())
        first_seen_price = num(old.get("first_seen_price"), row["discovery_price"])
        first_seen_change = num(old.get("first_seen_change_24h_pct"), row["change_24h_pct"])
        first_seen_volume = num(old.get("first_seen_quote_volume_24h_usd"), row["quote_volume_24h_usd"])
        is_new = key not in old_pairs
        row["positive_gainer_rank"] = rank.get(key)
        row["first_seen_at"] = first_seen
        row["first_seen_price"] = first_seen_price
        row["first_seen_change_24h_pct"] = first_seen_change
        row["first_seen_quote_volume_24h_usd"] = first_seen_volume
        row["observed_at"] = ts.isoformat()
        row["new_first_seen"] = is_new
        row["forced_cex_watch"] = key in configured_watch
        row["forced_hot_watch"] = bool(row.get("forced_hot_watch"))
        row["status"] = "DISCOVERED_CEX_SPOT"

        old_exact = (
            old.get("identity_status") == "RESOLVED_EXACT"
            and old.get("network") and old.get("contract") and old.get("pair")
        )
        should_resolve = idx < resolution_budget or row.get("forced_hot_watch") or key in configured_watch
        if should_resolve:
            ident = resolve_identity(
                row["symbol"],
                native_registry=native_registry,
                cex_price=row["discovery_price"],
            )
            if ident.get("identity_status") != "RESOLVED_EXACT" and old_exact:
                ident = {
                    "identity_status": "RESOLVED_EXACT",
                    "identity_reason": old.get("identity_reason") or "PERSISTED_EXACT_IDENTITY",
                    "network": old.get("network"),
                    "contract": old.get("contract"),
                    "pair": old.get("pair"),
                    "dex_url": old.get("dex_url") or "",
                    "dex_liquidity_usd": old.get("dex_liquidity_usd"),
                    "identity_source": old.get("identity_source") or "Persisted exact identity",
                }
            row.update(ident)
            if ident.get("identity_status") == "RESOLVED_EXACT":
                row["status"] = "IDENTITY_RESOLVED"
        elif old_exact:
            row.update({
                "identity_status": "RESOLVED_EXACT",
                "identity_reason": old.get("identity_reason") or "PERSISTED_EXACT_IDENTITY",
                "network": old.get("network"),
                "contract": old.get("contract"),
                "pair": old.get("pair"),
                "dex_url": old.get("dex_url") or "",
                "dex_liquidity_usd": old.get("dex_liquidity_usd"),
                "identity_source": old.get("identity_source") or "Persisted exact identity",
            })
            row["status"] = "IDENTITY_RESOLVED"
        else:
            row.update({"identity_status": "PENDING", "identity_reason": "RESOLUTION_BUDGET"})

        current_gain = ((row["discovery_price"] / first_seen_price) - 1.0) * 100.0 if first_seen_price and first_seen_price > 0 else 0.0
        row["gain_from_first_seen_pct"] = round(current_gain, 4)
        old_peak = num(old.get("peak_change_24h_pct"), row["change_24h_pct"])
        old_peak_momentum = num(old.get("peak_discovery_momentum_change_pct"), row.get("discovery_momentum_change_pct")) or 0.0
        old_peak_gain = num(old.get("peak_gain_from_first_seen_pct"), current_gain) or current_gain
        peak_momentum = max(old_peak_momentum, float(row.get("discovery_momentum_change_pct") or 0))
        peak_gain = max(old_peak_gain, current_gain)
        hot_until = old.get("hot_until")
        if peak_momentum >= 25.0 or peak_gain >= 25.0:
            hot_until = (ts + timedelta(hours=36)).isoformat()

        new_pairs[key] = {
            "symbol": row["symbol"],
            "first_seen_at": first_seen,
            "first_seen_price": first_seen_price,
            "first_seen_change_24h_pct": first_seen_change,
            "first_seen_quote_volume_24h_usd": first_seen_volume,
            "last_seen_at": ts.isoformat(),
            "last_price": row["discovery_price"],
            "last_change_24h_pct": row["change_24h_pct"],
            "last_discovery_momentum_change_pct": row.get("discovery_momentum_change_pct"),
            "peak_change_24h_pct": max(old_peak if old_peak is not None else row["change_24h_pct"], row["change_24h_pct"]),
            "peak_discovery_momentum_change_pct": peak_momentum,
            "peak_gain_from_first_seen_pct": peak_gain,
            "hot_until": hot_until,
            "identity_status": row.get("identity_status"),
            "identity_reason": row.get("identity_reason"),
            "network": row.get("network") or old.get("network"),
            "contract": row.get("contract") or old.get("contract"),
            "pair": row.get("pair") or old.get("pair"),
            "dex_url": row.get("dex_url") or old.get("dex_url"),
            "dex_liquidity_usd": row.get("dex_liquidity_usd") if row.get("dex_liquidity_usd") is not None else old.get("dex_liquidity_usd"),
            "identity_source": row.get("identity_source") or old.get("identity_source"),
            "forced_cex_watch": bool(row.get("forced_cex_watch")),
            "forced_hot_watch": bool(row.get("forced_hot_watch")),
        }

    resolved = [r for r in selected if r.get("status") == "IDENTITY_RESOLVED"]
    output = {
        "version": 1,
        "generated_at": ts.isoformat(),
        "mode": "DISCOVERY_ONLY_NO_DIRECT_ALERTS",
        "source": "Gate public Spot API",
        "rules": {
            "quote": "USDT",
            "top_positive_scan": 100,
            "minimum_positive_change_pct": 3.0,
            "gate_change_windows": ["change_percentage", "change_utc0", "change_utc8"],
            "discovery_uses_max_positive_change_window": True,
            "hot_mover_sticky_hours": 36,
            "state_retention_days": 7,
            "persist_exact_identity_across_resolution_budget": True,
            "new_listing_window_days": 14,
            "identity_resolution_budget": resolution_budget,
            "configured_cex_research_watch_pairs": sorted(configured_watch),
            "leveraged_products_excluded": True,
            "st_risk_pairs_excluded": True,
            "curated_native_discovery_bridge_enabled": True,
            "curated_native_discovery_symbols": sorted(native_registry),
            "native_proxy_research_only": True,
            "missing_identity_self_recovery_enabled": True,
            "missing_identity_recovery_sources": [
                "Gate currency_chains",
                "curated native registry",
                "CoinGecko unique/price-coherent symbol resolution",
                "CoinGecko exact platform contract",
                "DexScreener exact token pair",
            ],
            "identity_recovery_max_cex_dex_price_divergence_pct": IDENTITY_RECOVERY_MAX_PRICE_DIVERGENCE_PCT,
        },
        "market_counts": {
            "eligible_non_leveraged_spot": len(eligible),
            "ignored_leveraged": len(ignored_leveraged),
            "discovered": len(selected),
            "identity_resolved": len(resolved),
            "identity_recovery_attempted": sum(1 for r in selected if r.get("identity_recovery_attempted")),
            "identity_recovered": sum(
                1 for r in selected
                if r.get("identity_reason") == "EXACT_IDENTITY_RECOVERED_FROM_COINGECKO_PLATFORM"
            ),
            "configured_cex_watch_present": sum(1 for r in selected if r.get("forced_cex_watch")),
        },
        "ignored_leveraged_examples": ignored_leveraged[:25],
        "candidates": selected,
        "resolved_candidates": resolved,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    STATE.write_text(json.dumps({"version": 1, "updated_at": ts.isoformat(), "pairs": new_pairs}, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "OK", **output["market_counts"], "new_first_seen": sum(1 for r in selected if r.get("new_first_seen"))}, ensure_ascii=False))
    return output


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
