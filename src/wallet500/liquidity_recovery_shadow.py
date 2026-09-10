from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODE = "RESEARCH_ONLY_LIQUIDITY_RECOVERY_SHADOW_V3"
CONTRACT = "LIQUIDITY_RECOVERY_FORWARD_ONLY_V3"

RESEARCH_MIN_LIQUIDITY_USD = 15_000.0
PRODUCTION_MIN_LIQUIDITY_USD = 50_000.0
MIN_MARKET_AGE_DAYS = 90.0
MIN_CONFIRMATION_SPAN_MINUTES = 15.0
MIN_LIQUIDITY_GROWTH_FROM_REJECT = 1.15
MIN_LIQUIDITY_RETENTION = 0.90
MIN_GAIN_SINCE_REJECT_PCT = -20.0
MAX_GAIN_SINCE_REJECT_PCT = 35.0
MIN_VOLUME_H1_USD = 43_000.0
MIN_TURNOVER_H1 = 0.20
MIN_TXNS_H1 = 350
MIN_BUY_SELL_RATIO_H1 = 1.18
MIN_ACTIVITY_AVAILABLE = 3
MIN_ACTIVITY_PASS = 3
REQUIRED_CONSECUTIVE = 2

ELIGIBLE_SOURCE = "LIVE_SURVIVAL_FAILED"
LIQUIDITY_REASONS = {"CURRENT_LIQUIDITY_BELOW_50K", "CURRENT_LIQUIDITY_BELOW_15K"}
QUALITY_PASS_REASON = "PASSED_SCORE_LIQUIDITY_VOLUME_ACTIVITY_MANIPULATION"
HARD_EXCLUDED_REASONS = {
    "VERIFIED_RETURN_BELOW_MINUS_25PCT",
    "VERIFIED_PEAK_DRAWDOWN_BELOW_MINUS_25PCT",
    "PUMP_THEN_FAST_REVERSAL",
    "PARABOLIC_MOVE_ALREADY_REVERSING",
    "RUG_PULL_CONFIRMED",
}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _dt(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _norm_chain(value: Any) -> str:
    c = str(value or "").strip().lower()
    if c == "eth":
        return "ethereum"
    if c in {"bnb", "bsc"}:
        return "bsc"
    if c in {"sol", "solana"}:
        return "solana"
    return c


def _key(chain: Any, token: Any, pair: Any) -> str:
    c = _norm_chain(chain)
    t = str(token or "").strip()
    p = str(pair or "").strip()
    if c in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"}:
        t, p = t.lower(), p.lower()
    return f"{c}|{t}|{p}" if c and t and p else ""


def _reasons(record: dict) -> set[str]:
    snap = record.get("first_reject_snapshot") if isinstance(record.get("first_reject_snapshot"), dict) else {}
    out: set[str] = set()
    for field in ("live_survival_reasons", "qualification_reasons", "production_risk_reasons", "holder_cluster_reasons"):
        values = snap.get(field)
        if isinstance(values, list):
            out.update(str(x) for x in values if x)
    return out


def eligible_reject(record: dict) -> tuple[bool, dict]:
    snap = record.get("first_reject_snapshot") if isinstance(record.get("first_reject_snapshot"), dict) else {}
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    reasons = _reasons(record)
    liquidity = _f(snap.get("liquidity_usd"))
    age_days = _f(snap.get("market_age_min_days") or record.get("market_age_min_days"))
    age_verified = snap.get("market_age_verified") is True or record.get("market_age_verified") is True
    pair = identity.get("pair_address") or snap.get("pair_address")
    checks = {
        "source_live_survival_failed": str(record.get("first_reject_source") or "") == ELIGIBLE_SOURCE,
        "veteran_90d_plus_verified": age_verified and age_days >= MIN_MARKET_AGE_DAYS,
        "exact_pair_present": bool(pair),
        "research_liquidity_floor_met": liquidity >= RESEARCH_MIN_LIQUIDITY_USD,
        "below_production_liquidity_gate": 0 < liquidity < PRODUCTION_MIN_LIQUIDITY_USD,
        "liquidity_reject_reason_present": bool(reasons & LIQUIDITY_REASONS),
        "other_quality_checks_passed": QUALITY_PASS_REASON in reasons,
        "no_hard_failure_reason": not bool(reasons & HARD_EXCLUDED_REASONS),
    }
    return all(checks.values()), {
        "checks": checks,
        "first_liquidity_usd": liquidity,
        "reasons": sorted(reasons),
    }


def _activity(row: dict) -> tuple[dict, dict]:
    liq = _f(row.get("liquidity_usd"))
    vol = _f(row.get("volume_h1"))
    buys_raw, sells_raw = row.get("buys_h1"), row.get("sells_h1")
    buys, sells = _i(buys_raw), _i(sells_raw)
    txns = buys + sells
    turnover = vol / max(liq, 1.0)
    ratio = buys / max(sells, 1)
    available = {
        "volume_h1": row.get("volume_h1") is not None,
        "turnover_h1": row.get("volume_h1") is not None and row.get("liquidity_usd") is not None,
        "txns_h1": buys_raw is not None and sells_raw is not None,
        "buy_sell_ratio_h1": buys_raw is not None and sells_raw is not None,
    }
    passed = {
        "volume_h1": available["volume_h1"] and vol >= MIN_VOLUME_H1_USD,
        "turnover_h1": available["turnover_h1"] and turnover >= MIN_TURNOVER_H1,
        "txns_h1": available["txns_h1"] and txns >= MIN_TXNS_H1,
        "buy_sell_ratio_h1": available["buy_sell_ratio_h1"] and ratio >= MIN_BUY_SELL_RATIO_H1,
    }
    metrics = {
        "volume_h1_usd": round(vol, 2),
        "turnover_h1": round(turnover, 4),
        "txns_h1": txns,
        "buy_sell_ratio_h1": round(ratio, 4),
        "activity_checks_available": sum(available.values()),
        "activity_checks_passed": sum(bool(passed[k]) for k in passed if available[k]),
    }
    return passed, metrics


def observation_passes(row: dict, reject_price: float, reject_liquidity: float) -> tuple[bool, dict]:
    price = _f(row.get("price_usd"))
    liq = _f(row.get("liquidity_usd"))
    gain = (price / reject_price - 1.0) * 100.0 if reject_price > 0 and price > 0 else -10_000.0
    _, activity = _activity(row)
    checks = {
        "price_present": price > 0,
        "research_floor_held": liq >= RESEARCH_MIN_LIQUIDITY_USD,
        "liquidity_accelerating": liq >= reject_liquidity * MIN_LIQUIDITY_GROWTH_FROM_REJECT,
        "anti_chase_window": MIN_GAIN_SINCE_REJECT_PCT <= gain <= MAX_GAIN_SINCE_REJECT_PCT,
        "activity_coverage": int(activity["activity_checks_available"]) >= MIN_ACTIVITY_AVAILABLE,
        "activity_separator": int(activity["activity_checks_passed"]) >= MIN_ACTIVITY_PASS,
    }
    return all(checks.values()), {
        "checks": checks,
        "gain_since_reject_pct": round(gain, 4),
        "price_usd": price,
        "liquidity_usd": round(liq, 2),
        "liquidity_growth_from_reject_pct": round((liq / reject_liquidity - 1.0) * 100.0, 2) if reject_liquidity > 0 else None,
        **activity,
    }


def first_forward_trigger(record: dict, observations: list[dict], not_before: str) -> dict | None:
    eligible, meta = eligible_reject(record)
    if not eligible:
        return None
    snap = record.get("first_reject_snapshot") or {}
    ident = record.get("identity") or {}
    reject_price = _f(snap.get("price_usd"))
    reject_liq = _f(snap.get("liquidity_usd"))
    expected_pair = ident.get("pair_address") or snap.get("pair_address")
    expected_key = _key(ident.get("chain") or snap.get("chain"), ident.get("token") or snap.get("token"), expected_pair)
    cutoff = max(filter(None, [_dt(record.get("first_rejected_at") or snap.get("observed_at")), _dt(not_before)]), default=None)
    streak: list[tuple[dict, dict]] = []
    for row in sorted([x for x in observations if isinstance(x, dict)], key=lambda x: str(x.get("observed_at") or "")):
        observed = _dt(row.get("observed_at"))
        if cutoff is not None and (observed is None or observed <= cutoff):
            continue
        row_key = _key(ident.get("chain") or snap.get("chain"), ident.get("token") or snap.get("token"), row.get("pair_address") or expected_pair)
        if row_key != expected_key:
            streak = []
            continue
        passed, metrics = observation_passes(row, reject_price, reject_liq)
        if not passed:
            streak = []
            continue
        if streak:
            prev_liq = _f(streak[-1][0].get("liquidity_usd"))
            prev_price = _f(streak[-1][0].get("price_usd"))
            if _f(row.get("liquidity_usd")) < prev_liq * MIN_LIQUIDITY_RETENTION or _f(row.get("price_usd")) < prev_price:
                streak = []
        streak.append((row, metrics))
        if len(streak) < REQUIRED_CONSECUTIVE:
            continue
        first_at, current_at = _dt(streak[0][0].get("observed_at")), observed
        if first_at is None or current_at is None:
            continue
        span = (current_at - first_at).total_seconds() / 60.0
        if span < MIN_CONFIRMATION_SPAN_MINUTES:
            continue
        current = streak[-1]
        return {
            "triggered_at": row.get("observed_at"),
            "first_confirmation_at": streak[0][0].get("observed_at"),
            "confirmation_span_minutes": round(span, 2),
            "confirmation_observations": len(streak),
            "pair_address": expected_pair,
            "metrics": current[1],
            "first_reject_liquidity_usd": meta["first_liquidity_usd"],
            "production_liquidity_gate_met": _f(row.get("liquidity_usd")) >= PRODUCTION_MIN_LIQUIDITY_USD,
        }
    return None


def run(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ledger = _load(out / "rejected-candidate-ledger.json", {})
    records = ledger.get("records") if isinstance(ledger, dict) and isinstance(ledger.get("records"), dict) else {}
    tracker = _load(out / "outcome-tracker.json", {})
    tracker_tokens = tracker.get("tokens") if isinstance(tracker, dict) and isinstance(tracker.get("tokens"), dict) else {}
    state_path = out / "liquidity-recovery-shadow-state.json"
    old = _load(state_path, {})
    now = datetime.now(timezone.utc).isoformat()
    started_at = str(old.get("v3_started_at") or now)
    triggers = old.get("triggers") if isinstance(old.get("triggers"), dict) else {}

    tracker_index: dict[str, dict] = {}
    for tr in tracker_tokens.values():
        if not isinstance(tr, dict):
            continue
        key = _key(tr.get("chain"), tr.get("token"), tr.get("entry_pair_address"))
        if key:
            tracker_index[key] = tr

    eligible_count = 0
    tracked_count = 0
    rows: list[dict] = []
    for ledger_key, record in records.items():
        if not isinstance(record, dict):
            continue
        eligible, _ = eligible_reject(record)
        if not eligible:
            continue
        eligible_count += 1
        snap = record.get("first_reject_snapshot") or {}
        ident = record.get("identity") or {}
        key = _key(ident.get("chain") or snap.get("chain"), ident.get("token") or snap.get("token"), ident.get("pair_address") or snap.get("pair_address"))
        tr = tracker_index.get(key)
        if not isinstance(tr, dict):
            continue
        tracked_count += 1
        history = tr.get("history") if isinstance(tr.get("history"), list) else []
        found = first_forward_trigger(record, history, started_at)
        immutable = triggers.get(ledger_key)
        if found is not None and not isinstance(immutable, dict):
            immutable = {
                "token_key": ledger_key,
                "chain": ident.get("chain") or snap.get("chain"),
                "token": ident.get("token") or snap.get("token"),
                "pair_address": ident.get("pair_address") or snap.get("pair_address"),
                "first_rejected_at": record.get("first_rejected_at"),
                "v3_started_at": started_at,
                **found,
            }
            triggers[ledger_key] = immutable
        if isinstance(immutable, dict):
            rows.append({**immutable, "status": "LIQUIDITY_RECOVERY_SHADOW", "production_effect": False})

    rows.sort(key=lambda x: str(x.get("triggered_at") or ""), reverse=True)
    payload = {
        "version": 3,
        "mode": MODE,
        "contract": CONTRACT,
        "generated_at": now,
        "v3_started_at": started_at,
        "production_gate_changed": False,
        "production_liquidity_gate_usd": PRODUCTION_MIN_LIQUIDITY_USD,
        "research_floor_usd": RESEARCH_MIN_LIQUIDITY_USD,
        "automatic_buy": False,
        "no_hindsight": True,
        "selection_rule": {
            "source": ELIGIBLE_SOURCE,
            "market_age_days_gte": MIN_MARKET_AGE_DAYS,
            "reject_liquidity_range_usd": [RESEARCH_MIN_LIQUIDITY_USD, PRODUCTION_MIN_LIQUIDITY_USD],
            "required_quality_reason": QUALITY_PASS_REASON,
            "liquidity_reasons": sorted(LIQUIDITY_REASONS),
            "hard_excluded_reasons": sorted(HARD_EXCLUDED_REASONS),
        },
        "recovery_rule": {
            "liquidity_growth_from_reject_gte_pct": round((MIN_LIQUIDITY_GROWTH_FROM_REJECT - 1.0) * 100.0, 2),
            "liquidity_retention_gte": MIN_LIQUIDITY_RETENTION,
            "confirmation_observations": REQUIRED_CONSECUTIVE,
            "confirmation_span_minutes_gte": MIN_CONFIRMATION_SPAN_MINUTES,
            "gain_since_reject_pct_range": [MIN_GAIN_SINCE_REJECT_PCT, MAX_GAIN_SINCE_REJECT_PCT],
            "exact_pair_locked": True,
            "forward_only": True,
        },
        "activity_separator": {
            "volume_h1_gte_usd": MIN_VOLUME_H1_USD,
            "turnover_h1_gte": MIN_TURNOVER_H1,
            "txns_h1_gte": MIN_TXNS_H1,
            "buy_sell_ratio_h1_gte": MIN_BUY_SELL_RATIO_H1,
            "minimum_checks_available": MIN_ACTIVITY_AVAILABLE,
            "minimum_checks_passed": MIN_ACTIVITY_PASS,
        },
        "counts": {
            "rejected_ledger_records": len(records),
            "eligible_below_50k_rejects": eligible_count,
            "exact_pair_tracker_matches": tracked_count,
            "shadow_triggers": len(rows),
        },
        "targets": rows,
    }
    _write(state_path, {"version": 3, "mode": MODE, "updated_at": now, "v3_started_at": started_at, "triggers": triggers})
    _write(out / "liquidity-recovery-shadow.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
