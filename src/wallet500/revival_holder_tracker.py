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
DOGE1_CASE = DATA / "case-study-doge1.json"
MODE = "RESEARCH_ONLY_REVIVAL_HOLDER_TRACKER_V1"
NETWORK = "solana"
DEFAULT_BATCH = 30
HISTORY_RETENTION_SECONDS = 9 * 24 * 60 * 60
MAX_HISTORY_POINTS = 500


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


def parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def seed_history(previous: dict) -> list[dict]:
    history = []
    for at_key, count_key in (
        ("first_holder_observed_at", "first_holder_count"),
        ("holder_observed_at", "holder_count"),
    ):
        at = previous.get(at_key)
        count = previous.get(count_key)
        if at and count is not None and parse_ts(at) is not None:
            history.append({"at": str(at), "count": int(count)})
    history.sort(key=lambda x: parse_ts(x["at"]) or 0)
    deduped = []
    seen = set()
    for point in history:
        key = (point["at"], point["count"])
        if key not in seen:
            seen.add(key)
            deduped.append(point)
    return deduped


def append_history(previous: dict, observed_at: str, current: int) -> list[dict]:
    history = list(previous.get("observations") or seed_history(previous))
    history.append({"at": observed_at, "count": int(current)})
    cur_ts = parse_ts(observed_at)
    if cur_ts is not None:
        floor = cur_ts - HISTORY_RETENTION_SECONDS
        history = [x for x in history if (parse_ts(x.get("at")) or 0) >= floor]
    history.sort(key=lambda x: parse_ts(x.get("at")) or 0)
    if len(history) > MAX_HISTORY_POINTS:
        history = history[-MAX_HISTORY_POINTS:]
    return history


def horizon_growth(history: list[dict], observed_at: str, current: int, horizon_seconds: int) -> dict:
    cur_ts = parse_ts(observed_at)
    if cur_ts is None:
        return {"ready": False}
    target_ts = cur_ts - horizon_seconds
    eligible = []
    for point in history:
        ts = parse_ts(point.get("at"))
        if ts is None or ts > target_ts:
            continue
        try:
            count = int(point.get("count"))
        except (TypeError, ValueError):
            continue
        eligible.append((ts, count, str(point.get("at"))))
    if not eligible:
        return {"ready": False}
    base_ts, base_count, base_at = max(eligible, key=lambda x: x[0])
    return {
        "ready": True,
        "base_count": base_count,
        "base_observed_at": base_at,
        "window_hours": round((cur_ts - base_ts) / 3600.0, 2),
        "growth_count": int(current) - int(base_count),
        "growth_pct": pct(current, base_count),
    }


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

    # Research case studies can be tracked even when they are intentionally
    # outside the canonical Revival universe. They never alter production gates.
    case = load(DOGE1_CASE, {})
    asset = case.get("asset") or {}
    mint = str(asset.get("mint") or asset.get("token_address") or "")
    if looks_like_solana_address(mint) and mint not in seen:
        first_seen = (
            (case.get("research_origin") or {}).get("observed_at")
            or (case.get("latest_user_snapshot") or {}).get("observed_at")
        )
        out.insert(0, {
            "network": NETWORK,
            "token_address": mint,
            "symbol": asset.get("symbol") or "DOGE-1",
            "name": asset.get("name") or "DOGE-1 Satellite",
            "t0": {"first_seen_at": first_seen},
            "_priority_holder_track": True,
            "_research_case": "DOGE1",
        })
    return out


def select_batch(coins: list[dict], state: dict, batch_size: int) -> tuple[list[dict], int]:
    if not coins or batch_size <= 0:
        return [], 0
    priority = [x for x in coins if x.get("_priority_holder_track") is True]
    priority_mints = {str(x.get("token_address")) for x in priority}
    waking = [
        x for x in coins
        if x.get("watch_status") == "WAKING_MARKET_ONLY"
        and str(x.get("token_address")) not in priority_mints
    ]
    fixed = (priority + waking)[:batch_size]
    fixed_mints = {str(x.get("token_address")) for x in fixed}
    rotating = [x for x in coins if str(x.get("token_address")) not in fixed_mints]
    cursor = int(state.get("cursor") or 0)
    room = max(0, batch_size - len(fixed))
    picked = list(fixed)
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

    state = load(STATE, {"version": 2, "cursor": 0, "coins": {}})
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
        current = int(current)
        first = previous.get("first_holder_count")
        first_at = previous.get("first_holder_observed_at")
        if first is None:
            first = current
            first_at = observed_at
        t0 = coin.get("t0") or {}
        history = append_history(previous, observed_at, current)
        h24 = horizon_growth(history, observed_at, current, 24 * 60 * 60)
        h7d = horizon_growth(history, observed_at, current, 7 * 24 * 60 * 60)
        first_hist_ts = parse_ts(history[0]["at"]) if history else None
        cur_ts = parse_ts(observed_at)
        span_hours = (
            round((cur_ts - first_hist_ts) / 3600.0, 2)
            if cur_ts is not None and first_hist_ts is not None
            else 0.0
        )
        row = {
            "network": NETWORK,
            "token_address": mint,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "research_case": coin.get("_research_case"),
            "discovery_first_seen_at": t0.get("first_seen_at"),
            "first_holder_count": int(first),
            "first_holder_observed_at": first_at,
            "holder_count": current,
            "holder_observed_at": holders.get("observed_at") or observed_at,
            "holder_growth_count": current - int(first),
            "holder_growth_pct": pct(current, first),
            "latest_scan_change_pct": metrics.get("holder_change_pct"),
            "holder_growth_24h_ready": bool(h24.get("ready")),
            "holder_growth_24h_count": h24.get("growth_count"),
            "holder_growth_24h_pct": h24.get("growth_pct"),
            "holder_24h_base_count": h24.get("base_count"),
            "holder_24h_base_observed_at": h24.get("base_observed_at"),
            "holder_24h_window_hours": h24.get("window_hours"),
            "holder_growth_7d_ready": bool(h7d.get("ready")),
            "holder_growth_7d_count": h7d.get("growth_count"),
            "holder_growth_7d_pct": h7d.get("growth_pct"),
            "holder_7d_base_count": h7d.get("base_count"),
            "holder_7d_base_observed_at": h7d.get("base_observed_at"),
            "holder_7d_window_hours": h7d.get("window_hours"),
            "holder_history_observations": len(history),
            "holder_history_span_hours": span_hours,
            "source": holders.get("source"),
            "source_limitations": holders.get("limitations") or [],
            "baseline_relation": "AT_OR_AFTER_DISCOVERY_NO_RETROACTIVE_BACKFILL",
            "horizon_rule": "NEAREST_VERIFIED_OBSERVATION_AT_OR_BEFORE_HORIZON; NO_INTERPOLATION",
            "top1_pct": ((distribution or {}).get("metrics") or {}).get("top1_pct"),
            "top10_pct": ((distribution or {}).get("metrics") or {}).get("top10_pct"),
            "concentration_risk_score": (distribution or {}).get("risk_score"),
            "updated_at": observed_at,
            "observations": history,
        }
        rows[mint] = row
        time.sleep(0.12)

    state.update({
        "version": 2,
        "network": NETWORK,
        "cursor": next_cursor,
        "last_updated_at": observed_at,
        "history_retention_days": 9,
        "horizon_rule": "NEAREST_VERIFIED_OBSERVATION_AT_OR_BEFORE_HORIZON; NO_INTERPOLATION",
        "coins": rows,
    })
    write(STATE, state)

    ordered = []
    by_mint = {str(x.get("token_address")): x for x in coins}
    for mint, row in rows.items():
        if mint not in by_mint:
            continue
        public_row = {k: v for k, v in row.items() if k != "observations"}
        ordered.append(public_row)
    ordered.sort(key=lambda x: str(x.get("symbol") or ""))
    successful_now = sum(1 for x in provider_status if x.get("status") == "OK")
    payload = {
        "version": 2,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": observed_at,
        "source_generated_at": revival.get("generated_at"),
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "truth_rule": "HOLDER_T0_IS_FIRST_VERIFIED_HOLDER_OBSERVATION; NEVER FABRICATE RETROACTIVE HOLDER COUNT AT PRICE DISCOVERY",
        "horizon_rule": "NEAREST_VERIFIED_OBSERVATION_AT_OR_BEFORE_HORIZON; NO_INTERPOLATION",
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
