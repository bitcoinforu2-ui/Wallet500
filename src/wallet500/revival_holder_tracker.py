from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .revival_1000 import looks_like_solana_address
from .solscan_holder_truth import SOURCE as SOLSCAN_SOURCE, fetch_holder_truth, suspicious_jump
from .waking_fallbacks import scan_rugcheck

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
STATE = DATA / "revival-holder-state.json"
LATEST = DATA / "revival-holder-latest.json"
DOGE1_CASE = DATA / "case-study-doge1.json"
MODE = "RESEARCH_ONLY_REVIVAL_HOLDER_TRACKER_V2"
NETWORK = "solana"
DEFAULT_BATCH = 30
HISTORY_RETENTION_SECONDS = 9 * 24 * 60 * 60
MAX_HISTORY_POINTS = 500
JUMP_GUARD_PCT = 25.0


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(cur, base):
    try:
        cur = float(cur); base = float(base)
        return None if base <= 0 else round((cur / base - 1.0) * 100.0, 4)
    except (TypeError, ValueError):
        return None


def parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def trusted_history(previous: dict) -> list[dict]:
    history = []
    for point in previous.get("trusted_observations") or []:
        if not isinstance(point, dict) or point.get("source") != SOLSCAN_SOURCE:
            continue
        if parse_ts(point.get("at")) is None:
            continue
        try:
            count = int(point.get("count"))
        except (TypeError, ValueError):
            continue
        history.append({"at": str(point["at"]), "count": count, "source": SOLSCAN_SOURCE})
    history.sort(key=lambda x: parse_ts(x["at"]) or 0)
    return history[-MAX_HISTORY_POINTS:]


def append_trusted(history: list[dict], observed_at: str, current: int) -> list[dict]:
    history = list(history)
    history.append({"at": observed_at, "count": int(current), "source": SOLSCAN_SOURCE})
    cur_ts = parse_ts(observed_at)
    if cur_ts is not None:
        floor = cur_ts - HISTORY_RETENTION_SECONDS
        history = [x for x in history if (parse_ts(x.get("at")) or 0) >= floor]
    history.sort(key=lambda x: parse_ts(x.get("at")) or 0)
    return history[-MAX_HISTORY_POINTS:]


def horizon_growth(history: list[dict], observed_at: str, current: int, horizon_seconds: int) -> dict:
    cur_ts = parse_ts(observed_at)
    if cur_ts is None:
        return {"ready": False}
    target = cur_ts - horizon_seconds
    eligible = []
    for point in history:
        ts = parse_ts(point.get("at"))
        if ts is None or ts > target:
            continue
        eligible.append((ts, int(point["count"]), str(point["at"])))
    if not eligible:
        return {"ready": False}
    base_ts, base_count, base_at = max(eligible, key=lambda x: x[0])
    return {
        "ready": True,
        "base_count": base_count,
        "base_observed_at": base_at,
        "window_hours": round((cur_ts - base_ts) / 3600.0, 2),
        "growth_count": int(current) - base_count,
        "growth_pct": pct(current, base_count),
    }


def valid_coins(revival: dict) -> list[dict]:
    out, seen = [], set()
    for coin in revival.get("coins") or []:
        if coin.get("network") != NETWORK:
            continue
        mint = str(coin.get("token_address") or "")
        if not looks_like_solana_address(mint) or mint in seen:
            continue
        seen.add(mint); out.append(coin)
    case = load(DOGE1_CASE, {})
    asset = case.get("asset") or {}
    mint = str(asset.get("mint") or asset.get("token_address") or "")
    if looks_like_solana_address(mint) and mint not in seen:
        first_seen = (case.get("research_origin") or {}).get("observed_at") or (case.get("latest_user_snapshot") or {}).get("observed_at")
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
    priority = [x for x in coins if x.get("_priority_holder_track") is True]
    priority_mints = {str(x.get("token_address")) for x in priority}
    waking = [x for x in coins if x.get("watch_status") == "WAKING_MARKET_ONLY" and str(x.get("token_address")) not in priority_mints]
    fixed = (priority + waking)[:batch_size]
    fixed_mints = {str(x.get("token_address")) for x in fixed}
    rotating = [x for x in coins if str(x.get("token_address")) not in fixed_mints]
    cursor = int(state.get("cursor") or 0)
    room = max(0, batch_size - len(fixed)); picked = list(fixed)
    if rotating and room:
        n = min(room, len(rotating))
        picked.extend(rotating[(cursor + i) % len(rotating)] for i in range(n))
        cursor = (cursor + n) % len(rotating)
    return picked, cursor


def _horizon_fields(prefix: str, h: dict) -> dict:
    return {
        f"holder_growth_{prefix}_ready": bool(h.get("ready")),
        f"holder_growth_{prefix}_count": h.get("growth_count"),
        f"holder_growth_{prefix}_pct": h.get("growth_pct"),
        f"holder_{prefix}_base_count": h.get("base_count"),
        f"holder_{prefix}_base_observed_at": h.get("base_observed_at"),
        f"holder_{prefix}_window_hours": h.get("window_hours"),
    }


def build() -> dict:
    revival = load(REVIVAL, {})
    if revival.get("network") != NETWORK or not revival.get("no_hindsight"):
        raise SystemExit("REVIVAL_HOLDER_SOURCE_CONTRACT_INVALID")
    coins = valid_coins(revival)
    if not coins:
        raise SystemExit("REVIVAL_HOLDER_NO_COINS")

    state = load(STATE, {"version": 3, "cursor": 0, "coins": {}})
    rows = state.setdefault("coins", {})
    batch_size = max(1, min(60, int(os.getenv("REVIVAL_HOLDER_BATCH", str(DEFAULT_BATCH)))))
    selected, next_cursor = select_batch(coins, state, batch_size)
    observed_at = now_iso()
    api_key = os.getenv("SOLSCAN_API_KEY") or ""
    provider_status = []

    for coin in selected:
        mint = str(coin.get("token_address") or "")
        previous = dict(rows.get(mint) or {})
        truth = fetch_holder_truth(mint, api_key)
        provider_status.append({"token_address": mint, "provider": SOLSCAN_SOURCE, "status": truth.get("status")})

        # RugCheck is retained only for concentration/raw confirmation. Its holder total is never a baseline.
        _holders_raw, distribution, _st, rug_status = scan_rugcheck(mint, {}, observed_at)
        raw_rug_count = (((_holders_raw or {}).get("metrics") or {}).get("holder_count"))
        provider_status.append({"token_address": mint, "provider": "rugcheck", "status": rug_status.get("status")})

        if truth.get("verified") is not True:
            previous.update({
                "network": NETWORK,
                "token_address": mint,
                "symbol": coin.get("symbol"),
                "name": coin.get("name"),
                "research_case": coin.get("_research_case"),
                "raw_rugcheck_holder_count": raw_rug_count,
                "holder_truth_status": truth.get("status") or "TRUST_SOURCE_UNAVAILABLE",
                "growth_eligible": False,
                "updated_at": observed_at,
            })
            rows[mint] = previous
            continue

        current = int(truth["holder_count"])
        history = trusted_history(previous)
        previous_count = history[-1]["count"] if history else None
        if suspicious_jump(previous_count, current, JUMP_GUARD_PCT):
            previous.update({
                "network": NETWORK,
                "token_address": mint,
                "symbol": coin.get("symbol"),
                "name": coin.get("name"),
                "research_case": coin.get("_research_case"),
                "candidate_holder_count": current,
                "candidate_observed_at": observed_at,
                "raw_rugcheck_holder_count": raw_rug_count,
                "holder_truth_status": "ANOMALY_REQUIRES_SECOND_SOURCE",
                "growth_eligible": False,
                "jump_guard_pct": JUMP_GUARD_PCT,
                "updated_at": observed_at,
            })
            rows[mint] = previous
            continue

        history = append_trusted(history, observed_at, current)
        first = history[0]["count"]
        first_at = history[0]["at"]
        h1 = horizon_growth(history, observed_at, current, 1 * 3600)
        h6 = horizon_growth(history, observed_at, current, 6 * 3600)
        h24 = horizon_growth(history, observed_at, current, 24 * 3600)
        h7d = horizon_growth(history, observed_at, current, 7 * 24 * 3600)
        first_ts = parse_ts(first_at); cur_ts = parse_ts(observed_at)
        span_hours = round((cur_ts - first_ts) / 3600.0, 2) if cur_ts is not None and first_ts is not None else 0.0
        row = {
            "network": NETWORK,
            "token_address": mint,
            "symbol": coin.get("symbol"),
            "name": coin.get("name"),
            "research_case": coin.get("_research_case"),
            "discovery_first_seen_at": (coin.get("t0") or {}).get("first_seen_at"),
            "first_holder_count": first,
            "first_holder_observed_at": first_at,
            "holder_count": current,
            "holder_observed_at": observed_at,
            "holder_growth_count": current - first,
            "holder_growth_pct": pct(current, first),
            "latest_scan_change_count": None if previous_count is None else current - previous_count,
            "latest_scan_change_pct": pct(current, previous_count) if previous_count else None,
            "holder_history_observations": len(history),
            "holder_history_span_hours": span_hours,
            "source": SOLSCAN_SOURCE,
            "holder_truth_status": "FORWARD_VERIFIED",
            "growth_eligible": True,
            "owner_semantics_sample_rows": truth.get("sample_owner_rows"),
            "owner_semantics_unique_sample": truth.get("sample_unique_owners"),
            "raw_rugcheck_holder_count": raw_rug_count,
            "source_limitations": [
                "Solscan provider holder count is used as the stable forward series; it is not a count of human beings",
                "provider change resets the trusted baseline; quarantined RugCheck history is never reused",
                "absolute jump above 25% versus the last trusted snapshot is quarantined pending a second trusted source",
            ],
            "baseline_relation": "FIRST_SOLSCAN_TRUSTED_OBSERVATION_FORWARD_ONLY",
            "horizon_rule": "NEAREST_TRUSTED_OBSERVATION_AT_OR_BEFORE_HORIZON; NO_INTERPOLATION",
            "jump_guard_pct": JUMP_GUARD_PCT,
            "top1_pct": ((distribution or {}).get("metrics") or {}).get("top1_pct"),
            "top10_pct": ((distribution or {}).get("metrics") or {}).get("top10_pct"),
            "concentration_risk_score": (distribution or {}).get("risk_score"),
            "updated_at": observed_at,
            "trusted_observations": history,
        }
        row.update(_horizon_fields("1h", h1))
        row.update(_horizon_fields("6h", h6))
        row.update(_horizon_fields("24h", h24))
        row.update(_horizon_fields("7d", h7d))
        rows[mint] = row
        time.sleep(0.12)

    state.update({
        "version": 3,
        "network": NETWORK,
        "cursor": next_cursor,
        "last_updated_at": observed_at,
        "history_retention_days": 9,
        "trusted_holder_source": SOLSCAN_SOURCE,
        "growth_fail_closed": True,
        "jump_guard_pct": JUMP_GUARD_PCT,
        "coins": rows,
    })
    write(STATE, state)

    by_mint = {str(x.get("token_address")): x for x in coins}
    ordered = []
    for mint, row in rows.items():
        if mint not in by_mint:
            continue
        ordered.append({k: v for k, v in row.items() if k != "trusted_observations"})
    ordered.sort(key=lambda x: (0 if x.get("research_case") == "DOGE1" else 1, str(x.get("symbol") or "")))
    successful_now = sum(1 for x in provider_status if x.get("provider") == SOLSCAN_SOURCE and x.get("status") == "OK")
    payload = {
        "version": 3,
        "mode": MODE,
        "network": NETWORK,
        "generated_at": observed_at,
        "source_generated_at": revival.get("generated_at"),
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "truth_rule": "HOLDER_T0_IS_FIRST_VERIFIED_HOLDER_OBSERVATION; NEVER FABRICATE RETROACTIVE HOLDER COUNT AT PRICE DISCOVERY",
        "holder_truth_policy": "SOLSCAN_STABLE_FORWARD_SERIES; RUGCHECK_TOTAL_QUARANTINED; >25PCT_JUMP_REQUIRES_SECOND_TRUSTED_SOURCE",
        "growth_fail_closed": True,
        "horizon_rule": "NEAREST_TRUSTED_OBSERVATION_AT_OR_BEFORE_HORIZON; NO_INTERPOLATION",
        "provider": SOLSCAN_SOURCE,
        "provider_configured": bool(api_key),
        "batch_size": batch_size,
        "selected_this_run": len(selected),
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
    print(json.dumps({k: payload.get(k) for k in ("mode", "provider_configured", "universe", "covered", "selected_this_run", "successful_this_run")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
