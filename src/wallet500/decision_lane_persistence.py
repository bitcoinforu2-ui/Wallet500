from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
REAL = DATA / "real-alerts.json"
OUT = DATA / "decision-lane-persistence.json"
MODE = "RESEARCH_ONLY_DECISION_LANE_PERSISTENCE_V1"
EVM_CHAINS = {
    "ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "linea", "zksync", "mantle",
    "scroll", "blast",
}
MAX_TRANSITIONS = 1000


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _norm(chain: object, value: object) -> str:
    c = str(chain or "").strip().lower()
    raw = str(value or "").strip()
    return raw.lower() if c in EVM_CHAINS else raw


def _identity(row: dict) -> str:
    chain = str(row.get("chain") or row.get("network") or "").strip().lower()
    token = row.get("token_address") or row.get("token") or row.get("mint")
    pair = row.get("pair_address") or row.get("entry_pair_address") or row.get("dex_pair_address")
    if not chain or not token or not pair:
        return ""
    return f"{chain}|{_norm(chain, token)}|{_norm(chain, pair)}"


def _strong_lane(row: dict) -> bool:
    gates = row.get("readiness_gates") if isinstance(row.get("readiness_gates"), dict) else {}
    if "STRONG_DECISION_LANE" in gates:
        return gates.get("STRONG_DECISION_LANE") is True
    missing = {str(x) for x in row.get("missing_gates") or []}
    blockers = {str(x) for x in row.get("blockers") or []}
    return "STRONG_DECISION_LANE" not in missing and "NO_STRONG_DECISION_LANE" not in blockers


def _current_rows(real: dict) -> list[dict]:
    rows: list[dict] = []
    for field in ("alerts", "verified_watch"):
        value = real.get(field) if isinstance(real, dict) else []
        if isinstance(value, list):
            rows.extend(x for x in value if isinstance(x, dict))
    return rows


def _snapshot(row: dict, observed_at: str) -> dict:
    strong = _strong_lane(row)
    readiness = int(row.get("readiness_passed") or 0)
    total = int(row.get("readiness_total") or 7)
    missing = sorted({str(x) for x in row.get("missing_gates") or [] if x})
    blockers = sorted({str(x) for x in row.get("blockers") or [] if x})
    lanes = sorted({str(x) for x in row.get("source_lanes") or [] if x})
    return {
        "identity_key": _identity(row),
        "observed_at": observed_at,
        "symbol": row.get("symbol"),
        "chain": row.get("chain"),
        "token_address": row.get("token_address"),
        "pair_address": row.get("pair_address"),
        "radar_tier": row.get("radar_tier"),
        "status": row.get("status"),
        "readiness_passed": readiness,
        "readiness_total": total,
        "missing_gates": missing,
        "blockers": blockers,
        "source_lanes": lanes,
        "source_lane_count": int(row.get("source_lane_count") or len(lanes)),
        "signal_score": round(_num(row.get("signal_score")), 4),
        "strong_decision_lane": strong,
        "exact_identity_verified": row.get("exact_identity_verified") is True,
        "exact_pair_verified": row.get("exact_pair_verified") is True,
        "execution_pool_liquidity_usd": _num(row.get("execution_pool_liquidity_usd")),
        "research_only": True,
        "production_effect": False,
        "automatic_buy": False,
    }


def _transition(previous: dict, current: dict) -> dict | None:
    if not previous:
        return None
    added_lanes = sorted(set(current.get("source_lanes") or []) - set(previous.get("source_lanes") or []))
    removed_lanes = sorted(set(previous.get("source_lanes") or []) - set(current.get("source_lanes") or []))
    added_blockers = sorted(set(current.get("blockers") or []) - set(previous.get("blockers") or []))
    removed_blockers = sorted(set(previous.get("blockers") or []) - set(current.get("blockers") or []))
    added_missing = sorted(set(current.get("missing_gates") or []) - set(previous.get("missing_gates") or []))
    removed_missing = sorted(set(previous.get("missing_gates") or []) - set(current.get("missing_gates") or []))
    before = int(previous.get("readiness_passed") or 0)
    after = int(current.get("readiness_passed") or 0)
    score_delta = round(_num(current.get("signal_score")) - _num(previous.get("signal_score")), 4)
    lane_delta = int(current.get("source_lane_count") or 0) - int(previous.get("source_lane_count") or 0)
    strong_changed = previous.get("strong_decision_lane") is not current.get("strong_decision_lane")
    tier_changed = previous.get("radar_tier") != current.get("radar_tier")
    status_changed = previous.get("status") != current.get("status")
    if not any((added_lanes, removed_lanes, added_blockers, removed_blockers, added_missing, removed_missing,
                before != after, score_delta != 0, lane_delta != 0, strong_changed, tier_changed, status_changed)):
        return None

    reason_codes: list[str] = []
    if before == 6 and after == 7:
        reason_codes.append("READINESS_6_TO_7")
    if before == 7 and after == 6:
        reason_codes.append("READINESS_7_TO_6")
    if previous.get("strong_decision_lane") is False and current.get("strong_decision_lane") is True:
        reason_codes.append("STRONG_DECISION_LANE_GAINED")
    if previous.get("strong_decision_lane") is True and current.get("strong_decision_lane") is False:
        reason_codes.append("STRONG_DECISION_LANE_LOST")
    if "NO_STRONG_DECISION_LANE" in added_blockers:
        reason_codes.append("NO_STRONG_DECISION_LANE_BLOCKER_RETURNED")
    if "NO_STRONG_DECISION_LANE" in removed_blockers:
        reason_codes.append("NO_STRONG_DECISION_LANE_BLOCKER_CLEARED")
    if added_lanes:
        reason_codes.append("SOURCE_LANE_ADDED")
    if removed_lanes:
        reason_codes.append("SOURCE_LANE_REMOVED")
    if not reason_codes:
        reason_codes.append("STATE_CHANGED")

    return {
        "identity_key": current.get("identity_key"),
        "symbol": current.get("symbol"),
        "observed_at": current.get("observed_at"),
        "previous_observed_at": previous.get("observed_at"),
        "readiness_before": before,
        "readiness_after": after,
        "strong_lane_before": previous.get("strong_decision_lane") is True,
        "strong_lane_after": current.get("strong_decision_lane") is True,
        "added_source_lanes": added_lanes,
        "removed_source_lanes": removed_lanes,
        "source_lane_count_delta": lane_delta,
        "added_blockers": added_blockers,
        "removed_blockers": removed_blockers,
        "added_missing_gates": added_missing,
        "removed_missing_gates": removed_missing,
        "signal_score_delta": score_delta,
        "radar_tier_before": previous.get("radar_tier"),
        "radar_tier_after": current.get("radar_tier"),
        "reason_codes": reason_codes,
        "research_only": True,
        "production_effect": False,
    }


def build(data_dir: str | Path = DATA, observed_at: str | None = None) -> dict:
    data = Path(data_dir)
    real = _load(data / REAL.name, {})
    previous_payload = _load(data / OUT.name, {})
    now = observed_at or str(real.get("generated_at") or datetime.now(timezone.utc).isoformat())

    previous_candidates = {
        str(x.get("identity_key")): x
        for x in (previous_payload.get("candidates") or [])
        if isinstance(x, dict) and x.get("identity_key")
    }
    previous_ledger = [x for x in (previous_payload.get("transition_ledger") or []) if isinstance(x, dict)]

    candidates: list[dict] = []
    new_transitions: list[dict] = []
    for row in _current_rows(real):
        snap = _snapshot(row, now)
        identity = snap.get("identity_key")
        if not identity:
            continue
        prev = previous_candidates.get(str(identity), {})
        strong = snap.get("strong_decision_lane") is True
        prev_strong = prev.get("strong_decision_lane") is True
        streak = int(prev.get("strong_lane_streak") or 0) + 1 if strong and prev_strong else (1 if strong else 0)
        first_seen = prev.get("strong_lane_first_seen_at") if strong and prev_strong else (now if strong else None)
        last_seen = now if strong else prev.get("strong_lane_last_seen_at")

        readiness = int(snap.get("readiness_passed") or 0)
        total = int(snap.get("readiness_total") or 7)
        only_missing_strong = snap.get("missing_gates") == ["STRONG_DECISION_LANE"]
        if strong and readiness == total:
            shadow_status = "7_OF_7_CONFIRMED" if streak >= 2 else "7_OF_7_TRANSIENT"
        elif not strong and readiness == total - 1 and only_missing_strong:
            shadow_status = "STRONG_LANE_BUILDING"
        else:
            shadow_status = "NO_PERSISTENCE_CLASSIFICATION"

        snap.update({
            "strong_lane_streak": streak,
            "strong_lane_first_seen_at": first_seen,
            "strong_lane_last_seen_at": last_seen,
            "shadow_persistence_status": shadow_status,
            "shadow_confirmation_required_scans": 2,
        })
        change = _transition(prev, snap)
        if change:
            new_transitions.append(change)
        candidates.append(snap)

    candidates.sort(key=lambda x: (
        int(x.get("readiness_passed") or 0),
        int(x.get("strong_lane_streak") or 0),
        int(x.get("source_lane_count") or 0),
        _num(x.get("signal_score")),
    ), reverse=True)

    ledger = (previous_ledger + new_transitions)[-MAX_TRANSITIONS:]
    blocker_stats: dict[str, dict[str, int]] = {}
    for event in ledger:
        for blocker in event.get("added_blockers") or []:
            bucket = blocker_stats.setdefault(str(blocker), {"added": 0, "cleared": 0})
            bucket["added"] += 1
        for blocker in event.get("removed_blockers") or []:
            bucket = blocker_stats.setdefault(str(blocker), {"added": 0, "cleared": 0})
            bucket["cleared"] += 1

    strong_candidates = [x for x in candidates if x.get("strong_decision_lane") is True]
    confirmed = [x for x in candidates if x.get("shadow_persistence_status") == "7_OF_7_CONFIRMED"]
    transient = [x for x in candidates if x.get("shadow_persistence_status") == "7_OF_7_TRANSIENT"]
    building = [x for x in candidates if x.get("shadow_persistence_status") == "STRONG_LANE_BUILDING"]
    strong_losses = sum(1 for x in ledger if "STRONG_DECISION_LANE_LOST" in (x.get("reason_codes") or []))
    strong_gains = sum(1 for x in ledger if "STRONG_DECISION_LANE_GAINED" in (x.get("reason_codes") or []))

    payload = {
        "version": 1,
        "mode": MODE,
        "generated_at": now,
        "source_real_alerts_generated_at": real.get("generated_at") if isinstance(real, dict) else None,
        "production_change": False,
        "candidates": candidates,
        "transition_ledger": ledger,
        "new_transition_count": len(new_transitions),
        "summary": {
            "candidate_count": len(candidates),
            "strong_lane_now": len(strong_candidates),
            "seven_of_seven_transient": len(transient),
            "seven_of_seven_confirmed": len(confirmed),
            "strong_lane_building": len(building),
        },
        "metrics": {
            "alert_churn_strong_lane_losses": strong_losses,
            "strong_lane_gains": strong_gains,
            "strong_lane_net_transitions": strong_gains - strong_losses,
            "confirmation_latency_scans_required": 2,
            "blocker_transition_counts": blocker_stats,
            "false_negative_rate_by_blocker": "PENDING_OUTCOME_MATURITY_NOT_INFERRED",
            "alert_survival": "PENDING_OUTCOME_MATURITY_NOT_INFERRED",
        },
        "research_lifecycle": {
            "allowed_states": ["OBSERVED", "REPEATED", "SHADOW_READY", "SHADOW_TESTING", "PROMOTE", "REJECT"],
            "current_state": "OBSERVED" if len(ledger) < 2 else "REPEATED",
            "automatic_promotion": False,
        },
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "strict_identity_key": "chain|token_address|pair_address",
            "pair_identity_must_not_mix": True,
            "real_alert_gate_changed": False,
            "real_alert_thresholds_weakened": False,
            "telegram_alerts_changed": False,
            "automatic_buy": False,
            "automatic_promotion": False,
            "automatic_weight_mutation": False,
            "shadow_confirmation_does_not_override_production": True,
            "first_7_of_7_is_shadow_transient": True,
            "two_consecutive_strong_scans_is_shadow_confirmed": True,
        },
    }
    _write(data / OUT.name, payload)
    return payload


def main() -> None:
    payload = build()
    print(json.dumps({
        "mode": payload.get("mode"),
        "summary": payload.get("summary"),
        "new_transition_count": payload.get("new_transition_count"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
