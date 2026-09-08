from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
WAKING = DATA / "waking-confirmation-latest.json"
HOLDERS = DATA / "revival-holder-latest.json"
LIQUIDITY_STATE = DATA / "revival-liquidity-learning-state.json"
STATE = DATA / "revival-forensics-state.json"
LATEST = DATA / "revival-forensics-latest.json"
DASHBOARD = DATA / "revival-forensics-dashboard.json"
FEATURES = DATA / "revival-feature-analysis.json"

MODE = "RESEARCH_ONLY_REVIVAL_FORENSICS_V2"
CONTRACT = "REVIVAL_FORENSICS_V2"
NETWORK = "solana"
MIN_AGE_DAYS = 90
HORIZONS_MIN = (5, 15, 30, 60, 240, 720, 1440)
WAKING_STATUS = "WAKING_MARKET_ONLY"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def n(value: object, default: float | None = None) -> float | None:
    try:
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return default
        return x
    except (TypeError, ValueError):
        return default


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(base: object, current: object) -> float | None:
    b, c = n(base), n(current)
    if b is None or b <= 0 or c is None or c <= 0:
        return None
    return round((c / b - 1.0) * 100.0, 6)


def sha256(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def token_key(row: dict) -> str:
    return str(row.get("token_address") or row.get("token") or row.get("mint") or "")


def exact_pair(row: dict) -> str:
    return str(row.get("dex_pair_address") or row.get("pair_address") or row.get("exact_pair") or row.get("pair") or "")


def _coin_index(revival: dict) -> dict[str, dict]:
    return {token_key(x): x for x in revival.get("coins") or [] if isinstance(x, dict) and token_key(x)}


def _holder_index(holder_payload: dict) -> dict[str, dict]:
    return {token_key(x): x for x in holder_payload.get("tokens") or [] if isinstance(x, dict) and token_key(x)}


def _qualifies_t0(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("watch_status") != WAKING_STATUS:
        return False
    if row.get("market_age_verified") is not True:
        return False
    if n(row.get("market_age_min_days"), 0.0) < MIN_AGE_DAYS:
        return False
    if not exact_pair(row):
        return False
    return True


def _feature_snapshot(coin: dict, holder: dict | None = None) -> dict:
    holder = holder or {}
    return {
        "revival_score_verified": n(coin.get("revival_score_verified")),
        "liquidity_usd": n(coin.get("dex_pair_liquidity_usd")),
        "volume_h1_usd": n(coin.get("dex_pair_volume_h1_usd")),
        "volume_h24_usd": n(coin.get("dex_pair_volume_24h_usd")),
        "txns_h1": n(coin.get("dex_pair_txns_h1")),
        "buys_h1": n(coin.get("dex_pair_buys_h1")),
        "sells_h1": n(coin.get("dex_pair_sells_h1")),
        "holder_count": n(holder.get("holder_count") or holder.get("holders")),
        "holder_growth_24h_pct": n(holder.get("holder_growth_24h_pct")),
    }


def _event_id(token: str, pair: str, t0: str) -> str:
    return hashlib.sha256(f"{NETWORK}|{token}|{pair}|{t0}".encode()).hexdigest()[:24]


def _current_market(coin: dict) -> dict:
    return {
        "price_usd": n(coin.get("dex_pair_price_usd") or coin.get("price_usd")),
        "liquidity_usd": n(coin.get("dex_pair_liquidity_usd")),
        "volume_h1_usd": n(coin.get("dex_pair_volume_h1_usd")),
        "volume_h24_usd": n(coin.get("dex_pair_volume_24h_usd")),
    }


def _outcome(base: dict, current: dict) -> dict:
    p0 = n(base.get("price_usd"))
    p1 = n(current.get("price_usd"))
    l0 = n(base.get("liquidity_usd"))
    l1 = n(current.get("liquidity_usd"))
    return {
        "price_change_pct": pct(p0, p1),
        "liquidity_change_pct": pct(l0, l1),
        "current_price_usd": p1,
        "current_liquidity_usd": l1,
    }


def _status_from_outcomes(obs: list[dict]) -> str:
    gains = [n(x.get("outcome", {}).get("price_change_pct")) for x in obs]
    gains = [x for x in gains if x is not None]
    if not gains:
        return "INSUFFICIENT_COVERAGE"
    peak = max(gains)
    if peak >= 100:
        return "WINNER_2X_PLUS"
    if peak >= 25:
        return "WINNER_25PCT_PLUS"
    if min(gains) <= -50:
        return "FAILED_SURVIVAL"
    return "CONTROL_NO_BREAKOUT"


def run() -> dict:
    revival = load(REVIVAL, {})
    waking = load(WAKING, {})
    holders = load(HOLDERS, {})
    state = load(STATE, {"version": CONTRACT, "events": {}})
    events = state.setdefault("events", {})
    coin_idx = _coin_index(revival)
    holder_idx = _holder_index(holders)
    now = datetime.now(timezone.utc)

    for row in waking.get("coins") or waking.get("tokens") or []:
        if not _qualifies_t0(row):
            continue
        token = token_key(row)
        pair = exact_pair(row)
        t0 = str(row.get("generated_at") or waking.get("generated_at") or revival.get("generated_at") or now_iso())
        event_id = _event_id(token, pair, t0)
        if event_id in events:
            continue
        coin = coin_idx.get(token) or row
        holder = holder_idx.get(token)
        market = _current_market(coin)
        events[event_id] = {
            "event_id": event_id,
            "network": NETWORK,
            "token_address": token,
            "symbol": coin.get("symbol") or row.get("symbol"),
            "exact_pair": pair,
            "t0": t0,
            "feature_snapshot_t0": _feature_snapshot(coin, holder),
            "market_t0": market,
            "observations": [],
            "no_hindsight": True,
        }

    horizons = set(HORIZONS_MIN)
    for event in events.values():
        if not isinstance(event, dict):
            continue
        token = str(event.get("token_address") or "")
        pair = str(event.get("exact_pair") or "")
        coin = coin_idx.get(token)
        if not coin or exact_pair(coin) != pair:
            continue
        t0 = parse_dt(event.get("t0"))
        if not t0:
            continue
        existing = {int(x.get("horizon_min")) for x in event.get("observations") or [] if x.get("horizon_min") is not None}
        elapsed = (now - t0).total_seconds() / 60.0
        for horizon in HORIZONS_MIN:
            if horizon in existing or elapsed < horizon:
                continue
            current = _current_market(coin)
            event.setdefault("observations", []).append({
                "observed_at": now_iso(),
                "horizon_min": horizon,
                "outcome": _outcome(event.get("market_t0") or {}, current),
            })
        event["classification"] = _status_from_outcomes(event.get("observations") or [])

    state["updated_at"] = now_iso()
    state["minimum_market_age_days"] = MIN_AGE_DAYS
    state["no_hindsight"] = True
    state["production_portfolio_impact"] = "NONE"
    write(STATE, state)

    event_list = sorted(events.values(), key=lambda x: str(x.get("t0") or ""), reverse=True)
    counts: dict[str, int] = {}
    for e in event_list:
        status = str(e.get("classification") or "OPEN")
        counts[status] = counts.get(status, 0) + 1

    payload = {
        "version": CONTRACT,
        "mode": MODE,
        "generated_at": now_iso(),
        "network": NETWORK,
        "minimum_market_age_days": MIN_AGE_DAYS,
        "no_hindsight": True,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "counts": counts,
        "events": event_list,
    }
    write(LATEST, payload)
    write(DASHBOARD, payload)

    # Conservative feature summary: only completed events with timestamp-safe T0 features.
    completed = [e for e in event_list if e.get("classification") not in {None, "OPEN", "INSUFFICIENT_COVERAGE"}]
    winners = [e for e in completed if str(e.get("classification") or "").startswith("WINNER_")]
    controls = [e for e in completed if e.get("classification") == "CONTROL_NO_BREAKOUT"]
    failed = [e for e in completed if e.get("classification") == "FAILED_SURVIVAL"]

    def med(group: list[dict], key: str) -> float | None:
        vals = [n((e.get("feature_snapshot_t0") or {}).get(key)) for e in group]
        vals = [v for v in vals if v is not None]
        return round(float(median(vals)), 6) if vals else None

    feature_keys = ["revival_score_verified", "liquidity_usd", "volume_h1_usd", "volume_h24_usd", "txns_h1", "holder_growth_24h_pct"]
    feature_payload = {
        "version": "REVIVAL_FEATURE_ANALYSIS_V2",
        "generated_at": now_iso(),
        "no_hindsight": True,
        "sample": {"completed": len(completed), "winners": len(winners), "controls": len(controls), "failed_survival": len(failed)},
        "medians": {k: {"winners": med(winners, k), "controls": med(controls, k), "failed_survival": med(failed, k)} for k in feature_keys},
        "statistical_status": "INSUFFICIENT_SAMPLE" if len(winners) < 10 else "EXPLORATORY_ONLY",
    }
    write(FEATURES, feature_payload)
    print(json.dumps({"events": len(event_list), "counts": counts, "sample": feature_payload["sample"]}, ensure_ascii=False))
    return payload


if __name__ == "__main__":
    run()
