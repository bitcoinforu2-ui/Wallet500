from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
EVIDENCE = DATA / "discovery-evidence-ledger.json"
PERFORMANCE = DATA / "cash-verified-performance.json"
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


def build_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    evidence = _load(EVIDENCE, {})
    perf = _load(PERFORMANCE, {})
    records = evidence.get("records", {}) if isinstance(evidence, dict) else {}
    rows = perf.get("rows", []) if isinstance(perf, dict) else []

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

    report = {
        "generated_at": now.isoformat(),
        "mode": "RESEARCH_ONLY_NO_PRODUCTION_WRITES",
        "replay_status": "PHASE_1_IMMUTABLE_EVIDENCE_REPLAY",
        "important_limit": "This report does NOT claim a full historical blockchain replay yet. It uses immutable evidence captured by Wallet500 plus exact-pair performance data when available. No look-ahead data is used for entry evidence. Full 7/30/90-day pre-Wallet500 replay requires point-in-time chain/DEX reconstruction.",
        "lookahead_policy": "FORBIDDEN",
        "production_portfolio_impact": "NONE",
        "windows": windows,
        "records": sorted(normalized, key=lambda x: x["observed_at"], reverse=True),
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    report = build_report()
    print(json.dumps({"mode": report["mode"], "status": report["replay_status"], "windows": report["windows"]}, indent=2))


if __name__ == "__main__":
    main()
