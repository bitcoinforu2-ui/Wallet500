from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from .market_data import token_pairs

DATA = Path("data")
UA = {"User-Agent": "Wallet500/1.9", "Accept": "application/json"}
DEX_SEARCH = "https://api.dexscreener.com/latest/dex/search?q="
GT_BASE = "https://api.geckoterminal.com/api/v2"
CG_LIST_WITH_PLATFORMS = "https://api.coingecko.com/api/v3/coins/list?include_platform=true"

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


def _platform_rows(platforms: dict | None, source: str) -> list[dict]:
    out = []
    for platform, address in (platforms or {}).items():
        chain = PLATFORM_TO_DEX.get(str(platform))
        address = str(address or "").strip()
        if chain and address:
            out.append({
                "coingecko_platform": str(platform),
                "chain": chain,
                "token_address": address,
                "identity_candidate_source": source,
            })
    return out


def _coin_platforms(coin_id: str) -> list[dict]:
    """Single-coin compatibility fallback; live batch runs do not fan this out."""
    url = (
        "https://api.coingecko.com/api/v3/coins/"
        + quote(coin_id, safe="")
        + "?localization=false&tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false"
    )
    row = _get_json(url, coingecko=True)
    return _platform_rows(row.get("platforms") if isinstance(row, dict) else {}, "COINGECKO_SINGLE_COIN_PLATFORM")


def _platform_catalog(coin_ids: set[str], attempts: int = 3) -> tuple[dict[str, list[dict]], str | None]:
    """Resolve all exact CoinGecko IDs with one provider request, avoiding 429 storms."""
    if not coin_ids:
        return {}, None
    last = None
    for attempt in range(attempts):
        try:
            payload = _get_json(CG_LIST_WITH_PLATFORMS, timeout=30, coingecko=True)
            out: dict[str, list[dict]] = {}
            for row in payload if isinstance(payload, list) else []:
                cid = str(row.get("id") or "").strip()
                if cid in coin_ids:
                    out[cid] = _platform_rows(row.get("platforms") if isinstance(row, dict) else {}, "COINGECKO_PLATFORM_CATALOG")
            return out, None
        except Exception as e:
            last = e
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    return {}, f"{type(last).__name__}: {last}"[:300] if last else "UNKNOWN"


def _load_registry(path: Path = DATA / "cex-identity-registry.json") -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}
    symbols = raw.get("symbols") if isinstance(raw, dict) else {}
    return symbols if isinstance(symbols, dict) else {}


def _base_symbol(value: object) -> str:
    s = str(value or "").upper().replace("-", "").replace("_", "").strip()
    if s.endswith("USDTM"):
        return s[:-5]
    if s.endswith("USDT"):
        return s[:-4]
    return s


def _registry_candidates(alert: dict, registry: dict) -> list[dict]:
    """Registry fallback is accepted only when symbol seed AND exact CoinGecko ID agree."""
    reg = registry.get(_base_symbol(alert.get("symbol"))) if isinstance(registry, dict) else None
    if not isinstance(reg, dict):
        return []
    cid = str(alert.get("coingecko_id") or "").strip()
    if not cid or str(reg.get("coingecko_id") or "").strip() != cid:
        return []
    chain = str(reg.get("chain") or "").strip().lower()
    token = str(reg.get("token_address") or "").strip()
    if not chain or not token:
        return []
    return [{
        "coingecko_platform": "identity-registry",
        "chain": chain,
        "token_address": token,
        "identity_candidate_source": "EXACT_IDENTITY_REGISTRY_CGID_MATCH",
    }]


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
    return {
        **candidate,
        "pair_address": pair.get("pairAddress"),
        "dex": pair.get("dexId"),
        "dex_url": pair.get("url"),
        "price_usd": _float(pair.get("priceUsd")) if token_is_base else 0.0,
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
    return rid.split("_", 1)[1] if "_" in rid else None


def _geckoterminal_pairs(candidate: dict) -> list[dict]:
    network = DEX_TO_GT.get(candidate["chain"])
    if not network:
        return []
    token = candidate["token_address"]
    url = f"{GT_BASE}/networks/{quote(network, safe='')}/tokens/{quote(token, safe='')}/pools?page=1&include=base_token,quote_token,dex"
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
        pair_created_at = None
        created = attrs.get("pool_created_at")
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
                pass
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
    unique = {}
    for row in pairs:
        key = (str(row.get("chain") or "").lower(), str(row.get("pair_address") or "").lower())
        old = unique.get(key)
        if old is None or (_float(row.get("liquidity_usd")), _float(row.get("volume_h24"))) > (_float(old.get("liquidity_usd")), _float(old.get("volume_h24"))):
            unique[key] = row
    return list(unique.values())


def resolve_one(alert: dict, catalog: dict[str, list[dict]] | None = None, registry: dict | None = None, *, allow_single_lookup: bool = True) -> dict:
    coin_id = str(alert.get("coingecko_id") or "").strip()
    if not coin_id:
        return {**alert, "identity_status": "IDENTITY_PENDING", "identity_blocker": "COINGECKO_ID_MISSING", "actionable": False}

    candidates = list((catalog or {}).get(coin_id) or [])
    if not candidates:
        candidates = _registry_candidates(alert, registry or {})
    if not candidates and allow_single_lookup:
        try:
            candidates = _coin_platforms(coin_id)
        except Exception as e:
            return {**alert, "identity_status": "IDENTITY_PENDING", "identity_blocker": f"COINGECKO_PLATFORM_LOOKUP_FAILED:{type(e).__name__}", "actionable": False}
    if not candidates:
        return {**alert, "identity_status": "IDENTITY_PENDING", "identity_blocker": "NO_EXACT_ONCHAIN_PLATFORM_IDENTITY", "actionable": False}

    pairs = []
    with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as pool:
        futures = [pool.submit(_verified_pairs, c) for c in candidates]
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
    candidate_source = best.get("identity_candidate_source") or "COINGECKO_EXACT_ID_PLATFORM"
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
        "identity_source": f"{candidate_source}_PLUS_EXACT_ADDRESS_DEX_POOL",
        "pair_selection_rule": "HIGHEST_CURRENT_LIQUIDITY_AMONG_EXACT_TOKEN_PAIRS_ACROSS_FALLBACK_PROVIDERS",
        "actionable": False,
    }


def run(path: Path = DATA / "cex-revival-radar.json") -> dict:
    if not path.exists():
        raise SystemExit("CEX_REVIVAL_RADAR_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    alerts = list(payload.get("alerts") or [])
    coin_ids = {str(x.get("coingecko_id") or "").strip() for x in alerts if str(x.get("coingecko_id") or "").strip()}
    catalog, catalog_error = _platform_catalog(coin_ids)
    registry = _load_registry(path.parent / "cex-identity-registry.json")

    by_index = {}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(alerts)))) as pool:
        futures = {
            pool.submit(resolve_one, row, catalog, registry, allow_single_lookup=False): i
            for i, row in enumerate(alerts)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                by_index[idx] = fut.result()
            except Exception as e:
                by_index[idx] = {**alerts[idx], "identity_status": "IDENTITY_PENDING", "identity_blocker": f"RESOLUTION_FAILED:{type(e).__name__}", "actionable": False}
    resolved = [by_index[i] for i in range(len(alerts))]

    payload["version"] = max(int(payload.get("version") or 0), 11)
    payload["generated_identity_at"] = datetime.now(timezone.utc).isoformat()
    payload["identity_contract"] = {
        "symbol_only_actionable": False,
        "exact_coingecko_id_required": True,
        "exact_onchain_address_required": True,
        "exact_dex_pair_required": True,
        "platform_resolution": "ONE_BATCH_COINGECKO_COINS_LIST_INCLUDE_PLATFORM_THEN_EXACT_REGISTRY_CGID_FALLBACK",
        "providers": ["COINGECKO_PLATFORM_CATALOG", "EXACT_IDENTITY_REGISTRY_CGID_MATCH", "DEXSCREENER_TOKEN_PAIRS", "DEXSCREENER_EXACT_ADDRESS_SEARCH", "GECKOTERMINAL_EXACT_TOKEN_POOLS"],
        "provider_fallback_never_allows_symbol_only_match": True,
        "cex_identity_verified_is_not_a_buy_signal": True,
    }
    payload["platform_catalog"] = {
        "requested_coin_ids": len(coin_ids),
        "resolved_coin_ids": sum(1 for cid in coin_ids if catalog.get(cid)),
        "status": "OK" if catalog_error is None else "DEGRADED_FAIL_CLOSED",
        "error": catalog_error,
        "anti_rate_limit_rule": "ONE_CATALOG_REQUEST_PER_RUN_NOT_ONE_COIN_REQUEST_PER_ALERT",
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
