from __future__ import annotations

"""Second-observation hold gate for stale-signal CEX reactivations.

A stale discovery may still become interesting when several CEX venues reactivate at
once, but the first reactivation tick is not enough to call the move confirmed. This
module wraps the existing guarded CEX action lane and requires a fresh exact-pair
follow-up observation 5-20 minutes later. Telegram remains action-only: pending or
faded reactivations are persisted for audit/reporting but are never promoted as a
REAL_ALERT.
"""

import json
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIN_HOLD_MINUTES = 5.0
MAX_HOLD_MINUTES = 20.0
STATE_VERSION = 1
REPORT_FILE = "cex-fast-promotion-report.json"
ALERT_FILE = "cex-fast-real-alerts.json"
EVM_CHAINS = {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche"}


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


def _addr(chain: str, value: object) -> str:
    text = str(value or "").strip()
    return text.lower() if chain in EVM_CHAINS else text


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def evaluate_hold(
    previous: dict | None,
    *,
    now: datetime,
    pair_address: str,
    current_pair_price: float,
) -> dict:
    """Pure point-in-time hold decision used by production and tests.

    The original trigger price/time stay immutable while the same pair remains inside
    the confirmation window. A follow-up below the trigger becomes FADE and requires
    a reclaim. A stale window or pair change starts a new trigger instead of borrowing
    confirmation from old evidence.
    """
    now_dt = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    pair = str(pair_address or "").strip()
    price = float(current_pair_price or 0.0)
    if not pair or price <= 0:
        return {
            "state": "MISSING_EXACT_PAIR_PRICE",
            "confirmed": False,
            "entry": dict(previous or {}),
            "hold_age_minutes": None,
            "change_since_trigger_pct": None,
        }

    prev = dict(previous or {})
    triggered = _parse_ts(prev.get("triggered_at"))
    same_pair = str(prev.get("pair_address") or "").strip() == pair
    age_minutes = (
        (now_dt - triggered).total_seconds() / 60.0
        if triggered is not None and same_pair
        else None
    )

    reset = (
        triggered is None
        or not same_pair
        or age_minutes is None
        or age_minutes < -1.0
        or age_minutes > MAX_HOLD_MINUTES
    )
    if reset:
        entry = {
            "triggered_at": now_dt.isoformat(),
            "pair_address": pair,
            "trigger_price_usd": price,
            "last_checked_at": now_dt.isoformat(),
            "last_pair_price_usd": price,
            "last_state": "PENDING_HOLD",
        }
        return {
            "state": "PENDING_HOLD",
            "confirmed": False,
            "entry": entry,
            "hold_age_minutes": 0.0,
            "change_since_trigger_pct": 0.0,
        }

    trigger_price = float(prev.get("trigger_price_usd") or 0.0)
    if trigger_price <= 0:
        entry = {
            "triggered_at": now_dt.isoformat(),
            "pair_address": pair,
            "trigger_price_usd": price,
            "last_checked_at": now_dt.isoformat(),
            "last_pair_price_usd": price,
            "last_state": "PENDING_HOLD",
        }
        return {
            "state": "PENDING_HOLD",
            "confirmed": False,
            "entry": entry,
            "hold_age_minutes": 0.0,
            "change_since_trigger_pct": 0.0,
        }

    delta = ((price / trigger_price) - 1.0) * 100.0
    entry = dict(prev)
    entry.update({
        "last_checked_at": now_dt.isoformat(),
        "last_pair_price_usd": price,
        "hold_age_minutes": round(age_minutes, 3),
        "change_since_trigger_pct": round(delta, 4),
    })

    if age_minutes < MIN_HOLD_MINUTES:
        state = "PENDING_HOLD"
        confirmed = False
    elif price < trigger_price:
        state = "FADE_RECLAIM_REQUIRED"
        confirmed = False
    else:
        state = "CONFIRMED_HOLD"
        confirmed = True
        entry["confirmed_at"] = now_dt.isoformat()

    entry["last_state"] = state
    return {
        "state": state,
        "confirmed": confirmed,
        "entry": entry,
        "hold_age_minutes": round(age_minutes, 3),
        "change_since_trigger_pct": round(delta, 4),
    }


class ReactivationHoldGate:
    def __init__(self, guard: Any):
        self.guard = guard
        self.out = Path(os.getenv("WALLET500_OUTPUT_DIR", "data"))
        self.original_eligibility = guard.promo._eligibility
        self.original_message = guard.promo._message
        self.state = self._load_state()

    def _load_state(self) -> dict:
        path = self.out / REPORT_FILE
        try:
            payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            payload = {}
        state = payload.get("reactivation_hold_state") if isinstance(payload, dict) else None
        if not isinstance(state, dict):
            state = {}
        assets = state.get("assets") if isinstance(state.get("assets"), dict) else {}
        return {
            "version": STATE_VERSION,
            "updated_at": state.get("updated_at"),
            "assets": dict(assets),
        }

    def _fresh_exact_pair_snapshot(self, row: dict) -> dict | None:
        chain = str(row.get("chain") or "").lower().strip()
        token = _addr(chain, row.get("token_address"))
        pair = _addr(chain, row.get("pair_address"))
        if not chain or not token or not pair:
            return None
        url = (
            "https://api.dexscreener.com/latest/dex/pairs/"
            + urllib.parse.quote(chain, safe="")
            + "/"
            + urllib.parse.quote(str(row.get("pair_address") or "").strip(), safe="")
        )
        try:
            payload = self.guard.promo._get(url, timeout=8)
        except Exception:
            return None
        pairs = (payload or {}).get("pairs") if isinstance(payload, dict) else None
        if not isinstance(pairs, list):
            return None
        for item in pairs:
            if not isinstance(item, dict):
                continue
            item_chain = str(item.get("chainId") or "").lower().strip()
            item_pair = _addr(chain, item.get("pairAddress"))
            base = item.get("baseToken") if isinstance(item.get("baseToken"), dict) else {}
            item_token = _addr(chain, base.get("address"))
            price = float(item.get("priceUsd") or 0.0)
            if item_chain != chain or item_pair != pair or item_token != token or price <= 0:
                continue
            return {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "price_usd": price,
                "liquidity_usd": float(((item.get("liquidity") or {}).get("usd")) or 0.0),
                "pair_address": str(item.get("pairAddress") or ""),
                "source": "DEXSCREENER_EXACT_PAIR_FRESH_VALIDATION",
            }
        return None

    def eligibility(self, row: object):
        ok, metrics = self.original_eligibility(row)
        if not isinstance(row, dict):
            return ok, metrics

        # Fresh discoveries keep their existing BUY_ZONE behavior. Only a stale
        # discovery revived by current multi-CEX evidence needs the second observation.
        if not ok or str(metrics.get("action_state") or "") != "REENTRY_ZONE":
            return ok, metrics

        key = self.guard.canonical_key(row)
        snapshot = self._fresh_exact_pair_snapshot(row)
        if snapshot is None:
            blockers = sorted(set(list(metrics.get("blockers") or []) + ["REACTIVATION_EXACT_PAIR_PRICE_UNAVAILABLE"]))
            metrics.update({
                "action_state": "REACTIVATION_PENDING",
                "action_basis": "FRESH_MULTI_CEX_REACTIVATION_AWAITING_EXACT_PAIR_VALIDATION",
                "reactivation_hold_state": "MISSING_EXACT_PAIR_PRICE",
                "reactivation_hold_verified": False,
                "runner_candidate": False,
                "blockers": blockers,
            })
            return False, metrics

        now_dt = datetime.now(timezone.utc)
        previous = self.state["assets"].get(key)
        decision = evaluate_hold(
            previous if isinstance(previous, dict) else None,
            now=now_dt,
            pair_address=str(snapshot.get("pair_address") or row.get("pair_address") or ""),
            current_pair_price=float(snapshot.get("price_usd") or 0.0),
        )
        entry = decision["entry"]
        entry.update({
            "chain": row.get("chain"),
            "token_address": row.get("token_address"),
            "symbol": metrics.get("symbol") or row.get("symbol"),
            "trigger_exchanges": (
                entry.get("trigger_exchanges")
                or list(metrics.get("fresh_reactivation_exchanges") or [])
            ),
            "last_exchanges": list(metrics.get("fresh_reactivation_exchanges") or []),
            "last_cex_reference_price_usd": float(metrics.get("current_price") or 0.0),
            "last_exact_pair_source": snapshot.get("source"),
            "last_exact_pair_liquidity_usd": float(snapshot.get("liquidity_usd") or 0.0),
        })
        self.state["assets"][key] = entry
        self.state["updated_at"] = now_dt.isoformat()

        metrics.update({
            "reactivation_hold_state": decision["state"],
            "reactivation_hold_verified": bool(decision["confirmed"]),
            "reactivation_triggered_at": entry.get("triggered_at"),
            "reactivation_trigger_pair_price_usd": float(entry.get("trigger_price_usd") or 0.0),
            "reactivation_validation_pair_price_usd": float(snapshot.get("price_usd") or 0.0),
            "reactivation_hold_age_minutes": decision.get("hold_age_minutes"),
            "reactivation_change_since_trigger_pct": decision.get("change_since_trigger_pct"),
            "reactivation_confirmation_min_minutes": MIN_HOLD_MINUTES,
            "reactivation_confirmation_max_minutes": MAX_HOLD_MINUTES,
            "reactivation_exact_pair_source": snapshot.get("source"),
            "runner_candidate": bool(decision["confirmed"]),
        })

        if decision["confirmed"]:
            metrics["action_state"] = "REENTRY_ZONE"
            metrics["action_basis"] = "FRESH_MULTI_CEX_REACTIVATION_HOLD_VERIFIED"
            metrics["blockers"] = []
            return True, metrics

        blocker = (
            "REACTIVATION_RECLAIM_REQUIRED"
            if decision["state"] == "FADE_RECLAIM_REQUIRED"
            else "REACTIVATION_HOLD_PENDING"
        )
        metrics["blockers"] = sorted(set(list(metrics.get("blockers") or []) + [blocker]))
        metrics["action_state"] = (
            "REACTIVATION_FADE"
            if decision["state"] == "FADE_RECLAIM_REQUIRED"
            else "REACTIVATION_PENDING"
        )
        metrics["action_basis"] = (
            "FRESH_MULTI_CEX_REACTIVATION_RECLAIM_REQUIRED"
            if decision["state"] == "FADE_RECLAIM_REQUIRED"
            else "FRESH_MULTI_CEX_REACTIVATION_AWAITING_HOLD"
        )
        return False, metrics

    def message(self, row: dict, metrics: dict, now: str, event_id: str) -> str:
        text = self.original_message(row, metrics, now, event_id)
        if metrics.get("reactivation_hold_verified") is not True:
            return text
        trigger_price = float(metrics.get("reactivation_trigger_pair_price_usd") or 0.0)
        validation_price = float(metrics.get("reactivation_validation_pair_price_usd") or 0.0)
        delta = float(metrics.get("reactivation_change_since_trigger_pct") or 0.0)
        age = float(metrics.get("reactivation_hold_age_minutes") or 0.0)
        extra = [
            "🏃 RUNNER CANDIDATE — REACTIVATION HOLD VERIFIED ✅",
            "🧭 Reactivation state: CONFIRMED_HOLD ✅",
            f"🕒 Reactivation trigger time: {metrics.get('reactivation_triggered_at')}",
            f"🎯 Reactivation trigger exact-pair price: {self.guard.promo._fmt_price(trigger_price)}",
            f"📍 Hold-validation exact-pair price: {self.guard.promo._fmt_price(validation_price)}",
            f"📈 Since reactivation trigger: {delta:+.2f}%",
            f"⏱ Hold validation: {age:.1f}m · required {MIN_HOLD_MINUTES:.0f}-{MAX_HOLD_MINUTES:.0f}m",
        ]
        lines = text.splitlines()
        return "\n".join([lines[0], *extra, *lines[1:]]) if lines else "\n".join(extra)

    def persist(self) -> None:
        # Prune very old state while preserving active audit evidence long enough to
        # diagnose false positives/negatives without allowing it to satisfy new holds.
        now = datetime.now(timezone.utc)
        kept: dict[str, dict] = {}
        for key, entry in self.state.get("assets", {}).items():
            if not isinstance(entry, dict):
                continue
            last = _parse_ts(entry.get("last_checked_at") or entry.get("triggered_at"))
            if last is not None and (now - last).total_seconds() <= 7 * 86400:
                kept[key] = entry
        self.state["assets"] = kept
        self.state["updated_at"] = now.isoformat()

        report_path = self.out / REPORT_FILE
        try:
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        except Exception:
            report = {}
        if not isinstance(report, dict):
            report = {}
        report["reactivation_hold_state"] = self.state
        report["reactivation_hold_summary"] = {
            "tracked_assets": len(kept),
            "pending": sum(1 for x in kept.values() if x.get("last_state") == "PENDING_HOLD"),
            "fade_reclaim_required": sum(1 for x in kept.values() if x.get("last_state") == "FADE_RECLAIM_REQUIRED"),
            "confirmed": sum(1 for x in kept.values() if x.get("last_state") == "CONFIRMED_HOLD"),
        }
        truth = report.get("truth_contract") if isinstance(report.get("truth_contract"), dict) else {}
        truth.update({
            "stale_reactivation_requires_second_fresh_observation": True,
            "reactivation_exact_pair_hold_required": True,
            "reactivation_confirmation_min_minutes": MIN_HOLD_MINUTES,
            "reactivation_confirmation_max_minutes": MAX_HOLD_MINUTES,
            "reactivation_fade_never_real_alert": True,
            "runner_candidate_requires_hold_verified": True,
        })
        report["truth_contract"] = truth
        _atomic_json_write(report_path, report)

        alert_path = self.out / ALERT_FILE
        try:
            alerts = json.loads(alert_path.read_text(encoding="utf-8")) if alert_path.exists() else {}
        except Exception:
            alerts = {}
        if isinstance(alerts, dict):
            alert_truth = alerts.get("truth_contract") if isinstance(alerts.get("truth_contract"), dict) else {}
            alert_truth.update(truth)
            alerts["truth_contract"] = alert_truth
            _atomic_json_write(alert_path, alerts)


def install(guard: Any) -> ReactivationHoldGate:
    gate = ReactivationHoldGate(guard)
    guard.promo._eligibility = gate.eligibility
    guard.bypass._eligibility = gate.eligibility
    guard.promo._message = gate.message
    guard.bypass._message = gate.message
    return gate
