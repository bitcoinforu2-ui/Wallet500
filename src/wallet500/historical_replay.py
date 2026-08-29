from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
EVIDENCE = DATA / "discovery-evidence-ledger.json"
PERFORMANCE = DATA / "cash-verified-performance.json"
BACKFILL = DATA / "historical-backfill-state.json"
OUT = DATA / "historical-replay-report.json"
WINDOWS = (7, 30, 90)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _key(chain: str, token: str, pair: str) -> str:
    if chain.lower() in {"ethereum", "bsc"}:
        token, pair = token.lower(), pair.lower()
    return f"{chain.lower()}:{token}:{pair}"


def _price_counterfactual(backfill_pairs: dict[str, Any], now: datetime, days: int) -> dict[str, Any]:
    cutoff_ts = int((now - timedelta(days=days)).timestamp())
    ledger: list[dict[str, Any]] = []

    for key, row in backfill_pairs.items():
        if not isinstance(row, dict) or row.get("status") != "FETCHED":
            continue
        candles = [c for c in (row.get("candles") or []) if isinstance(c, dict)]
        candles.sort(key=lambda c: int(c.get("timestamp") or 0))
        if not candles:
            continue

        # Daily OHLCV only. Use the first candle OPEN at/after the target cutoff,
        # never a later high/close for entry. This is a coarse price-only research
        # mark and is explicitly NOT a historical Wallet500 decision replay.
        entry_candle = next((c for c in candles if int(c.get("timestamp") or 0) >= cutoff_ts), None)
        if not entry_candle:
            continue
        current_candle = candles[-1]
        entry = float(entry_candle.get("open") or 0)
        current = float(current_candle.get("close") or 0)
        if entry <= 0 or current <= 0:
            continue

        ret = ((current / entry) - 1.0) * 100.0
        one_dollar_value = current / entry
        ledger.append({
            "key": key,
            "chain": row.get("chain"),
            "token": row.get("token"),
            "pair_address": row.get("pair_address"),
            "target_days_ago": days,
            "target_cutoff_ts": cutoff_ts,
            "entry_candle_ts": int(entry_candle.get("timestamp") or 0),
            "entry_price_usd": entry,
            "current_candle_ts": int(current_candle.get("timestamp") or 0),
            "current_price_usd": current,
            "return_pct": round(ret, 6),
            "hypothetical_1usd_value": round(one_dollar_value, 8),
            "hypothetical_1usd_pnl": round(one_dollar_value - 1.0, 8),
            "historical_liquidity_verified": bool(row.get("historical_liquidity_verified")),
            "historical_holder_cluster_verified": bool(row.get("historical_holder_cluster_verified")),
            "countable_as_full_wallet500_backtest": False,
            "status": "PRICE_ONLY_COUNTERFACTUAL_NOT_BACKTEST_VERIFIED",
        })

    wins = sum(1 for r in ledger if r["return_pct"] > 0)
    losses = sum(1 for r in ledger if r["return_pct"] < 0)
    invested = float(len(ledger))
    final_value = sum(float(r["hypothetical_1usd_value"]) for r in ledger)
    pnl = final_value - invested

    return {
        "days": days,
        "records": len(ledger),
        "wins": wins,
        "losses": losses,
        "hit_rate_pct": round(wins / len(ledger) * 100.0, 2) if ledger else None,
        "hypothetical_1usd_each_invested": round(invested, 2),
        "hypothetical_final_value": round(final_value, 8),
        "hypothetical_pnl": round(pnl, 8),
        "hypothetical_roi_pct": round(pnl / invested * 100.0, 4) if invested else None,
        "portfolio_100usd_status": "INSUFFICIENT_VERIFIED_DECISION_COVERAGE",
        "status": "PRICE_ONLY_COUNTERFACTUAL_NOT_BACKTEST_VERIFIED",
        "ledger": ledger,
    }


def build_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    evidence = _load(EVIDENCE, {})
    perf = _load(PERFORMANCE, {})
    backfill = _load(BACKFILL, {})
    records = evidence.get("records", {}) if isinstance(evidence, dict) else {}
    rows = perf.get("rows", []) if isinstance(perf, dict) else []
    backfill_pairs = backfill.get("pairs", {}) if isinstance(backfill, dict) else {}
    if not isinstance(backfill_pairs, dict):
        backfill_pairs = {}

    perf_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        chain = str(row.get("chain") or "")
        token = str(row.get("token") or "")
        pair = str(row.get("pair_address") or "")
        if chain and token and pair:
            perf_by_key[_key(chain, token, pair)] = row

    normalized: list[dict[str, Any]] = []
    for raw_key, rec in records.items():
        ident = rec.get("identity", {})
        market = rec.get("market", {})
        observed = _dt(rec.get("observed_at"))
        if not observed:
            continue
        chain = str(ident.get("chain") or "")
        token = str(ident.get("token") or "")
        pair = str(ident.get("pair_address") or "")
        k = _key(chain, token, pair) if chain and token and pair else str(raw_key)
        p = perf_by_key.get(k)
        entry = float(market.get("price_usd") or 0)
        current = float((p or {}).get("current_price_usd") or 0)
        ret = ((current / entry) - 1.0) * 100.0 if entry > 0 and current > 0 else None
        normalized.append({
            "key": k,
            "observed_at": observed.isoformat(),
            "chain": chain,
            "token": token,
            "pair_address": pair,
            "dex": ident.get("dex"),
            "entry_price_usd": entry or None,
            "entry_liquidity_usd": market.get("liquidity_usd"),
            "anomaly_score": rec.get("signals", {}).get("anomaly_score"),
            "holder_status": rec.get("holder_intelligence", {}).get("status"),
            "current_price_usd": current or None,
            "marked_return_pct": round(ret, 6) if ret is not None else None,
            "peak_return_pct": (p or {}).get("peak_return_pct"),
            "cash_status": (p or {}).get("cash_status"),
            "proof_level": (p or {}).get("proof_level"),
            "data_class": "IMMUTABLE_EVIDENCE_PLUS_CURRENT_MARK" if p else "IMMUTABLE_EVIDENCE_ONLY",
        })

    windows: dict[str, Any] = {}
    price_only: dict[str, Any] = {}
    for days in WINDOWS:
        cutoff = now - timedelta(days=days)
        cohort = [r for r in normalized if (_dt(r["observed_at"]) or now) >= cutoff]
        marked = [r for r in cohort if r["marked_return_pct"] is not None]
        wins = [r for r in marked if r["marked_return_pct"] > 0]
        losses = [r for r in marked if r["marked_return_pct"] < 0]
        total = sum(float(r["marked_return_pct"]) for r in marked)
        windows[str(days)] = {
            "days": days,
            "records": len(cohort),
            "marked_records": len(marked),
            "coverage_pct": round((len(marked) / len(cohort) * 100.0), 2) if cohort else 0.0,
            "wins": len(wins),
            "losses": len(losses),
            "mean_marked_return_pct": round(total / len(marked), 4) if marked else None,
            "status": "RESEARCH_PARTIAL_REPLAY",
        }
        price_only[str(days)] = _price_counterfactual(backfill_pairs, now, days)

    report = {
        "generated_at": now.isoformat(),
        "mode": "RESEARCH_ONLY_NO_PRODUCTION_WRITES",
        "replay_status": "PHASE_2B_PRICE_ONLY_COUNTERFACTUAL",
        "important_limit": "This is NOT yet a verified historical Wallet500 backtest. The new 7/30/90 price-only ledger uses exact-pair daily OHLCV and the first daily candle OPEN at/after each target cutoff. It does not claim the pair would have been discovered or qualified then. Historical point-in-time liquidity, holders/clusters, discovery universe and exact decision timestamps remain mandatory before BACKTEST VERIFIED or a real $100 portfolio result.",
        "lookahead_policy": "FORBIDDEN",
        "production_portfolio_impact": "NONE",
        "windows": windows,
        "price_only_counterfactual": price_only,
        "records": sorted(normalized, key=lambda x: x["observed_at"], reverse=True),
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    report = build_report()
    print(json.dumps({
        "mode": report["mode"],
        "status": report["replay_status"],
        "windows": report["windows"],
        "price_only_counterfactual": {k: {kk: vv for kk, vv in v.items() if kk != "ledger"} for k, v in report["price_only_counterfactual"].items()},
    }, indent=2))


if __name__ == "__main__":
    main()
