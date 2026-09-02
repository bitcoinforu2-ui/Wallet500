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
UA = {"User-Agent": "Wallet500/1.6", "Accept": "application/json"}

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


def _headers() -> dict[str, str]:
    h = dict(UA)
    key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def _get_json(url: str, timeout: int = 20):
    req = Request(url, headers=_headers())
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _coin_platforms(coin_id: str) -> list[dict]:
    url = (
        "https://api.coingecko.com/api/v3/coins/"
        + quote(coin_id, safe="")
        + "?localization=false&tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false"
    )
    row = _get_json(url)
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


def _verified_pairs(candidate: dict) -> list[dict]:
    chain = candidate["chain"]
    token = candidate["token_address"]
    out = []
    for pair in token_pairs(chain, token):
        if not isinstance(pair, dict) or not pair.get("pairAddress"):
            continue
        base = (pair.get("baseToken") or {}).get("address")
        quote_token = (pair.get("quoteToken") or {}).get("address")
        if not (_addr_eq(base, token) or _addr_eq(quote_token, token)):
            continue
        liq = float(((pair.get("liquidity") or {}).get("usd") or 0))
        out.append({
            **candidate,
            "pair_address": pair.get("pairAddress"),
            "dex": pair.get("dexId"),
            "dex_url": pair.get("url"),
            "price_usd": float(pair.get("priceUsd") or 0),
            "liquidity_usd": liq,
            "volume_h1": float(((pair.get("volume") or {}).get("h1") or 0)),
            "volume_h24": float(((pair.get("volume") or {}).get("h24") or 0)),
            "pair_created_at": pair.get("pairCreatedAt"),
        })
    return out


def resolve_one(alert: dict) -> dict:
    """Resolve one already age-gated CEX alert without ever trusting its symbol as identity."""
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
            "identity_blocker": "DEX_PAIR_NOT_VERIFIED",
            "identity_candidates": candidates,
            "actionable": False,
        }

    best = max(pairs, key=lambda x: (float(x.get("liquidity_usd") or 0), float(x.get("volume_h24") or 0)))
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
        "identity_source": "COINGECKO_EXACT_ID_PLATFORM_PLUS_DEXSCREENER_EXACT_TOKEN_PAIR",
        "pair_selection_rule": "HIGHEST_CURRENT_LIQUIDITY_AMONG_EXACT_TOKEN_PAIRS",
        # Exact identity makes the alert inspectable, but CEX alone never becomes a trade instruction.
        "actionable": False,
    }


def run(path: Path = DATA / "cex-revival-radar.json") -> dict:
    if not path.exists():
        raise SystemExit("CEX_REVIVAL_RADAR_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    alerts = list(payload.get("alerts") or [])
    resolved = []
    # Current CEX alert sets are small; parallelize lookups but keep deterministic final ordering.
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

    payload["version"] = max(int(payload.get("version") or 0), 8)
    payload["generated_identity_at"] = datetime.now(timezone.utc).isoformat()
    payload["identity_contract"] = {
        "symbol_only_actionable": False,
        "exact_coingecko_id_required": True,
        "exact_onchain_address_required": True,
        "exact_dex_pair_required": True,
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
