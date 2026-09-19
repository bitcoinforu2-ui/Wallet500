from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
LEDGER = DATA / "research-sample-ledger.json"
REPORT = DATA / "research-sample-report.json"
REAL = DATA / "real-alerts.json"
OUT = DATA / "candidate-lifecycle.json"
MODE = "RESEARCH_ONLY_CANDIDATE_LIFECYCLE_V1"
EVM_CHAINS = {"ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon"}
CONFIRMATION_ONLY_BLOCKERS = {"NO_STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION_LT_2"}
CONFIRMATION_ONLY_GATES = {"STRONG_DECISION_LANE", "INDEPENDENT_CONFIRMATION"}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm(chain: object, value: object) -> str:
    c = str(chain or "").strip().lower()
    raw = str(value or "").strip()
    return raw.lower() if c in EVM_CHAINS else raw


def _key(chain: object, token: object, pair: object) -> str:
    c = str(chain or "").strip().lower()
    return f"{c}|{_norm(c, token)}|{_norm(c, pair)}" if c and token and pair else ""


def _rows(payload: dict, field: str) -> list[dict]:
    value = payload.get(field) if isinstance(payload, dict) else []
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _row_key(row: dict) -> str:
    return _key(
        row.get("chain") or row.get("network"),
        row.get("token_address") or row.get("token") or row.get("mint"),
        row.get("pair_address") or row.get("entry_pair_address") or row.get("dex_pair_address"),
    )


def _entry(rec: dict) -> dict:
    decision = rec.get("decision_snapshot") if isinstance(rec.get("decision_snapshot"), dict) else {}
    value = decision.get("entry") if isinstance(decision.get("entry"), dict) else {}
    return value


def _confirmation_loss_only(row: dict) -> bool:
    blockers = {str(x) for x in (row.get("blockers") or []) if x}
    missing = {str(x) for x in (row.get("missing_gates") or []) if x}
    if not blockers or not missing:
        return False
    return blockers <= CONFIRMATION_ONLY_BLOCKERS and missing <= CONFIRMATION_ONLY_GATES


def _reason_for_live(row: dict, entry: dict, previous_state: str | None = None) -> tuple[str, str]:
    readiness = int(row.get("readiness_passed") or 0)
    total = int(row.get("readiness_total") or 7)
    blockers = {str(x) for x in (row.get("blockers") or []) if x}
    missing = [str(x) for x in (row.get("missing_gates") or []) if x]

    if row.get("exact_pair_verified") is False:
        return "LIVE_REGRESSED", "PAIR_CONFLICT_OR_UNVERIFIED"
    if any("LIQUIDITY" in x or "EXECUTION_DEPTH" in x for x in blockers):
        return "LIVE_REGRESSED", "FAILED_OR_UNVERIFIED_LIQUIDITY"

    entry_readiness = int(entry.get("readiness_passed") or 0)
    was_real_alert = previous_state == "PROMOTED" or (entry_readiness >= 7 and int(entry.get("readiness_total") or 7) == 7)
    if was_real_alert and _confirmation_loss_only(row):
        return "LIVE_CONFIRMATION_LOST", "CONFIRMATION_REVALIDATION_REQUIRED"

    if readiness == 6 and total == 7:
        return "LIVE_6_OF_7", "DECISION_BLOCKED"
    if readiness < int(entry.get("readiness_passed") or readiness):
        return "LIVE_REGRESSED", "LOST_MOMENTUM_OR_GATE_REGRESSION"
    if "NO_STRONG_DECISION_LANE" in blockers or missing == ["STRONG_DECISION_LANE"]:
        return "LIVE_VERIFIED_WATCH", "DECISION_BLOCKED"
    return "LIVE_VERIFIED_WATCH", "PENDING_CONFIRMATION"


def _outcome(rec: dict) -> dict:
    checkpoints = rec.get("checkpoints") if isinstance(rec.get("checkpoints"), dict) else {}
    preferred = None
    for label in ("7d", "24h", "6h", "1h"):
        cp = checkpoints.get(label)
        if isinstance(cp, dict):
            preferred = (label, cp)
            break
    if preferred is None:
        return {"status": "IMMATURE", "horizon": None, "friction_adjusted_return_pct": None}
    label, cp = preferred
    value = cp.get("friction_adjusted_return_pct")
    try:
        ret = float(value)
    except (TypeError, ValueError):
        ret = None
    if ret is None:
        status = "IMMATURE"
    elif ret >= 100:
        status = "BIG_WINNER"
    elif ret >= 20:
        status = "WINNER"
    elif ret <= -20:
        status = "LOSER"
    else:
        status = "NEUTRAL"
    return {"status": status, "horizon": label, "friction_adjusted_return_pct": ret}


def build(data_dir: str | Path = DATA, observed_at: str | None = None) -> dict:
    data = Path(data_dir)
    now = observed_at or datetime.now(timezone.utc).isoformat()
    ledger = _load(data / LEDGER.name, {})
    report = _load(data / REPORT.name, {})
    real = _load(data / REAL.name, {})
    previous = _load(data / OUT.name, {})

    watch_by_key = {_row_key(row): row for row in _rows(real, "verified_watch") if _row_key(row)}
    alert_by_key = {_row_key(row): row for row in _rows(real, "alerts") if _row_key(row)}
    previous_by_identity = {
        str(row.get("identity_key")): row
        for row in _rows(previous, "candidates")
        if row.get("identity_key")
    }
    records = ledger.get("records") if isinstance(ledger, dict) and isinstance(ledger.get("records"), dict) else {}

    items: list[dict] = []
    counts: dict[str, int] = {}
    for rec_key, rec in records.items():
        if not isinstance(rec, dict):
            continue
        chain = rec.get("chain")
        token = rec.get("token_address")
        pair = rec.get("pair_address")
        identity = _key(chain, token, pair)
        if not identity:
            continue
        entry = _entry(rec)
        previous_row = previous_by_identity.get(identity) or {}
        previous_state = str(previous_row.get("lifecycle_state") or "") or None
        alert = alert_by_key.get(identity)
        watch = watch_by_key.get(identity)
        if isinstance(alert, dict):
            lifecycle_state = "PROMOTED"
            reason_code = "PROMOTED_REAL_ALERT"
            current = alert
        elif isinstance(watch, dict):
            lifecycle_state, reason_code = _reason_for_live(watch, entry, previous_state)
            current = watch
        else:
            lifecycle_state = "SHADOW_LEARNING"
            reason_code = "LEFT_LIVE_RADAR_AFTER_PROMOTION" if previous_state == "PROMOTED" else "LEFT_LIVE_RADAR"
            current = {}

        outcome = _outcome(rec)
        missing_at_entry = [str(x) for x in (entry.get("missing_gates") or []) if x]
        current_lanes = list(current.get("source_lanes") or []) if current else []
        previous_lanes = list(previous_row.get("current_source_lanes") or previous_row.get("source_lanes") or [])
        lost_lanes = sorted(set(previous_lanes) - set(current_lanes)) if previous_lanes else []
        transition = None
        if previous_state and previous_state != lifecycle_state:
            transition = f"{previous_state}->{lifecycle_state}"

        item = {
            "record_key": rec_key,
            "identity_key": identity,
            "chain": chain,
            "symbol": current.get("symbol") or rec.get("symbol") or entry.get("symbol"),
            "token_address": token,
            "pair_address": pair,
            "event_at": rec.get("event_at"),
            "enrolled_at": rec.get("enrolled_at"),
            "entry_readiness": f"{int(entry.get('readiness_passed') or 0)}/{int(entry.get('readiness_total') or 7)}",
            "entry_missing_gates": missing_at_entry,
            "entry_price_usd": rec.get("entry_price_usd"),
            "entry_verified_execution_liquidity_usd": entry.get("verified_execution_liquidity_usd"),
            "previous_lifecycle_state": previous_state,
            "lifecycle_state": lifecycle_state,
            "reason_code": reason_code,
            "transition": transition,
            "current_readiness": (
                f"{int(current.get('readiness_passed') or 0)}/{int(current.get('readiness_total') or 7)}"
                if current else None
            ),
            "current_missing_gates": list(current.get("missing_gates") or []) if current else [],
            "current_blockers": list(current.get("blockers") or []) if current else [],
            "current_source_lanes": current_lanes,
            "previous_source_lanes": previous_lanes,
            "lost_source_lanes": lost_lanes,
            "confirmation_revalidation_required": lifecycle_state == "LIVE_CONFIRMATION_LOST",
            "latest_observed_at": rec.get("latest_observed_at"),
            "latest_return_pct": rec.get("latest_return_pct"),
            "latest_friction_adjusted_return_pct": rec.get("latest_friction_adjusted_return_pct"),
            "checkpoints": rec.get("checkpoints") if isinstance(rec.get("checkpoints"), dict) else {},
            "outcome": outcome,
            "research_only": True,
            "actionable": False,
            "automatic_buy": False,
        }
        items.append(item)
        counts[lifecycle_state] = counts.get(lifecycle_state, 0) + 1

    priority = {
        "PROMOTED": 6,
        "LIVE_CONFIRMATION_LOST": 5,
        "LIVE_6_OF_7": 4,
        "LIVE_REGRESSED": 3,
        "LIVE_VERIFIED_WATCH": 2,
        "SHADOW_LEARNING": 1,
    }
    items.sort(key=lambda x: (priority.get(str(x.get("lifecycle_state")), 0), str(x.get("event_at") or "")), reverse=True)

    payload = {
        "version": 2,
        "mode": MODE,
        "generated_at": now,
        "source_ledger_updated_at": ledger.get("updated_at") if isinstance(ledger, dict) else None,
        "source_real_alerts_generated_at": real.get("generated_at") if isinstance(real, dict) else None,
        "candidate_count": len(items),
        "counts": counts,
        "candidates": items,
        "learning_feedback": {
            "gate_attribution_24h": report.get("gate_attribution_24h") if isinstance(report, dict) else [],
            "learning_review_queue": report.get("learning_review_queue") if isinstance(report, dict) else [],
            "sample_acceleration": report.get("sample_acceleration") if isinstance(report, dict) else {},
            "source": "research-sample-report.json",
            "automatic_weight_mutation": False,
        },
        "truth_contract": {
            "candidate_never_disappears_when_it_leaves_live_radar": True,
            "persistent_source": "research-sample-ledger.json",
            "live_state_source": "real-alerts.json",
            "shadow_outcomes_source": "research-sample-ledger.json checkpoints",
            "confirmation_loss_state_is_non_actionable": True,
            "confirmation_loss_does_not_preserve_real_alert": True,
            "confirmation_loss_requires_current_hard_truth_to_survive": True,
            "confirmation_loss_only_for_decision_confirmation_gates": sorted(CONFIRMATION_ONLY_GATES),
            "reason_codes_are_explanatory_not_trade_signals": True,
            "production_effect": False,
            "automatic_buy": False,
            "automatic_weight_mutation": False,
        },
    }
    _write(data / OUT.name, payload)
    return payload


def main() -> None:
    payload = build()
    print(json.dumps({
        "mode": payload.get("mode"),
        "candidate_count": payload.get("candidate_count"),
        "counts": payload.get("counts"),
        "learning_review_queue": len((payload.get("learning_feedback") or {}).get("learning_review_queue") or []),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
