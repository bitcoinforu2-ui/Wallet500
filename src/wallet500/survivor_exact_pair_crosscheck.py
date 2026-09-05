from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
OUT = DATA / "survivor-exact-pair-crosscheck.json"
GT_BASE = "https://api.geckoterminal.com/api/v2"
UA = {"User-Agent": "Wallet500/exact-pair-crosscheck-v1", "Accept": "application/json"}

NETWORK = {
    "solana": "solana",
    "ethereum": "eth",
    "eth": "eth",
    "bsc": "bsc",
    "bnb": "bsc",
    "base": "base",
    "arbitrum": "arbitrum",
    "polygon": "polygon_pos",
    "optimism": "optimism",
    "avalanche": "avax",
}
EVM = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "polygon", "optimism", "avalanche"}


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def norm(chain: str, value) -> str:
    s = str(value or "").strip()
    return s.lower() if str(chain or "").lower() in EVM else s


def fnum(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def pct_delta(primary, secondary):
    a, b = fnum(primary), fnum(secondary)
    if a is None or b is None or a == 0:
        return None
    return (b / a - 1.0) * 100.0


def get_pool(network: str, pair: str) -> dict:
    url = f"{GT_BASE}/networks/{quote(network, safe='')}/pools/{quote(pair, safe='')}?include=base_token,quote_token,dex"
    req = Request(url, headers=UA)
    with urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def included_addresses(payload: dict) -> dict[str, str]:
    out = {}
    for item in payload.get("included") or []:
        if item.get("type") != "token":
            continue
        iid = str(item.get("id") or "").strip()
        addr = str((item.get("attributes") or {}).get("address") or "").strip()
        if iid and addr:
            out[iid] = addr
    return out


def relationship_address(rel: dict, included: dict[str, str]) -> str | None:
    rid = str((((rel or {}).get("data") or {}).get("id") or "")).strip()
    if not rid:
        return None
    if rid in included:
        return included[rid]
    return rid.split("_", 1)[1] if "_" in rid else None


def crosscheck(row: dict) -> dict:
    chain = str(row.get("chain") or "").strip().lower()
    network = NETWORK.get(chain)
    pair = str(row.get("pair_address") or "").strip()
    token = str(row.get("token") or "").strip()
    base = {
        "chain": row.get("chain"),
        "token": token,
        "pair_address": pair,
        "provider": "GECKOTERMINAL_PUBLIC_API_V2",
        "exact_pair_only": True,
    }
    if not network or not pair or not token:
        return {**base, "coverage": "UNSUPPORTED_OR_MISSING_IDENTITY"}
    try:
        payload = get_pool(network, pair)
        item = payload.get("data") or {}
        attrs = item.get("attributes") or {}
        returned_pair = str(attrs.get("address") or "").strip()
        if not returned_pair or norm(chain, returned_pair) != norm(chain, pair):
            return {**base, "coverage": "EXACT_PAIR_IDENTITY_MISMATCH", "provider_pair_address": returned_pair or None}

        inc = included_addresses(payload)
        rel = item.get("relationships") or {}
        base_addr = relationship_address(rel.get("base_token") or {}, inc)
        quote_addr = relationship_address(rel.get("quote_token") or {}, inc)
        if norm(chain, token) == norm(chain, base_addr):
            token_side = "BASE"
            price = fnum(attrs.get("base_token_price_usd"))
        elif norm(chain, token) == norm(chain, quote_addr):
            token_side = "QUOTE"
            price = fnum(attrs.get("quote_token_price_usd"))
        else:
            return {
                **base,
                "coverage": "EXACT_TOKEN_NOT_IN_PROVIDER_PAIR",
                "provider_pair_address": returned_pair,
                "base_token_address": base_addr,
                "quote_token_address": quote_addr,
            }

        vol = attrs.get("volume_usd") or {}
        tx = attrs.get("transactions") or {}
        h1tx = tx.get("h1") or {}
        h24tx = tx.get("h24") or {}
        gt = {
            "price_usd": price,
            "liquidity_usd": fnum(attrs.get("reserve_in_usd")),
            "volume_h1": fnum(vol.get("h1")),
            "volume_h24": fnum(vol.get("h24")),
            "buys_h1": h1tx.get("buys"),
            "sells_h1": h1tx.get("sells"),
            "buys_h24": h24tx.get("buys"),
            "sells_h24": h24tx.get("sells"),
        }
        diffs = {
            "price_pct_vs_primary": pct_delta(row.get("price_usd"), gt["price_usd"]),
            "liquidity_pct_vs_primary": pct_delta(row.get("liquidity_usd"), gt["liquidity_usd"]),
            "volume_h1_pct_vs_primary": pct_delta(row.get("volume_h1"), gt["volume_h1"]),
            "volume_h24_pct_vs_primary": pct_delta(row.get("volume_h24"), gt["volume_h24"]),
        }
        flags = []
        if diffs["price_pct_vs_primary"] is not None and abs(diffs["price_pct_vs_primary"]) > 5:
            flags.append("PRICE_DIVERGENCE_GT_VS_PRIMARY_GT5PCT")
        if diffs["liquidity_pct_vs_primary"] is not None and abs(diffs["liquidity_pct_vs_primary"]) > 20:
            flags.append("LIQUIDITY_DIVERGENCE_GT_VS_PRIMARY_GT20PCT")
        return {
            **base,
            "coverage": "VERIFIED_INDEPENDENT_EXACT_PAIR_CROSSCHECK",
            "network": network,
            "provider_pair_address": returned_pair,
            "target_token_side": token_side,
            "base_token_address": base_addr,
            "quote_token_address": quote_addr,
            "provider_metrics": gt,
            "differences_vs_primary": diffs,
            "evidence_flags": flags or ["EXACT_PAIR_CONFIRMED"],
        }
    except Exception as exc:
        return {**base, "coverage": "PROVIDER_ERROR", "error": f"{type(exc).__name__}: {exc}"[:500]}


def main():
    watch = load(WATCH, {})
    if not watch:
        raise SystemExit("SURVIVOR_WATCH_OUTPUT_MISSING")
    rows = [crosscheck(row) for row in watch.get("tokens") or []]
    payload = {
        "version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "provider": "GECKOTERMINAL_PUBLIC_API_V2",
        "research_only": True,
        "production_gates_changed": False,
        "exact_pair_only": True,
        "purpose": "INDEPENDENT_EXACT_PAIR_MARKET_CROSSCHECK_NOT_PRODUCTION_REPLACEMENT",
        "tokens": rows,
        "summary": {
            "token_n": len(rows),
            "verified_n": sum(1 for x in rows if x.get("coverage") == "VERIFIED_INDEPENDENT_EXACT_PAIR_CROSSCHECK"),
            "provider_error_n": sum(1 for x in rows if x.get("coverage") == "PROVIDER_ERROR"),
            "identity_mismatch_n": sum(1 for x in rows if "MISMATCH" in str(x.get("coverage"))),
            "price_divergence_n": sum(1 for x in rows if "PRICE_DIVERGENCE_GT_VS_PRIMARY_GT5PCT" in (x.get("evidence_flags") or [])),
            "liquidity_divergence_n": sum(1 for x in rows if "LIQUIDITY_DIVERGENCE_GT_VS_PRIMARY_GT20PCT" in (x.get("evidence_flags") or [])),
        },
    }
    dump(OUT, payload)
    print(json.dumps(payload["summary"]))


if __name__ == "__main__":
    main()
