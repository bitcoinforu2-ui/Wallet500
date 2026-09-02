from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from .market_data import token_pairs

DATA = Path("data")
UA = {"User-Agent": "Wallet500/1.8", "Accept": "application/json"}
DEX_SEARCH = "https://api.dexscreener.com/latest/dex/search?q="
GT_BASE = "https://api.geckoterminal.com/api/v2"

# CoinGecko platform id -> DexScreener chain id. Unknown platforms fail closed.
PLATFORM_TO_DEX = {
    "solana": "solana",
    "ethereum": "ethereum",
    "binance-smart-chain": "bsc",
    "sui": "sui",
    "base": "base",
    "arbitrum-one": "arbitrum",
    "optimistic-ethereum": "optimism",
    "polygon-pos": "polygon",
    "avalanche": "avalanche",
    "fantom": "fantom",
    "linea": "linea",
    "zksync": "zksync",
    "mantle": "mantle",
    "scroll": "scroll",
    "blast": "blast",
    "tron": "tron",
    "aptos": "aptos",
}

# GeckoTerminal network ids are not identical to DexScreener ids.
DEX_TO_GT = {
    "solana": "solana",
    "ethereum": "eth",
    "bsc": "bsc",
    "sui": "sui-network",
    "base": "base",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon_pos",
    "avalanche": "avax",
    "fantom": "ftm",
    "linea": "linea",
    "zksync": "zksync",
    "mantle": "mantle",
    "scroll": "scroll",
    "blast": "blast",
    "tron": "tron",
    "aptos": "aptos",
}


def _headers() -> dict[str, str]:
    h = dict(UA)
    key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def _get_json(url: str, timeout: int = 20, *, coingecko: bool = False):
    req = Request(url, headers=_headers() if coingecko else UA)
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _coin_platforms(coin_id: str) -> list[dict]:
    url = (
        "https://api.coingecko.com/api/v3/coins/"
        + quote(coin_id, safe="")
        + "?localization=false&tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false"
    )
    row = _get_json(url, coingecko=True)
    platforms = row.get("platforms") if isinstance(row, dict) else {}
    out = []
    for platform, address in (platforms or {}).items():
        chain = PLATFORM_TO_DEX.get(str(platform))
        address = str(address or "").strip()
        if chain and address:
            out.append({"coingecko_platform": platform, "chain": chain, "token_address": address})
    return out


def _addr_eq(a: object, b: object) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _dex_pair(candidate: dict, pair: dict, provider: str) -> dict | None:
    if not isinstance(pair, dict) or not pair.get("pairAddress"):
        return None
    chain = candidate["chain"]
    token = candidate["token_address"]
    pair_chain = str(pair.get("chainId") or chain).strip().lower()
    if pair_chain != chain.lower():
        return None
    base = (pair.get("baseToken") or {}).get("address")
    quote_token = (pair.get("quoteToken") or {}).get("address")
    token_is_base = _addr_eq(base, token)
    token_is_quote = _addr_eq(quote_token, token)
    if not (token_is_base or token_is_quote):
        return None
    # DexScreener priceUsd is the base-token price. Never mislabel it as the
    # exact token price when our exact token happens to be the quote asset.
    price_usd = _float(pair.get("priceUsd")) if token_is_base else 0.0
    return {
        **candidate,
        "pair_address": pair.get("pairAddress"),
        "dex": pair.get("dexId"),
        "dex_url": pair.get("url"),
        "price_usd": price_usd,
        "liquidity_usd": _float((pair.get("liquidity") or {}).get("usd")),
        "volume_h1": _float((pair.get("volume") or {}).get("h1")),
        "volume_h24": _float((pair.get("volume") or {}).get("h24")),
        "pair_created_at": pair.get("pairCreatedAt"),
        "pair_provider": provider,
        "exact_token_side": "BASE" if token_is_base else "QUOTE",
    }


def _dexscreener_token_pairs(candidate: dict) -> list[dict]:
    out = []
    for pair in token_pairs(candidate["chain"], candidate["token_address"]):
        row = _dex_pair(candidate, pair, "DEXSCREENER_TOKEN_PAIRS")
        if row:
            out.append(row)
    return out


def _dexscreener_search_pairs(candidate: dict) -> list[dict]:
    """Fallback for transient/incomplete token-pairs responses.

    Search results are accepted only when chain AND exact contract/mint match.
    Symbol/name text is never sufficient.
    """
    try:
        data = _get_json(DEX_SEARCH + quote(candidate["token_address"], safe=""))
    except Exception:
        return []
    out = []
    for pair in (data or {}).get("pairs") or []:
        row = _dex_pair(candidate, pair, "DEXSCREENER_EXACT_ADDRESS_SEARCH")
        if row:
            out.append(row)
    return out


def _gt_relation_address(rel: dict, included: dict[str, str]) -> str | None:
    rid = str((((rel or {}).get("data") or {}).get("id") or "")).strip()
    if not rid:
        return None
    if rid in included:
        return included[rid]
    # GeckoTerminal token ids are typically <network>_<address>.
    return rid.split("_", 1)[1] if "_" in rid else None


def _geckoterminal_pairs(candidate: dict) -> list[dict]:
    """Independent exact-address fallback when DexScreener misses a live pool."""
    network = DEX_TO_GT.get(candidate["chain"])
    if not network:
        return []
    token = candidate["token_address"]
    url = (
        f"{GT_BASE}/networks/{quote(network, safe='')}/tokens/{quote(token, safe='')}/pools"
        "?page=1&include=base_token,quote_token,dex"
    )
    try:
        payload = _get_json(url)
    except Exception:
        return []
    included: dict[str, str] = {}
    dex_names: dict[str, str] = {}
    for item in (payload or {}).get("included") or []:
        iid = str(item.get("id") or "")
        attrs = item.get("attributes") or {}
        if item.get("type") == "token":
            address = str(attrs.get("address") or "").strip()
            if iid and address:
                included[iid] = address
        elif item.get("type") == "dex":
            dex_names[iid] = str(attrs.get("name") or iid)

    out = []
    for item in (payload or {}).get("data") or []:
        if item.get("type") != "pool":
            continue
        attrs = item.get("attributes") or {}
        rel = item.get("relationships") or {}
        base = _gt_relation_address(rel.get("base_token") or {}, included)
        quote_token = _gt_relation_address(rel.get("quote_token") or {}, included)
        token_is_base = _addr_eq(base, token)
        token_is_quote = _addr_eq(quote_token, token)
        if not (token_is_base or token_is_quote):
            continue
        pair_address = str(attrs.get("address") or "").strip()
        if not pair_address:
            continue
        dex_id = str((((rel.get("dex") or {}).get("data") or {}).get("id") or "")).strip()
        volume = attrs.get("volume_usd") or {}
        created = attrs.get("pool_created_at")
        pair_created_at = None
        if created:
            try:
                s = str(created)
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                pair_created_at = int(dt.timestamp() * 1000)
            except Exception:
                pair_created_at = None
        out.append({
            **candidate,
            "pair_address": pair_address,
            "dex": dex_names.get(dex_id) or dex_id or "geckoterminal",
            "dex_url": f"https://www.geckoterminal.com/{network}/pools/{pair_address}",
            "price_usd": _float(attrs.get("base_token_price_usd") if token_is_base else attrs.get("quote_token_price_usd")),
            "liquidity_usd": _float(attrs.get("reserve_in_usd")),
            "volume_h1": _float(volume.get("h1")),
            "volume_h24": _float(volume.get("h24")),
            "pair_created_at": pair_created_at,
            "pair_provider": "GECKOTERMINAL_EXACT_TOKEN_POOLS",
            "exact_token_side": "BASE" if token_is_base else "QUOTE",
        })
    return out


def _verified_pairs(candidate: dict) -> list[dict]:
    pairs = _dexscreener_token_pairs(candidate)
    if not pairs:
        pairs = _dexscreener_search_pairs(candidate)
    if not pairs:
        pairs = _geckoterminal_pairs(candidate)
    # Deduplicate exact pair addresses without weakening exact-token proof.
    unique = {}
    for row in pairs:
        key = (str(row.get("chain") or "").lower(), str(row.get("pair_address") or "").lower())
        old = unique.get(key)
        if old is None or (_float(row.get("liquidity_usd")), _float(row.get("volume_h24"))) > (_float(old.get("liquidity_usd")), _float(old.get("volume_h24"))):
            unique[key] = row
    return list(unique.values())


def resolve_one(alert: dict) -> dict:
    """Resolve one age-gated CEX alert without ever trusting symbol text as identity."""
    coin_id = str(alert.get("coingecko_id") or "").strip()
    if not coin_id:
        return {**alert, "identity_status": "IDENTITY_PENDING", "identity_blocker": "COINGECKO_ID_MISSING", "actionable": False}
    try:
        candidates = _coin_platforms(coin_id)
    except Exception as e:
        return {**alert, "identity_status": "IDENTITY_PENDING", "identity_blocker": f"COINGECKO_PLATFORM_LOOKUP_FAILED:{type(e).__name__}", "actionable": False}
    if not candidates:
        return {**alert, "identity_status": "IDENTITY_PENDING", "identity_blocker": "NO_SUPPORTED_ONCHAIN_PLATFORM", "actionable": False}

    pairs = []
    with ThreadPoolExecutor(max_workers=min(6, len(candidates))) as pool:
        futures = {pool.submit(_verified_pairs, c): c for c in candidates}
        for fut in as_completed(futures):
            try:
                pairs.extend(fut.result())
            except Exception:
                pass
    if not pairs:
        return {
            **alert,
            "identity_status": "IDENTITY_RESOLVED_PAIR_PENDING" if len(candidates) == 1 else "IDENTITY_PENDING",
            "identity_blocker": "EXACT_DEX_PAIR_NOT_FOUND_ACROSS_PROVIDERS",
            "identity_candidates": candidates,
            "identity_providers_tried": ["DEXSCREENER_TOKEN_PAIRS", "DEXSCREENER_EXACT_ADDRESS_SEARCH", "GECKOTERMINAL_EXACT_TOKEN_POOLS"],
            "actionable": False,
        }

    best = max(pairs, key=lambda x: (_float(x.get("liquidity_usd")), _float(x.get("volume_h24"))))
    return {
        **alert,
        "identity_status": "DEX_VERIFIED",
        "identity_verified": True,
        "chain": best["chain"],
        "token_address": best["token_address"],
        "pair_address": best["pair_address"],
        "dex": best.get("dex"),
        "dex_url": best.get("dex_url"),
        "dex_price_usd": best.get("price_usd"),
        "dex_liquidity_usd": best.get("liquidity_usd"),
        "dex_volume_h1": best.get("volume_h1"),
        "dex_volume_h24": best.get("volume_h24"),
        "pair_created_at": best.get("pair_created_at"),
        "pair_provider": best.get("pair_provider"),
        "exact_token_side": best.get("exact_token_side"),
        "identity_source": "COINGECKO_EXACT_ID_PLATFORM_PLUS_EXACT_ADDRESS_DEX_POOL",
        "pair_selection_rule": "HIGHEST_CURRENT_LIQUIDITY_AMONG_EXACT_TOKEN_PAIRS_ACROSS_FALLBACK_PROVIDERS",
        # Exact identity makes the alert inspectable, but CEX alone never becomes a trade instruction.
        "actionable": False,
    }


def run(path: Path = DATA / "cex-revival-radar.json") -> dict:
    if not path.exists():
        raise SystemExit("CEX_REVIVAL_RADAR_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    alerts = list(payload.get("alerts") or [])
    resolved = []
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(alerts)))) as pool:
        futures = {pool.submit(resolve_one, row): i for i, row in enumerate(alerts)}
        by_index = {}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                by_index[idx] = fut.result()
            except Exception as e:
                row = alerts[idx]
                by_index[idx] = {**row, "identity_status": "IDENTITY_PENDING", "identity_blocker": f"RESOLUTION_FAILED:{type(e).__name__}", "actionable": False}
        resolved = [by_index[i] for i in range(len(alerts))]

    payload["version"] = max(int(payload.get("version") or 0), 10)
    payload["generated_identity_at"] = datetime.now(timezone.utc).isoformat()
    payload["identity_contract"] = {
        "symbol_only_actionable": False,
        "exact_coingecko_id_required": True,
        "exact_onchain_address_required": True,
        "exact_dex_pair_required": True,
        "providers": ["DEXSCREENER_TOKEN_PAIRS", "DEXSCREENER_EXACT_ADDRESS_SEARCH", "GECKOTERMINAL_EXACT_TOKEN_POOLS"],
        "provider_fallback_never_allows_symbol_only_match": True,
        "cex_identity_verified_is_not_a_buy_signal": True,
    }
    payload["alerts"] = resolved
    payload["identity_counts"] = {
        "dex_verified": sum(1 for x in resolved if x.get("identity_status") == "DEX_VERIFIED"),
        "pair_pending": sum(1 for x in resolved if x.get("identity_status") == "IDENTITY_RESOLVED_PAIR_PENDING"),
        "identity_pending": sum(1 for x in resolved if x.get("identity_status") == "IDENTITY_PENDING"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["identity_counts"]


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
