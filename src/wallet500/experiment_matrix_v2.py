from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
CONFIG = Path("experiments/experiment-matrix-v2.json")
SOURCE = DATA / "active-qualified-candidates.json"
HOLDER_PASS = DATA / "holder-cluster-production-qualified.json"
WALLET = DATA / "wallet-candidates.json"
LEDGER = DATA / "experiment-matrix-v2-ledger.json"
SUMMARY = DATA / "experiment-matrix-v2-summary.json"
MIN_LIQ = 50_000.0
TARGET = 50
MIN_EVAL = 30
MIN_TIME_MINUTES = 15.0
MIN_RETENTION = 0.80


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def f(row: dict[str, Any], *names: str) -> float:
    for name in names:
        try:
            value = row.get(name)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass
    return 0.0


def norm(chain: str, value: Any) -> str:
    s = str(value or "")
    return s.lower() if chain.lower() in {"bsc", "bnb", "ethereum", "eth"} else s


def key(row: dict[str, Any]) -> str:
    chain = str(row.get("chain") or "").lower()
    token = norm(chain, row.get("token") or row.get("mint"))
    pair = norm(chain, row.get("pair_address") or row.get("locked_pair_address"))
    return f"{chain}|{token}|{pair}"


def rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        for name in ("rows", "candidates", "active", "qualified"):
            if isinstance(value.get(name), list):
                return [x for x in value[name] if isinstance(x, dict)]
    return []


def base_gate(r: dict[str, Any]) -> bool:
    pair = r.get("pair_address")
    locked = r.get("locked_pair_address")
    chain = str(r.get("chain") or "")
    exact = bool(pair) and r.get("pair_identity_locked") is not False and (not locked or norm(chain, pair) == norm(chain, locked))
    return (
        exact
        and f(r, "price_usd", "current_price_usd") > 0
        and f(r, "live_liquidity_usd", "liquidity_usd") >= MIN_LIQ
        and r.get("live_survival_gate") in {None, "ACTIVE"}
        and r.get("pump_dump_blocked") is not True
        and r.get("production_risk_blocked") is not True
        and r.get("pre_rug_exit_warning") is not True
    )


def lp_ok(r: dict[str, Any]) -> bool:
    return r.get("lp_removal_protection_verified") is True


def time_ok(r: dict[str, Any]) -> bool:
    span = f(r, "observation_span_minutes", "pair_age_minutes")
    retention = f(r, "production_liquidity_retention_from_peak", "liquidity_retention")
    history = int(f(r, "production_history_points"))
    return span >= MIN_TIME_MINUTES and retention >= MIN_RETENTION and history >= 3


def wallet_verified_keys(wallet_data: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(wallet_data, dict):
        return out
    for item in wallet_data.get("solana") or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        verified = [w for w in item.get("wallets") or [] if isinstance(w, dict) and w.get("verified") is True]
        if verified:
            out.add(key(item))
    return out


def holder_keys(holder_data: Any) -> set[str]:
    return {key(r) for r in rows(holder_data)}


def arm_pass(arm: str, r: dict[str, Any], holder: set[str], wallet: set[str]) -> bool:
    k = key(r)
    if not base_gate(r):
        return False
    if arm == "A":
        return lp_ok(r)
    if arm == "B":
        return time_ok(r)
    if arm == "C":
        return k in holder and k in wallet
    if arm == "D":
        return lp_ok(r) and time_ok(r) and k in holder and k in wallet
    return False


def entry(r: dict[str, Any], ts: str) -> dict[str, Any]:
    px = f(r, "price_usd", "current_price_usd")
    liq = f(r, "live_liquidity_usd", "liquidity_usd")
    return {
        "key": key(r),
        "chain": str(r.get("chain") or "").lower(),
        "token": r.get("token") or r.get("mint"),
        "pair_address": r.get("pair_address"),
        "symbol": r.get("base_token_symbol"),
        "entry_at": ts,
        "entry_price_usd": px,
        "entry_liquidity_usd": liq,
        "quantity": 1.0 / px,
        "cost_usd": 1.0,
        "current_price_usd": px,
        "current_liquidity_usd": liq,
        "current_value_usd": 1.0,
        "return_pct": 0.0,
        "status": "LIVE",
        "last_mark_at": ts,
        "entry_snapshot": {
            "anomaly_score": r.get("anomaly_score"),
            "volume_h1": f(r, "live_volume_h1", "volume_h1"),
            "activity_h1": f(r, "live_activity_h1", "txns_h1"),
            "observation_span_minutes": f(r, "observation_span_minutes", "pair_age_minutes"),
            "liquidity_retention": f(r, "production_liquidity_retention_from_peak", "liquidity_retention"),
            "history_points": int(f(r, "production_history_points")),
            "lp_verified": r.get("lp_removal_protection_verified") is True,
        },
    }


def mark(position: dict[str, Any], current: dict[str, Any] | None, ts: str) -> None:
    if current is None:
        position["status"] = "UNRESOLVED"
        position["last_mark_at"] = ts
        return
    px = f(current, "price_usd", "current_price_usd")
    liq = f(current, "live_liquidity_usd", "liquidity_usd")
    if px <= 0:
        position["status"] = "UNRESOLVED"
        position["last_mark_at"] = ts
        return
    value = float(position["quantity"]) * px
    position["current_price_usd"] = px
    position["current_liquidity_usd"] = liq
    position["current_value_usd"] = round(value, 10)
    position["return_pct"] = round((value - 1.0) * 100.0, 6)
    position["last_mark_at"] = ts
    position["status"] = "LIVE" if base_gate(current) else "FAILED_SURVIVAL"
    if position["status"] == "FAILED_SURVIVAL" and not position.get("failed_at"):
        position["failed_at"] = ts


def run() -> dict[str, Any]:
    ts = now()
    config = load(CONFIG, {})
    source_rows = rows(load(SOURCE, []))
    current = {key(r): r for r in source_rows}
    holder = holder_keys(load(HOLDER_PASS, []))
    wallet = wallet_verified_keys(load(WALLET, {}))
    ledger = load(LEDGER, {})
    if not isinstance(ledger, dict) or ledger.get("experiment_id") != "W500-EXP-V2-SURVIVAL-ALPHA":
        ledger = {"experiment_id": "W500-EXP-V2-SURVIVAL-ALPHA", "mode": "PAPER_ONLY_REAL_DATA_EXACT_PAIR", "created_at": ts, "control_status": "FAILED_BASELINE_FROZEN", "arms": {a: [] for a in "ABCD"}}
    arms = ledger.setdefault("arms", {a: [] for a in "ABCD"})
    report: dict[str, Any] = {}
    for arm in "ABCD":
        positions = arms.setdefault(arm, [])
        existing = {p.get("key") for p in positions if isinstance(p, dict)}
        eligible = [r for r in source_rows if arm_pass(arm, r, holder, wallet)]
        eligible.sort(key=lambda r: (f(r, "anomaly_score"), f(r, "live_liquidity_usd", "liquidity_usd"), key(r)), reverse=True)
        for r in eligible:
            if len(positions) >= TARGET:
                break
            if key(r) not in existing:
                positions.append(entry(r, ts))
                existing.add(key(r))
        for p in positions:
            mark(p, current.get(p.get("key")), ts)
        live = [p for p in positions if p.get("status") == "LIVE"]
        failed = [p for p in positions if p.get("status") == "FAILED_SURVIVAL"]
        marked = [p for p in positions if p.get("status") in {"LIVE", "FAILED_SURVIVAL"}]
        cost = float(len(marked))
        value = sum(float(p.get("current_value_usd") or 0) for p in marked)
        roi = ((value / cost) - 1.0) * 100.0 if cost else None
        report[arm] = {
            "sample": len(positions),
            "target": TARGET,
            "evaluation_ready": len(positions) >= MIN_EVAL,
            "eligible_now": len(eligible),
            "live": len(live),
            "failed_survival": len(failed),
            "unresolved": len(positions) - len(marked),
            "survival_rate_pct": round(len(live) / len(marked) * 100.0, 4) if marked else None,
            "roi_pct": round(roi, 6) if roi is not None else None,
        }
    ledger["updated_at"] = ts
    ledger["config_sha_policy"] = config.get("global_rules")
    summary = {
        "experiment_id": ledger["experiment_id"],
        "updated_at": ts,
        "status": "ACTIVE",
        "control": "FAILED_BASELINE_FROZEN",
        "hard_liquidity_usd": MIN_LIQ,
        "minimum_time_survival_minutes": MIN_TIME_MINUTES,
        "minimum_liquidity_retention": MIN_RETENTION,
        "holder_pass_keys_now": len(holder),
        "verified_wallet_pair_keys_now": len(wallet),
        "arms": report,
        "truth_note": "No missing evidence is treated as PASS. C/D remain empty until holder and wallet evidence are verified. Entries are immutable; failed survival remains in history.",
    }
    write(LEDGER, ledger)
    write(SUMMARY, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    run()
