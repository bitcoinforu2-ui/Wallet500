from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
SOURCE = DATA / "realizable-performance.json"
LEDGER = DATA / "blocked-cohort-paper-ledger.json"
SUMMARY = DATA / "blocked-cohort-paper-summary.json"
POSITION_USD = 1.0
COHORT_SIZE = 10
MODE = "PAPER_ONLY_BLOCKED_COHORT_EXPERIMENT"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _norm(chain: str, value: Any) -> str:
    s = str(value or "")
    return s.lower() if str(chain).lower() in {"ethereum", "bsc"} else s


def _key(row: dict[str, Any]) -> str:
    c = str(row.get("chain") or "").lower()
    t = _norm(c, row.get("token") or row.get("mint"))
    p = _norm(c, row.get("pair_address") or row.get("locked_pair_address"))
    return f"{c}|{t}|{p}"


def _f(row: dict[str, Any], name: str) -> float:
    try:
        return float(row.get(name) or 0)
    except (TypeError, ValueError):
        return 0.0


def _current_quality(row: dict[str, Any]) -> float:
    """Forward-only ranking: closeness to current execution thresholds, never past return."""
    liq = min(_f(row, "liquidity_usd") / 50_000.0, 1.0)
    vol = min(_f(row, "volume_h1") / 15_000.0, 1.0)
    tx = min(_f(row, "txns_h1") / 50.0, 1.0)
    return round(50.0 * liq + 30.0 * vol + 20.0 * tx, 6)


def _candidates(perf: dict[str, Any]) -> list[dict[str, Any]]:
    rows = perf.get("rows") if isinstance(perf, dict) else []
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if r.get("current_status") != "CURRENTLY_BLOCKED":
            continue
        if _f(r, "current_price_usd") <= 0:
            continue
        if not r.get("pair_address") or not (r.get("token") or r.get("mint")):
            continue
        x = dict(r)
        x["experiment_rank_score"] = _current_quality(r)
        out.append(x)
    # No hindsight: current_return_pct and peak_return_pct are intentionally excluded.
    out.sort(
        key=lambda r: (
            r["experiment_rank_score"],
            _f(r, "liquidity_usd"),
            _f(r, "volume_h1"),
            _f(r, "txns_h1"),
            _key(r),
        ),
        reverse=True,
    )
    return out


def _initial(perf: dict[str, Any], now: str) -> dict[str, Any]:
    pool = _candidates(perf)
    selected = pool[:COHORT_SIZE]
    positions = []
    for rank, r in enumerate(selected, 1):
        px = _f(r, "current_price_usd")
        positions.append({
            "rank": rank,
            "chain": str(r.get("chain") or "").lower(),
            "token": r.get("token") or r.get("mint"),
            "pair_address": r.get("pair_address"),
            "dex": r.get("dex"),
            "entry_time": now,
            "entry_price_usd": px,
            "quantity": POSITION_USD / px,
            "cost_usd": POSITION_USD,
            "entry_liquidity_usd": _f(r, "liquidity_usd"),
            "entry_volume_h1": _f(r, "volume_h1"),
            "entry_txns_h1": int(_f(r, "txns_h1")),
            "blocked_reasons_at_entry": list(r.get("reasons") or []),
            "experiment_rank_score": r.get("experiment_rank_score"),
            "current_price_usd": px,
            "current_value_usd": POSITION_USD,
            "return_pct": 0.0,
            "last_mark_at": now,
            "mark_status": "ENTRY_MARK",
        })
    return {
        "version": 1,
        "mode": MODE,
        "paper_only": True,
        "production_bypass": False,
        "selection_policy": "TOP_CURRENT_BLOCKED_BY_THRESHOLD_CLOSENESS_NO_RETURN_OR_PEAK_USED",
        "selection_source": SOURCE.name,
        "selected_at": now,
        "source_blocked_now": int(perf.get("blocked_now") or perf.get("not_realizable_now_count") or 0),
        "eligible_live_blocked_pool": len(pool),
        "cohort_size_target": COHORT_SIZE,
        "position_size_usd": POSITION_USD,
        "starting_value_usd": round(len(positions) * POSITION_USD, 8),
        "positions": positions,
        "updated_at": now,
    }


def update(now: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = now or _now()
    perf = _load(SOURCE, {})
    ledger = _load(LEDGER, {})
    if not isinstance(ledger, dict) or ledger.get("mode") != MODE or not isinstance(ledger.get("positions"), list) or not ledger.get("positions"):
        ledger = _initial(perf, ts)

    current = {_key(r): r for r in (perf.get("rows") or []) if isinstance(r, dict)}
    for p in ledger.get("positions", []):
        r = current.get(_key(p))
        if not r or _f(r, "current_price_usd") <= 0:
            p["mark_status"] = "UNRESOLVED_NO_CURRENT_EXACT_PAIR_MARK"
            continue
        px = _f(r, "current_price_usd")
        value = float(p["quantity"]) * px
        p["current_price_usd"] = px
        p["current_value_usd"] = round(value, 8)
        p["return_pct"] = round((value / float(p["cost_usd"]) - 1.0) * 100.0, 6)
        p["current_liquidity_usd"] = _f(r, "liquidity_usd")
        p["current_status"] = r.get("current_status")
        p["current_reasons"] = list(r.get("reasons") or [])
        p["last_mark_at"] = ts
        p["mark_status"] = "EXACT_PAIR_MARK"

    positions = ledger.get("positions", [])
    marked = [p for p in positions if p.get("mark_status") in {"ENTRY_MARK", "EXACT_PAIR_MARK"}]
    unresolved = len(positions) - len(marked)
    start = float(ledger.get("starting_value_usd") or 0)
    value = sum(float(p.get("current_value_usd") or 0) for p in marked)
    # Unresolved positions are excluded from P&L instead of fabricated as zero.
    comparable_cost = sum(float(p.get("cost_usd") or 0) for p in marked)
    pnl = value - comparable_cost
    roi = (pnl / comparable_cost * 100.0) if comparable_cost > 0 else 0.0
    ledger["updated_at"] = ts
    ledger["positions"] = positions
    summary = {
        "version": 1,
        "mode": MODE,
        "paper_only": True,
        "production_bypass": False,
        "selected_at": ledger.get("selected_at"),
        "updated_at": ts,
        "positions": len(positions),
        "position_size_usd": POSITION_USD,
        "starting_value_usd": start,
        "marked_positions": len(marked),
        "unresolved_positions": unresolved,
        "comparable_cost_usd": round(comparable_cost, 8),
        "current_value_usd": round(value, 8),
        "pnl_usd": round(pnl, 8),
        "roi_pct": round(roi, 6),
        "selection_policy": ledger.get("selection_policy"),
        "source_blocked_now_at_selection": ledger.get("source_blocked_now"),
        "note": "Frozen cohort. No reselection after entry. Exact-pair marks only; unresolved marks are not converted to losses.",
    }
    _write(LEDGER, ledger)
    _write(SUMMARY, summary)
    print(json.dumps(summary, indent=2))
    return ledger, summary


if __name__ == "__main__":
    update()
