from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable

from .near_alert_observatory import _fetch_exact_pair_market

DATA = Path("data")
LEDGER = DATA / "research-sample-ledger.json"
REPORT = DATA / "research-sample-report.json"
REAL_ALERTS = DATA / "real-alerts.json"
ALPHA_REPORT = DATA / "alpha-proof-report.json"
MODE = "RESEARCH_ONLY_FORWARD_SAMPLE_ACCELERATOR_V1"
ROUND_TRIP_FRICTION_PCT = 2.0
MIN_READINESS_PASSED = 5
MIN_VERIFIED_EXECUTION_LIQUIDITY_USD = 15_000.0
MAX_DUE_FETCHES_PER_RUN = 25
HORIZONS = ((60, "1h"), (360, "6h"), (1440, "24h"), (10080, "7d"))
WINNER_PCT = 20.0
BIG_WINNER_PCT = 100.0
LOSER_PCT = -20.0
MIN_GATE_REVIEW_SAMPLE = 5
MIN_GATE_WINNER_RATE_PCT = 20.0


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _dt(value: Any) -> datetime | None:
    try:
        out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _norm(chain: Any, value: Any) -> str:
    c = str(chain or "").strip().lower()
    raw = str(value or "").strip()
    return raw.lower() if c in {"bsc", "bnb", "ethereum", "eth", "base", "arbitrum", "optimism", "polygon"} else raw


def _identity_key(chain: Any, token: Any, pair: Any) -> str:
    c = str(chain or "").strip().lower()
    return f"{c}|{_norm(c, token)}|{_norm(c, pair)}"


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _entry_price(row: dict[str, Any]) -> float | None:
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    for value in (
        row.get("price_usd"), row.get("current_price_usd"), row.get("dex_price_usd"),
        row.get("reference_price"), market.get("price_usd"), market.get("current_price_usd"),
    ):
        x = _num(value)
        if x is not None and x > 0:
            return x
    return None


def _execution_liquidity(row: dict[str, Any]) -> float | None:
    market = row.get("market") if isinstance(row.get("market"), dict) else {}
    for value in (row.get("execution_pool_liquidity_usd"), market.get("execution_pool_liquidity_usd")):
        x = _num(value)
        if x is not None and x > 0:
            return x
    blockers = {str(x) for x in (row.get("blockers") or [])}
    if "EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL" not in blockers:
        for value in (row.get("liquidity_usd"), market.get("liquidity_usd")):
            x = _num(value)
            if x is not None and x > 0:
                return x
    return None


def _eligible_shadow(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    tier = str(row.get("radar_tier") or "").upper()
    readiness = int(row.get("readiness_passed") or 0)
    chain = row.get("chain")
    token = row.get("token_address") or row.get("token")
    pair = row.get("pair_address") or row.get("entry_pair_address")
    if tier not in {"NEAR_ALERT", "VERIFIED_WATCH"}:
        reasons.append("NOT_NEAR_OR_VERIFIED_WATCH")
    if readiness < MIN_READINESS_PASSED:
        reasons.append("READINESS_LT_5_OF_7")
    if not chain or not token or not pair:
        reasons.append("EXACT_IDENTITY_MISSING")
    if row.get("exact_identity_verified") is not True:
        reasons.append("EXACT_IDENTITY_NOT_VERIFIED")
    if row.get("exact_pair_verified") is not True:
        reasons.append("EXACT_PAIR_NOT_VERIFIED")
    if row.get("market_age_verified") is not True:
        reasons.append("MARKET_AGE_NOT_VERIFIED")
    if _entry_price(row) is None:
        reasons.append("PRICE_MISSING")
    if row.get("actionable_research_alert") is True or row.get("actionable") is True or tier == "REAL_ALERT" or str(row.get("status") or "").upper() == "REAL_ALERT":
        reasons.append("ACTIONABLE_ROW_EXCLUDED_FROM_SHADOW")
    return not reasons, reasons


def _snapshot(row: dict[str, Any], observed_at: datetime) -> dict[str, Any]:
    execution_liq = _execution_liquidity(row)
    blockers = [str(x) for x in (row.get("blockers") or []) if x]
    missing_gates = [str(x) for x in (row.get("missing_gates") or []) if x]
    return {
        "observed_at": observed_at.isoformat(),
        "radar_tier": str(row.get("radar_tier") or "").upper(),
        "status": row.get("status"),
        "readiness_passed": int(row.get("readiness_passed") or 0),
        "readiness_total": int(row.get("readiness_total") or 7),
        "signal_score": _num(row.get("signal_score")),
        "signal_score_semantics": "MAX_AVAILABLE_SIGNAL_NOT_PROBABILITY",
        "missing_gates": missing_gates,
        "blockers": blockers,
        "evidence_ready": row.get("evidence_ready") is True,
        "evidence_positive_count": int(row.get("evidence_positive_count") or 0),
        "evidence_positive_lanes": list(row.get("evidence_positive_lanes") or []),
        "source_lane_count": int(row.get("source_lane_count") or 0),
        "market_age_days": _num(row.get("market_age_days") or row.get("market_age_min_days")),
        "entry_price_usd": _entry_price(row),
        "verified_execution_liquidity_usd": execution_liq,
        "verified_execution_tradable": execution_liq is not None and execution_liq >= MIN_VERIFIED_EXECUTION_LIQUIDITY_USD,
        "pool_value_informational_only_usd": _num(row.get("provider_reported_pool_value_usd") or row.get("pool_tvl_usd")),
    }


def _new_record(row: dict[str, Any], observed_at: datetime, enrolled_at: datetime) -> dict[str, Any]:
    chain = str(row.get("chain") or "").strip().lower()
    token = row.get("token_address") or row.get("token")
    pair = row.get("pair_address") or row.get("entry_pair_address")
    snap = _snapshot(row, observed_at)
    lane = "NEAR_ALERT_SHADOW" if snap["radar_tier"] == "NEAR_ALERT" else "VERIFIED_WATCH_SHADOW"
    frozen = {
        "identity": {"chain": chain, "token": token, "pair_address": pair},
        "entry": snap,
    }
    return {
        "lane": lane,
        "key": _identity_key(chain, token, pair),
        "chain": chain,
        "token_address": token,
        "pair_address": pair,
        "event_at": observed_at.isoformat(),
        "enrolled_at": enrolled_at.isoformat(),
        "entry_price_usd": snap["entry_price_usd"],
        "decision_snapshot": frozen,
        "decision_snapshot_sha256": _canonical_hash(frozen),
        "checkpoints": {},
        "observations": 0,
        "latest_return_pct": None,
        "latest_friction_adjusted_return_pct": None,
        "integrity": "PASS",
    }


def _initial_ledger(now: datetime) -> dict[str, Any]:
    return {
        "version": 1,
        "mode": MODE,
        "activation_at": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "records": {},
        "contract": {
            "research_only": True,
            "formal_alpha_proof_unchanged": True,
            "real_alert_gate_changed": False,
            "telegram_alerts_changed": False,
            "automatic_promotion": False,
            "automatic_weight_mutation": False,
            "forward_only": True,
            "exact_pair_only": True,
            "first_decision_snapshot_immutable": True,
            "minimum_readiness_passed": MIN_READINESS_PASSED,
            "verified_execution_tradable_threshold_usd": MIN_VERIFIED_EXECUTION_LIQUIDITY_USD,
            "pool_tvl_never_substitutes_for_execution_depth": True,
            "round_trip_friction_pct": ROUND_TRIP_FRICTION_PCT,
        },
    }


def _integrity_check(rec: dict[str, Any]) -> bool:
    frozen = rec.get("decision_snapshot")
    expected = str(rec.get("decision_snapshot_sha256") or "")
    ok = isinstance(frozen, dict) and expected == _canonical_hash(frozen)
    rec["integrity"] = "PASS" if ok else "FAIL"
    return ok


def _enroll(ledger: dict[str, Any], real: dict[str, Any], now: datetime) -> tuple[int, Counter[str]]:
    records = ledger.setdefault("records", {})
    rows = real.get("verified_watch") if isinstance(real.get("verified_watch"), list) else []
    observed_at = _dt(real.get("generated_at")) or now
    activation = _dt(ledger.get("activation_at")) or now
    enrolled = 0
    blocked: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ok, reasons = _eligible_shadow(row)
        if not ok:
            blocked.update(reasons)
            continue
        chain = row.get("chain")
        token = row.get("token_address") or row.get("token")
        pair = row.get("pair_address") or row.get("entry_pair_address")
        key = _identity_key(chain, token, pair)
        if not key or key == "||":
            continue
        rec_key = f"SHADOW|{key}"
        if rec_key in records:
            continue
        event = _dt(row.get("watch_added_at") or row.get("watch_entered_at") or row.get("first_seen_at")) or observed_at
        if event < activation:
            event = observed_at
        records[rec_key] = _new_record(row, event, now)
        enrolled += 1
    return enrolled, blocked


def _extract_market(market: dict[str, Any]) -> tuple[float | None, float | None]:
    price = _num(market.get("priceUsd"))
    liquidity = market.get("liquidity") if isinstance(market.get("liquidity"), dict) else {}
    liq = _num(liquidity.get("usd"))
    return (price if price is not None and price > 0 else None, liq if liq is not None and liq > 0 else None)


def _checkpoint(rec: dict[str, Any], observed_at: datetime, price: float, liquidity: float | None) -> None:
    event = _dt(rec.get("event_at"))
    entry = _num(rec.get("entry_price_usd"))
    if event is None or entry is None or entry <= 0 or observed_at < event:
        return
    age_min = (observed_at - event).total_seconds() / 60.0
    gross = (price / entry - 1.0) * 100.0
    adjusted = gross - ROUND_TRIP_FRICTION_PCT
    rec["observations"] = int(rec.get("observations") or 0) + 1
    rec["latest_observed_at"] = observed_at.isoformat()
    rec["latest_price_usd"] = price
    rec["latest_provider_pool_value_usd"] = liquidity
    rec["latest_return_pct"] = round(gross, 6)
    rec["latest_friction_adjusted_return_pct"] = round(adjusted, 6)
    cps = rec.setdefault("checkpoints", {})
    for minutes, label in HORIZONS:
        if label in cps or age_min < minutes:
            continue
        cps[label] = {
            "captured_at": observed_at.isoformat(),
            "captured_age_minutes": round(age_min, 3),
            "price_usd": price,
            "provider_pool_value_usd": liquidity,
            "provider_pool_value_semantics": "INFORMATIONAL_ONLY_NOT_EXECUTION_DEPTH",
            "gross_return_pct": round(gross, 6),
            "friction_adjusted_return_pct": round(adjusted, 6),
            "source": "DEXSCREENER_EXACT_PAIR_DUE_CHECKPOINT",
        }


def _due_records(ledger: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    due: list[tuple[datetime, dict[str, Any]]] = []
    for rec in (ledger.get("records") or {}).values():
        if not isinstance(rec, dict) or not _integrity_check(rec):
            continue
        event = _dt(rec.get("event_at"))
        if event is None:
            continue
        cps = rec.get("checkpoints") if isinstance(rec.get("checkpoints"), dict) else {}
        due_at: datetime | None = None
        for minutes, label in HORIZONS:
            if label not in cps and now >= event + timedelta(minutes=minutes):
                due_at = event + timedelta(minutes=minutes)
                break
        if due_at is not None:
            due.append((due_at, rec))
    due.sort(key=lambda item: item[0])
    return [rec for _, rec in due]


def _observe_due(
    ledger: dict[str, Any], now: datetime, fetcher: Callable[[dict[str, Any]], dict[str, Any] | None]
) -> dict[str, Any]:
    requested = succeeded = failed = 0
    for rec in _due_records(ledger, now)[:MAX_DUE_FETCHES_PER_RUN]:
        requested += 1
        probe = {
            "chain": rec.get("chain"),
            "token_address": rec.get("token_address"),
            "pair_address": rec.get("pair_address"),
            "exact_identity_verified": True,
            "exact_pair_verified": True,
        }
        try:
            market = fetcher(probe)
        except Exception:
            market = None
        if not isinstance(market, dict):
            failed += 1
            continue
        price, liq = _extract_market(market)
        if price is None:
            failed += 1
            continue
        _checkpoint(rec, now, price, liq)
        succeeded += 1
    return {"requested": requested, "succeeded": succeeded, "failed": failed, "cap": MAX_DUE_FETCHES_PER_RUN}


def _classify(value: float | None) -> str:
    if value is None:
        return "IMMATURE"
    if value >= BIG_WINNER_PCT:
        return "BIG_WINNER"
    if value >= WINNER_PCT:
        return "WINNER"
    if value <= LOSER_PCT:
        return "LOSER"
    return "NEUTRAL"


def _metrics(records: list[dict[str, Any]], horizon: str, tradable_only: bool = False) -> dict[str, Any]:
    vals: list[float] = []
    classes: Counter[str] = Counter()
    for rec in records:
        entry = ((rec.get("decision_snapshot") or {}).get("entry") or {})
        if tradable_only and entry.get("verified_execution_tradable") is not True:
            continue
        cp = (rec.get("checkpoints") or {}).get(horizon)
        value = _num(cp.get("friction_adjusted_return_pct")) if isinstance(cp, dict) else None
        if value is None:
            continue
        vals.append(value)
        classes[_classify(value)] += 1
    return {
        "n": len(vals),
        "mean_friction_adjusted_return_pct": round(mean(vals), 6) if vals else None,
        "median_friction_adjusted_return_pct": round(median(vals), 6) if vals else None,
        "winner_rate_pct": round(sum(v >= WINNER_PCT for v in vals) / len(vals) * 100.0, 4) if vals else None,
        "big_winner_rate_pct": round(sum(v >= BIG_WINNER_PCT for v in vals) / len(vals) * 100.0, 4) if vals else None,
        "loser_rate_pct": round(sum(v <= LOSER_PCT for v in vals) / len(vals) * 100.0, 4) if vals else None,
        "class_counts": dict(classes),
    }


def _gate_attribution(records: list[dict[str, Any]], horizon: str = "24h") -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        entry = ((rec.get("decision_snapshot") or {}).get("entry") or {})
        if entry.get("verified_execution_tradable") is not True:
            continue
        cp = (rec.get("checkpoints") or {}).get(horizon)
        value = _num(cp.get("friction_adjusted_return_pct")) if isinstance(cp, dict) else None
        if value is None:
            continue
        labels = list(entry.get("missing_gates") or []) + list(entry.get("blockers") or [])
        for label in {str(x) for x in labels if x}:
            buckets[label].append(value)
    out = []
    for gate, vals in buckets.items():
        winner_rate = sum(v >= WINNER_PCT for v in vals) / len(vals) * 100.0
        loser_rate = sum(v <= LOSER_PCT for v in vals) / len(vals) * 100.0
        out.append({
            "gate_or_blocker": gate,
            "n": len(vals),
            "winner_count": sum(v >= WINNER_PCT for v in vals),
            "big_winner_count": sum(v >= BIG_WINNER_PCT for v in vals),
            "loser_count": sum(v <= LOSER_PCT for v in vals),
            "winner_rate_pct": round(winner_rate, 4),
            "loser_rate_pct": round(loser_rate, 4),
            "mean_friction_adjusted_return_pct": round(mean(vals), 6),
            "review_candidate": len(vals) >= MIN_GATE_REVIEW_SAMPLE and winner_rate >= MIN_GATE_WINNER_RATE_PCT,
        })
    return sorted(out, key=lambda x: (x["review_candidate"], x["winner_count"], x["n"]), reverse=True)


def _formal_context(data_dir: Path) -> dict[str, Any]:
    alpha = _load(data_dir / ALPHA_REPORT.name, {})
    maturity = alpha.get("sample_maturity") if isinstance(alpha.get("sample_maturity"), dict) else {}
    return {
        "mode": alpha.get("mode"),
        "primary_proof_status": alpha.get("primary_proof_status"),
        "mature_24h_signal_count": int(maturity.get("mature_24h_signal_count") or 0),
        "mature_24h_control_count": int(maturity.get("mature_24h_control_count") or 0),
        "formal_proof_unchanged_by_accelerator": True,
    }


def _report(ledger: dict[str, Any], data_dir: Path, now: datetime, enrolled: int, blocked: Counter[str], fetch_audit: dict[str, Any]) -> dict[str, Any]:
    records = [r for r in (ledger.get("records") or {}).values() if isinstance(r, dict)]
    integrity_failures = [r.get("key") for r in records if not _integrity_check(r)]
    lane_counts = Counter(str(r.get("lane") or "UNKNOWN") for r in records)
    tradable = [r for r in records if (((r.get("decision_snapshot") or {}).get("entry") or {}).get("verified_execution_tradable") is True)]
    horizons = {label: {"all_shadow": _metrics(records, label), "verified_execution_subset": _metrics(records, label, True)} for _, label in HORIZONS}
    gate_attr = _gate_attribution(records, "24h")
    mature24 = horizons["24h"]["verified_execution_subset"]["n"]
    early_target, strong_target, deep_target = 20, 50, 100
    return {
        "version": 1,
        "mode": MODE,
        "updated_at": now.isoformat(),
        "activation_at": ledger.get("activation_at"),
        "research_only": True,
        "formal_alpha_proof_unchanged": True,
        "record_count": len(records),
        "verified_execution_record_count": len(tradable),
        "enrolled_this_run": enrolled,
        "lane_counts": dict(lane_counts),
        "integrity": {"status": "PASS" if not integrity_failures else "FAIL", "checked_records": len(records), "hash_mismatch_keys": integrity_failures},
        "checkpoint_fetch": fetch_audit,
        "horizons": horizons,
        "sample_acceleration": {
            "primary_learning_horizon": "24h",
            "primary_learning_cohort": "verified_execution_subset",
            "mature_24h_count": mature24,
            "usable_target": early_target,
            "strong_target": strong_target,
            "deep_target": deep_target,
            "usable_remaining": max(0, early_target - mature24),
            "strong_remaining": max(0, strong_target - mature24),
            "deep_remaining": max(0, deep_target - mature24),
            "usable_progress_pct": round(min(1.0, mature24 / early_target) * 100.0, 1),
            "strong_progress_pct": round(min(1.0, mature24 / strong_target) * 100.0, 1),
            "deep_progress_pct": round(min(1.0, mature24 / deep_target) * 100.0, 1),
            "purpose": "ACCELERATE_GATE_AND_WEIGHT_LEARNING_WITHOUT_RELAXING_REAL_ALERT_OR_FORMAL_ALPHA_PROOF",
        },
        "gate_attribution_24h": gate_attr,
        "learning_review_queue": [
            {"gate_or_blocker": x["gate_or_blocker"], "n": x["n"], "winner_rate_pct": x["winner_rate_pct"], "action": "REVIEW_IN_SHADOW_ONLY", "production_change_allowed": False}
            for x in gate_attr if x.get("review_candidate")
        ],
        "formal_alpha_context": _formal_context(data_dir),
        "blocked_enrollment_reasons": dict(blocked),
        "guardrails": {
            "real_alert_gate_changed": False,
            "real_alert_thresholds_weakened": False,
            "telegram_alerts_changed": False,
            "production_scoring_changed": False,
            "production_gates_changed": False,
            "automatic_promotion": False,
            "automatic_weight_mutation": False,
            "research_only": True,
        },
        "truth_notes": [
            "The accelerator creates a separate prospective shadow cohort; it never counts as formal Alpha Proof signals or controls.",
            "One immutable first decision snapshot is kept per exact token+pair to prevent pseudo-sample inflation.",
            "Only exact-pair forward prices observed after activation may populate outcome checkpoints.",
            "Verified execution depth is separated from provider pool value; pool TVL never makes a row tradable.",
            "Gate/weight review requires repeated 24h evidence and can only enter shadow review; production cannot auto-change.",
        ],
    }


def run(
    data_dir: str | Path = DATA,
    now: datetime | None = None,
    fetcher: Callable[[dict[str, Any]], dict[str, Any] | None] = _fetch_exact_pair_market,
) -> dict[str, Any]:
    data_dir = Path(data_dir)
    reference = now or datetime.now(timezone.utc)
    ledger_path = data_dir / LEDGER.name
    ledger = _load(ledger_path, None)
    if not isinstance(ledger, dict) or ledger.get("mode") != MODE or not _dt(ledger.get("activation_at")):
        ledger = _initial_ledger(reference)
    real = _load(data_dir / REAL_ALERTS.name, {})
    enrolled, blocked = _enroll(ledger, real if isinstance(real, dict) else {}, reference)
    fetch_audit = _observe_due(ledger, reference, fetcher)
    ledger["updated_at"] = reference.isoformat()
    _write(ledger_path, ledger)
    report = _report(ledger, data_dir, reference, enrolled, blocked, fetch_audit)
    _write(data_dir / REPORT.name, report)
    print(json.dumps({
        "mode": MODE,
        "record_count": report["record_count"],
        "verified_execution_record_count": report["verified_execution_record_count"],
        "mature_24h_count": report["sample_acceleration"]["mature_24h_count"],
        "enrolled_this_run": enrolled,
        "integrity": report["integrity"]["status"],
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
