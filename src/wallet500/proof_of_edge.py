from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

DATA = Path("data")
LEDGER_PATH = DATA / "proof-of-edge-ledger.json"
REPORT_PATH = DATA / "proof-of-edge-report.json"
MODE = "FORWARD_PROOF_OF_EDGE_V1"
PRIMARY_HORIZON = "24h"
ANALYSIS_HORIZONS = ("1h", "6h", "24h", "7d")
WINNER_RETURN_PCT = 20.0
BIG_WINNER_RETURN_PCT = 100.0
LOSER_RETURN_PCT = -20.0
SEVERE_LOSS_RETURN_PCT = -50.0
MIN_BLOCKER_SAMPLE_FOR_REVIEW = 5
MIN_BLOCKER_MISS_RATE_FOR_REVIEW_PCT = 20.0


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
    c = str(chain or "").lower()
    s = str(value or "")
    return s.lower() if c in {"bsc", "bnb", "ethereum", "eth"} else s


def _identity_key(chain: Any, token: Any, pair: Any) -> str:
    c = str(chain or "").lower()
    return f"{c}|{_norm(c, token)}|{_norm(c, pair)}"


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _initial_ledger(now: datetime, alpha_activation_at: str | None) -> dict[str, Any]:
    ts = now.isoformat()
    return {
        "version": 1,
        "mode": MODE,
        "created_at": ts,
        "updated_at": ts,
        "decision_snapshot_activation_at": ts,
        "alpha_activation_at": alpha_activation_at,
        "records": {},
        "policy": {
            "no_hindsight": True,
            "exact_pair_identity_required": True,
            "decision_context_frozen_on_first_observation": True,
            "decision_context_sha256_verified_each_run": True,
            "performance_source": "alpha-proof-ledger immutable checkpoints",
            "production_weight_changes": False,
            "primary_horizon": PRIMARY_HORIZON,
            "winner_return_pct_after_friction": WINNER_RETURN_PCT,
            "big_winner_return_pct_after_friction": BIG_WINNER_RETURN_PCT,
            "loser_return_pct_after_friction": LOSER_RETURN_PCT,
            "severe_loss_return_pct_after_friction": SEVERE_LOSS_RETURN_PCT,
        },
    }


def _evidence_index(payload: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return out
    for snap in records.values():
        if not isinstance(snap, dict):
            continue
        ident = snap.get("identity") if isinstance(snap.get("identity"), dict) else {}
        key = _identity_key(ident.get("chain"), ident.get("token"), ident.get("pair_address"))
        out.setdefault(key, []).append(snap)
    return out


def _rejected_index(payload: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return out
    for source_key, row in records.items():
        if not isinstance(row, dict):
            continue
        ident = row.get("identity") if isinstance(row.get("identity"), dict) else {}
        snap = row.get("first_reject_snapshot") if isinstance(row.get("first_reject_snapshot"), dict) else {}
        key = _identity_key(
            ident.get("chain") or snap.get("chain"),
            ident.get("token") or snap.get("token"),
            ident.get("pair_address") or snap.get("pair_address"),
        )
        out[source_key] = row
        out.setdefault(key, row)
    return out


def _closest_evidence(candidates: list[dict[str, Any]], event_at: Any) -> dict[str, Any] | None:
    if not candidates:
        return None
    target = _dt(event_at)
    if target is None:
        return candidates[0]
    ranked: list[tuple[float, dict[str, Any]]] = []
    for snap in candidates:
        observed = _dt(snap.get("observed_at"))
        delta = abs((observed - target).total_seconds()) if observed else float("inf")
        ranked.append((delta, snap))
    ranked.sort(key=lambda x: x[0])
    return ranked[0][1]


def _freeze_signal_context(alpha_rec: dict[str, Any], evidence: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    key = str(alpha_rec.get("key") or "")
    if alpha_rec.get("lane") == "PRODUCTION_FIRST_QUALIFIED":
        snap = _closest_evidence(evidence.get(key, []), alpha_rec.get("event_at"))
        if isinstance(snap, dict):
            return {
                "snapshot_quality": "IMMUTABLE_FIRST_QUALIFIED_EVIDENCE",
                "source": "discovery-evidence-ledger.json",
                "evidence": deepcopy(snap),
            }
    return {
        "snapshot_quality": "ALPHA_ENTRY_FACTS_ONLY",
        "source": alpha_rec.get("source"),
        "evidence": {
            "lane": alpha_rec.get("lane"),
            "chain": alpha_rec.get("chain"),
            "token": alpha_rec.get("token"),
            "pair_address": alpha_rec.get("pair_address"),
            "event_at": alpha_rec.get("event_at"),
            "entry_price_usd": alpha_rec.get("entry_price_usd"),
            "entry_liquidity_usd": alpha_rec.get("entry_liquidity_usd"),
        },
    }


def _freeze_control_context(alpha_rec: dict[str, Any], rejected: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = rejected.get(str(alpha_rec.get("source_record_key") or "")) or rejected.get(str(alpha_rec.get("key") or ""))
    if isinstance(row, dict):
        snap = row.get("first_reject_snapshot") if isinstance(row.get("first_reject_snapshot"), dict) else {}
        return {
            "snapshot_quality": "IMMUTABLE_FIRST_REJECT_EVIDENCE",
            "source": alpha_rec.get("source"),
            "first_reject_source": row.get("first_reject_source") or alpha_rec.get("first_reject_source"),
            "first_decision_class": row.get("first_decision_class") or alpha_rec.get("first_decision_class"),
            "evidence": deepcopy(snap),
        }
    return {
        "snapshot_quality": "ALPHA_ENTRY_FACTS_ONLY",
        "source": alpha_rec.get("source"),
        "first_reject_source": alpha_rec.get("first_reject_source"),
        "first_decision_class": alpha_rec.get("first_decision_class"),
        "evidence": {
            "chain": alpha_rec.get("chain"),
            "token": alpha_rec.get("token"),
            "pair_address": alpha_rec.get("pair_address"),
            "event_at": alpha_rec.get("event_at"),
            "entry_price_usd": alpha_rec.get("entry_price_usd"),
            "entry_liquidity_usd": alpha_rec.get("entry_liquidity_usd"),
        },
    }


def _sync_records(ledger: dict[str, Any], alpha: dict[str, Any], data_dir: Path, now: datetime) -> None:
    records = ledger.setdefault("records", {})
    evidence = _evidence_index(_load(data_dir / "discovery-evidence-ledger.json", {}))
    rejected = _rejected_index(_load(data_dir / "rejected-candidate-ledger.json", {}))
    for cohort_name, decision in (("signals", "ACCEPT"), ("controls", "REJECT_OR_HOLD")):
        cohort = alpha.get(cohort_name) if isinstance(alpha.get(cohort_name), dict) else {}
        for alpha_key, alpha_rec in cohort.items():
            if not isinstance(alpha_rec, dict):
                continue
            proof_key = f"{decision}|{alpha_key}"
            if proof_key not in records:
                context = (
                    _freeze_signal_context(alpha_rec, evidence)
                    if decision == "ACCEPT"
                    else _freeze_control_context(alpha_rec, rejected)
                )
                records[proof_key] = {
                    "decision": decision,
                    "lane": alpha_rec.get("lane"),
                    "alpha_record_key": alpha_key,
                    "identity_key": alpha_rec.get("key"),
                    "chain": alpha_rec.get("chain"),
                    "token": alpha_rec.get("token"),
                    "pair_address": alpha_rec.get("pair_address"),
                    "event_at": alpha_rec.get("event_at"),
                    "entry_price_usd": alpha_rec.get("entry_price_usd"),
                    "entry_liquidity_usd": alpha_rec.get("entry_liquidity_usd"),
                    "first_seen_by_proof_of_edge_at": now.isoformat(),
                    "decision_context": context,
                    "decision_context_sha256": _canonical_hash(context),
                }
            rec = records[proof_key]
            rec["latest_alpha_observation_at"] = alpha_rec.get("latest_observed_at")
            rec["latest_return_pct"] = alpha_rec.get("latest_return_pct")
            rec["peak_sampled_return_pct"] = alpha_rec.get("peak_sampled_return_pct")
            rec["low_sampled_return_pct"] = alpha_rec.get("low_sampled_return_pct")
            rec["checkpoints"] = deepcopy(alpha_rec.get("checkpoints") or {})


def _integrity(records: dict[str, Any]) -> dict[str, Any]:
    checked = 0
    mismatches: list[str] = []
    for key, rec in records.items():
        if not isinstance(rec, dict) or "decision_context" not in rec:
            continue
        checked += 1
        expected = rec.get("decision_context_sha256")
        actual = _canonical_hash(rec.get("decision_context"))
        if expected != actual:
            mismatches.append(key)
    return {
        "checked_records": checked,
        "hash_mismatch_count": len(mismatches),
        "hash_mismatch_keys": mismatches[:25],
        "status": "PASS" if not mismatches else "FAIL",
    }


def _checkpoint_return(rec: dict[str, Any], horizon: str) -> float | None:
    checkpoints = rec.get("checkpoints") if isinstance(rec.get("checkpoints"), dict) else {}
    cp = checkpoints.get(horizon) if isinstance(checkpoints.get(horizon), dict) else {}
    return _num(cp.get("friction_adjusted_return_pct"))


def _classify(decision: str, ret: float | None) -> str:
    if ret is None:
        return "IMMATURE"
    if decision == "ACCEPT":
        if ret >= BIG_WINNER_RETURN_PCT:
            return "TRUE_POSITIVE_BIG_WINNER"
        if ret >= WINNER_RETURN_PCT:
            return "TRUE_POSITIVE_WINNER"
        if ret <= SEVERE_LOSS_RETURN_PCT:
            return "FALSE_POSITIVE_SEVERE_LOSS"
        if ret <= LOSER_RETURN_PCT:
            return "FALSE_POSITIVE_LOSER"
        return "ACCEPTED_NEUTRAL"
    if ret >= BIG_WINNER_RETURN_PCT:
        return "MISSED_BIG_WINNER"
    if ret >= WINNER_RETURN_PCT:
        return "MISSED_WINNER"
    if ret <= SEVERE_LOSS_RETURN_PCT:
        return "CORRECT_REJECT_SEVERE_LOSS_AVOIDED"
    if ret <= LOSER_RETURN_PCT:
        return "CORRECT_REJECT_LOSS_AVOIDED"
    return "REJECTED_NEUTRAL"


def _reason_list(rec: dict[str, Any]) -> list[str]:
    context = rec.get("decision_context") if isinstance(rec.get("decision_context"), dict) else {}
    evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
    reasons: list[str] = []
    source = context.get("first_reject_source") or context.get("source")
    if source:
        reasons.append(f"SOURCE:{source}")
    for field in (
        "qualification_reasons",
        "live_survival_reasons",
        "production_risk_reasons",
        "holder_cluster_reasons",
        "fresh_solana_reasons",
    ):
        value = evidence.get(field)
        if isinstance(value, list):
            reasons.extend(str(x) for x in value if x)
    for field in ("live_survival_gate", "holder_cluster_status", "qualification"):
        value = evidence.get(field)
        if value:
            reasons.append(f"{field.upper()}:{value}")
    return sorted(set(reasons)) or ["UNATTRIBUTED_GATE"]


def _horizon_matrix(records: list[dict[str, Any]], horizon: str) -> dict[str, Any]:
    accepted = [r for r in records if r.get("decision") == "ACCEPT"]
    rejected = [r for r in records if r.get("decision") != "ACCEPT"]
    classes: dict[str, int] = {}
    mature_accept = 0
    mature_reject = 0
    for rec in records:
        ret = _checkpoint_return(rec, horizon)
        cls = _classify(str(rec.get("decision")), ret)
        classes[cls] = classes.get(cls, 0) + 1
        if ret is not None:
            if rec.get("decision") == "ACCEPT":
                mature_accept += 1
            else:
                mature_reject += 1
    tp = classes.get("TRUE_POSITIVE_WINNER", 0) + classes.get("TRUE_POSITIVE_BIG_WINNER", 0)
    fp = classes.get("FALSE_POSITIVE_LOSER", 0) + classes.get("FALSE_POSITIVE_SEVERE_LOSS", 0)
    miss = classes.get("MISSED_WINNER", 0) + classes.get("MISSED_BIG_WINNER", 0)
    avoided = classes.get("CORRECT_REJECT_LOSS_AVOIDED", 0) + classes.get("CORRECT_REJECT_SEVERE_LOSS_AVOIDED", 0)
    return {
        "mature_accepts": mature_accept,
        "mature_controls": mature_reject,
        "class_counts": classes,
        "accepted_winner_rate_pct": round(tp / mature_accept * 100.0, 4) if mature_accept else None,
        "accepted_loser_rate_pct": round(fp / mature_accept * 100.0, 4) if mature_accept else None,
        "missed_winner_rate_pct": round(miss / mature_reject * 100.0, 4) if mature_reject else None,
        "avoided_loser_rate_pct": round(avoided / mature_reject * 100.0, 4) if mature_reject else None,
        "total_records": len(records),
        "total_accept_records": len(accepted),
        "total_control_records": len(rejected),
    }


def _blocker_attribution(records: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec.get("decision") == "ACCEPT":
            continue
        ret = _checkpoint_return(rec, horizon)
        if ret is None:
            continue
        cls = _classify(str(rec.get("decision")), ret)
        for reason in _reason_list(rec):
            bucket = buckets.setdefault(reason, {"reason": reason, "n": 0, "returns": [], "missed_winners": 0, "avoided_losers": 0})
            bucket["n"] += 1
            bucket["returns"].append(ret)
            if cls in {"MISSED_WINNER", "MISSED_BIG_WINNER"}:
                bucket["missed_winners"] += 1
            if cls in {"CORRECT_REJECT_LOSS_AVOIDED", "CORRECT_REJECT_SEVERE_LOSS_AVOIDED"}:
                bucket["avoided_losers"] += 1
    out: list[dict[str, Any]] = []
    for bucket in buckets.values():
        n = int(bucket["n"])
        miss_rate = bucket["missed_winners"] / n * 100.0 if n else 0.0
        avoided_rate = bucket["avoided_losers"] / n * 100.0 if n else 0.0
        out.append({
            "reason": bucket["reason"],
            "n": n,
            "missed_winners": bucket["missed_winners"],
            "avoided_losers": bucket["avoided_losers"],
            "missed_winner_rate_pct": round(miss_rate, 4),
            "avoided_loser_rate_pct": round(avoided_rate, 4),
            "mean_friction_adjusted_return_pct": round(mean(bucket["returns"]), 6),
            "review_candidate": n >= MIN_BLOCKER_SAMPLE_FOR_REVIEW and miss_rate >= MIN_BLOCKER_MISS_RATE_FOR_REVIEW_PCT,
        })
    out.sort(key=lambda x: (x["review_candidate"], x["missed_winner_rate_pct"], x["n"]), reverse=True)
    return out


def _exceptions(records: list[dict[str, Any]], horizon: str) -> dict[str, Any]:
    missed: list[dict[str, Any]] = []
    false_positive: list[dict[str, Any]] = []
    for rec in records:
        ret = _checkpoint_return(rec, horizon)
        cls = _classify(str(rec.get("decision")), ret)
        if cls in {"MISSED_WINNER", "MISSED_BIG_WINNER"}:
            missed.append({
                "classification": cls,
                "return_pct": ret,
                "chain": rec.get("chain"),
                "token": rec.get("token"),
                "pair_address": rec.get("pair_address"),
                "event_at": rec.get("event_at"),
                "reasons": _reason_list(rec),
            })
        elif cls in {"FALSE_POSITIVE_LOSER", "FALSE_POSITIVE_SEVERE_LOSS"}:
            false_positive.append({
                "classification": cls,
                "return_pct": ret,
                "chain": rec.get("chain"),
                "token": rec.get("token"),
                "pair_address": rec.get("pair_address"),
                "event_at": rec.get("event_at"),
                "lane": rec.get("lane"),
            })
    missed.sort(key=lambda x: x.get("return_pct") or 0, reverse=True)
    false_positive.sort(key=lambda x: x.get("return_pct") or 0)
    return {"missed_winners": missed[:50], "false_positives": false_positive[:50]}


def _learning_queue(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = []
    for row in blockers:
        if not row.get("review_candidate"):
            continue
        queue.append({
            "reason": row.get("reason"),
            "evidence_n": row.get("n"),
            "missed_winner_rate_pct": row.get("missed_winner_rate_pct"),
            "avoided_loser_rate_pct": row.get("avoided_loser_rate_pct"),
            "action": "REVIEW_GATE_OR_WEIGHT_IN_SHADOW_ONLY",
            "production_change_allowed": False,
        })
    return queue[:20]


def run(data_dir: str | Path = DATA, now: datetime | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    reference = now or datetime.now(timezone.utc)
    alpha_ledger = _load(data_dir / "alpha-proof-ledger.json", {})
    alpha_report = _load(data_dir / "alpha-proof-report.json", {})
    if not isinstance(alpha_ledger, dict) or alpha_ledger.get("mode") != "FORWARD_ONLY_ALPHA_PROOF_V1":
        raise SystemExit("PROOF_OF_EDGE_REQUIRES_FORWARD_ALPHA_LEDGER")

    ledger_path = data_dir / LEDGER_PATH.name
    report_path = data_dir / REPORT_PATH.name
    ledger = _load(ledger_path, None)
    if not isinstance(ledger, dict) or ledger.get("mode") != MODE:
        ledger = _initial_ledger(reference, alpha_ledger.get("activation_at"))

    _sync_records(ledger, alpha_ledger, data_dir, reference)
    ledger["updated_at"] = reference.isoformat()
    records_dict = ledger.get("records") if isinstance(ledger.get("records"), dict) else {}
    integrity = _integrity(records_dict)
    records = [r for r in records_dict.values() if isinstance(r, dict)]
    matrices = {h: _horizon_matrix(records, h) for h in ANALYSIS_HORIZONS}
    blockers = _blocker_attribution(records, PRIMARY_HORIZON)
    exceptions = _exceptions(records, PRIMARY_HORIZON)

    report = {
        "version": 1,
        "mode": MODE,
        "updated_at": reference.isoformat(),
        "decision_snapshot_activation_at": ledger.get("decision_snapshot_activation_at"),
        "alpha_activation_at": ledger.get("alpha_activation_at"),
        "alpha_primary_proof_status": alpha_report.get("primary_proof_status"),
        "primary_horizon": PRIMARY_HORIZON,
        "record_count": len(records),
        "accepted_record_count": sum(r.get("decision") == "ACCEPT" for r in records),
        "control_record_count": sum(r.get("decision") != "ACCEPT" for r in records),
        "integrity": integrity,
        "decision_matrix": matrices,
        "blocker_attribution_24h": blockers,
        "exceptions_24h": exceptions,
        "learning_review_queue": _learning_queue(blockers),
        "guardrails": {
            "production_scoring_changed": False,
            "production_gates_changed": False,
            "telegram_alerts_changed": False,
            "research_only": True,
            "automatic_weight_mutation": False,
            "minimum_blocker_sample_for_review": MIN_BLOCKER_SAMPLE_FOR_REVIEW,
            "minimum_blocker_miss_rate_for_review_pct": MIN_BLOCKER_MISS_RATE_FOR_REVIEW_PCT,
        },
        "truth_notes": [
            "Decision context is frozen the first time Proof of Edge observes an alpha record and is SHA-256 protected.",
            "Existing immutable discovery evidence and first-reject snapshots are reused when available; otherwise only alpha entry facts are frozen.",
            "Outcome truth comes only from Alpha Proof immutable exact-pair checkpoints; no current-price hindsight is used for mature classifications.",
            "Missed winners and false positives are diagnostics only and cannot change production weights or gates automatically.",
            "All winner/loser labels use friction-adjusted returns at the stated horizon.",
        ],
    }
    _write(ledger_path, ledger)
    _write(report_path, report)
    print(json.dumps({
        "mode": MODE,
        "records": report["record_count"],
        "integrity": integrity["status"],
        "mature_24h_accepts": matrices[PRIMARY_HORIZON]["mature_accepts"],
        "mature_24h_controls": matrices[PRIMARY_HORIZON]["mature_controls"],
        "missed_winners_24h": len(exceptions["missed_winners"]),
        "false_positives_24h": len(exceptions["false_positives"]),
        "learning_review_queue": len(report["learning_review_queue"]),
    }, indent=2))
    return report


if __name__ == "__main__":
    run()
