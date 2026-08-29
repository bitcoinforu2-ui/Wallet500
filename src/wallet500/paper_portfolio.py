from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .cash_verified import (
    evm_entry_quote,
    evm_quote,
    evm_token_decimals,
    solana_entry_quote,
    solana_quote,
    solana_token_decimals,
)

DATA_DIR = Path("data")
STARTING_CASH_USD = 100.0
POSITION_SIZE_USD = 1.0
MIN_LIQUIDITY_USD = 50_000.0
LEDGER_PATH = DATA_DIR / "paper-portfolio-ledger.json"
SUMMARY_PATH = DATA_DIR / "paper-portfolio-summary.json"

MARK_SOURCES = (
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


def _mark_index(data_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for name in MARK_SOURCES:
        for row in _flatten(_read(data_dir / name, [])):
            key = _key(row)
            if key.count("|") != 2 or key.endswith("|"):
                continue
            price = _num(row, "live_price_usd", "price_usd", "current_price_usd")
            if price > 0 and key not in index:
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
        "version": 2,
        "mode": "PAPER_QUOTE_VERIFIED_NO_REAL_MONEY",
        "created_at": ts,
        "updated_at": ts,
        "starting_cash_usd": STARTING_CASH_USD,
        "position_size_usd": POSITION_SIZE_USD,
        "min_liquidity_usd": MIN_LIQUIDITY_USD,
        "cash_usd": STARTING_CASH_USD,
        "positions": [],
        "events": [],
        "truth_policy": "NO ENTRY OR EXIT IS BOOKED WITHOUT A SAME-CYCLE FIRM ROUTER QUOTE. ROUTER QUOTE IS NOT A TRADE EXECUTION AND IS NOT CLAIMED TO BE CONSTRAINED TO THE DISCOVERY PAIR.",
    }


def _entry_quote_for(row: dict[str, Any]) -> dict[str, Any]:
    chain = str(row.get("chain") or "").upper()
    token = row.get("token") or row.get("mint")
    if not token:
        return {"status": "UNAVAILABLE", "reason": "TOKEN_MISSING"}
    result, err = (solana_entry_quote(token) if chain in {"SOL", "SOLANA"} else evm_entry_quote(chain, token))
    if err or not result:
        return {"status": "UNAVAILABLE", "reason": err or "ENTRY_QUOTE_EMPTY"}
    quote = result.get("quote") or {}
    raw = int(quote.get("amount_out") or 0) if chain in {"SOL", "SOLANA"} else int(quote.get("buyAmount") or 0)
    if raw <= 0:
        return {"status": "UNAVAILABLE", "reason": "ENTRY_QUOTE_ZERO_OUTPUT"}
    dec, dec_err = (solana_token_decimals(token) if chain in {"SOL", "SOLANA"} else evm_token_decimals(chain, token))
    if dec is None:
        return {"status": "UNAVAILABLE", "reason": dec_err or "TOKEN_DECIMALS_UNVERIFIED"}
    quantity = raw / (10 ** int(dec))
    if quantity <= 0:
        return {"status": "UNAVAILABLE", "reason": "ENTRY_QUANTITY_INVALID"}
    return {
        "status": "VERIFIED",
        "token_amount_base_units": raw,
        "token_decimals": int(dec),
        "quantity": quantity,
        "quoted_entry_cost_usd": POSITION_SIZE_USD,
        "effective_entry_price_usd": POSITION_SIZE_USD / quantity,
        "stable_symbol": result.get("stable_symbol"),
        "proof_level": "FIRM_ROUTER_ENTRY_QUOTE_NOT_EXECUTED_NOT_EXACT_PAIR_CONSTRAINED",
    }


def _exit_quote_for(position: dict[str, Any]) -> dict[str, Any]:
    chain = str(position.get("chain") or "").upper()
    token = position.get("token")
    amount = position.get("token_amount_base_units")
    try:
        amount = int(amount)
    except Exception:
        amount = 0
    if not token or amount <= 0:
        return {"status": "UNAVAILABLE", "reason": "TOKEN_OR_VERIFIED_ENTRY_AMOUNT_MISSING"}
    result, err = (solana_quote(token, amount) if chain in {"SOL", "SOLANA"} else evm_quote(chain, token, amount))
    if err or not result:
        return {"status": "UNAVAILABLE", "reason": err or "EXIT_QUOTE_EMPTY"}
    quote = result.get("quote") or {}
    raw = int(quote.get("amount_out") or 0) if chain in {"SOL", "SOLANA"} else int(quote.get("buyAmount") or 0)
    stable_decimals = int(result.get("stable_decimals") or 0)
    if raw <= 0 or stable_decimals < 0:
        return {"status": "UNAVAILABLE", "reason": "EXIT_QUOTE_ZERO_OUTPUT"}
    value = raw / (10 ** stable_decimals)
    return {
        "status": "VERIFIED",
        "quoted_exit_value_usd": value,
        "stable_symbol": result.get("stable_symbol"),
        "proof_level": "FIRM_ROUTER_EXIT_QUOTE_NOT_EXECUTED_NOT_EXACT_PAIR_CONSTRAINED",
    }


def reconcile_portfolio(
    ledger: dict[str, Any],
    production_rows: list[dict[str, Any]],
    marks: dict[str, dict[str, Any]],
    now: str | None = None,
    entry_quotes: dict[str, dict[str, Any]] | None = None,
    exit_quotes: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = now or _now()
    ledger = dict(ledger or initial_ledger(ts))
    ledger["version"] = 2
    ledger["mode"] = "PAPER_QUOTE_VERIFIED_NO_REAL_MONEY"
    positions = list(ledger.get("positions") or [])
    events = list(ledger.get("events") or [])
    cash = float(ledger.get("cash_usd", STARTING_CASH_USD))
    active = {_key(r): r for r in production_rows if _entry_is_safe(r)}
    existing = {_key(p): p for p in positions}
    entry_quotes = entry_quotes or {}
    exit_quotes = exit_quotes or {}

    for p in positions:
        if p.get("status") != "OPEN":
            continue
        key = _key(p)
        mark = active.get(key) or marks.get(key)
        if mark:
            px = _num(mark, "live_price_usd", "price_usd", "current_price_usd")
            if px > 0:
                p["current_price_usd"] = px
                p["current_value_usd"] = float(p.get("quantity") or 0) * px
                p["last_mark_at"] = ts
                p["last_liquidity_usd"] = _num(mark, "live_liquidity_usd", "liquidity_usd")
                p["mark_proof_level"] = "EXACT_PAIR_MARKET_DATA_PROXY_NOT_EXECUTION_QUOTE"
        if key not in active:
            xq = exit_quotes.get(key) or {}
            if xq.get("status") == "VERIFIED" and _num(xq, "quoted_exit_value_usd") >= 0:
                proceeds = _num(xq, "quoted_exit_value_usd")
                p.update({
                    "status": "CLOSED",
                    "exit_time": ts,
                    "exit_value_usd": proceeds,
                    "realized_pnl_usd": proceeds - float(p.get("cost_usd") or POSITION_SIZE_USD),
                    "exit_reason": "NO_LONGER_PRODUCTION_QUALIFIED",
                    "exit_pending": False,
                    "exit_quote_proof_level": xq.get("proof_level"),
                    "exit_quote_stable_symbol": xq.get("stable_symbol"),
                    "realized_accounting_basis": "SAME_CYCLE_FIRM_ROUTER_EXIT_QUOTE_NOT_EXECUTED",
                })
                cash += proceeds
                events.append({"at": ts, "type": "SELL_QUOTE_VERIFIED", "key": key, "value_usd": proceeds, "reason": p["exit_reason"], "proof_level": xq.get("proof_level")})
            else:
                p["exit_pending"] = True
                p["exit_reason"] = "EXIT_PENDING_FIRM_ROUTER_QUOTE_UNAVAILABLE"
                p["exit_quote_last_reason"] = xq.get("reason") or "NO_EXIT_QUOTE"

    for key, row in active.items():
        if key in existing or cash + 1e-12 < POSITION_SIZE_USD:
            continue
        eq = entry_quotes.get(key) or {}
        if eq.get("status") != "VERIFIED":
            events.append({"at": ts, "type": "ENTRY_SKIPPED", "key": key, "value_usd": 0.0, "reason": eq.get("reason") or "FIRM_ENTRY_QUOTE_UNAVAILABLE"})
            continue
        quantity = _num(eq, "quantity")
        amount_base = int(eq.get("token_amount_base_units") or 0)
        if quantity <= 0 or amount_base <= 0:
            events.append({"at": ts, "type": "ENTRY_SKIPPED", "key": key, "value_usd": 0.0, "reason": "VERIFIED_ENTRY_QUOTE_INVALID_AMOUNT"})
            continue
        market_px = _num(row, "live_price_usd", "price_usd", "current_price_usd")
        effective_px = _num(eq, "effective_entry_price_usd")
        pos = {
            "chain": str(row.get("chain") or "").lower(),
            "token": row.get("token") or row.get("mint"),
            "pair_address": row.get("pair_address") or row.get("locked_pair_address"),
            "dex": row.get("dex"),
            "status": "OPEN",
            "entry_time": ts,
            "entry_market_price_usd": market_px,
            "entry_price_usd": effective_px,
            "cost_usd": POSITION_SIZE_USD,
            "quantity": quantity,
            "token_amount_base_units": amount_base,
            "token_decimals_verified": int(eq.get("token_decimals")),
            "current_price_usd": market_px,
            "current_value_usd": quantity * market_px,
            "last_mark_at": ts,
            "entry_liquidity_usd": _num(row, "live_liquidity_usd", "liquidity_usd"),
            "last_liquidity_usd": _num(row, "live_liquidity_usd", "liquidity_usd"),
            "entry_anomaly_score": _num(row, "anomaly_score"),
            "entry_gate": "HOLDER_CLUSTER_PRODUCTION_PASS",
            "entry_quote_proof_level": eq.get("proof_level"),
            "entry_quote_stable_symbol": eq.get("stable_symbol"),
            "paper_only": True,
        }
        positions.append(pos)
        existing[key] = pos
        cash -= POSITION_SIZE_USD
        events.append({"at": ts, "type": "BUY_QUOTE_VERIFIED", "key": key, "value_usd": POSITION_SIZE_USD, "reason": "PRODUCTION_QUALIFIED_AND_FIRM_ROUTER_ENTRY_QUOTE", "proof_level": eq.get("proof_level")})

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

    ledger.update({
        "updated_at": ts,
        "cash_usd": cash,
        "positions": positions,
        "events": events[-5000:],
        "truth_policy": "NO ENTRY OR EXIT IS BOOKED WITHOUT A SAME-CYCLE FIRM ROUTER QUOTE. ROUTER QUOTE IS NOT A TRADE EXECUTION AND IS NOT CLAIMED TO BE CONSTRAINED TO THE DISCOVERY PAIR.",
    })
    summary = {
        "updated_at": ts,
        "mode": "PAPER_QUOTE_VERIFIED_NO_REAL_MONEY",
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
        "entry_quote_verified_positions": sum(1 for p in positions if p.get("entry_quote_proof_level")),
        "exit_quote_verified_closures": sum(1 for p in closed_positions if p.get("exit_quote_proof_level")),
        "realized_accounting_basis": "FIRM_ROUTER_QUOTES_AT_DECISION_TIME_NOT_EXECUTED_TRADES",
        "historical_backfill_policy": "NO RETROACTIVE ENTRY/EXIT EXECUTION CLAIMS WITHOUT POINT_IN_TIME_QUOTES",
        "policy": {
            "entry": "exact-pair production PASS + holder/cluster verified + liquidity >= $50K + same-cycle firm router entry quote",
            "exit": "exit signal when exact pair is no longer production-qualified; close accounting only with same-cycle firm router exit quote",
            "reentry": "disabled for an already-seen exact pair",
            "truth_limit": "router quote is real market evidence but is not a broadcast/executed trade and is not claimed to be constrained to the discovery pair",
        },
    }
    return ledger, summary


def summary_start(ledger: dict[str, Any]) -> float:
    value = float(ledger.get("starting_cash_usd", STARTING_CASH_USD) or STARTING_CASH_USD)
    return value if value > 0 else STARTING_CASH_USD


def main() -> None:
    production = list(_flatten(_read(DATA_DIR / "holder-cluster-production-qualified.json", [])))
    ledger = _read(LEDGER_PATH, initial_ledger())
    marks = _mark_index(DATA_DIR)
    existing = {_key(p): p for p in (ledger.get("positions") or [])}
    active = {_key(r): r for r in production if _entry_is_safe(r)}

    entry_quotes: dict[str, dict[str, Any]] = {}
    for key, row in active.items():
        if key not in existing:
            entry_quotes[key] = _entry_quote_for(row)

    exit_quotes: dict[str, dict[str, Any]] = {}
    for p in (ledger.get("positions") or []):
        if p.get("status") == "OPEN" and _key(p) not in active:
            exit_quotes[_key(p)] = _exit_quote_for(p)

    ledger, summary = reconcile_portfolio(ledger, production, marks, entry_quotes=entry_quotes, exit_quotes=exit_quotes)
    _write(LEDGER_PATH, ledger)
    _write(SUMMARY_PATH, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
