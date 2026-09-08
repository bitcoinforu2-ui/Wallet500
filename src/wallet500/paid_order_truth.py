from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

MODE = "RESEARCH_ONLY_DEXSCREENER_PAID_ORDER_TRUTH_V1"
CONTRACT = "DEXSCREENER_PAID_ORDER_TRUTH_V1"
NETWORK = "solana"
PRODUCTION_IMPACT = "NONE"
ORDER_DELAY_SECONDS = 1.05
ACTIVE_ORDER_STATUSES = {"processing", "on-hold", "approved"}
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_INDEX = {c: i for i, c in enumerate(BASE58)}

DATA = Path("data")
OUTPUT = DATA / "paid-order-truth.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _n(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _err(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return "NETWORK_UNAVAILABLE"
    return f"{type(exc).__name__}:{str(exc)[:120]}"


def _get_json(url: str, timeout: int = 20):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "Wallet500-PaidOrderTruth/1.0"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _b58decode(value: str) -> bytes | None:
    if not value:
        return None
    number = 0
    try:
        for char in value:
            number = number * 58 + BASE58_INDEX[char]
    except KeyError:
        return None
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    zeros = len(value) - len(value.lstrip("1"))
    return b"\x00" * zeros + raw


def is_solana_address(value: str) -> bool:
    value = str(value or "").strip()
    decoded = _b58decode(value)
    return 32 <= len(value) <= 44 and decoded is not None and len(decoded) == 32


def _fetch_list(url: str, provider: str, statuses: list[dict]) -> list[dict]:
    try:
        value = _get_json(url)
        rows = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        statuses.append({"provider": provider, "status": "OK", "count": len(rows)})
        return [x for x in rows if isinstance(x, dict)]
    except Exception as exc:
        statuses.append({"provider": provider, "status": _err(exc), "count": 0})
        return []


def collect_candidates(statuses: list[dict]) -> dict[str, dict]:
    candidates: dict[str, dict] = {}
    sources = [
        ("TOKEN_PROFILE_LATEST", "https://api.dexscreener.com/token-profiles/latest/v1"),
        ("COMMUNITY_TAKEOVER_LATEST", "https://api.dexscreener.com/community-takeovers/latest/v1"),
    ]
    for source, url in sources:
        for row in _fetch_list(url, source, statuses):
            if str(row.get("chainId") or "").lower() != NETWORK:
                continue
            token = str(row.get("tokenAddress") or "")
            if not is_solana_address(token):
                continue
            item = candidates.setdefault(token, {"token_address": token, "candidate_sources": [], "profile_url": row.get("url")})
            if source not in item["candidate_sources"]:
                item["candidate_sources"].append(source)
            if row.get("claimDate"):
                item["claim_date"] = row.get("claimDate")

    # Re-check recent tokens already surfaced by the fast redundancy layer. This
    # does not create discovery by itself; it asks the official orders endpoint
    # whether an independently observed token also has a paid DEXScreener order.
    fast = _load(DATA / "paid-fast-redundancy-ledger.json", {})
    for event in fast.get("events") or []:
        if not isinstance(event, dict) or event.get("network") != NETWORK:
            continue
        token = str(event.get("token_address") or "")
        if not is_solana_address(token) or not event.get("pair_identity_locked"):
            continue
        item = candidates.setdefault(token, {"token_address": token, "candidate_sources": []})
        if "FAST_REDUNDANCY_EXACT_PAIR" not in item["candidate_sources"]:
            item["candidate_sources"].append("FAST_REDUNDANCY_EXACT_PAIR")
    return candidates


def fetch_orders(token: str) -> tuple[list[dict], str]:
    try:
        value = _get_json(f"https://api.dexscreener.com/orders/v1/solana/{quote(token)}")
        rows = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        return [x for x in rows if isinstance(x, dict)], "OK"
    except Exception as exc:
        return [], _err(exc)


def active_orders(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        status = str(row.get("status") or "").lower()
        if status not in ACTIVE_ORDER_STATUSES:
            continue
        out.append({
            "type": row.get("type"),
            "status": row.get("status"),
            "payment_timestamp": row.get("paymentTimestamp"),
        })
    return out


def fetch_pair(token: str, observed_at: str) -> tuple[dict | None, str]:
    try:
        value = _get_json(f"https://api.dexscreener.com/token-pairs/v1/solana/{quote(token)}")
        pairs = []
        for pair in value if isinstance(value, list) else []:
            if not isinstance(pair, dict) or str((pair.get("baseToken") or {}).get("address") or "") != token:
                continue
            pairs.append((_n((pair.get("liquidity") or {}).get("usd"), 0) or 0.0, pair))
        if not pairs:
            return None, "PAIR_NOT_FOUND"
        pair = max(pairs, key=lambda x: x[0])[1]
        return {
            "observed_at": observed_at,
            "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"),
            "symbol": (pair.get("baseToken") or {}).get("symbol"),
            "name": (pair.get("baseToken") or {}).get("name"),
            "price_usd": _n(pair.get("priceUsd")),
            "liquidity_usd": _n((pair.get("liquidity") or {}).get("usd")),
            "market_cap_usd": _n(pair.get("marketCap")),
            "boosts_active": int(_n((pair.get("boosts") or {}).get("active"), 0) or 0),
        }, "OK"
    except Exception as exc:
        return None, _err(exc)


def _main_tokens() -> set[str]:
    main = _load(DATA / "paid-visibility-ledger.json", {})
    return {
        str(x.get("token_address"))
        for x in main.get("events") or []
        if isinstance(x, dict) and str(x.get("chain") or "").lower() == NETWORK and x.get("token_address")
    }


def run(output_dir: str = "data") -> dict:
    global DATA, OUTPUT
    DATA = Path(output_dir)
    OUTPUT = DATA / "paid-order-truth.json"
    DATA.mkdir(parents=True, exist_ok=True)
    observed_at = now_iso()
    statuses: list[dict] = []
    candidates = collect_candidates(statuses)
    main_tokens = _main_tokens()
    rows = []
    order_status_counts: dict[str, int] = {}
    pair_status_counts: dict[str, int] = {}

    for index, token in enumerate(sorted(candidates)):
        if index:
            time.sleep(ORDER_DELAY_SECONDS)
        raw_orders, order_status = fetch_orders(token)
        order_status_counts[order_status] = order_status_counts.get(order_status, 0) + 1
        paid = active_orders(raw_orders)
        if not paid:
            continue
        pair, pair_status = fetch_pair(token, observed_at)
        pair_status_counts[pair_status] = pair_status_counts.get(pair_status, 0) + 1
        row = {
            **candidates[token],
            "network": NETWORK,
            "verified_by_official_orders_api": True,
            "active_paid_orders": paid,
            "pair_address": (pair or {}).get("pair_address"),
            "pair_identity_locked": bool((pair or {}).get("pair_address")),
            "market": pair,
            "main_paid_ledger_covered": token in main_tokens,
            "production_portfolio_impact": PRODUCTION_IMPACT,
        }
        rows.append(row)

    type_counts: dict[str, int] = {}
    for row in rows:
        for order in row.get("active_paid_orders") or []:
            name = str(order.get("type") or "UNKNOWN")
            type_counts[name] = type_counts.get(name, 0) + 1

    not_main = [x for x in rows if not x.get("main_paid_ledger_covered")]
    payload = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "network": NETWORK,
        "generated_at": observed_at,
        "production_portfolio_impact": PRODUCTION_IMPACT,
        "no_hindsight": True,
        "truth_policy": "Only active paid orders returned by DEXScreener's official orders API are marked verified. This layer never creates a buy or PRE-ALPHA signal.",
        "counts": {
            "candidates_checked": len(candidates),
            "verified_active_paid_tokens": len(rows),
            "verified_active_paid_tokens_not_in_main_ledger": len(not_main),
            "verified_with_locked_pair": sum(bool(x.get("pair_identity_locked")) for x in rows),
            "order_types": type_counts,
        },
        "provider_status": statuses,
        "orders_api_status_counts": order_status_counts,
        "pair_status_counts": pair_status_counts,
        "verified_paid_tokens": rows,
        "verified_not_in_main_ledger": not_main,
    }
    _write(OUTPUT, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
