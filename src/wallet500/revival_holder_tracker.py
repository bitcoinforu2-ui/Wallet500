from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .revival_1000 import looks_like_solana_address
from .waking_fallbacks import scan_rugcheck

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-holder-state.json"
LATEST = DATA / "revival-holder-latest.json"
MODE = "RESEARCH_ONLY_REVIVAL_HOLDER_TRACKER_V1"
NETWORK = "solana"
DEFAULT_BATCH = 30


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def pct(cur, base):
    try:
        cur = float(cur)
        base = float(base)
        if base <= 0:
            return None
        return round((cur / base - 1.0) * 100.0, 4)
    except (TypeError, ValueError):
        return None


def valid_coins(revival: dict) -> list[dict]:
    out = []
    seen = set()
    for coin in revival.get("coins") or []:
        if coin.get("network") != NETWORK:
            continue
        mint = str(coin.get("token_address") or "")
        if not looks_like_solana_address(mint) or mint in seen:
            continue
        seen.add(mint)
        out.append(coin)
    return out


def select_batch(coins: list[dict], state: dict, batch_size: int) -> tuple[list[dict], int]:
    if not coins or batch_size <= 0:
        return [], 0
    waking = [x for x in coins if x.get("watch_status") == "WAKING_MARKET_ONLY"]
    waking_mints = {str(x.get("token_address")) for x in waking}
    rotating = [x for x in coins if str(x.get("token_address")) not in waking_mints]
    cursor = int(state.get("cursor") or 0)
    room = max(0, batch_size - len(waking))
    picked = list(waking[:batch_size])
    if rotating and room:
        for i in range(min(room, len(rotating))):
            picked.append(rotating[(cursor + i) % len(rotating)])
        cursor = (cursor + min(room, len(rotating))) % len(rotating)
    return picked, cursor


def build() -> dict:
    revival = load(REVIVAL, {})
    if revival.get("network") != NETWORK or not revival.get("no_hindsight"):
        raise SystemExit("REVIVAL_HOLDER_SOURCE_CONTRACT_INVALID")
    coins = valid_coins(revival)
    if not coins:
        raise SystemExit("REVIVAL_HOLDER_NO_COINS")

    state = load(STATE, {"version": 1, "cursor": 0, "coins": {}})
    rows = state.setdefault("coins", {})
    batch_size = max(1, min(60, int(os.getenv("REVIVAL_HOLDER_BATCH", str(DEFAULT_BATCH)))))
    selected, next_cursor = select_batch(coins, state, batch_size)
    observed_at = now_iso()
    selected_mints = {str(x.get("token_address")) for x in selected}
    provider_status = []

    for coin in selected:
        mint = str(coin.get("token_address") or "")
        previous = dict(rows.get(mint) or {})
        shim = {"rugcheck_holder_count": previous.get("holder_count")}
        holders, distribution, _st, status = scan_rugcheck(mint, shim, observed_at)
        provider_status.append({"token_address": mint, **status})
        if not holders or holders.get("verified") is not True:
            continue
        metrics = holders.get("metrics") or {}
        current = metrics.get("holder_count")
        if current is None:
            continue
        first = previous.get("first_holder_count")
        first_at = previous.get("first_holder_observed_at")
        if first is None:
            first = int(current)
            first_at = observed_at
        t0 = coin.get("t0") or {}
        row = {
            "network": NETWORK,
            "token_address": mint,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "discovery_first_seen_at": t0.get("first_seen_at"),
            "first_holder_count": int(first),
            "first_holder_observed_at": first_at,
            "holder_count": int(current),
            "holder_observed_at": holders.get("observed_at") or observed_at,
            "holder_growth_count": int(current) - int(first),
            "holder_growth_pct": pct(current, first),
            "latest_scan_change_pct": metrics.get("holder_change_pct"),
            "source": holders.get("source"),
            "source_limitations": holders.get("limitations") or [],
            "baseline_relation": "AT_OR_AFTER_DISCOVERY_NO_RETROACTIVE_BACKFILL",
            "top1_pct": ((distribution or {}).get("metrics") or {}).get("top1_pct"),
            "top10_pct": ((distribution or {}).get("metrics") or {}).get("top10_pct"),
            "concentration_risk_score": (distribution or {}).get("risk_score"),
            "updated_at": observed_at,
        }
        rows[mint] = row
        time.sleep(0.12)

    state.update({
        "version": 1,
        "network": NETWORK,
        "cursor": next_cursor,
        "last_updated_at": observed_at,
        "coins": rows,
    })
    write(STATE, state)

    ordered = []
    by_mint = {str(x.get("token_address")): x for x in coins}
    for mint, row in rows.items():
        if mint not in by_mint:
            continue
        ordered.append(row)
    ordered.sort(key=lambda x: str(x.get("symbol") or ""))
    successful_now = sum(1 for x in provider_status if x.get("status") == "OK")
    payload = {
        "version": 1,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": observed_at,
        "source_generated_at": revival.get("generated_at"),
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "truth_rule": "HOLDER_T0_IS_FIRST_VERIFIED_HOLDER_OBSERVATION; NEVER FABRICATE RETROACTIVE HOLDER COUNT AT PRICE DISCOVERY",
        "provider": "RUGCHECK_EXACT_MINT_PUBLIC_REPORT",
        "batch_size": batch_size,
        "selected_this_run": len(selected_mints),
        "successful_this_run": successful_now,
        "universe": len(coins),
        "covered": len(ordered),
        "coverage_pct": round(100.0 * len(ordered) / len(coins), 2),
        "provider_status": provider_status,
        "coins": ordered,
    }
    write(LATEST, payload)
    return payload


def main() -> None:
    payload = build()
    print(json.dumps({
        "mode": payload["mode"],
        "universe": payload["universe"],
        "covered": payload["covered"],
        "coverage_pct": payload["coverage_pct"],
        "selected_this_run": payload["selected_this_run"],
        "successful_this_run": payload["successful_this_run"],
    }))


if __name__ == "__main__":
    main()
