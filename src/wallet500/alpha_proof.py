from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

DATA = Path("data")
LEDGER_PATH = DATA / "alpha-proof-ledger.json"
REPORT_PATH = DATA / "alpha-proof-report.json"
MODE = "FORWARD_ONLY_ALPHA_PROOF_V1"
MIN_TRADABLE_LIQUIDITY_USD = 50_000.0
ROUND_TRIP_FRICTION_BPS = 200.0
HORIZONS = (
    (5, "5m"),
    (15, "15m"),
    (60, "1h"),
    (360, "6h"),
    (1440, "24h"),
    (10080, "7d"),
)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dt(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _num(value: Any) -> float | None:
    try:
        v = float(value)
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    except Exception:
        return None


def _norm(chain: Any, value: Any) -> str:
    chain_s = str(chain or "").lower()
    s = str(value or "")
    return s.lower() if chain_s in {"bsc", "bnb", "ethereum", "eth"} else s


def _key(chain: Any, token: Any, pair: Any) -> str:
    c = str(chain or "").lower()
    return f"{c}|{_norm(c, token)}|{_norm(c, pair)}"


def _return_pct(current: Any, entry: Any) -> float | None:
    c = _num(current)
    e = _num(entry)
    if c is None or e is None or c <= 0 or e <= 0:
        return None
    return round((c / e - 1.0) * 100.0, 6)


def _friction_adjusted(ret: float | None) -> float | None:
    if ret is None:
        return None
    return round(ret - ROUND_TRIP_FRICTION_BPS / 100.0, 6)


def _initial_ledger(now: datetime) -> dict[str, Any]:
    ts = now.isoformat()
    return {
        "version": 1,
        "mode": MODE,
        "activation_at": ts,
        "created_at": ts,
        "updated_at": ts,
        "signals": {},
        "controls": {},
        "policy": {
            "formal_proof_starts_at_activation": True,
            "pre_activation_events_formal_proof": False,
            "exact_pair_identity_required": True,
            "minimum_control_entry_liquidity_usd": MIN_TRADABLE_LIQUIDITY_USD,
            "round_trip_friction_bps": ROUND_TRIP_FRICTION_BPS,
            "checkpoint_rule": "FIRST OBSERVATION AT OR AFTER HORIZON; CHECKPOINT NEVER REWRITTEN",
            "horizons": [label for _, label in HORIZONS],
            "no_hindsight": True,
        },
    }


def _signal_record(
    lane: str,
    chain: Any,
    token: Any,
    pair: Any,
    event_at: Any,
    entry_price: Any,
    entry_liquidity: Any,
    source: str,
    enrolled_at: str,
) -> dict[str, Any] | None:
    event = _dt(event_at)
    price = _num(entry_price)
    if event is None or price is None or price <= 0 or not chain or not token or not pair:
        return None
    return {
        "lane": lane,
        "key": _key(chain, token, pair),
        "chain": str(chain).lower(),
        "token": token,
        "pair_address": pair,
        "event_at": event.isoformat(),
        "entry_price_usd": price,
        "entry_liquidity_usd": _num(entry_liquidity),
        "source": source,
        "enrolled_at": enrolled_at,
        "checkpoints": {},
        "observations": 0,
        "latest_return_pct": None,
        "latest_friction_adjusted_return_pct": None,
        "peak_sampled_return_pct": None,
        "low_sampled_return_pct": None,
    }


def _observe(record: dict[str, Any], observed_at: Any, current_price: Any, current_liquidity: Any = None) -> None:
    obs = _dt(observed_at)
    event = _dt(record.get("event_at"))
    ret = _return_pct(current_price, record.get("entry_price_usd"))
    if obs is None or event is None or ret is None or obs < event:
        return
    age_min = max(0.0, (obs - event).total_seconds() / 60.0)
    record["observations"] = int(record.get("observations") or 0) + 1
    record["latest_observed_at"] = obs.isoformat()
    record["latest_price_usd"] = _num(current_price)
    record["latest_liquidity_usd"] = _num(current_liquidity)
    record["latest_return_pct"] = ret
    record["latest_friction_adjusted_return_pct"] = _friction_adjusted(ret)
    peak = _num(record.get("peak_sampled_return_pct"))
    low = _num(record.get("low_sampled_return_pct"))
    record["peak_sampled_return_pct"] = ret if peak is None else max(peak, ret)
    record["low_sampled_return_pct"] = ret if low is None else min(low, ret)
    checkpoints = record.setdefault("checkpoints", {})
    for minutes, label in HORIZONS:
        if label in checkpoints or age_min < minutes:
            continue
        checkpoints[label] = {
            "captured_at": obs.isoformat(),
            "captured_age_minutes": round(age_min, 3),
            "price_usd": _num(current_price),
            "liquidity_usd": _num(current_liquidity),
            "gross_return_pct": ret,
            "friction_adjusted_return_pct": _friction_adjusted(ret),
        }


def _reawakening_index(payload: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return out
    for row in payload.get("targets") or []:
        if not isinstance(row, dict):
            continue
        pair = row.get("pair_address") or row.get("entry_pair_address")
        k = _key(row.get("chain"), row.get("token"), pair)
        if k != "||":
            out[k] = row
    return out


def _outcome_index(payload: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    records = payload.get("tokens") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return out
    for row in records.values():
        if not isinstance(row, dict):
            continue
        pair = row.get("entry_pair_address") or row.get("pair_address")
        k = _key(row.get("chain"), row.get("token"), pair)
        if k != "||":
            out[k] = row
    return out


def _latest_liquidity_from_outcome(row: dict[str, Any]) -> Any:
    hist = row.get("history") if isinstance(row.get("history"), list) else []
    for item in reversed(hist):
        if isinstance(item, dict) and item.get("liquidity_usd") is not None:
            return item.get("liquidity_usd")
    return row.get("liquidity_usd")


def _enroll_signals(ledger: dict[str, Any], data_dir: Path, activation: datetime, now: datetime) -> None:
    signals = ledger.setdefault("signals", {})
    now_s = now.isoformat()

    reawakening = _load(data_dir / "reawakening-shadow.json", {})
    for row in (reawakening.get("targets") or []) if isinstance(reawakening, dict) else []:
        if not isinstance(row, dict):
            continue
        event = _dt(row.get("triggered_at"))
        pair = row.get("pair_address") or row.get("entry_pair_address")
        k0 = _key(row.get("chain"), row.get("token"), pair)
        rec_key = f"PRECURSOR_REAWAKENING|{k0}|{event.isoformat() if event else ''}"
        if event is None or event < activation or rec_key in signals:
            continue
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        rec = _signal_record(
            "PRECURSOR_REAWAKENING", row.get("chain"), row.get("token"), pair,
            event, row.get("price_usd"), metrics.get("liquidity_usd"),
            "reawakening-shadow.json", now_s,
        )
        if rec:
            signals[rec_key] = rec

    evidence = _load(data_dir / "discovery-evidence-ledger.json", {})
    records = evidence.get("records") if isinstance(evidence, dict) else None
    if isinstance(records, dict):
        for snap in records.values():
            if not isinstance(snap, dict):
                continue
            event = _dt(snap.get("observed_at"))
            ident = snap.get("identity") if isinstance(snap.get("identity"), dict) else {}
            market = snap.get("market") if isinstance(snap.get("market"), dict) else {}
            k0 = _key(ident.get("chain"), ident.get("token"), ident.get("pair_address"))
            rec_key = f"PRODUCTION_FIRST_QUALIFIED|{k0}|{event.isoformat() if event else ''}"
            if event is None or event < activation or rec_key in signals:
                continue
            rec = _signal_record(
                "PRODUCTION_FIRST_QUALIFIED", ident.get("chain"), ident.get("token"), ident.get("pair_address"),
                event, market.get("price_usd"), market.get("liquidity_usd"),
                "discovery-evidence-ledger.json", now_s,
            )
            if rec:
                signals[rec_key] = rec


def _enroll_controls(ledger: dict[str, Any], data_dir: Path, activation: datetime, now: datetime) -> None:
    controls = ledger.setdefault("controls", {})
    rejected = _load(data_dir / "rejected-candidate-ledger.json", {})
    records = rejected.get("records") if isinstance(rejected, dict) else None
    if not isinstance(records, dict):
        return
    for source_key, row in records.items():
        if not isinstance(row, dict):
            continue
        event = _dt(row.get("first_rejected_at"))
        snap = row.get("first_reject_snapshot") if isinstance(row.get("first_reject_snapshot"), dict) else {}
        price = _num(snap.get("price_usd"))
        liq = _num(snap.get("liquidity_usd"))
        if event is None or event < activation or price is None or price <= 0 or liq is None or liq < MIN_TRADABLE_LIQUIDITY_USD:
            continue
        ident = row.get("identity") if isinstance(row.get("identity"), dict) else {}
        pair = ident.get("pair_address") or snap.get("pair_address")
        k0 = _key(ident.get("chain") or snap.get("chain"), ident.get("token") or snap.get("token"), pair)
        rec_key = f"REJECTED_TRADABLE_CONTROL|{k0}|{event.isoformat()}"
        if rec_key in controls:
            continue
        rec = _signal_record(
            "REJECTED_TRADABLE_CONTROL",
            ident.get("chain") or snap.get("chain"),
            ident.get("token") or snap.get("token"),
            pair,
            event, price, liq,
            f"rejected-candidate-ledger:{row.get('first_reject_source') or 'UNKNOWN'}",
            now.isoformat(),
        )
        if rec:
            rec["first_reject_source"] = row.get("first_reject_source")
            rec["first_decision_class"] = row.get("first_decision_class")
            rec["source_record_key"] = source_key
            controls[rec_key] = rec


def _update_observations(ledger: dict[str, Any], data_dir: Path) -> None:
    reawakening = _reawakening_index(_load(data_dir / "reawakening-shadow.json", {}))
    outcomes = _outcome_index(_load(data_dir / "outcome-tracker.json", {}))
    rejected = _load(data_dir / "rejected-candidate-ledger.json", {})
    rejected_records = rejected.get("records") if isinstance(rejected, dict) and isinstance(rejected.get("records"), dict) else {}

    for rec in ledger.get("signals", {}).values():
        if not isinstance(rec, dict):
            continue
        row = reawakening.get(rec.get("key")) if rec.get("lane") == "PRECURSOR_REAWAKENING" else outcomes.get(rec.get("key"))
        if not isinstance(row, dict):
            continue
        if rec.get("lane") == "PRECURSOR_REAWAKENING":
            observed_at = row.get("updated_at") or row.get("triggered_at")
            current_price = row.get("current_price_usd") or row.get("price_usd")
            metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
            current_liquidity = row.get("current_liquidity_usd") or metrics.get("liquidity_usd")
        else:
            observed_at = row.get("updated_at")
            current_price = row.get("current_price_usd")
            current_liquidity = _latest_liquidity_from_outcome(row)
        _observe(rec, observed_at, current_price, current_liquidity)

    for rec in ledger.get("controls", {}).values():
        if not isinstance(rec, dict):
            continue
        row = rejected_records.get(rec.get("source_record_key"))
        if not isinstance(row, dict):
            continue
        latest = row.get("latest_observation") if isinstance(row.get("latest_observation"), dict) else {}
        _observe(rec, latest.get("observed_at"), latest.get("price_usd"), latest.get("liquidity_usd"))


def _stats(records: list[dict[str, Any]], horizon: str) -> dict[str, Any]:
    gross: list[float] = []
    friction: list[float] = []
    for row in records:
        cp = (row.get("checkpoints") or {}).get(horizon)
        if not isinstance(cp, dict):
            continue
        g = _num(cp.get("gross_return_pct"))
        f = _num(cp.get("friction_adjusted_return_pct"))
        if g is not None:
            gross.append(g)
        if f is not None:
            friction.append(f)
    if not gross:
        return {"n": 0}
    return {
        "n": len(gross),
        "mean_gross_return_pct": round(mean(gross), 6),
        "median_gross_return_pct": round(median(gross), 6),
        "mean_friction_adjusted_return_pct": round(mean(friction), 6) if friction else None,
        "median_friction_adjusted_return_pct": round(median(friction), 6) if friction else None,
        "positive_rate_pct": round(sum(x > 0 for x in gross) / len(gross) * 100.0, 4),
        "gain_20_rate_pct": round(sum(x >= 20 for x in gross) / len(gross) * 100.0, 4),
        "gain_100_rate_pct": round(sum(x >= 100 for x in gross) / len(gross) * 100.0, 4),
        "loss_50_rate_pct": round(sum(x <= -50 for x in gross) / len(gross) * 100.0, 4),
    }


def _bootstrap_mean_delta(signal_values: list[float], control_values: list[float], samples: int = 2000) -> dict[str, Any] | None:
    if len(signal_values) < 10 or len(control_values) < 10:
        return None
    rng = random.Random(500)
    deltas = []
    for _ in range(samples):
        s = [signal_values[rng.randrange(len(signal_values))] for _ in signal_values]
        c = [control_values[rng.randrange(len(control_values))] for _ in control_values]
        deltas.append(mean(s) - mean(c))
    deltas.sort()
    lo = deltas[int(0.025 * (len(deltas) - 1))]
    hi = deltas[int(0.975 * (len(deltas) - 1))]
    return {"lower_95_pct": round(lo, 6), "upper_95_pct": round(hi, 6), "samples": samples}


def _values(records: list[dict[str, Any]], horizon: str, field: str) -> list[float]:
    out: list[float] = []
    for row in records:
        cp = (row.get("checkpoints") or {}).get(horizon)
        if isinstance(cp, dict):
            v = _num(cp.get(field))
            if v is not None:
                out.append(v)
    return out


def _proof_status(signal_records: list[dict[str, Any]], control_records: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    sig24 = _values(signal_records, "24h", "friction_adjusted_return_pct")
    ctl24 = _values(control_records, "24h", "friction_adjusted_return_pct")
    sig7 = _values(signal_records, "7d", "friction_adjusted_return_pct")
    ctl7 = _values(control_records, "7d", "friction_adjusted_return_pct")
    ci24 = _bootstrap_mean_delta(sig24, ctl24)
    detail = {
        "signal_n_24h": len(sig24),
        "control_n_24h": len(ctl24),
        "signal_n_7d": len(sig7),
        "control_n_7d": len(ctl7),
        "mean_alpha_24h_pct": round(mean(sig24) - mean(ctl24), 6) if sig24 and ctl24 else None,
        "mean_alpha_7d_pct": round(mean(sig7) - mean(ctl7), 6) if sig7 and ctl7 else None,
        "bootstrap_mean_alpha_24h_ci": ci24,
    }
    if len(sig24) < 20:
        return "COLLECTING_FORWARD_SAMPLE", detail
    if len(ctl24) < 20:
        return "COLLECTING_CONTROL_SAMPLE", detail
    if detail["mean_alpha_24h_pct"] is None or detail["mean_alpha_24h_pct"] <= 0:
        return "NO_FORWARD_ALPHA_YET", detail
    if len(sig24) >= 100 and len(ctl24) >= 100 and len(sig7) >= 30 and len(ctl7) >= 30 and ci24 and ci24["lower_95_pct"] > 0 and (detail["mean_alpha_7d_pct"] or 0) > 0:
        return "ALPHA_PROVEN_FORWARD_V1", detail
    if len(sig24) >= 50 and len(ctl24) >= 50 and ci24 and ci24["lower_95_pct"] > 0:
        return "STRONG_FORWARD_EVIDENCE", detail
    return "EARLY_FORWARD_EVIDENCE", detail


def _supporting_pre_activation(data_dir: Path, activation: datetime) -> dict[str, Any]:
    payload = _load(data_dir / "reawakening-shadow.json", {})
    rows = []
    for row in (payload.get("targets") or []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict):
            continue
        event = _dt(row.get("triggered_at"))
        if event is None or event >= activation:
            continue
        rows.append({
            "chain": row.get("chain"),
            "token": row.get("token"),
            "pair_address": row.get("pair_address") or row.get("entry_pair_address"),
            "triggered_at": row.get("triggered_at"),
            "current_return_pct": row.get("current_return_pct"),
            "peak_return_pct": row.get("peak_return_pct"),
            "formal_proof": False,
        })
    vals = [_num(x.get("current_return_pct")) for x in rows]
    vals = [x for x in vals if x is not None]
    return {
        "classification": "SUPPORTING_ONLY_PRE_ACTIVATION_NOT_FORMAL_PROOF",
        "count": len(rows),
        "positive_current": sum(x > 0 for x in vals),
        "median_current_return_pct": round(median(vals), 6) if vals else None,
        "best_peak_return_pct": max((_num(x.get("peak_return_pct")) for x in rows if _num(x.get("peak_return_pct")) is not None), default=None),
        "rows": rows[:25],
    }


def run(data_dir: str | Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    reference = now or datetime.now(timezone.utc)
    ledger_path = data_dir / LEDGER_PATH.name
    report_path = data_dir / REPORT_PATH.name
    ledger = _load(ledger_path, None)
    if not isinstance(ledger, dict) or ledger.get("mode") != MODE or not _dt(ledger.get("activation_at")):
        ledger = _initial_ledger(reference)
    activation = _dt(ledger["activation_at"]) or reference

    _enroll_signals(ledger, data_dir, activation, reference)
    _enroll_controls(ledger, data_dir, activation, reference)
    _update_observations(ledger, data_dir)
    ledger["updated_at"] = reference.isoformat()

    all_signals = [x for x in ledger.get("signals", {}).values() if isinstance(x, dict)]
    controls = [x for x in ledger.get("controls", {}).values() if isinstance(x, dict)]
    lanes = sorted({str(x.get("lane")) for x in all_signals})
    lane_reports: dict[str, Any] = {}
    for lane in lanes:
        cohort = [x for x in all_signals if x.get("lane") == lane]
        horizons: dict[str, Any] = {}
        for _, label in HORIZONS:
            s = _stats(cohort, label)
            c = _stats(controls, label)
            entry = {"signal": s, "control": c}
            if s.get("n") and c.get("n"):
                entry["alpha_delta_mean_gross_pct"] = round(float(s["mean_gross_return_pct"]) - float(c["mean_gross_return_pct"]), 6)
                entry["alpha_delta_median_gross_pct"] = round(float(s["median_gross_return_pct"]) - float(c["median_gross_return_pct"]), 6)
            horizons[label] = entry
        status, proof_detail = _proof_status(cohort, controls)
        lane_reports[lane] = {
            "formal_signal_count": len(cohort),
            "proof_status": status,
            "proof_detail": proof_detail,
            "horizons": horizons,
        }

    primary = lane_reports.get("PRECURSOR_REAWAKENING") or {"proof_status": "COLLECTING_FORWARD_SAMPLE", "proof_detail": {}}
    report = {
        "version": 1,
        "mode": MODE,
        "updated_at": reference.isoformat(),
        "activation_at": activation.isoformat(),
        "formal_proof_rule": "ONLY EVENTS WHOSE IMMUTABLE EVENT TIME IS AT/AFTER ACTIVATION ARE COUNTED",
        "primary_alpha_hypothesis": "PRECURSOR_REAWAKENING",
        "primary_proof_status": primary.get("proof_status"),
        "formal_signal_count": len(all_signals),
        "formal_control_count": len(controls),
        "lanes": lane_reports,
        "supporting_pre_activation": _supporting_pre_activation(data_dir, activation),
        "proof_thresholds": {
            "early_min_signal_24h": 20,
            "early_min_control_24h": 20,
            "strong_min_signal_24h": 50,
            "strong_min_control_24h": 50,
            "proven_min_signal_24h": 100,
            "proven_min_control_24h": 100,
            "proven_min_signal_7d": 30,
            "proven_min_control_7d": 30,
            "requires_positive_95pct_bootstrap_lower_bound_at_24h": True,
            "requires_positive_7d_mean_alpha": True,
            "round_trip_friction_bps": ROUND_TRIP_FRICTION_BPS,
        },
        "truth_notes": [
            "Pre-activation wins and losses are visible but never counted as formal proof.",
            "Every formal entry is immutable and exact-pair keyed.",
            "Horizon checkpoints are first-observation-after-horizon and are never rewritten.",
            "Returns are reported gross and after a conservative 200 bps round-trip friction haircut.",
            "Rejected-but-tradable candidates form the forward control cohort.",
            "ALPHA_PROVEN_FORWARD_V1 is withheld until minimum sample, control, 24h confidence and 7d persistence rules all pass.",
            "This is research validation, not evidence of guaranteed profit and not real-money execution proof.",
        ],
    }
    _write(ledger_path, ledger)
    _write(report_path, report)
    print(json.dumps({
        "mode": MODE,
        "activation_at": report["activation_at"],
        "primary_proof_status": report["primary_proof_status"],
        "formal_signal_count": report["formal_signal_count"],
        "formal_control_count": report["formal_control_count"],
        "supporting_pre_activation_count": report["supporting_pre_activation"]["count"],
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
