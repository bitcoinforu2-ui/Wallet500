from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
SOURCE = DATA / "active-qualified-candidates.json"
LEDGER = DATA / "blocked-cohort-paper-ledger.json"
SUMMARY = DATA / "blocked-cohort-paper-summary.json"
POSITION_USD = 1.0
COHORT_SIZE = 10
MIN_LIQUIDITY_USD = 50_000.0
MODE = "PAPER_ONLY_REVALIDATED_TOP10_EXPERIMENT_V2"


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


def _f(row: dict[str, Any], *names: str) -> float:
    for name in names:
        try:
            v = row.get(name)
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            pass
    return 0.0


def _activity(row: dict[str, Any]) -> float:
    v = _f(row, "live_activity_h1", "txns_h1")
    if v > 0:
        return v
    return _f(row, "buys_h1") + _f(row, "sells_h1")


def _rank_score(row: dict[str, Any]) -> float:
    # Forward-only score: current quality only. Never uses return/peak hindsight.
    anomaly = min(max(_f(row, "anomaly_score"), 0.0), 100.0) / 100.0
    liq = min(_f(row, "live_liquidity_usd", "liquidity_usd") / 100_000.0, 1.0)
    vol = min(_f(row, "live_volume_h1", "volume_h1") / 100_000.0, 1.0)
    tx = min(_activity(row) / 500.0, 1.0)
    return round(40.0 * anomaly + 25.0 * liq + 20.0 * vol + 15.0 * tx, 6)


def _revalidate(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    price = _f(row, "price_usd", "current_price_usd")
    liq = _f(row, "live_liquidity_usd", "liquidity_usd")
    vol = _f(row, "live_volume_h1", "volume_h1")
    activity = _activity(row)
    pair = row.get("pair_address")
    locked = row.get("locked_pair_address")

    if price <= 0: reasons.append("NO_LIVE_PRICE")
    if liq < MIN_LIQUIDITY_USD: reasons.append("LIQUIDITY_BELOW_50K")
    if vol <= 0: reasons.append("NO_LIVE_H1_VOLUME")
    if activity <= 0: reasons.append("NO_LIVE_H1_ACTIVITY")
    if not pair or not (row.get("token") or row.get("mint")): reasons.append("MISSING_EXACT_PAIR_IDENTITY")
    if locked and _norm(str(row.get("chain") or ""), locked) != _norm(str(row.get("chain") or ""), pair):
        reasons.append("PAIR_IDENTITY_MISMATCH")
    if row.get("pair_identity_locked") is False: reasons.append("PAIR_NOT_LOCKED")
    if row.get("qualification") not in {None, "QUALIFIED"}: reasons.append("NOT_QUALIFIED")
    if row.get("live_survival_gate") not in {None, "ACTIVE"}: reasons.append("SURVIVAL_NOT_ACTIVE")
    if row.get("pump_dump_blocked") is True: reasons.append("PUMP_DUMP_BLOCKED")
    if row.get("production_risk_blocked") is True: reasons.append("PRODUCTION_RISK_BLOCKED")
    if row.get("pre_rug_exit_warning") is True: reasons.append("PRE_RUG_EXIT_WARNING")
    return not reasons, reasons


def _candidates(source: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = source if isinstance(source, list) else (source.get("rows") or source.get("candidates") or []) if isinstance(source, dict) else []
    accepted, rejected = [], []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ok, why = _revalidate(r)
        x = dict(r)
        x["experiment_rank_score"] = _rank_score(r)
        if ok:
            accepted.append(x)
        else:
            rejected.append({"chain": r.get("chain"), "token": r.get("token") or r.get("mint"), "pair_address": r.get("pair_address"), "rejected_reasons": why})
    accepted.sort(key=lambda r: (r["experiment_rank_score"], _f(r, "live_liquidity_usd", "liquidity_usd"), _f(r, "live_volume_h1", "volume_h1"), _activity(r), _key(r)), reverse=True)
    return accepted, rejected


def _initial(source: Any, now: str) -> dict[str, Any]:
    pool, rejected = _candidates(source)
    selected = pool[:COHORT_SIZE]
    positions = []
    for rank, r in enumerate(selected, 1):
        px = _f(r, "price_usd", "current_price_usd")
        positions.append({
            "rank": rank, "chain": str(r.get("chain") or "").lower(), "token": r.get("token") or r.get("mint"),
            "pair_address": r.get("pair_address"), "dex": r.get("dex"), "entry_time": now, "entry_verified_at": now,
            "entry_price_usd": px, "quantity": POSITION_USD / px, "cost_usd": POSITION_USD,
            "entry_liquidity_usd": _f(r, "live_liquidity_usd", "liquidity_usd"),
            "entry_volume_h1": _f(r, "live_volume_h1", "volume_h1"), "entry_txns_h1": int(_activity(r)),
            "experiment_rank_score": r.get("experiment_rank_score"), "current_price_usd": px,
            "current_value_usd": POSITION_USD, "return_pct": 0.0, "last_mark_at": now, "mark_status": "ENTRY_VERIFIED_MARK",
        })
    return {
        "version": 2, "mode": MODE, "paper_only": True, "production_bypass": False,
        "selection_policy": "TOP10_ONLY_AFTER_FRESH_EXACT_PAIR_REVALIDATION_LIQ50K_SURVIVAL_ACTIVE_NO_HINDSIGHT",
        "selection_source": SOURCE.name, "selected_at": now, "eligible_revalidated_pool": len(pool),
        "rejected_at_entry_count": len(rejected), "rejected_at_entry": rejected,
        "cohort_size_target": COHORT_SIZE, "position_size_usd": POSITION_USD,
        "starting_value_usd": round(len(positions) * POSITION_USD, 8), "positions": positions, "updated_at": now,
    }


def update(now: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = now or _now()
    source = _load(SOURCE, [])
    ledger = _load(LEDGER, {})
    # Mode change intentionally retires the old blocked cohort and creates one fresh verified cohort.
    if not isinstance(ledger, dict) or ledger.get("mode") != MODE or not isinstance(ledger.get("positions"), list) or not ledger.get("positions"):
        ledger = _initial(source, ts)

    rows = source if isinstance(source, list) else (source.get("rows") or source.get("candidates") or []) if isinstance(source, dict) else []
    current = {_key(r): r for r in rows if isinstance(r, dict)}
    for p in ledger.get("positions", []):
        r = current.get(_key(p))
        if not r or _f(r, "price_usd", "current_price_usd") <= 0:
            p["mark_status"] = "UNRESOLVED_NO_CURRENT_EXACT_PAIR_MARK"
            continue
        px = _f(r, "price_usd", "current_price_usd")
        value = float(p["quantity"]) * px
        p["current_price_usd"] = px; p["current_value_usd"] = round(value, 8)
        p["return_pct"] = round((value / float(p["cost_usd"]) - 1.0) * 100.0, 6)
        p["current_liquidity_usd"] = _f(r, "live_liquidity_usd", "liquidity_usd")
        p["last_mark_at"] = ts; p["mark_status"] = "EXACT_PAIR_MARK"

    positions = ledger.get("positions", [])
    marked = [p for p in positions if p.get("mark_status") in {"ENTRY_VERIFIED_MARK", "EXACT_PAIR_MARK"}]
    value = sum(float(p.get("current_value_usd") or 0) for p in marked)
    cost = sum(float(p.get("cost_usd") or 0) for p in marked)
    pnl = value - cost; roi = pnl / cost * 100.0 if cost else 0.0
    ledger["updated_at"] = ts
    summary = {"version": 2, "mode": MODE, "paper_only": True, "production_bypass": False,
        "selected_at": ledger.get("selected_at"), "updated_at": ts, "positions": len(positions), "position_size_usd": POSITION_USD,
        "starting_value_usd": ledger.get("starting_value_usd", 0), "marked_positions": len(marked), "unresolved_positions": len(positions)-len(marked),
        "comparable_cost_usd": round(cost,8), "current_value_usd": round(value,8), "pnl_usd": round(pnl,8), "roi_pct": round(roi,6),
        "selection_policy": ledger.get("selection_policy"), "eligible_revalidated_pool": ledger.get("eligible_revalidated_pool"),
        "rejected_at_entry_count": ledger.get("rejected_at_entry_count"),
        "note": "Fresh Top-10 entry cohort: exact-pair revalidation before $1 paper entry; >=$50K liquidity and active survival required. After entry, positions remain immutable."}
    _write(LEDGER, ledger); _write(SUMMARY, summary)
    print(json.dumps(summary, indent=2)); return ledger, summary


if __name__ == "__main__":
    update()
