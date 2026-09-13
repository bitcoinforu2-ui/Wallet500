from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

DATA = Path("data")
SOURCE = "research-sample-ledger.json"
LEDGER = "decision-replay-ledger.json"
REPORT = "decision-replay-report.json"
MODE = "RESEARCH_ONLY_DECISION_REPLAY_V1"
HORIZON_MINUTES = {
    "15m": 15,
    "1h": 60,
    "3h": 180,
    "6h": 360,
    "24h": 1440,
    "72h": 4320,
    "7d": 10080,
}
HORIZONS = tuple(HORIZON_MINUTES)
NEUTRAL_WINNER_24H_PCT = 20.0
TERMINAL_WINNER_7D_PCT = 20.0
ROUND_TRIP_FRICTION_PCT = 2.0
MIN_MATURED_DECISIONS = 30
MIN_VALIDATION_WINDOWS = 2
MIN_REFERENCE_DECISIONS = 10
VALIDATION_WINDOW_SIZE = 10

EVM_CHAINS = {
    "ethereum", "eth", "base", "arbitrum", "optimism", "polygon", "matic",
    "bsc", "bnb", "avalanche", "avax", "fantom", "linea", "scroll",
}
POLICY_NAMES = (
    "A_CURRENT_PRODUCTION",
    "B_ACCELERATION_TURNOVER",
    "C_LIQUIDITY_SURVIVAL",
    "D_WALLET_CAPITAL_SOCIAL",
    "E_WINNER_DNA_PERSISTENCE",
)
MATERIAL_INTEGRITY_TYPES = {
    "IMMUTABLE_T0_MISMATCH_PRESERVED_OLD_VALUE",
    "REJECTED_INCOMPLETE_EXACT_IDENTITY",
    "REJECTED_IDENTITY_CONFLICT",
    "REJECTED_CHECKPOINT_IDENTITY_CONFLICT",
}


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


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _normalise_address(chain: str, value: Any) -> str:
    text = str(value or "").strip()
    return text.lower() if chain in EVM_CHAINS else text


def _entry(row: dict) -> dict:
    snap = row.get("decision_snapshot") if isinstance(row.get("decision_snapshot"), dict) else {}
    return snap.get("entry") if isinstance(snap.get("entry"), dict) else {}


def _snapshot_identity(row: dict) -> dict:
    snap = row.get("decision_snapshot") if isinstance(row.get("decision_snapshot"), dict) else {}
    return snap.get("identity") if isinstance(snap.get("identity"), dict) else {}


def _identity_conflicts(row: dict) -> list[str]:
    ident = _snapshot_identity(row)
    chain_values = [str(v).strip().lower() for v in (row.get("chain"), ident.get("chain")) if str(v or "").strip()]
    if len(set(chain_values)) > 1:
        return ["chain"]
    chain = chain_values[0] if chain_values else ""
    conflicts: list[str] = []
    token_values = [_normalise_address(chain, v) for v in (row.get("token_address"), ident.get("token"), ident.get("token_address")) if str(v or "").strip()]
    pair_values = [_normalise_address(chain, v) for v in (row.get("pair_address"), ident.get("pair_address")) if str(v or "").strip()]
    if len(set(token_values)) > 1:
        conflicts.append("token_address")
    if len(set(pair_values)) > 1:
        conflicts.append("pair_address")
    return conflicts


def _identity(row: dict) -> tuple[str, str, str, str] | None:
    if _identity_conflicts(row):
        return None
    ident = _snapshot_identity(row)
    entry = _entry(row)
    chain = str(row.get("chain") or ident.get("chain") or "").strip().lower()
    token = _normalise_address(chain, row.get("token_address") or ident.get("token") or ident.get("token_address"))
    pair = _normalise_address(chain, row.get("pair_address") or ident.get("pair_address"))
    first_raw = row.get("first_decision_at") or row.get("event_at") or entry.get("observed_at")
    first_dt = _dt(first_raw)
    if not (chain and token and pair and first_dt):
        return None
    return chain, token, pair, _iso(first_dt)


def _immutable_key(identity: tuple[str, str, str, str]) -> str:
    return "|".join(identity)


def _frozen(entry: dict, row: dict, entry_key: str, row_key: str | None = None) -> Any:
    if entry_key in entry:
        return entry.get(entry_key)
    key = row_key or entry_key
    return row.get(key) if key in row else None


def _list_value(value: Any) -> list[Any] | None:
    if value is None:
        return None
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _t0_snapshot(row: dict, identity: tuple[str, str, str, str]) -> dict:
    entry = _entry(row)
    _, _, _, first_at = identity
    price_raw = _frozen(entry, row, "entry_price_usd")
    liq_raw = _frozen(entry, row, "verified_execution_liquidity_usd")
    volume_h1_raw = _frozen(entry, row, "volume_h1_usd")
    volume_h24_raw = _frozen(entry, row, "volume_h24_usd")
    wallet_flow_verified = _frozen(entry, row, "wallet_flow_verified")
    holder_growth_verified = _frozen(entry, row, "holder_growth_point_in_time_verified")
    actionable = _frozen(entry, row, "actionable")
    return {
        "observed_at": first_at,
        "decision_label": _frozen(entry, row, "radar_tier", "lane"),
        "status": _frozen(entry, row, "status"),
        "actionable": actionable,
        "price_usd": _num(price_raw),
        "exact_pair_liquidity_usd": _num(liq_raw),
        "provider_pool_value_informational_only_usd": _num(_frozen(entry, row, "pool_value_informational_only_usd")),
        "volume_h1_usd": _num(volume_h1_raw),
        "volume_h24_usd": _num(volume_h24_raw),
        "turnover": _num(_frozen(entry, row, "turnover")),
        "buy_flow_usd": _num(_frozen(entry, row, "buy_flow_usd")),
        "sell_flow_usd": _num(_frozen(entry, row, "sell_flow_usd")),
        "market_cap_usd": _num(_frozen(entry, row, "market_cap_usd")),
        "fdv_usd": _num(_frozen(entry, row, "fdv_usd")),
        "market_age_days": _num(_frozen(entry, row, "market_age_days")),
        "signal_score": _num(_frozen(entry, row, "signal_score")),
        "readiness_passed": _num(_frozen(entry, row, "readiness_passed")),
        "readiness_total": _num(_frozen(entry, row, "readiness_total")),
        "source_lane_count": _num(_frozen(entry, row, "source_lane_count")),
        "evidence_positive_count": _num(_frozen(entry, row, "evidence_positive_count")),
        "evidence_positive_lanes": _list_value(_frozen(entry, row, "evidence_positive_lanes")),
        "missing_gates": _list_value(_frozen(entry, row, "missing_gates")),
        "blockers": _list_value(_frozen(entry, row, "blockers")),
        "verified_execution_tradable": _frozen(entry, row, "verified_execution_tradable"),
        "coverage": {
            "price": "KNOWN_AT_T0" if price_raw is not None else "INSUFFICIENT_COVERAGE",
            "exact_pair_liquidity": "KNOWN_AT_T0" if liq_raw is not None else "INSUFFICIENT_COVERAGE",
            "volume_h1": "KNOWN_AT_T0" if volume_h1_raw is not None else "INSUFFICIENT_COVERAGE",
            "volume_h24": "KNOWN_AT_T0" if volume_h24_raw is not None else "INSUFFICIENT_COVERAGE",
            "wallet_flow": "KNOWN_AT_T0" if wallet_flow_verified is True else "INSUFFICIENT_COVERAGE",
            "holder_growth": "KNOWN_AT_T0" if holder_growth_verified is True else "INSUFFICIENT_COVERAGE",
        },
    }


def _iter_checkpoint_payloads(row: dict) -> Iterable[tuple[str, dict]]:
    checkpoints = row.get("checkpoints")
    if isinstance(checkpoints, dict):
        for label, payload in checkpoints.items():
            if isinstance(payload, dict):
                yield str(label), payload
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        yield str(label), item
    for history_key in ("checkpoint_history", "observations_history", "forward_observations"):
        history = row.get(history_key)
        if isinstance(history, list):
            for item in history:
                if isinstance(item, dict):
                    yield str(item.get("horizon") or item.get("label") or history_key), item
        elif isinstance(history, dict):
            for label, payload in history.items():
                if isinstance(payload, dict):
                    yield str(label), payload
                elif isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, dict):
                            yield str(label), item


def _checkpoint_identity(cp: dict, base_identity: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    base_chain, base_token, base_pair, _ = base_identity
    nested = cp.get("identity") if isinstance(cp.get("identity"), dict) else {}
    raw_chain = cp.get("chain") or nested.get("chain")
    chain = str(raw_chain or base_chain).strip().lower()
    raw_token = cp.get("token_address") or cp.get("token") or nested.get("token_address") or nested.get("token")
    raw_pair = cp.get("pair_address") or nested.get("pair_address")
    token = _normalise_address(chain, raw_token if raw_token is not None else base_token)
    pair = _normalise_address(chain, raw_pair if raw_pair is not None else base_pair)
    source_kind = "CHECKPOINT_EXPLICIT" if any(v is not None for v in (raw_chain, raw_token, raw_pair)) else "ROW_EXACT_IDENTITY_INHERITED"
    return chain, token, pair, source_kind


def _reliable_candidates(row: dict, identity: tuple[str, str, str, str]) -> tuple[list[dict], list[dict]]:
    base_chain, base_token, base_pair, first_at = identity
    first_dt = _dt(first_at)
    assert first_dt is not None
    candidates: list[dict] = []
    events: list[dict] = []
    seen: set[tuple[Any, ...]] = set()
    for label, cp in _iter_checkpoint_payloads(row):
        observed = _dt(cp.get("captured_at") or cp.get("observed_at") or cp.get("timestamp") or cp.get("at"))
        if observed is None:
            events.append({"type": "REJECTED_CHECKPOINT_MISSING_TIMESTAMP", "label": label})
            continue
        chain, token, pair, identity_source = _checkpoint_identity(cp, identity)
        if (chain, token, pair) != (base_chain, base_token, base_pair):
            events.append({
                "type": "REJECTED_CHECKPOINT_IDENTITY_CONFLICT",
                "label": label,
                "observed_at": _iso(observed),
                "expected": {"chain": base_chain, "token_address": base_token, "pair_address": base_pair},
                "observed": {"chain": chain, "token_address": token, "pair_address": pair},
            })
            continue
        if observed < first_dt:
            events.append({"type": "REJECTED_PRE_T0_CHECKPOINT", "label": label, "observed_at": _iso(observed)})
            continue
        integrity = str(cp.get("integrity") or "").strip().upper()
        if cp.get("reliable") is False or cp.get("valid") is False or integrity in {"FAIL", "FAILED", "INVALID", "UNRELIABLE"}:
            events.append({"type": "REJECTED_UNRELIABLE_CHECKPOINT", "label": label, "observed_at": _iso(observed)})
            continue
        price = _num(cp.get("price_usd"))
        if price is None or price <= 0:
            events.append({"type": "REJECTED_CHECKPOINT_MISSING_PRICE", "label": label, "observed_at": _iso(observed)})
            continue
        source = cp.get("source")
        dedupe = (_iso(observed), price, chain, token, pair, str(source or ""))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        exact_liq = _num(cp.get("verified_execution_liquidity_usd"))
        if exact_liq is None:
            exact_liq = _num(cp.get("exact_pair_liquidity_usd"))
        candidates.append({
            "label_hint": label,
            "observed_dt": observed,
            "observed_at": _iso(observed),
            "price_usd": price,
            "exact_pair_liquidity_usd": exact_liq,
            "provider_pool_value_informational_only_usd": _num(cp.get("provider_pool_value_usd")),
            "source": source,
            "identity_source": identity_source,
            "chain": chain,
            "token_address": token,
            "pair_address": pair,
            "source_reported_captured_age_minutes": _num(cp.get("captured_age_minutes")),
            "source_reported_gross_return_pct": _num(cp.get("gross_return_pct")),
            "source_reported_friction_adjusted_return_pct": _num(cp.get("friction_adjusted_return_pct")),
        })
    candidates.sort(key=lambda x: (x["observed_dt"], str(x["label_hint"]), str(x.get("source") or "")))
    return candidates, events


def _pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return (current / baseline - 1.0) * 100.0


def _forward_outcomes(row: dict, identity: tuple[str, str, str, str], t0: dict) -> tuple[dict, list[dict], str | None]:
    candidates, events = _reliable_candidates(row, identity)
    first_dt = _dt(identity[3])
    assert first_dt is not None
    entry_price = _num(t0.get("price_usd"))
    out: dict[str, Any] = {}
    for horizon, minutes in HORIZON_MINUTES.items():
        target = first_dt + timedelta(minutes=minutes)
        selected = next((c for c in candidates if c["observed_dt"] >= target), None)
        if selected is None:
            out[horizon] = {
                "status": "NOT_MATURED_OR_INSUFFICIENT_COVERAGE",
                "target_at": _iso(target),
                "selection_rule": "FIRST_RELIABLE_EXACT_PAIR_OBSERVATION_AT_OR_AFTER_TARGET",
            }
            continue
        gross = _pct_change(selected["price_usd"], entry_price)
        friction = None if gross is None else gross - ROUND_TRIP_FRICTION_PCT
        path_prices = [entry_price] if entry_price is not None and entry_price > 0 else []
        path_prices.extend(
            c["price_usd"] for c in candidates
            if first_dt <= c["observed_dt"] <= selected["observed_dt"] and c["price_usd"] > 0
        )
        observed_drawdown = None
        if entry_price is not None and entry_price > 0 and path_prices:
            observed_drawdown = (min(path_prices) / entry_price - 1.0) * 100.0
        exact_liq = selected["exact_pair_liquidity_usd"]
        provider_pool = selected["provider_pool_value_informational_only_usd"]
        out[horizon] = {
            "status": "OBSERVED",
            "target_at": _iso(target),
            "observed_at": selected["observed_at"],
            "lag_seconds": round((selected["observed_dt"] - target).total_seconds(), 3),
            "actual_age_minutes": round((selected["observed_dt"] - first_dt).total_seconds() / 60.0, 6),
            "selection_rule": "FIRST_RELIABLE_EXACT_PAIR_OBSERVATION_AT_OR_AFTER_TARGET",
            "source_label_hint": selected["label_hint"],
            "source": selected["source"],
            "price_usd": selected["price_usd"],
            "gross_return_pct": gross,
            "friction_adjusted_return_pct": friction,
            "research_round_trip_friction_pct": ROUND_TRIP_FRICTION_PCT,
            "observed_drawdown_pct": observed_drawdown,
            "exact_pair_liquidity_usd": exact_liq,
            "exact_pair_liquidity_change_pct": _pct_change(exact_liq, _num(t0.get("exact_pair_liquidity_usd"))),
            "provider_pool_value_informational_only_usd": provider_pool,
            "provider_pool_value_change_pct_informational_only": _pct_change(
                provider_pool, _num(t0.get("provider_pool_value_informational_only_usd"))
            ),
            "source_reported": {
                "captured_age_minutes": selected["source_reported_captured_age_minutes"],
                "gross_return_pct": selected["source_reported_gross_return_pct"],
                "friction_adjusted_return_pct": selected["source_reported_friction_adjusted_return_pct"],
            },
            "provenance": {
                "chain": selected["chain"],
                "token_address": selected["token_address"],
                "pair_address": selected["pair_address"],
                "identity_source": selected["identity_source"],
                "exact_pair_identity_preserved": (
                    selected["chain"], selected["token_address"], selected["pair_address"]
                ) == identity[:3],
            },
        }
    last_observed_at = candidates[-1]["observed_at"] if candidates else None
    return out, events, last_observed_at


def _classification(record: dict) -> str:
    t0 = record.get("t0") or {}
    actionable = t0.get("actionable")
    h24 = (record.get("outcomes") or {}).get("24h") or {}
    ret = _num(h24.get("friction_adjusted_return_pct"))
    if actionable not in (True, False) or ret is None or h24.get("status") != "OBSERVED":
        return "INSUFFICIENT_COVERAGE"
    winner = ret >= NEUTRAL_WINNER_24H_PCT
    if actionable is True and winner:
        return "TRUE_POSITIVE"
    if actionable is True and not winner:
        return "FALSE_POSITIVE"
    if actionable is False and winner:
        return "FALSE_NEGATIVE"
    return "TRUE_NEGATIVE"


def _readiness_ratio(t0: dict) -> float | None:
    passed = _num(t0.get("readiness_passed"))
    total = _num(t0.get("readiness_total"))
    if passed is None or total is None or total <= 0:
        return None
    return passed / total


def _shadow_decisions(t0: dict) -> dict[str, bool | None]:
    actionable = t0.get("actionable")
    a = actionable if actionable in (True, False) else None

    turnover = _num(t0.get("turnover"))
    readiness = _readiness_ratio(t0)
    b = None if turnover is None or readiness is None else bool(turnover >= 0.50 and readiness >= (6.0 / 7.0))

    liquidity = _num(t0.get("exact_pair_liquidity_usd"))
    tradable = t0.get("verified_execution_tradable")
    c = None if liquidity is None or tradable not in (True, False) else bool(tradable is True and liquidity >= 15000.0)

    buy_flow = _num(t0.get("buy_flow_usd"))
    sell_flow = _num(t0.get("sell_flow_usd"))
    lane_count = _num(t0.get("source_lane_count"))
    evidence_count = _num(t0.get("evidence_positive_count"))
    d = None if None in (buy_flow, sell_flow, lane_count, evidence_count) else bool(
        buy_flow > sell_flow and lane_count >= 2 and evidence_count >= 1
    )

    signal_score = _num(t0.get("signal_score"))
    e = None if None in (signal_score, readiness, evidence_count, liquidity) else bool(
        signal_score >= 70.0 and readiness >= (6.0 / 7.0) and evidence_count >= 2 and liquidity >= 50000.0
    )
    return {
        "A_CURRENT_PRODUCTION": a,
        "B_ACCELERATION_TURNOVER": b,
        "C_LIQUIDITY_SURVIVAL": c,
        "D_WALLET_CAPITAL_SOCIAL": d,
        "E_WINNER_DNA_PERSISTENCE": e,
    }


def _terminal_row(record: dict) -> dict | None:
    first_dt = _dt(record.get("first_decision_at"))
    h7 = (record.get("outcomes") or {}).get("7d") or {}
    observed_dt = _dt(h7.get("observed_at"))
    provenance = h7.get("provenance") if isinstance(h7.get("provenance"), dict) else {}
    ret = _num(h7.get("friction_adjusted_return_pct"))
    if (
        first_dt is None or observed_dt is None or h7.get("status") != "OBSERVED" or
        provenance.get("exact_pair_identity_preserved") is not True or ret is None
    ):
        return None
    return {
        "key": record.get("key"),
        "first_decision_dt": first_dt,
        "first_decision_at": _iso(first_dt),
        "label_available_dt": observed_dt,
        "label_available_at": _iso(observed_dt),
        "terminal_return_pct": ret,
        "terminal_drawdown_pct": _num(h7.get("observed_drawdown_pct")),
        "winner": ret >= TERMINAL_WINNER_7D_PCT,
        "shadow_decisions": record.get("shadow_decisions") or {},
    }


def _policy_metrics(rows: list[dict], policy_name: str) -> dict:
    evaluated: list[dict] = []
    for row in rows:
        decision = (row.get("shadow_decisions") or {}).get(policy_name)
        if decision in (True, False):
            evaluated.append({**row, "decision": decision})
    tp = sum(1 for r in evaluated if r["decision"] is True and r["winner"] is True)
    fp = sum(1 for r in evaluated if r["decision"] is True and r["winner"] is False)
    fn = sum(1 for r in evaluated if r["decision"] is False and r["winner"] is True)
    tn = sum(1 for r in evaluated if r["decision"] is False and r["winner"] is False)
    positives = [r for r in evaluated if r["decision"] is True]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    mean_return = sum(r["terminal_return_pct"] for r in positives) / len(positives) if positives else None
    drawdowns = [r["terminal_drawdown_pct"] for r in positives if r["terminal_drawdown_pct"] is not None]
    mean_drawdown = sum(drawdowns) / len(drawdowns) if drawdowns else None
    return {
        "validation_records": len(rows),
        "evaluated": len(evaluated),
        "coverage_ratio": (len(evaluated) / len(rows)) if rows else 0.0,
        "predicted_positive": len(positives),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": precision,
        "recall": recall,
        "mean_7d_return_pct_when_positive": mean_return,
        "mean_observed_drawdown_pct_when_positive": mean_drawdown,
    }


def _walk_forward(records: dict[str, dict]) -> dict:
    matured = [row for row in (_terminal_row(rec) for rec in records.values()) if row is not None]
    matured.sort(key=lambda r: (r["first_decision_dt"], str(r["key"])))
    windows: list[dict] = []
    evaluation_rows: list[dict] = []
    for start in range(MIN_REFERENCE_DECISIONS, len(matured), VALIDATION_WINDOW_SIZE):
        validation = matured[start:start + VALIDATION_WINDOW_SIZE]
        if len(validation) < VALIDATION_WINDOW_SIZE:
            break
        validation_started = validation[0]["first_decision_dt"]
        earlier = matured[:start]
        reference = [r for r in earlier if r["label_available_dt"] < validation_started]
        excluded = len(earlier) - len(reference)
        leakage_free = all(r["label_available_dt"] < validation_started for r in reference)
        valid = len(reference) >= MIN_REFERENCE_DECISIONS and leakage_free
        window = {
            "window_index": len(windows) + 1,
            "validation_started_at": _iso(validation_started),
            "validation_ended_at": validation[-1]["first_decision_at"],
            "validation_records": len(validation),
            "reference_records_available_before_window": len(reference),
            "reference_labels_excluded_as_not_yet_available": excluded,
            "reference_label_max_at": max((r["label_available_at"] for r in reference), default=None),
            "leakage_free": leakage_free,
            "status": "VALID" if valid else "INSUFFICIENT_PRIOR_MATURED_REFERENCE",
            "validation_keys": [r["key"] for r in validation],
        }
        windows.append(window)
        if valid:
            evaluation_rows.extend(validation)
    valid_windows = [w for w in windows if w["status"] == "VALID"]
    policies = {name: _policy_metrics(evaluation_rows, name) for name in POLICY_NAMES}
    return {
        "terminal_horizon": "7d",
        "terminal_winner_threshold_pct": TERMINAL_WINNER_7D_PCT,
        "matured_decisions": len(matured),
        "minimum_reference_decisions": MIN_REFERENCE_DECISIONS,
        "validation_window_size": VALIDATION_WINDOW_SIZE,
        "candidate_windows": len(windows),
        "valid_validation_windows": len(valid_windows),
        "non_overlapping_validation_windows": windows,
        "validation_records_evaluated": len(evaluation_rows),
        "policy_metrics": policies,
    }


def _baseline_semantics_unchanged(records: dict[str, dict]) -> bool:
    for rec in records.values():
        actionable = (rec.get("t0") or {}).get("actionable")
        expected = actionable if actionable in (True, False) else None
        if (rec.get("shadow_decisions") or {}).get("A_CURRENT_PRODUCTION") is not expected:
            return False
    return True


def _candidate_clears(candidate: dict, baseline: dict) -> bool:
    if candidate.get("evaluated", 0) < 20 or candidate.get("coverage_ratio", 0.0) < 0.80 or candidate.get("predicted_positive", 0) < 5:
        return False
    if baseline.get("evaluated", 0) < 20 or baseline.get("coverage_ratio", 0.0) < 0.80 or baseline.get("predicted_positive", 0) < 5:
        return False
    c_precision, b_precision = candidate.get("precision"), baseline.get("precision")
    c_return, b_return = candidate.get("mean_7d_return_pct_when_positive"), baseline.get("mean_7d_return_pct_when_positive")
    c_dd, b_dd = candidate.get("mean_observed_drawdown_pct_when_positive"), baseline.get("mean_observed_drawdown_pct_when_positive")
    if None in (c_precision, b_precision, c_return, b_return, c_dd, b_dd):
        return False
    return bool(c_precision >= b_precision + 0.05 and c_return >= b_return and c_dd >= b_dd)


def _promotion_gate(records: dict[str, dict], integrity_events: list[dict], walk_forward: dict) -> dict:
    material_events = [e for e in integrity_events if e.get("type") in MATERIAL_INTEGRITY_TYPES]
    baseline_unchanged = _baseline_semantics_unchanged(records)
    windows = walk_forward.get("non_overlapping_validation_windows") or []
    leakage_free = all(w.get("leakage_free") is True for w in windows if w.get("status") == "VALID")
    hard = {
        "matured_decisions_gte_30": walk_forward.get("matured_decisions", 0) >= MIN_MATURED_DECISIONS,
        "valid_non_overlapping_validation_windows_gte_2": walk_forward.get("valid_validation_windows", 0) >= MIN_VALIDATION_WINDOWS,
        "immutable_t0_integrity_clean": not any(e.get("type") == "IMMUTABLE_T0_MISMATCH_PRESERVED_OLD_VALUE" for e in material_events),
        "exact_pair_integrity_clean": not any(e.get("type") in {"REJECTED_IDENTITY_CONFLICT", "REJECTED_CHECKPOINT_IDENTITY_CONFLICT", "REJECTED_INCOMPLETE_EXACT_IDENTITY"} for e in material_events),
        "walk_forward_leakage_free": leakage_free,
        "baseline_policy_a_unchanged": baseline_unchanged,
    }
    baseline = (walk_forward.get("policy_metrics") or {}).get("A_CURRENT_PRODUCTION") or {}
    clearing = [
        name for name in POLICY_NAMES[1:]
        if _candidate_clears((walk_forward.get("policy_metrics") or {}).get(name) or {}, baseline)
    ]
    hard_pass = all(hard.values())
    if not hard_pass:
        status = "NOT_READY_FOR_REVIEW"
        failed = [name for name, passed in hard.items() if not passed]
        reason = "HARD_PREREQUISITES_NOT_MET:" + ",".join(failed)
    elif not clearing:
        status = "NOT_READY_FOR_REVIEW"
        reason = "NO_SHADOW_POLICY_CLEARS_WALK_FORWARD_PERFORMANCE_AND_COVERAGE_CRITERIA"
    else:
        status = "READY_FOR_REVIEW"
        reason = "RESEARCH_REVIEW_PREREQUISITES_AND_WALK_FORWARD_CRITERIA_MET"
    return {
        "minimum_matured_decisions": MIN_MATURED_DECISIONS,
        "minimum_valid_non_overlapping_validation_windows": MIN_VALIDATION_WINDOWS,
        "requires_two_non_overlapping_windows": True,
        "requires_no_material_drawdown_or_liquidity_survival_regression": True,
        "requires_no_leakage_or_exact_pair_contamination": True,
        "hard_prerequisites": hard,
        "clearing_shadow_policies": clearing,
        "status": status,
        "reason": reason,
        "promotion_scope": "RESEARCH_REVIEW_ONLY_NEVER_AUTOMATIC_PRODUCTION_PROMOTION",
    }


def _deterministic_updated_at(source: dict, records: dict[str, dict]) -> str:
    candidates: list[datetime] = []
    for field in ("updated_at", "created_at", "activation_at"):
        parsed = _dt(source.get(field)) if isinstance(source, dict) else None
        if parsed:
            candidates.append(parsed)
    for rec in records.values():
        for field in ("last_observed_at", "first_decision_at"):
            parsed = _dt(rec.get(field))
            if parsed:
                candidates.append(parsed)
    return _iso(max(candidates)) if candidates else "1970-01-01T00:00:00+00:00"


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
        conflicts = _identity_conflicts(row)
        if conflicts:
            integrity_events.append({"type": "REJECTED_IDENTITY_CONFLICT", "source_key": row.get("key"), "fields": conflicts})
            continue
        identity = _identity(row)
        if identity is None:
            integrity_events.append({"type": "REJECTED_INCOMPLETE_EXACT_IDENTITY", "source_key": row.get("key")})
            continue
        chain, token, pair, first_at = identity
        base = f"{chain}|{token}|{pair}"
        seen_without_timestamp[base] = seen_without_timestamp.get(base, 0) + 1
        key = _immutable_key(identity)
        proposed_t0 = _t0_snapshot(row, identity)
        proposed_t0_hash = _sha(proposed_t0)
        existing = records.get(key)
        if isinstance(existing, dict):
            frozen_t0 = existing.get("t0") if isinstance(existing.get("t0"), dict) else proposed_t0
            frozen_hash = existing.get("t0_sha256") or _sha(frozen_t0)
            if frozen_hash != proposed_t0_hash:
                integrity_events.append({
                    "type": "IMMUTABLE_T0_MISMATCH_PRESERVED_OLD_VALUE",
                    "key": key,
                    "old_t0_sha256": frozen_hash,
                    "new_source_t0_sha256": proposed_t0_hash,
                })
            existing["t0"] = frozen_t0
            existing["t0_sha256"] = frozen_hash
            outcomes, cp_events, last_observed_at = _forward_outcomes(row, identity, frozen_t0)
            for event in cp_events:
                integrity_events.append({"key": key, **event})
            existing["outcomes"] = outcomes
            existing["last_observed_at"] = last_observed_at
            existing["shadow_decisions"] = _shadow_decisions(frozen_t0)
            existing["classification_24h"] = _classification(existing)
            existing["research_only"] = True
            continue

        outcomes, cp_events, last_observed_at = _forward_outcomes(row, identity, proposed_t0)
        for event in cp_events:
            integrity_events.append({"key": key, **event})
        record = {
            "key": key,
            "chain": chain,
            "token_address": token,
            "pair_address": pair,
            "first_decision_at": first_at,
            "source_lane": row.get("lane"),
            "t0": proposed_t0,
            "t0_sha256": proposed_t0_hash,
            "source_decision_snapshot_sha256": row.get("decision_snapshot_sha256"),
            "outcomes": outcomes,
            "last_observed_at": last_observed_at,
            "classification_24h": "INSUFFICIENT_COVERAGE",
            "shadow_decisions": _shadow_decisions(proposed_t0),
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

    records = dict(sorted(records.items()))
    updated_at = _deterministic_updated_at(source, records)
    walk_forward = _walk_forward(records)
    promotion_gate = _promotion_gate(records, integrity_events, walk_forward)
    ledger = {
        "version": 2,
        "mode": MODE,
        "updated_at": updated_at,
        "research_only": True,
        "production_effect": False,
        "identity_contract": "chain|token_address|pair_address|first_decision_at",
        "immutable_t0": True,
        "observation_selection_contract": "FIRST_RELIABLE_EXACT_PAIR_OBSERVATION_AT_OR_AFTER_TARGET",
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
        "version": 2,
        "mode": MODE,
        "updated_at": updated_at,
        "research_only": True,
        "production_effect": False,
        "production_thresholds_modified": False,
        "sample": {
            "records": len(records),
            "matured_24h": matured_24h,
            "matured_terminal_7d": walk_forward["matured_decisions"],
        },
        "classification_24h": classifications,
        "source_integrity": {
            "source_ledger": SOURCE,
            "source_key_includes_first_decision_timestamp": False,
            "replay_key_includes_first_decision_timestamp": True,
            "material_integrity_events": sum(1 for e in integrity_events if e.get("type") in MATERIAL_INTEGRITY_TYPES),
            "integrity_events": integrity_events,
        },
        "policy_contract": {
            "A_CURRENT_PRODUCTION": "Frozen T0 actionable boolean only; shadow evaluation never rewrites it.",
            "B_ACCELERATION_TURNOVER": "T0 turnover >= 0.50 and readiness >= 6/7.",
            "C_LIQUIDITY_SURVIVAL": "T0 verified tradable and exact-pair execution liquidity >= 15,000 USD.",
            "D_WALLET_CAPITAL_SOCIAL": "T0 buy flow > sell flow, >=2 source lanes and >=1 positive evidence lane.",
            "E_WINNER_DNA_PERSISTENCE": "T0 score >=70, readiness >=6/7, >=2 positive evidence lanes and exact-pair liquidity >=50,000 USD.",
        },
        "walk_forward": walk_forward,
        "policies": walk_forward["policy_metrics"],
        "promotion_gate": promotion_gate,
        "guardrails": {
            "no_hindsight_t0_backfill": True,
            "exact_pair_required": True,
            "first_observation_at_or_after_horizon_required": True,
            "symbol_only_identity_forbidden": True,
            "t0_mutation_forbidden": True,
            "walk_forward_future_label_leakage_forbidden": True,
            "minimum_matured_decisions_for_review": MIN_MATURED_DECISIONS,
            "minimum_validation_windows_for_review": MIN_VALIDATION_WINDOWS,
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
    (DATA / LEDGER).write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (DATA / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DECISION_REPLAY_OK", report["sample"], report["promotion_gate"]["status"])


if __name__ == "__main__":
    main()
