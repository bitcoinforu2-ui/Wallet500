from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
LEDGER = DATA / "alpha-proof-ledger.json"
REAL_ALERTS = DATA / "real-alerts.json"
OUT = DATA / "alpha-forward-control-audit.json"
MODE = "FORWARD_VERIFIED_WATCH_CONTROL_ENROLLMENT_V1"
ALPHA_MODE = "FORWARD_ONLY_ALPHA_PROOF_V1"
MIN_LIQUIDITY_USD = 15_000.0
MIN_MARKET_AGE_DAYS = 90.0


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _dt(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _norm(chain: Any, value: Any) -> str:
    c = str(chain or "").lower()
    s = str(value or "")
    return s.lower() if c in {"bsc", "bnb", "ethereum", "eth"} else s


def _key(chain: Any, token: Any, pair: Any) -> str:
    c = str(chain or "").lower()
    return f"{c}|{_norm(c, token)}|{_norm(c, pair)}"


def _entry_liquidity(row: dict[str, Any]) -> float | None:
    # Only executable/verified liquidity may qualify a formal control. Pool TVL is never substituted.
    for field in ("execution_pool_liquidity_usd", "liquidity_usd"):
        value = _num(row.get(field))
        if value is not None and value > 0:
            return value
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    for field in ("execution_pool_liquidity_usd", "liquidity_usd"):
        value = _num(market.get(field))
        if value is not None and value > 0:
            return value
    return None


def _entry_price(row: dict[str, Any]) -> float | None:
    for field in ("price_usd", "current_price_usd"):
        value = _num(row.get(field))
        if value is not None and value > 0:
            return value
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    for field in ("price_usd", "current_price_usd"):
        value = _num(market.get(field))
        if value is not None and value > 0:
            return value
    return None


def _age(row: dict[str, Any]) -> float | None:
    for field in ("market_age_days", "market_age_min_days"):
        value = _num(row.get(field))
        if value is not None:
            return value
    truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
    return _num(truth.get("market_age_days"))


def _eligible(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    chain = row.get("chain")
    token = row.get("token_address") or row.get("token")
    pair = row.get("pair_address") or row.get("entry_pair_address")
    liq = _entry_liquidity(row)
    price = _entry_price(row)
    age = _age(row)
    if not chain or not token or not pair:
        reasons.append("EXACT_IDENTITY_MISSING")
    if row.get("exact_pair_verified") is False or row.get("pair_identity_verified") is False:
        reasons.append("EXACT_PAIR_NOT_VERIFIED")
    if row.get("market_age_verified") is False:
        reasons.append("MARKET_AGE_NOT_VERIFIED")
    if age is None or age < MIN_MARKET_AGE_DAYS:
        reasons.append("VETERAN_90D_NOT_VERIFIED")
    if liq is None or liq < MIN_LIQUIDITY_USD:
        reasons.append("VERIFIED_EXECUTION_LIQUIDITY_LT_15K_OR_MISSING")
    if price is None:
        reasons.append("PRICE_MISSING")
    if row.get("actionable_research_alert") is True or str(row.get("status") or "").upper() == "REAL_ALERT":
        reasons.append("NOT_A_CONTROL_SIGNAL_IS_ACTIONABLE")
    return not reasons, reasons


def _record(row: dict[str, Any], event_at: datetime, enrolled_at: str) -> dict[str, Any]:
    chain = str(row.get("chain") or "").lower()
    token = row.get("token_address") or row.get("token")
    pair = row.get("pair_address") or row.get("entry_pair_address")
    liq = _entry_liquidity(row)
    return {
        "lane": "VERIFIED_WATCH_FORWARD_CONTROL",
        "key": _key(chain, token, pair),
        "chain": chain,
        "token": token,
        "pair_address": pair,
        "event_at": event_at.isoformat(),
        "entry_price_usd": _entry_price(row),
        "entry_liquidity_usd": liq,
        "source": "real-alerts.json:verified_watch",
        "enrolled_at": enrolled_at,
        "checkpoints": {},
        "observations": 0,
        "latest_return_pct": None,
        "latest_friction_adjusted_return_pct": None,
        "peak_sampled_return_pct": None,
        "low_sampled_return_pct": None,
        "entry_context": {
            "score": row.get("score"),
            "readiness_passed": row.get("readiness_passed"),
            "readiness_total": row.get("readiness_total"),
            "source_lanes": row.get("source_lanes") or [],
            "blockers": row.get("blockers") or [],
            "market_age_days": _age(row),
            "market_age_verified": row.get("market_age_verified"),
            "execution_liquidity_usd": liq,
            "pool_tvl_usd": row.get("pool_tvl_usd"),
            "volume_h1_usd": row.get("dex_volume_h1") or row.get("volume_h1_usd"),
            "turnover_h1": row.get("turnover_h1"),
            "activity_verified": row.get("market_activity_verified") or row.get("dex_activity_verified"),
        },
    }


def _observe(rec: dict[str, Any], row: dict[str, Any], observed_at: datetime) -> None:
    entry = _num(rec.get("entry_price_usd"))
    current = _entry_price(row)
    event = _dt(rec.get("event_at"))
    if entry is None or current is None or event is None or observed_at < event:
        return
    ret = (current / entry - 1.0) * 100.0
    age_min = (observed_at - event).total_seconds() / 60.0
    rec["observations"] = int(rec.get("observations") or 0) + 1
    rec["latest_observed_at"] = observed_at.isoformat()
    rec["latest_price_usd"] = current
    rec["latest_liquidity_usd"] = _entry_liquidity(row)
    rec["latest_return_pct"] = round(ret, 6)
    rec["latest_friction_adjusted_return_pct"] = round(ret - 2.0, 6)
    peak = _num(rec.get("peak_sampled_return_pct"))
    low = _num(rec.get("low_sampled_return_pct"))
    rec["peak_sampled_return_pct"] = round(ret if peak is None else max(peak, ret), 6)
    rec["low_sampled_return_pct"] = round(ret if low is None else min(low, ret), 6)
    for minutes, label in ((5, "5m"), (15, "15m"), (60, "1h"), (360, "6h"), (1440, "24h"), (10080, "7d")):
        if age_min < minutes or label in rec.setdefault("checkpoints", {}):
            continue
        rec["checkpoints"][label] = {
            "captured_at": observed_at.isoformat(),
            "captured_age_minutes": round(age_min, 3),
            "price_usd": current,
            "liquidity_usd": _entry_liquidity(row),
            "gross_return_pct": round(ret, 6),
            "friction_adjusted_return_pct": round(ret - 2.0, 6),
            "source": "real-alerts.json:verified_watch",
        }


def run(data_dir: str | Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    reference = now or datetime.now(timezone.utc)
    ledger_path = data_dir / LEDGER.name
    real_path = data_dir / REAL_ALERTS.name
    ledger = _load(ledger_path, {})
    real = _load(real_path, {})
    if not isinstance(ledger, dict) or ledger.get("mode") != ALPHA_MODE:
        audit = {"version": 1, "mode": MODE, "updated_at": reference.isoformat(), "status": "ALPHA_LEDGER_UNAVAILABLE", "enrolled": 0, "observed": 0}
        _write(data_dir / OUT.name, audit)
        return audit
    activation = _dt(ledger.get("activation_at")) or reference
    controls = ledger.setdefault("controls", {})
    rows = real.get("verified_watch") if isinstance(real, dict) and isinstance(real.get("verified_watch"), list) else []
    generated = _dt(real.get("generated_at")) or reference
    enrolled = 0
    observed = 0
    blocked: dict[str, int] = {}
    active_index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        chain = row.get("chain")
        token = row.get("token_address") or row.get("token")
        pair = row.get("pair_address") or row.get("entry_pair_address")
        if chain and token and pair:
            active_index[_key(chain, token, pair)] = row
        ok, reasons = _eligible(row)
        if not ok:
            for reason in reasons:
                blocked[reason] = blocked.get(reason, 0) + 1
            continue
        event = _dt(row.get("watch_added_at") or row.get("watch_entered_at") or row.get("first_seen_at") or real.get("generated_at"))
        if event is None or event < activation:
            blocked["PRE_ACTIVATION_CONTROL"] = blocked.get("PRE_ACTIVATION_CONTROL", 0) + 1
            continue
        rec_key = f"VERIFIED_WATCH_FORWARD_CONTROL|{_key(chain, token, pair)}|{event.isoformat()}"
        if rec_key not in controls:
            controls[rec_key] = _record(row, event, reference.isoformat())
            enrolled += 1
    for rec in controls.values():
        if not isinstance(rec, dict) or rec.get("lane") != "VERIFIED_WATCH_FORWARD_CONTROL":
            continue
        row = active_index.get(str(rec.get("key") or ""))
        if isinstance(row, dict):
            before = int(rec.get("observations") or 0)
            _observe(rec, row, generated)
            if int(rec.get("observations") or 0) > before:
                observed += 1
    ledger["updated_at"] = reference.isoformat()
    _write(ledger_path, ledger)
    audit = {
        "version": 1,
        "mode": MODE,
        "updated_at": reference.isoformat(),
        "research_only": True,
        "production_impact": "NONE",
        "no_hindsight": True,
        "exact_pair_only": True,
        "policy": {
            "source": "real-alerts.json:verified_watch",
            "minimum_market_age_days": MIN_MARKET_AGE_DAYS,
            "minimum_verified_execution_liquidity_usd": MIN_LIQUIDITY_USD,
            "pool_tvl_never_substitutes_for_execution_liquidity": True,
            "actionable_rows_never_controls": True,
            "first_entry_is_immutable": True,
        },
        "eligible_source_rows": sum(1 for r in rows if isinstance(r, dict) and _eligible(r)[0]),
        "enrolled_this_run": enrolled,
        "observed_this_run": observed,
        "formal_control_count_after": len(controls),
        "blocked_reasons": blocked,
    }
    _write(data_dir / OUT.name, audit)
    print(json.dumps(audit, indent=2))
    return audit


if __name__ == "__main__":
    run()
