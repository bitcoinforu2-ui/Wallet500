from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
CONFIG_PATH = DATA / "exit-engine-experiment.json"
LEDGER_PATH = DATA / "real-alert-10usd-ledger.json"
LIVE_PATH = DATA / "exit-engine-experiment-live.json"
EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche"}

DEFAULT_STRATEGY = {
    "hard_stop_pct": -8.0,
    "trailing_activation_gain_pct": 25.0,
    "trailing_stop_from_peak_pct": 10.0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_ts(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def _norm(chain: str, value: object) -> str:
    text = str(value or "").strip()
    return text.lower() if chain.lower() in EVM else text


def _token_id(row: dict[str, Any]) -> str:
    chain = str(row.get("chain") or "").strip().lower()
    token = _norm(chain, row.get("token_address") or row.get("token"))
    return f"{chain}:{token}" if chain and token else ""


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _strategy(config: dict[str, Any]) -> dict[str, float]:
    raw = dict(DEFAULT_STRATEGY)
    raw.update(dict(config.get("strategy") or {}))
    return {
        "hard_stop_pct": _float(raw.get("hard_stop_pct"), -8.0),
        "trailing_activation_gain_pct": _float(raw.get("trailing_activation_gain_pct"), 25.0),
        "trailing_stop_from_peak_pct": _float(raw.get("trailing_stop_from_peak_pct"), 10.0),
    }


def _earliest_per_token(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = [r for r in rows if isinstance(r, dict) and _token_id(r) and _float(r.get("entry_price_usd")) > 0]
    valid.sort(key=lambda r: (_parse_ts(r.get("entry_time")) or datetime.max.replace(tzinfo=timezone.utc), str(r.get("key") or "")))
    chosen: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []
    for row in valid:
        token_id = _token_id(row)
        if token_id in chosen:
            excluded.append({
                "token_id": token_id,
                "symbol": row.get("symbol"),
                "excluded_key": row.get("key"),
                "kept_key": chosen[token_id].get("key"),
                "reason": "ONE_POSITION_PER_TOKEN_ACROSS_PAIRS",
            })
            continue
        chosen[token_id] = row
    return list(chosen.values()), excluded


def _initial_position(source: dict[str, Any], experiment_started_at: str) -> dict[str, Any]:
    entry = _float(source.get("entry_price_usd"))
    cost = _float(source.get("cost_usd"), 10.0) or 10.0
    quantity = _float(source.get("quantity")) or (cost / entry if entry > 0 else 0.0)
    legacy = bool(_parse_ts(source.get("entry_time")) and _parse_ts(experiment_started_at) and _parse_ts(source.get("entry_time")) < _parse_ts(experiment_started_at))
    return {
        "token_id": _token_id(source),
        "source_key": source.get("key"),
        "symbol": source.get("symbol"),
        "chain": source.get("chain"),
        "token_address": source.get("token_address"),
        "pair_address": source.get("pair_address"),
        "dex_url": source.get("dex_url"),
        "entry_time": source.get("entry_time"),
        "entry_price_usd": entry,
        "cost_usd": cost,
        "quantity": quantity,
        "status": "OPEN",
        "legacy_cohort": legacy,
        "historical_replay_basis": "PERSISTED_CHECKPOINTS_ONLY" if legacy else "FORWARD_MARKS_ONLY",
        "truth_rule": "NO_HINDSIGHT_FIRST_OBSERVED_MARK_ONLY",
        "observed_peak_price_usd": entry,
        "observed_peak_return_pct": 0.0,
        "trailing_active": False,
        "trailing_activated_at": None,
        "active_stop_price_usd": entry * 0.92 if entry > 0 else None,
        "active_stop_type": "HARD_STOP",
        "last_observed_at": source.get("entry_time"),
        "last_observed_price_usd": entry,
        "exit_time": None,
        "exit_price_usd": None,
        "exit_reason": None,
        "exit_value_usd": None,
        "realized_return_pct": None,
        "observations_applied": 1,
    }


def apply_observation(position: dict[str, Any], at: object, price: object, strategy: dict[str, float]) -> dict[str, Any]:
    """Apply one chronological observed mark. Never uses an unknown intraperiod high/low."""
    if position.get("status") != "OPEN":
        return position
    entry = _float(position.get("entry_price_usd"))
    qty = _float(position.get("quantity"))
    px = _float(price)
    if entry <= 0 or qty <= 0 or px <= 0:
        return position

    at_text = str(at or "")
    previous_ts = _parse_ts(position.get("last_observed_at"))
    this_ts = _parse_ts(at_text)
    if previous_ts and this_ts and this_ts <= previous_ts:
        return position

    peak = max(_float(position.get("observed_peak_price_usd"), entry), px)
    peak_return = ((peak / entry) - 1.0) * 100.0
    current_return = ((px / entry) - 1.0) * 100.0
    activation = _float(strategy.get("trailing_activation_gain_pct"), 25.0)
    trail_pct = _float(strategy.get("trailing_stop_from_peak_pct"), 10.0)
    hard_stop_pct = _float(strategy.get("hard_stop_pct"), -8.0)

    trailing_active = bool(position.get("trailing_active"))
    if not trailing_active and peak_return >= activation:
        trailing_active = True
        position["trailing_active"] = True
        position["trailing_activated_at"] = at_text

    if trailing_active:
        stop = peak * (1.0 - trail_pct / 100.0)
        stop_type = "TRAILING_STOP"
    else:
        stop = entry * (1.0 + hard_stop_pct / 100.0)
        stop_type = "HARD_STOP"

    position.update({
        "observed_peak_price_usd": peak,
        "observed_peak_return_pct": round(peak_return, 6),
        "active_stop_price_usd": stop,
        "active_stop_type": stop_type,
        "last_observed_at": at_text,
        "last_observed_price_usd": px,
        "current_return_pct": round(current_return, 6),
        "observations_applied": int(position.get("observations_applied") or 0) + 1,
    })

    should_exit = (trailing_active and px <= stop) or ((not trailing_active) and current_return <= hard_stop_pct)
    if should_exit:
        value = qty * px
        position.update({
            "status": "CLOSED",
            "exit_time": at_text,
            "exit_price_usd": px,
            "exit_reason": stop_type,
            "exit_value_usd": value,
            "realized_return_pct": round(((value / _float(position.get("cost_usd"), 10.0)) - 1.0) * 100.0, 6),
        })
    return position


def _bootstrap_observations(source: dict[str, Any]) -> list[tuple[str, float]]:
    points: list[tuple[str, float]] = []
    for cp in (source.get("checkpoints") or {}).values():
        if not isinstance(cp, dict):
            continue
        at = str(cp.get("captured_at") or "")
        price = _float(cp.get("price_usd"))
        if _parse_ts(at) and price > 0:
            points.append((at, price))
    at = str(source.get("last_mark_at") or "")
    price = _float(source.get("current_price_usd"))
    if _parse_ts(at) and price > 0:
        points.append((at, price))
    points.sort(key=lambda item: _parse_ts(item[0]) or datetime.max.replace(tzinfo=timezone.utc))
    seen: set[tuple[str, float]] = set()
    out: list[tuple[str, float]] = []
    for item in points:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _summary(state: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    positions = list((state.get("positions") or {}).values())
    strategy_equity = 0.0
    hold_equity = 0.0
    open_count = 0
    closed_count = 0
    rows: list[dict[str, Any]] = []
    for p in positions:
        source = sources.get(str(p.get("token_id"))) or {}
        current_price = _float(source.get("current_price_usd")) or _float(p.get("last_observed_price_usd"))
        hold_value = _float(p.get("quantity")) * current_price
        if p.get("status") == "CLOSED":
            strategy_value = _float(p.get("exit_value_usd"))
            closed_count += 1
        else:
            strategy_value = _float(p.get("quantity")) * current_price
            open_count += 1
        strategy_equity += strategy_value
        hold_equity += hold_value
        row = dict(p)
        row.update({
            "current_price_usd": current_price,
            "strategy_value_usd": round(strategy_value, 8),
            "hold_value_usd": round(hold_value, 8),
            "hold_return_pct": round(((hold_value / _float(p.get("cost_usd"), 10.0)) - 1.0) * 100.0, 6) if _float(p.get("cost_usd"), 10.0) > 0 else 0.0,
        })
        rows.append(row)

    initial = sum(_float(p.get("cost_usd"), 10.0) for p in positions)
    strategy_pnl = strategy_equity - initial
    hold_pnl = hold_equity - initial
    strategy_roi = strategy_pnl / initial * 100.0 if initial else 0.0
    hold_roi = hold_pnl / initial * 100.0 if initial else 0.0
    rows.sort(key=lambda p: (p.get("status") != "OPEN", -_float(p.get("strategy_value_usd"))))
    return {
        "positions_total": len(positions),
        "initial_capital_usd": round(initial, 8),
        "strategy_equity_usd": round(strategy_equity, 8),
        "strategy_pnl_usd": round(strategy_pnl, 8),
        "strategy_roi_pct": round(strategy_roi, 6),
        "hold_equity_usd": round(hold_equity, 8),
        "hold_pnl_usd": round(hold_pnl, 8),
        "hold_roi_pct": round(hold_roi, 6),
        "strategy_vs_hold_usd": round(strategy_equity - hold_equity, 8),
        "strategy_vs_hold_pct_points": round(strategy_roi - hold_roi, 6),
        "open_positions": open_count,
        "closed_positions": closed_count,
        "positions": rows,
    }


def reconcile(config: dict[str, Any], ledger: dict[str, Any], state: dict[str, Any] | None = None, now: str | None = None) -> dict[str, Any]:
    ts = now or _now()
    strategy = _strategy(config)
    started_at = str(config.get("started_at") or ts)
    source_rows, excluded = _earliest_per_token(list(ledger.get("positions") or []))
    sources = {_token_id(row): row for row in source_rows}

    if not isinstance(state, dict) or state.get("experiment_id") != config.get("experiment_id"):
        state = {
            "version": 1,
            "experiment_id": config.get("experiment_id") or "EXIT_ENGINE_V1",
            "mode": "PAPER_ONLY_NO_REAL_MONEY",
            "status": "ACTIVE",
            "started_at": started_at,
            "updated_at": ts,
            "strategy": strategy,
            "positions": {},
            "events": [],
        }
    positions = dict(state.get("positions") or {})
    events = list(state.get("events") or [])

    for token_id, source in sources.items():
        if token_id not in positions:
            p = _initial_position(source, started_at)
            positions[token_id] = p
            events.append({"at": ts, "type": "POSITION_ADDED", "token_id": token_id, "source_key": source.get("key"), "legacy_cohort": p.get("legacy_cohort")})
            if p.get("legacy_cohort"):
                for at, price in _bootstrap_observations(source):
                    before = p.get("status")
                    apply_observation(p, at, price, strategy)
                    if before == "OPEN" and p.get("status") == "CLOSED":
                        events.append({"at": p.get("exit_time"), "type": "PAPER_EXIT_REPLAY", "token_id": token_id, "reason": p.get("exit_reason"), "price_usd": p.get("exit_price_usd"), "basis": "PERSISTED_CHECKPOINT_FIRST_OBSERVED"})
                        break
        else:
            p = positions[token_id]
            if p.get("status") == "OPEN":
                mark_at = str(source.get("last_mark_at") or "")
                mark_price = _float(source.get("current_price_usd"))
                before = p.get("status")
                apply_observation(p, mark_at, mark_price, strategy)
                if before == "OPEN" and p.get("status") == "CLOSED":
                    events.append({"at": p.get("exit_time"), "type": "PAPER_EXIT", "token_id": token_id, "reason": p.get("exit_reason"), "price_usd": p.get("exit_price_usd"), "basis": "FORWARD_FIRST_OBSERVED_MARK"})

    state.update({
        "version": 1,
        "mode": "PAPER_ONLY_NO_REAL_MONEY",
        "status": "ACTIVE",
        "updated_at": ts,
        "strategy": strategy,
        "truth_rule": "NO_HINDSIGHT_FIRST_OBSERVED_MARK_ONLY",
        "positions": positions,
        "events": events[-1000:],
        "duplicates_excluded": excluded,
        "historical_replay_note": "Legacy positions are replayed only from timestamped persisted checkpoints plus the last recorded mark. Unknown intraperiod paths are never invented; this is intentionally conservative.",
    })
    state.update(_summary(state, sources))
    return state


def main() -> None:
    config = _read(CONFIG_PATH, {})
    if not config:
        raise SystemExit("EXIT_ENGINE_CONFIG_MISSING")
    ledger = _read(LEDGER_PATH, {})
    if not ledger:
        raise SystemExit("REAL_ALERT_10USD_LEDGER_MISSING")
    current = _read(LIVE_PATH, {})
    out = reconcile(config, ledger, current)
    _write(LIVE_PATH, out)
    print("EXIT_ENGINE_EXPERIMENT_OK", {
        "positions": out.get("positions_total"),
        "strategy_equity": out.get("strategy_equity_usd"),
        "strategy_roi_pct": out.get("strategy_roi_pct"),
        "hold_equity": out.get("hold_equity_usd"),
        "open": out.get("open_positions"),
        "closed": out.get("closed_positions"),
    })


if __name__ == "__main__":
    main()
