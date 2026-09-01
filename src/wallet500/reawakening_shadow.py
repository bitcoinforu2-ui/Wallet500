from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODE = "RESEARCH_ONLY_SURVIVOR_REAWAKENING_V1"
CONTRACT = "SURVIVOR_REAWAKENING_V1"

MAX_PRIOR_RETURN_PCT = -60.0
MIN_RECOVERY_RETURN_PCT = -20.0
MIN_LIQUIDITY_USD = 50_000.0
MIN_TURNOVER_H1 = 0.5
MAX_TURNOVER_H1 = 12.0
MIN_ACTIVITY_H1 = 100
MIN_BUY_SELL_RATIO = 1.10
REQUIRED_CONSECUTIVE = 2


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


def observation_passes(row: dict, previous: dict | None, prior_low_return_pct: float | None) -> tuple[bool, list[str], dict]:
    liquidity = _f(row.get("liquidity_usd"))
    volume = _f(row.get("volume_h1"))
    buys = int(_f(row.get("buys_h1")))
    sells = int(_f(row.get("sells_h1")))
    ret = _f(row.get("return_pct"), -10_000.0)
    turnover = volume / max(liquidity, 1.0)
    buy_sell = buys / max(sells, 1)
    price = _f(row.get("price_usd"))
    previous_price = _f((previous or {}).get("price_usd"))
    previous_liquidity = _f((previous or {}).get("liquidity_usd"))
    checks = {
        "prior_crash_observed": prior_low_return_pct is not None and prior_low_return_pct <= MAX_PRIOR_RETURN_PCT,
        "recovered_from_crash_zone": ret >= MIN_RECOVERY_RETURN_PCT,
        "liquidity_recovered": liquidity >= MIN_LIQUIDITY_USD,
        "turnover_healthy": MIN_TURNOVER_H1 <= turnover < MAX_TURNOVER_H1,
        "activity_recovered": buys + sells >= MIN_ACTIVITY_H1,
        "buyer_balance_positive": buy_sell >= MIN_BUY_SELL_RATIO,
        "price_not_falling": bool(previous) and price >= previous_price,
        "liquidity_not_drain": bool(previous) and liquidity >= previous_liquidity * 0.98,
        "exact_pair_present": bool(row.get("pair_address")),
    }
    reasons = [name.upper() for name, passed in checks.items() if passed]
    metrics = {
        "return_pct": round(ret, 4),
        "prior_low_return_pct": None if prior_low_return_pct is None else round(prior_low_return_pct, 4),
        "liquidity_usd": round(liquidity, 2),
        "turnover_h1": round(turnover, 4),
        "buy_sell_ratio_h1": round(buy_sell, 4),
        "activity_h1": buys + sells,
    }
    return all(checks.values()), reasons, metrics


def first_forward_trigger(record: dict) -> dict | None:
    """Replay in timestamp order; every decision uses only current and prior rows."""
    history = record.get("history") if isinstance(record.get("history"), list) else []
    prior_low: float | None = None
    previous: dict | None = None
    streak = 0
    first_pass_at: str | None = None
    first_pass_metrics: dict | None = None
    for row in history:
        if not isinstance(row, dict):
            continue
        passed, reasons, metrics = observation_passes(row, previous, prior_low)
        if passed:
            streak += 1
            if streak == 1:
                first_pass_at = row.get("observed_at")
                first_pass_metrics = metrics
        else:
            streak = 0
            first_pass_at = None
            first_pass_metrics = None
        if streak >= REQUIRED_CONSECUTIVE:
            return {
                "triggered_at": row.get("observed_at"),
                "first_confirmation_at": first_pass_at,
                "confirmation_observations": streak,
                "pair_address": row.get("pair_address"),
                "price_usd": row.get("price_usd"),
                "metrics": metrics,
                "first_confirmation_metrics": first_pass_metrics,
                "reasons": reasons,
            }
        current_return = _f(row.get("return_pct"), 10_000.0)
        prior_low = current_return if prior_low is None else min(prior_low, current_return)
        previous = row
    return None


def run(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tracker = _load(out / "outcome-tracker.json", {})
    state_path = out / "reawakening-shadow-state.json"
    state = _load(state_path, {"version": 1, "triggers": {}})
    triggers = state.setdefault("triggers", {})
    rows = []
    for key, record in (tracker.get("tokens") or {}).items():
        if not isinstance(record, dict) or not record.get("entry_pair_address"):
            continue
        found = first_forward_trigger(record)
        if found is None:
            continue
        immutable = triggers.get(key)
        if not isinstance(immutable, dict):
            immutable = {
                "token_key": key,
                "chain": record.get("chain"),
                "token": record.get("token"),
                "entry_pair_address": record.get("entry_pair_address"),
                **found,
            }
            triggers[key] = immutable
        rows.append({
            **immutable,
            "status": "SURVIVOR_REAWAKENING_SHADOW_WATCH",
            "current_price_usd": record.get("current_price_usd"),
            "current_return_pct": record.get("current_return_pct"),
            "peak_return_pct": record.get("peak_return_pct"),
            "updated_at": record.get("updated_at"),
            "production_portfolio_impact": "NONE",
        })
    rows.sort(key=lambda x: str(x.get("triggered_at") or ""), reverse=True)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 1,
        "mode": MODE,
        "contract": CONTRACT,
        "generated_at": now,
        "production_portfolio_impact": "NONE",
        "no_hindsight": True,
        "automatic_buy": False,
        "rule": {
            "prior_return_lte_pct": MAX_PRIOR_RETURN_PCT,
            "recovery_return_gte_pct": MIN_RECOVERY_RETURN_PCT,
            "liquidity_gte_usd": MIN_LIQUIDITY_USD,
            "turnover_h1_range": [MIN_TURNOVER_H1, MAX_TURNOVER_H1],
            "activity_h1_gte": MIN_ACTIVITY_H1,
            "buy_sell_ratio_h1_gte": MIN_BUY_SELL_RATIO,
            "consecutive_observations": REQUIRED_CONSECUTIVE,
            "requires_non_falling_price_and_no_liquidity_drain": True,
        },
        "truth_rules": [
            "the original pump/dump block is never removed retroactively",
            "a token can enter this shadow lane only after two consecutive forward observations",
            "the trigger uses only immutable exact-pair history available at that timestamp",
            "this experiment never creates BUY, QUALIFIED, or production portfolio impact",
        ],
        "counts": {"tracked": len((tracker.get("tokens") or {})), "shadow_triggers": len(rows)},
        "targets": rows,
    }
    state.update({"version": 1, "updated_at": now, "triggers": triggers})
    _write(state_path, state)
    _write(out / "reawakening-shadow.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
