from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path("data")
STARTING_CASH_USD = 100.0
POSITION_SIZE_USD = 1.0
MIN_LIQUIDITY_USD = 50_000.0
LEDGER_PATH = DATA_DIR / "paper-portfolio-ledger.json"
SUMMARY_PATH = DATA_DIR / "paper-portfolio-summary.json"

QUOTE_SOURCES = (
    "holder-cluster-production-qualified.json",
    "holder-cluster-production-blocked.json",
    "holder-cluster-quarantine.json",
    "production-risk-blocked.json",
    "active-qualified-candidates.json",
    "live-survival-pending.json",
    "live-survival-failed.json",
    "qualified-candidates.json",
    "anomaly-radar.json",
    "market-universe.json",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def _norm(chain: str, value: str) -> str:
    s = str(value or "")
    return s.lower() if str(chain or "").lower() in {"bsc", "ethereum"} else s


def _key(row: dict[str, Any]) -> str:
    chain = str(row.get("chain") or "").lower()
    token = _norm(chain, row.get("token") or row.get("mint") or "")
    pair = _norm(chain, row.get("pair_address") or row.get("locked_pair_address") or "")
    return f"{chain}|{token}|{pair}"


def _num(row: dict[str, Any], *names: str) -> float:
    for name in names:
        try:
            value = float(row.get(name))
            if value >= 0:
                return value
        except (TypeError, ValueError):
            pass
    return 0.0


def _flatten(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item
    elif isinstance(value, dict):
        for candidate in ("rows", "items", "candidates", "plausible_rows"):
            if isinstance(value.get(candidate), list):
                yield from _flatten(value[candidate])


def _quote_index(data_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for name in QUOTE_SOURCES:
        for row in _flatten(_read(data_dir / name, [])):
            key = _key(row)
            if key.count("|") != 2 or key.endswith("|"):
                continue
            price = _num(row, "live_price_usd", "price_usd", "current_price_usd")
            if price <= 0:
                continue
            # Earlier sources in QUOTE_SOURCES have higher authority.
            if key not in index:
                index[key] = row
    return index


def _entry_is_safe(row: dict[str, Any]) -> bool:
    pair = row.get("pair_address") or row.get("locked_pair_address")
    price = _num(row, "live_price_usd", "price_usd", "current_price_usd")
    liquidity = _num(row, "live_liquidity_usd", "liquidity_usd")
    return bool(
        row.get("holder_cluster_production_status") == "PASS"
        and row.get("holder_cluster_verification_complete") is True
        and pair
        and price > 0
        and liquidity >= MIN_LIQUIDITY_USD
    )


def initial_ledger(now: str | None = None) -> dict[str, Any]:
    ts = now or _now()
    return {
        "version": 1,
        "mode": "PAPER_ONLY_NO_REAL_MONEY",
        "created_at": ts,
        "updated_at": ts,
        "starting_cash_usd": STARTING_CASH_USD,
        "position_size_usd": POSITION_SIZE_USD,
        "min_liquidity_usd": MIN_LIQUIDITY_USD,
        "cash_usd": STARTING_CASH_USD,
        "positions": [],
        "events": [],
    }


def reconcile_portfolio(
    ledger: dict[str, Any],
    production_rows: list[dict[str, Any]],
    quotes: dict[str, dict[str, Any]],
    now: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = now or _now()
    ledger = dict(ledger or initial_ledger(ts))
    positions = list(ledger.get("positions") or [])
    events = list(ledger.get("events") or [])
    cash = float(ledger.get("cash_usd", STARTING_CASH_USD))
    active = {_key(r): r for r in production_rows if _entry_is_safe(r)}
    existing = {_key(p): p for p in positions}

    # Mark or close every existing open position. A production-gate removal is
    # treated as a sell signal, but the exit is not fabricated without an exact-pair quote.
    for p in positions:
        if p.get("status") != "OPEN":
            continue
        key = _key(p)
        quote = active.get(key) or quotes.get(key)
        if quote:
            px = _num(quote, "live_price_usd", "price_usd", "current_price_usd")
            if px > 0:
                p["current_price_usd"] = px
                p["current_value_usd"] = p["quantity"] * px
                p["last_mark_at"] = ts
                p["last_liquidity_usd"] = _num(quote, "live_liquidity_usd", "liquidity_usd")
        if key not in active:
            if quote and _num(quote, "live_price_usd", "price_usd", "current_price_usd") > 0:
                exit_px = _num(quote, "live_price_usd", "price_usd", "current_price_usd")
                proceeds = p["quantity"] * exit_px
                p.update({
                    "status": "CLOSED",
                    "exit_time": ts,
                    "exit_price_usd": exit_px,
                    "exit_value_usd": proceeds,
                    "realized_pnl_usd": proceeds - p["cost_usd"],
                    "exit_reason": "NO_LONGER_PRODUCTION_QUALIFIED",
                    "current_price_usd": exit_px,
                    "current_value_usd": proceeds,
                })
                cash += proceeds
                events.append({"at": ts, "type": "SELL", "key": key, "value_usd": proceeds, "reason": p["exit_reason"]})
            else:
                p["exit_pending"] = True
                p["exit_reason"] = "EXIT_UNVERIFIED_NO_EXACT_PAIR_QUOTE"

    # One immutable $1 paper entry per exact pair. Closed pairs are never silently re-opened.
    for key, row in active.items():
        if key in existing or cash + 1e-12 < POSITION_SIZE_USD:
            continue
        entry_px = _num(row, "live_price_usd", "price_usd", "current_price_usd")
        quantity = POSITION_SIZE_USD / entry_px
        pos = {
            "chain": str(row.get("chain") or "").lower(),
            "token": row.get("token") or row.get("mint"),
            "pair_address": row.get("pair_address") or row.get("locked_pair_address"),
            "dex": row.get("dex"),
            "status": "OPEN",
            "entry_time": ts,
            "entry_price_usd": entry_px,
            "cost_usd": POSITION_SIZE_USD,
            "quantity": quantity,
            "current_price_usd": entry_px,
            "current_value_usd": POSITION_SIZE_USD,
            "last_mark_at": ts,
            "entry_liquidity_usd": _num(row, "live_liquidity_usd", "liquidity_usd"),
            "last_liquidity_usd": _num(row, "live_liquidity_usd", "liquidity_usd"),
            "entry_anomaly_score": _num(row, "anomaly_score"),
            "entry_gate": "HOLDER_CLUSTER_PRODUCTION_PASS",
            "paper_only": True,
        }
        positions.append(pos)
        existing[key] = pos
        cash -= POSITION_SIZE_USD
        events.append({"at": ts, "type": "BUY", "key": key, "value_usd": POSITION_SIZE_USD, "reason": "PRODUCTION_QUALIFIED"})

    open_positions = [p for p in positions if p.get("status") == "OPEN"]
    closed_positions = [p for p in positions if p.get("status") == "CLOSED"]
    open_value = sum(float(p.get("current_value_usd") or 0) for p in open_positions)
    open_cost = sum(float(p.get("cost_usd") or 0) for p in open_positions)
    realized = sum(float(p.get("realized_pnl_usd") or 0) for p in closed_positions)
    unrealized = open_value - open_cost
    equity = cash + open_value
    total_pnl = equity - float(ledger.get("starting_cash_usd", STARTING_CASH_USD))
    wins = sum(1 for p in closed_positions if float(p.get("realized_pnl_usd") or 0) > 0)
    losses = sum(1 for p in closed_positions if float(p.get("realized_pnl_usd") or 0) < 0)
    exit_pending = sum(1 for p in open_positions if p.get("exit_pending"))

    ledger.update({"updated_at": ts, "cash_usd": cash, "positions": positions, "events": events[-5000:]})
    summary = {
        "updated_at": ts,
        "mode": "PAPER_ONLY_NO_REAL_MONEY",
        "starting_cash_usd": float(ledger.get("starting_cash_usd", STARTING_CASH_USD)),
        "position_size_usd": POSITION_SIZE_USD,
        "cash_usd": round(cash, 8),
        "open_positions": len(open_positions),
        "closed_positions": len(closed_positions),
        "exit_pending": exit_pending,
        "invested_open_usd": round(open_cost, 8),
        "open_value_usd": round(open_value, 8),
        "realized_pnl_usd": round(realized, 8),
        "unrealized_pnl_usd": round(unrealized, 8),
        "total_equity_usd": round(equity, 8),
        "total_pnl_usd": round(total_pnl, 8),
        "roi_pct": round((total_pnl / summary_start(ledger)) * 100, 6),
        "closed_wins": wins,
        "closed_losses": losses,
        "trades_total": len(positions),
        "policy": {
            "entry": "exact pair + production PASS + holder/cluster verified + liquidity >= $50K",
            "exit": "sell when exact pair is no longer production-qualified; no fabricated exit without exact-pair quote",
            "reentry": "disabled for an already-seen exact pair",
            "fees_slippage": "not yet deducted; paper mark-to-market only",
        },
    }
    return ledger, summary


def summary_start(ledger: dict[str, Any]) -> float:
    value = float(ledger.get("starting_cash_usd", STARTING_CASH_USD) or STARTING_CASH_USD)
    return value if value > 0 else STARTING_CASH_USD


def main() -> None:
    production = list(_flatten(_read(DATA_DIR / "holder-cluster-production-qualified.json", [])))
    ledger = _read(LEDGER_PATH, initial_ledger())
    quotes = _quote_index(DATA_DIR)
    ledger, summary = reconcile_portfolio(ledger, production, quotes)
    _write(LEDGER_PATH, ledger)
    _write(SUMMARY_PATH, summary)
    print(
        "PAPER PORTFOLIO:",
        f"equity=${summary['total_equity_usd']:.4f}",
        f"cash=${summary['cash_usd']:.4f}",
        "open", summary["open_positions"],
        "closed", summary["closed_positions"],
        f"pnl=${summary['total_pnl_usd']:.4f}",
    )


if __name__ == "__main__":
    main()
