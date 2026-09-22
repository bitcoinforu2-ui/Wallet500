from __future__ import annotations

"""Immutable confirmed-reactivation event ledger and sampled outcome tracking.

The active hold state is intentionally ephemeral and may be replaced by a later trigger.
This ledger is the durable learning record: each CONFIRMED_HOLD becomes one immutable
event keyed by asset + trigger timestamp + exact pair. Only the nested outcome section
is updated as fresh exact-pair observations arrive.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_VERSION = 1
HORIZONS_HOURS = (1, 6, 24, 72)
CHECKPOINT_TOLERANCE_HOURS = {1: 0.5, 6: 1.0, 24: 3.0, 72: 6.0}


def _parse_ts(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def empty_ledger() -> dict:
    return {
        "version": LEDGER_VERSION,
        "updated_at": None,
        "events": {},
        "truth_contract": {
            "confirmed_hold_events_immutable": True,
            "event_identity": "canonical_asset+triggered_at+exact_pair",
            "outcomes_are_sampled_not_tick_complete": True,
            "outcome_horizons_hours": list(HORIZONS_HOURS),
            "outcome_checkpoint_tolerance_hours": dict(CHECKPOINT_TOLERANCE_HOURS),
            "outcome_reference_price": "hold_confirmation_exact_pair_price",
        },
    }


def load_ledger(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    ledger = empty_ledger()
    events = payload.get("events") if isinstance(payload.get("events"), dict) else {}
    ledger["events"] = dict(events)
    ledger["updated_at"] = payload.get("updated_at")
    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    ledger["truth_contract"].update(truth)
    return ledger


def event_id(asset_key: str, triggered_at: object, pair_address: object) -> str:
    raw = f"{asset_key}|{str(triggered_at or '').strip()}|{str(pair_address or '').strip().lower()}"
    return "RH-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def build_confirmed_event(
    *,
    asset_key: str,
    entry: dict,
    metrics: dict,
    snapshot: dict,
    confirmed_at: datetime,
) -> dict:
    confirmed_dt = _utc(confirmed_at)
    triggered_at = str(entry.get("triggered_at") or "").strip()
    pair = str(snapshot.get("pair_address") or entry.get("pair_address") or "").strip()
    confirmation_price = float(snapshot.get("price_usd") or 0.0)
    trigger_price = float(entry.get("trigger_price_usd") or 0.0)
    eid = event_id(asset_key, triggered_at, pair)
    horizons = {
        f"{hours}h": {
            "target_hours": hours,
            "closed": False,
            "checkpoint_status": "PENDING",
            "sampled_mfe_pct": 0.0,
            "sampled_mae_pct": 0.0,
            "checkpoint_observed_at": None,
            "checkpoint_age_hours": None,
            "checkpoint_price_usd": None,
            "checkpoint_return_pct": None,
        }
        for hours in HORIZONS_HOURS
    }
    return {
        "event_id": eid,
        "status": "CONFIRMED_HOLD",
        "asset_key": asset_key,
        "chain": entry.get("chain"),
        "token_address": entry.get("token_address"),
        "symbol": entry.get("symbol") or metrics.get("symbol"),
        "pair_address": pair,
        "triggered_at": triggered_at,
        "trigger_price_usd": trigger_price,
        "confirmed_at": confirmed_dt.isoformat(),
        "confirmation_price_usd": confirmation_price,
        "hold_age_minutes": metrics.get("reactivation_hold_age_minutes"),
        "trigger_exchanges": list(entry.get("trigger_exchanges") or []),
        "confirmation_exchanges": list(metrics.get("fresh_reactivation_exchanges") or []),
        "confirmation_exact_pair_liquidity_usd": float(snapshot.get("liquidity_usd") or 0.0),
        "confirmation_cex_reference_price_usd": float(metrics.get("current_price") or 0.0),
        "signal_score": int(float(metrics.get("signal_score") or 0)),
        "signal_price_usd": float(metrics.get("signal_price") or 0.0),
        "signal_at": metrics.get("signal_at"),
        "signal_milestone": metrics.get("signal_milestone"),
        "since_discovery_pct": metrics.get("since_discovery_pct"),
        "change_since_trigger_pct": (
            round(((confirmation_price / trigger_price) - 1.0) * 100.0, 4)
            if trigger_price > 0 and confirmation_price > 0
            else None
        ),
        "outcome": {
            "reference_price_usd": confirmation_price,
            "latest_observed_at": confirmed_dt.isoformat(),
            "latest_price_usd": confirmation_price,
            "latest_return_pct": 0.0,
            "sample_count": 1,
            "sampled_mfe_pct": 0.0,
            "sampled_mae_pct": 0.0,
            "horizons": horizons,
        },
    }


def record_confirmed_event(ledger: dict, event: dict) -> tuple[dict, bool]:
    events = ledger.setdefault("events", {})
    eid = str(event.get("event_id") or "")
    if not eid:
        raise ValueError("event_id required")
    if eid in events:
        return events[eid], False
    events[eid] = event
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
    return events[eid], True


def observe_event(event: dict, *, observed_at: datetime, price_usd: float) -> dict:
    price = float(price_usd or 0.0)
    if price <= 0:
        return event
    confirmed = _parse_ts(event.get("confirmed_at"))
    if confirmed is None:
        return event
    now = _utc(observed_at)
    if now < confirmed:
        return event

    outcome = event.setdefault("outcome", {})
    reference = float(outcome.get("reference_price_usd") or event.get("confirmation_price_usd") or 0.0)
    if reference <= 0:
        return event

    age_hours = (now - confirmed).total_seconds() / 3600.0
    ret = ((price / reference) - 1.0) * 100.0
    outcome["latest_observed_at"] = now.isoformat()
    outcome["latest_price_usd"] = price
    outcome["latest_return_pct"] = round(ret, 4)
    outcome["sample_count"] = int(outcome.get("sample_count") or 0) + 1
    outcome["sampled_mfe_pct"] = round(max(float(outcome.get("sampled_mfe_pct") or 0.0), ret), 4)
    outcome["sampled_mae_pct"] = round(min(float(outcome.get("sampled_mae_pct") or 0.0), ret), 4)

    horizons = outcome.setdefault("horizons", {})
    for hours in HORIZONS_HOURS:
        key = f"{hours}h"
        h = horizons.setdefault(key, {
            "target_hours": hours,
            "closed": False,
            "checkpoint_status": "PENDING",
            "sampled_mfe_pct": 0.0,
            "sampled_mae_pct": 0.0,
            "checkpoint_observed_at": None,
            "checkpoint_age_hours": None,
            "checkpoint_price_usd": None,
            "checkpoint_return_pct": None,
        })
        if h.get("closed") is True:
            continue
        h["sampled_mfe_pct"] = round(max(float(h.get("sampled_mfe_pct") or 0.0), ret), 4)
        h["sampled_mae_pct"] = round(min(float(h.get("sampled_mae_pct") or 0.0), ret), 4)
        if age_hours >= hours:
            tolerance = float(CHECKPOINT_TOLERANCE_HOURS[hours])
            if age_hours <= hours + tolerance:
                h.update({
                    "closed": True,
                    "checkpoint_status": "CAPTURED",
                    "checkpoint_observed_at": now.isoformat(),
                    "checkpoint_age_hours": round(age_hours, 4),
                    "checkpoint_price_usd": price,
                    "checkpoint_return_pct": round(ret, 4),
                })
            else:
                h.update({
                    "closed": True,
                    "checkpoint_status": "MISSED_NO_TIMELY_SAMPLE",
                    "checkpoint_observed_at": None,
                    "checkpoint_age_hours": None,
                    "checkpoint_price_usd": None,
                    "checkpoint_return_pct": None,
                    "missed_detected_at": now.isoformat(),
                    "first_late_sample_age_hours": round(age_hours, 4),
                })
    return event


def event_needs_refresh(event: dict) -> bool:
    outcome = event.get("outcome") if isinstance(event.get("outcome"), dict) else {}
    horizons = outcome.get("horizons") if isinstance(outcome.get("horizons"), dict) else {}
    return any(
        not isinstance(horizons.get(f"{hours}h"), dict)
        or horizons[f"{hours}h"].get("closed") is not True
        for hours in HORIZONS_HOURS
    )


def ledger_summary(ledger: dict) -> dict:
    events = [x for x in (ledger.get("events") or {}).values() if isinstance(x, dict)]
    completed_72h = 0
    positive_72h = 0
    for event in events:
        outcome = event.get("outcome") if isinstance(event.get("outcome"), dict) else {}
        h = (outcome.get("horizons") or {}).get("72h") if isinstance(outcome.get("horizons"), dict) else None
        if isinstance(h, dict) and h.get("closed") is True:
            completed_72h += 1
            if float(h.get("checkpoint_return_pct") or 0.0) > 0:
                positive_72h += 1
    return {
        "confirmed_events": len(events),
        "open_outcome_events": sum(1 for x in events if event_needs_refresh(x)),
        "completed_72h_events": completed_72h,
        "positive_72h_events": positive_72h,
    }
