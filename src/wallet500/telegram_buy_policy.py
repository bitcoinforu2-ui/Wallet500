from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

MAX_DECISION_AGE_SECONDS = 35 * 60
EVM_CHAINS = {
    "ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast",
}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def _parse_dt(value: object) -> datetime | None:
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


def _chain(value: object) -> str:
    raw = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(raw, raw)


def _norm(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM_CHAINS else raw


def exact_key(row: object) -> str:
    if not isinstance(row, dict):
        return ""
    chain = _chain(row.get("chain") or row.get("network"))
    token = _norm(chain, row.get("token_address") or row.get("token") or row.get("mint"))
    pair = _norm(chain, row.get("pair_address") or row.get("locked_pair_address"))
    if chain and token and pair:
        return f"{chain}:{token}:{pair}"

    raw_key = str(row.get("key") or "").strip()
    parts = raw_key.split(":", 2)
    if len(parts) != 3:
        return ""
    chain = _chain(parts[0])
    token = _norm(chain, parts[1])
    pair = _norm(chain, parts[2])
    return f"{chain}:{token}:{pair}" if chain and token and pair else ""


def _decision_snapshot_status(payload: object, now: datetime) -> tuple[bool, str, float | None]:
    if not isinstance(payload, dict):
        return False, "DECISION_SNAPSHOT_MISSING", None
    if payload.get("mode") != "SHADOW_DECISION_ONLY_NO_REAL_MONEY_NO_PRODUCTION_GATE_CHANGE":
        return False, "DECISION_MODE_INVALID", None
    if payload.get("production_change") is not False:
        return False, "DECISION_PRODUCTION_CHANGE_DRIFT", None
    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    required = (
        "exact_pair_required",
        "holder_cluster_fail_closed_for_buy",
        "lp_protection_fail_closed_for_buy",
        "executable_exit_depth_fail_closed_for_buy",
    )
    if any(truth.get(name) is not True for name in required):
        return False, "DECISION_TRUTH_CONTRACT_INCOMPLETE", None
    generated = _parse_dt(payload.get("generated_at"))
    if generated is None:
        return False, "DECISION_TIMESTAMP_MISSING", None
    age = (now - generated).total_seconds()
    if age < -120:
        return False, "DECISION_TIMESTAMP_FROM_FUTURE", age
    if age > MAX_DECISION_AGE_SECONDS:
        return False, "DECISION_SNAPSHOT_STALE", age
    return True, "VALID", age


def _buy_decisions(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in payload.get("decisions") or []:
        if not isinstance(row, dict):
            continue
        if row.get("recommended_action") != "BUY" or row.get("state") != "BUY_ZONE":
            continue
        if str(row.get("model_signal") or "") not in {"BUY", "STRONG_BUY"}:
            continue
        if list(row.get("hard_safety_failures") or []):
            continue
        if list(row.get("evidence_gaps") or []):
            continue
        key = exact_key(row)
        if key:
            out[key] = row
    return out


def filter_buy_only_payload(
    real_payload: object,
    decision_payload: object,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a Telegram feed containing only exact-pair final BUY decisions.

    Research, PRE_WAVE, generic REAL_ALERT and review/actionable stages remain in
    the engine data, but they are not user-facing Telegram events in this lane.
    Near-buy and stage-transition alerts are intentionally not user-facing.
    """
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    source = dict(real_payload) if isinstance(real_payload, dict) else {}
    source_alerts = [row for row in source.get("alerts") or [] if isinstance(row, dict)]
    source_pre_wave = [row for row in source.get("pre_wave_alerts") or [] if isinstance(row, dict)]

    valid, status, age_seconds = _decision_snapshot_status(decision_payload, reference)
    decisions = _buy_decisions(decision_payload) if valid and isinstance(decision_payload, dict) else {}

    selected: list[dict] = []
    matched_keys: list[str] = []
    for row in source_alerts:
        key = exact_key(row)
        decision = decisions.get(key)
        if not decision:
            continue
        enriched = dict(row)
        enriched["telegram_buy_decision"] = {
            "recommended_action": "BUY",
            "state": "BUY_ZONE",
            "model_signal": decision.get("model_signal"),
            "scores": decision.get("scores") if isinstance(decision.get("scores"), dict) else {},
        }
        selected.append(enriched)
        matched_keys.append(key)

    source["alerts"] = selected
    source["pre_wave_alerts"] = []
    source["latest_real_alert"] = selected[0] if selected else None
    source["latest_pre_wave_alert"] = None
    counts = dict(source.get("counts") or {})
    counts["telegram_buy_only_alerts"] = len(selected)
    counts["telegram_generic_real_alerts_suppressed"] = max(0, len(source_alerts) - len(selected))
    counts["telegram_pre_wave_alerts_suppressed"] = len(source_pre_wave)
    source["counts"] = counts
    source["telegram_delivery_policy"] = {
        "mode": "BUY_ONLY_V2",
        "this_lane": "BUY_ONLY",
        "near_buy_lane": "DISABLED",
        "generic_real_alert_delivery": False,
        "pre_wave_delivery": False,
        "research_review_delivery": False,
        "final_buy_requires": [
            "fresh Decision Engine V1 snapshot",
            "recommended_action=BUY",
            "state=BUY_ZONE",
            "model_signal in BUY/STRONG_BUY",
            "hard_safety_failures=[]",
            "evidence_gaps=[]",
            "exact chain+token+pair match to canonical REAL_ALERT",
        ],
    }

    audit = {
        "mode": "BUY_ONLY_V2",
        "decision_snapshot_status": status,
        "decision_snapshot_age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "source_real_alert_count": len(source_alerts),
        "source_pre_wave_count": len(source_pre_wave),
        "eligible_buy_decision_count": len(decisions),
        "matched_buy_alert_count": len(selected),
        "suppressed_generic_real_alert_count": max(0, len(source_alerts) - len(selected)),
        "suppressed_pre_wave_count": len(source_pre_wave),
        "matched_keys": matched_keys,
    }
    return source, audit
