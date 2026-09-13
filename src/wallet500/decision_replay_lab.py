from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
SOURCE = "research-sample-ledger.json"
LEDGER = "decision-replay-ledger.json"
REPORT = "decision-replay-report.json"
MODE = "RESEARCH_ONLY_DECISION_REPLAY_V1"
HORIZONS = ("15m", "1h", "3h", "6h", "24h", "72h", "7d")
NEUTRAL_WINNER_24H_PCT = 20.0


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _sha(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _identity(row: dict) -> tuple[str, str, str, str] | None:
    snap = row.get("decision_snapshot") if isinstance(row.get("decision_snapshot"), dict) else {}
    ident = snap.get("identity") if isinstance(snap.get("identity"), dict) else {}
    chain = str(row.get("chain") or ident.get("chain") or "").strip().lower()
    token = str(row.get("token_address") or ident.get("token") or "").strip()
    pair = str(row.get("pair_address") or ident.get("pair_address") or "").strip()
    first_at = str(row.get("event_at") or ((snap.get("entry") or {}).get("observed_at")) or "").strip()
    if not (chain and token and pair and first_at):
        return None
    return chain, token, pair, first_at


def _immutable_key(identity: tuple[str, str, str, str]) -> str:
    return "|".join(identity)


def _t0_snapshot(row: dict) -> dict:
    snap = row.get("decision_snapshot") if isinstance(row.get("decision_snapshot"), dict) else {}
    entry = snap.get("entry") if isinstance(snap.get("entry"), dict) else {}
    return {
        "observed_at": entry.get("observed_at") or row.get("event_at"),
        "decision_label": entry.get("radar_tier") or row.get("lane"),
        "status": entry.get("status"),
        "actionable": entry.get("actionable") if "actionable" in entry else None,
        "price_usd": _num(entry.get("entry_price_usd") if entry.get("entry_price_usd") is not None else row.get("entry_price_usd")),
        "exact_pair_liquidity_usd": _num(entry.get("verified_execution_liquidity_usd")),
        "provider_pool_value_informational_only_usd": _num(entry.get("pool_value_informational_only_usd")),
        "volume_h1_usd": _num(entry.get("volume_h1_usd")),
        "volume_h24_usd": _num(entry.get("volume_h24_usd")),
        "turnover": _num(entry.get("turnover")),
        "buy_flow_usd": _num(entry.get("buy_flow_usd")),
        "sell_flow_usd": _num(entry.get("sell_flow_usd")),
        "market_cap_usd": _num(entry.get("market_cap_usd")),
        "fdv_usd": _num(entry.get("fdv_usd")),
        "market_age_days": _num(entry.get("market_age_days")),
        "signal_score": _num(entry.get("signal_score")),
        "readiness_passed": _num(entry.get("readiness_passed")),
        "readiness_total": _num(entry.get("readiness_total")),
        "source_lane_count": _num(entry.get("source_lane_count")),
        "evidence_positive_count": _num(entry.get("evidence_positive_count")),
        "evidence_positive_lanes": list(entry.get("evidence_positive_lanes") or []),
        "missing_gates": list(entry.get("missing_gates") or []),
        "blockers": list(entry.get("blockers") or []),
        "verified_execution_tradable": entry.get("verified_execution_tradable"),
        "coverage": {
            "price": "KNOWN_AT_T0" if (entry.get("entry_price_usd") is not None or row.get("entry_price_usd") is not None) else "INSUFFICIENT_COVERAGE",
            "exact_pair_liquidity": "KNOWN_AT_T0" if entry.get("verified_execution_liquidity_usd") is not None else "INSUFFICIENT_COVERAGE",
            "volume_h1": "KNOWN_AT_T0" if entry.get("volume_h1_usd") is not None else "INSUFFICIENT_COVERAGE",
            "volume_h24": "KNOWN_AT_T0" if entry.get("volume_h24_usd") is not None else "INSUFFICIENT_COVERAGE",
            "wallet_flow": "KNOWN_AT_T0" if entry.get("wallet_flow_verified") is True else "INSUFFICIENT_COVERAGE",
            "holder_growth": "KNOWN_AT_T0" if entry.get("holder_growth_point_in_time_verified") is True else "INSUFFICIENT_COVERAGE",
        },
    }


def _forward_outcomes(row: dict) -> dict:
    checkpoints = row.get("checkpoints") if isinstance(row.get("checkpoints"), dict) else {}
    out: dict[str, Any] = {}
    for horizon in HORIZONS:
        cp = checkpoints.get(horizon)
        if not isinstance(cp, dict):
            out[horizon] = {"status": "NOT_MATURED_OR_INSUFFICIENT_COVERAGE"}
            continue
        out[horizon] = {
            "status": "OBSERVED",
            "captured_at": cp.get("captured_at"),
            "captured_age_minutes": _num(cp.get("captured_age_minutes")),
            "price_usd": _num(cp.get("price_usd")),
            "gross_return_pct": _num(cp.get("gross_return_pct")),
            "friction_adjusted_return_pct": _num(cp.get("friction_adjusted_return_pct")),
            "provider_pool_value_usd": _num(cp.get("provider_pool_value_usd")),
            "source": cp.get("source"),
            "exact_pair_identity_preserved": True,
        }
    return out


def _classification(record: dict) -> str:
    t0 = record.get("t0") or {}
    actionable = t0.get("actionable")
    h24 = (record.get("outcomes") or {}).get("24h") or {}
    ret = _num(h24.get("friction_adjusted_return_pct"))
    if actionable not in (True, False) or ret is None:
        return "INSUFFICIENT_COVERAGE"
    winner = ret >= NEUTRAL_WINNER_24H_PCT
    if actionable is True and winner:
        return "TRUE_POSITIVE"
    if actionable is True and not winner:
        return "FALSE_POSITIVE"
    if actionable is False and winner:
        return "FALSE_NEGATIVE"
    return "TRUE_NEGATIVE"


def build(source: dict, previous: dict | None = None) -> tuple[dict, dict]:
    previous = previous if isinstance(previous, dict) else {}
    prior_records = previous.get("records") if isinstance(previous.get("records"), dict) else {}
    records = dict(prior_records)
    integrity_events: list[dict] = []
    source_rows = source.get("records") if isinstance(source, dict) else {}
    source_rows = source_rows.values() if isinstance(source_rows, dict) else source_rows or []

    seen_without_timestamp: dict[str, int] = {}
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        identity = _identity(row)
        if identity is None:
            integrity_events.append({"type": "REJECTED_INCOMPLETE_EXACT_IDENTITY", "source_key": row.get("key")})
            continue
        chain, token, pair, first_at = identity
        base = f"{chain}|{token}|{pair}"
        seen_without_timestamp[base] = seen_without_timestamp.get(base, 0) + 1
        key = _immutable_key(identity)
        t0 = _t0_snapshot(row)
        t0_hash = _sha(t0)
        existing = records.get(key)
        if isinstance(existing, dict):
            if existing.get("t0_sha256") != t0_hash:
                integrity_events.append({
                    "type": "IMMUTABLE_T0_MISMATCH_PRESERVED_OLD_VALUE",
                    "key": key,
                    "old_t0_sha256": existing.get("t0_sha256"),
                    "new_source_t0_sha256": t0_hash,
                })
            existing["outcomes"] = _forward_outcomes(row)
            existing["last_observed_at"] = row.get("latest_observed_at")
            existing["classification_24h"] = _classification(existing)
            continue
        record = {
            "key": key,
            "chain": chain,
            "token_address": token,
            "pair_address": pair,
            "first_decision_at": first_at,
            "source_lane": row.get("lane"),
            "t0": t0,
            "t0_sha256": t0_hash,
            "source_decision_snapshot_sha256": row.get("decision_snapshot_sha256"),
            "outcomes": _forward_outcomes(row),
            "last_observed_at": row.get("latest_observed_at"),
            "classification_24h": "INSUFFICIENT_COVERAGE",
            "research_only": True,
        }
        record["classification_24h"] = _classification(record)
        records[key] = record

    repeated_base_identities = sorted(k for k, n in seen_without_timestamp.items() if n > 1)
    if repeated_base_identities:
        integrity_events.append({
            "type": "SOURCE_KEY_COLLISION_RISK_WITHOUT_FIRST_DECISION_TIMESTAMP",
            "count": len(repeated_base_identities),
            "examples": repeated_base_identities[:5],
        })

    now = datetime.now(timezone.utc).isoformat()
    ledger = {
        "version": 1,
        "mode": MODE,
        "updated_at": now,
        "research_only": True,
        "production_effect": False,
        "identity_contract": "chain|token_address|pair_address|first_decision_at",
        "immutable_t0": True,
        "records": records,
        "integrity_events": integrity_events,
    }

    classifications: dict[str, int] = {}
    matured_24h = 0
    for rec in records.values():
        cls = str(rec.get("classification_24h") or "INSUFFICIENT_COVERAGE")
        classifications[cls] = classifications.get(cls, 0) + 1
        h24 = (rec.get("outcomes") or {}).get("24h") or {}
        if h24.get("status") == "OBSERVED":
            matured_24h += 1

    report = {
        "version": 1,
        "mode": MODE,
        "updated_at": now,
        "research_only": True,
        "production_effect": False,
        "production_thresholds_modified": False,
        "sample": {"records": len(records), "matured_24h": matured_24h},
        "classification_24h": classifications,
        "source_integrity": {
            "source_ledger": SOURCE,
            "source_key_includes_first_decision_timestamp": False,
            "replay_key_includes_first_decision_timestamp": True,
            "integrity_events": integrity_events,
        },
        "policies": {
            "A_CURRENT_PRODUCTION": {"status": "BASELINE_ONLY", "note": "No production semantics inferred when actionable is absent."},
            "B_ACCELERATION_TURNOVER": {"status": "SHADOW_ONLY_INSUFFICIENT_COVERAGE"},
            "C_LIQUIDITY_SURVIVAL": {"status": "SHADOW_ONLY_INSUFFICIENT_COVERAGE"},
            "D_WALLET_CAPITAL_SOCIAL": {"status": "SHADOW_ONLY_INSUFFICIENT_COVERAGE"},
            "E_WINNER_DNA_PERSISTENCE": {"status": "SHADOW_ONLY_INSUFFICIENT_COVERAGE"},
        },
        "promotion_gate": {
            "minimum_matured_decisions": 30,
            "requires_two_non_overlapping_windows": True,
            "requires_no_material_drawdown_or_liquidity_survival_regression": True,
            "requires_no_leakage_or_exact_pair_contamination": True,
            "status": "NOT_READY_FOR_REVIEW",
            "reason": "SHADOW_POLICY_FEATURE_COVERAGE_NOT_YET_SUFFICIENT_FOR_VALID_WALK_FORWARD_COMPARISON",
        },
        "guardrails": {
            "no_hindsight_t0_backfill": True,
            "exact_pair_required": True,
            "symbol_only_identity_forbidden": True,
            "t0_mutation_forbidden": True,
            "production_changes": False,
            "telegram_changes": False,
            "automatic_buy": False,
        },
    }
    return ledger, report


def main() -> None:
    source = _load(DATA / SOURCE, {})
    previous = _load(DATA / LEDGER, {})
    ledger, report = build(source, previous)
    (DATA / LEDGER).write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DECISION_REPLAY_OK", report["sample"], report["promotion_gate"]["status"])


if __name__ == "__main__":
    main()
