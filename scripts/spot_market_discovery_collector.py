from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/spot-market-discovery.json"
STATE = ROOT / "data/spot-market-discovery-state.json"
CONFIG = ROOT / "data/unified-watch-config.json"
NATIVE_IDENTITY = ROOT / "data/native-asset-identity-registry.json"
GATE = "https://api.gateio.ws/api/v4"
UA = "Wallet500-SpotDiscovery/1.0"

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
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print("SPOT_DISCOVERY_FETCH_ERROR", url.split("?")[0], type(exc).__name__)
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


def resolve_identity(symbol: str, native_registry: dict[str, dict] | None = None) -> dict:
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
        if not gate_currency_chains_available:
            reason = "GATE_CURRENCY_CHAINS_UNAVAILABLE_AND_NO_CURATED_NATIVE_PAIR"
        else:
            reason = "NO_SUPPORTED_CONTRACT_ADDRESS" if supported_contracts == 0 else "NO_EXACT_LIQUID_DEX_PAIR"
        return {"identity_status": "UNRESOLVED", "identity_reason": reason}
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
    tickers = get_json(f"{GATE}/spot/tickers?timezone=utc0")
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
        quote_volume = num(t.get("quote_volume"), 0.0) or 0.0
        if last is None or last <= 0 or change is None:
            continue
        buy_start = int(num(p.get("buy_start"), 0) or 0)
        eligible.append({
            "symbol": base,
            "currency_pair": pair_id,
            "source": "Gate Spot",
            "source_url": str(p.get("trade_url") or f"https://www.gate.com/trade/{pair_id}"),
            "discovery_price": last,
            "change_24h_pct": change,
            "quote_volume_24h_usd": round(quote_volume, 2),
            "high_24h": num(t.get("high_24h")),
            "low_24h": num(t.get("low_24h")),
            "buy_start": buy_start or None,
            "gate_pair_type": str(p.get("type") or "normal"),
            "leveraged": False,
        })

    eligible_by_pair = {r["currency_pair"]: r for r in eligible}
    positive = sorted((r for r in eligible if r["change_24h_pct"] > 0), key=lambda r: (r["change_24h_pct"], r["quote_volume_24h_usd"]), reverse=True)
    rank = {r["currency_pair"]: i for i, r in enumerate(positive, 1)}
    ts = now_dt()
    recent_cutoff = int(ts.timestamp()) - 14 * 86400

    # Broad discovery is intentionally permissive because it does not alert or trade.
    # Exact identity and the existing fusion/risk gates remain downstream.
    selected = []
    seen = set()
    for row in positive[:100]:
        if row["change_24h_pct"] < 3.0:
            continue
        selected.append(row)
        seen.add(row["currency_pair"])
    for row in eligible:
        if row["currency_pair"] in seen:
            continue
        if row.get("buy_start") and int(row["buy_start"]) >= recent_cutoff:
            selected.append(row)
            seen.add(row["currency_pair"])

    # Configured CEX research watches are sticky: keep observing the exact Gate
    # market every run even if momentum fades or the pair leaves the top gainers.
    # This is state/research only. Exact on-chain identity is still mandatory
    # before promotion into the actionable Unified Watch path or Telegram.
    for pair_id in sorted(configured_watch):
        row = eligible_by_pair.get(pair_id)
        if row and pair_id not in seen:
            selected.append(row)
            seen.add(pair_id)

    state = load_state()
    old_pairs = state.get("pairs") or {}
    new_pairs = {}
    selected.sort(key=lambda r: (0 if r["currency_pair"] in configured_watch else 1, rank.get(r["currency_pair"], 999999), -r["change_24h_pct"]))

    # Resolve the strongest movers/new listings first. Unresolved rows are still
    # retained as CEX discoveries so the engine can never silently miss them.
    resolution_budget = 30
    for idx, row in enumerate(selected):
        key = row["currency_pair"]
        old = old_pairs.get(key) or {}
        first_seen = str(old.get("first_seen_at") or ts.isoformat())
        is_new = key not in old_pairs
        row["positive_gainer_rank"] = rank.get(key)
        row["first_seen_at"] = first_seen
        row["observed_at"] = ts.isoformat()
        row["new_first_seen"] = is_new
        row["forced_cex_watch"] = key in configured_watch
        row["status"] = "DISCOVERED_CEX_SPOT"
        if idx < resolution_budget:
            ident = resolve_identity(row["symbol"], native_registry=native_registry)
            row.update(ident)
            if ident.get("identity_status") == "RESOLVED_EXACT":
                row["status"] = "IDENTITY_RESOLVED"
        else:
            row.update({"identity_status": "PENDING", "identity_reason": "RESOLUTION_BUDGET"})

        old_peak = num(old.get("peak_change_24h_pct"), row["change_24h_pct"])
        new_pairs[key] = {
            "symbol": row["symbol"],
            "first_seen_at": first_seen,
            "last_seen_at": ts.isoformat(),
            "last_price": row["discovery_price"],
            "last_change_24h_pct": row["change_24h_pct"],
            "peak_change_24h_pct": max(old_peak if old_peak is not None else row["change_24h_pct"], row["change_24h_pct"]),
            "identity_status": row.get("identity_status"),
            "forced_cex_watch": bool(row.get("forced_cex_watch")),
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
            "new_listing_window_days": 14,
            "identity_resolution_budget": resolution_budget,
            "configured_cex_research_watch_pairs": sorted(configured_watch),
            "leveraged_products_excluded": True,
            "st_risk_pairs_excluded": True,
            "curated_native_discovery_bridge_enabled": True,
            "curated_native_discovery_symbols": sorted(native_registry),
            "native_proxy_research_only": True,
        },
        "market_counts": {
            "eligible_non_leveraged_spot": len(eligible),
            "ignored_leveraged": len(ignored_leveraged),
            "discovered": len(selected),
            "identity_resolved": len(resolved),
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
