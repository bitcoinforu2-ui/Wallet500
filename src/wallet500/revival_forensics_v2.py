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


# Compatibility helpers used by revival_forensics_runner. These preserve the
# original no-hindsight/exact-pair contract while the lightweight core run()
# below keeps its newer payload shape.
def horizon_tolerance(minutes: int) -> int:
    if minutes <= 15:
        return 8
    if minutes <= 60:
        return 12
    if minutes <= 240:
        return 25
    if minutes <= 720:
        return 45
    return 90


def select_exact_pair_observation(
    history: list[dict], pair_address: str, target: datetime, tolerance_minutes: int
) -> dict | None:
    best: tuple[float, dict] | None = None
    for row in history:
        if str(row.get("pair_address") or "") != pair_address:
            continue
        at = parse_dt(row.get("at") or row.get("observed_at"))
        if not at or at < target:
            continue
        lag = (at - target).total_seconds() / 60.0
        if lag > tolerance_minutes:
            continue
        if best is None or lag < best[0]:
            best = (lag, row)
    return best[1] if best else None


def observations_since(history: list[dict], pair_address: str, t0: datetime) -> list[dict]:
    out = []
    for row in history:
        if str(row.get("pair_address") or "") != pair_address:
            continue
        at = parse_dt(row.get("at") or row.get("observed_at"))
        if at and at >= t0:
            out.append(row)
    out.sort(key=lambda x: parse_dt(x.get("at") or x.get("observed_at")) or t0)
    return out


def build_t0(coin: dict, target: dict, source_generated_at: str, created_at: str) -> dict:
    age = n(coin.get("market_age_min_days"))
    pair = exact_pair(coin)
    price = n(coin.get("price_usd") or coin.get("dex_pair_price_usd"))
    liquidity = n(coin.get("dex_pair_liquidity_usd"))
    market_cap = n(coin.get("market_cap_usd"))
    blockers = []
    if coin.get("market_age_verified") is not True or age is None or age < MIN_AGE_DAYS:
        blockers.append(f"AGE_NOT_VERIFIED_{MIN_AGE_DAYS}D_PLUS")
    if not pair:
        blockers.append("PAIR_ID_MISSING")
    if price is None or price <= 0:
        blockers.append("ENTRY_PRICE_MISSING")
    if liquidity is None or liquidity < 0:
        blockers.append("ENTRY_LIQUIDITY_MISSING")
    t0 = {
        "token_address": token_key(coin),
        "symbol": coin.get("symbol"),
        "name": coin.get("name"),
        "waking_t0": source_generated_at,
        "locked_at": created_at,
        "t0_source": "PUBLISHED_REVIVAL_SOURCE_GENERATED_AT",
        "price_usd": price,
        "liquidity_usd": liquidity,
        "market_cap_usd": market_cap,
        "pair_address": pair,
        "dex_link": coin.get("dex_link"),
        "market_age_verified": coin.get("market_age_verified") is True,
        "market_age_min_days": int(age) if age is not None else None,
        "market_age_evidence_at": coin.get("market_age_evidence_at"),
        "market_age_evidence_source": coin.get("market_age_evidence_source"),
        "revival_score_verified": n(coin.get("revival_score_verified")),
        "drawdown_from_ath_pct": n(coin.get("drawdown_from_ath_pct")),
        "change_24h_pct": n(coin.get("change_24h_pct")),
        "change_7d_pct": n(coin.get("change_7d_pct")),
        "change_30d_pct": n(coin.get("change_30d_pct")),
        "volume_24h_usd": n(coin.get("volume_24h_usd")),
        "pair_volume_24h_usd": n(coin.get("dex_pair_volume_24h_usd")),
        "confirmation_status_at_lock": target.get("confirmation_status"),
        "confirmation_score_at_lock": n(target.get("confirmation_score")),
        "blockers": blockers,
    }
    t0["evidence_sha256"] = sha256({k: v for k, v in t0.items() if k != "evidence_sha256"})
    return t0


def holder_evidence(holder_by_token: dict[str, dict], target: dict, mint: str) -> dict:
    holder = holder_by_token.get(mint) or {}
    ch = ((target.get("channels") or {}).get("holders") or {})
    cm = ch.get("metrics") or {}
    wallet = ((target.get("channels") or {}).get("wallets") or {})
    distribution = target.get("distribution_evidence") or {}
    dm = distribution.get("metrics") or {}
    return {
        "holder_baseline_count": holder.get("first_holder_count"),
        "holder_baseline_observed_at": holder.get("first_holder_observed_at"),
        "holder_count_latest": holder.get("holder_count") if holder else cm.get("holder_count"),
        "holder_growth_from_baseline_pct": holder.get("holder_growth_pct"),
        "holder_latest_scan_change_pct": holder.get("latest_scan_change_pct") if holder else cm.get("holder_change_pct"),
        "holder_source": holder.get("source") if holder else ch.get("source"),
        "holder_is_true_price_t0": False,
        "wallet_activity_available": wallet.get("available") is True,
        "wallet_activity_verified": wallet.get("verified") is True,
        "wallet_activity_source": wallet.get("source"),
        "wallet_activity_metrics": wallet.get("metrics") or {},
        "wallet500_smart_money_connected": False,
        "wallet500_smart_money_status": "NOT_CONNECTED_TO_WAKING_PIPELINE",
        "top1_token_account_pct": holder.get("top1_pct") if holder else dm.get("top1_pct"),
        "top10_token_accounts_pct": holder.get("top10_pct") if holder else dm.get("top10_pct"),
        "concentration_risk_score": holder.get("concentration_risk_score") if holder else distribution.get("risk_score"),
    }


def update_event(event: dict, history: list[dict], holder_ev: dict, now: datetime) -> dict:
    t0 = parse_dt((event.get("t0") or {}).get("waking_t0"))
    if not t0:
        event.setdefault("blockers", []).append("T0_TIMESTAMP_INVALID")
        return event
    pair = str((event.get("t0") or {}).get("pair_address") or "")
    entry_price = n((event.get("t0") or {}).get("price_usd"))
    entry_liq = n((event.get("t0") or {}).get("liquidity_usd"))
    exact = observations_since(history, pair, t0)
    horizons = event.setdefault("horizons", {})
    for mins in HORIZONS_MIN:
        key = f"{mins}m"
        if key in horizons:
            continue
        target = t0 + timedelta(minutes=mins)
        if now < target:
            continue
        row = select_exact_pair_observation(history, pair, target, horizon_tolerance(mins))
        if row is None:
            horizons[key] = {
                "target_at": target.isoformat(),
                "available": False,
                "reason": "NO_EXACT_PAIR_OBSERVATION_WITHIN_TOLERANCE",
            }
            continue
        observed = parse_dt(row.get("at") or row.get("observed_at"))
        price, liq = n(row.get("price_usd")), n(row.get("liquidity_usd"))
        horizons[key] = {
            "target_at": target.isoformat(),
            "observed_at": observed.isoformat() if observed else None,
            "lag_minutes": round((observed-target).total_seconds()/60.0, 3) if observed else None,
            "pair_address": pair,
            "pair_identity": "STRICT_MATCH",
            "price_usd": price,
            "return_pct": pct(entry_price, price),
            "liquidity_usd": liq,
            "liquidity_return_pct": pct(entry_liq, liq),
            "available": price is not None and price > 0,
        }
    prices = [n(x.get("price_usd")) for x in exact]
    prices = [x for x in prices if x is not None and x > 0]
    liqs = [n(x.get("liquidity_usd")) for x in exact]
    liqs = [x for x in liqs if x is not None and x >= 0]
    peak_price = max(prices) if prices else entry_price
    low_price = min(prices) if prices else entry_price
    min_liq = min(liqs) if liqs else entry_liq
    event["peak_return_pct"] = pct(entry_price, peak_price)
    event["max_drawdown_from_t0_pct"] = pct(entry_price, low_price)
    event["minimum_liquidity_return_pct"] = pct(entry_liq, min_liq)
    event["holder_confirmation"] = holder_ev
    event["last_updated_at"] = now.isoformat()
    age_min = (now - t0).total_seconds() / 60.0
    peak = n(event.get("peak_return_pct"), -10000.0) or -10000.0
    liq_floor = n(event.get("minimum_liquidity_return_pct"), 0.0)
    if liq_floor is not None and liq_floor <= -80:
        outcome = "FAILED_LIQUIDITY_SURVIVAL"
    elif peak >= 900:
        outcome = "REVIVAL_X10"
    elif peak >= 300:
        outcome = "REVIVAL_X4"
    elif peak >= 100:
        outcome = "REVIVAL_X2"
    elif age_min >= 1440:
        outcome = "NO_REVIVAL_24H"
    else:
        outcome = "PENDING_24H"
    event["outcome_class"] = outcome
    event["completed"] = age_min >= 1440
    if event["completed"] and not event.get("completed_at"):
        event["completed_at"] = now.isoformat()
    return event


def feature_analysis(events: list[dict]) -> dict:
    """Compare only immutable T0 fields from completed research events.

    Holder evidence is intentionally excluded because its baseline may be
    observed after WAKING T0. This helper exists for the full-lifecycle runner
    and does not affect production selection or portfolio logic.
    """
    completed = [e for e in events if e.get("completed")]
    winners = [
        e
        for e in completed
        if e.get("outcome_class") in {"REVIVAL_X2", "REVIVAL_X4", "REVIVAL_X10"}
    ]
    failures = [
        e
        for e in completed
        if e.get("outcome_class") in {"NO_REVIVAL_24H", "FAILED_LIQUIDITY_SURVIVAL"}
    ]
    fields = (
        "revival_score_verified",
        "drawdown_from_ath_pct",
        "change_24h_pct",
        "change_7d_pct",
        "change_30d_pct",
        "liquidity_usd",
        "market_cap_usd",
        "volume_24h_usd",
        "pair_volume_24h_usd",
    )
    comparison: dict[str, dict[str, Any]] = {}
    for field in fields:
        winner_values = [n((e.get("t0") or {}).get(field)) for e in winners]
        winner_values = [x for x in winner_values if x is not None]
        failure_values = [n((e.get("t0") or {}).get(field)) for e in failures]
        failure_values = [x for x in failure_values if x is not None]
        comparison[field] = {
            "winner_n": len(winner_values),
            "failure_n": len(failure_values),
            "winner_median": median(winner_values) if winner_values else None,
            "failure_median": median(failure_values) if failure_values else None,
            "sufficient_for_preliminary_comparison": (
                len(winner_values) >= 5 and len(failure_values) >= 5
            ),
        }
    return {
        "version": 2,
        "mode": MODE,
        "generated_at": now_iso(),
        "no_hindsight": True,
        "t0_only_features": True,
        "holders_excluded_from_t0_comparison": (
            "holder baseline can be observed after WAKING T0; retained as confirmation evidence only"
        ),
        "counts": {
            "completed": len(completed),
            "winners_x2_plus": len(winners),
            "failures": len(failures),
        },
        "claim_status": (
            "ENOUGH_FOR_PRELIMINARY_COMPARISON"
            if len(winners) >= 5 and len(failures) >= 5
            else "INSUFFICIENT_SAMPLE_FOR_STATISTICAL_CLAIM"
        ),
        "feature_comparison": comparison,
    }


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