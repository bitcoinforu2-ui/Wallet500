from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POLICY_PATH = DATA / "close-watch-intelligence-policy.json"
INTELLIGENCE_PATH = DATA / "close-watch-intelligence.json"

EVM_NETWORKS = {
    "ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "linea", "zksync", "mantle",
    "scroll", "blast",
}
NETWORK_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def _network(value: object) -> str:
    raw = str(value or "").strip().lower()
    return NETWORK_ALIASES.get(raw, raw)


def _address(value: object, chain: str) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM_NETWORKS else raw


def _identity(row: dict) -> tuple[str, str, str] | None:
    chain = _network(row.get("network") or row.get("chain"))
    contract = _address(row.get("contract") or row.get("token_address") or row.get("token") or row.get("mint"), chain)
    pair = _address(row.get("pair") or row.get("pair_address"), chain)
    if not chain or not contract or not pair:
        return None
    return chain, contract, pair


def _identity_key(identity: tuple[str, str, str]) -> str:
    return "|".join(identity)


def _parse(value: object) -> datetime | None:
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


def _age_seconds(value: object, now_dt: datetime) -> float | None:
    dt = _parse(value)
    if dt is None:
        return None
    return (now_dt - dt).total_seconds()


def _append_unique(row: dict, key: str, values: list[str]) -> None:
    current = [str(value) for value in (row.get(key) or []) if str(value).strip()]
    for value in values:
        if value not in current:
            current.append(value)
    row[key] = current


def _block(row: dict, reasons: list[str], status: str) -> None:
    row["pre_intelligence_actionable_research_alert"] = row.get("actionable_research_alert") is True
    row["actionable_research_alert"] = False
    row["intelligence_used_in_actionable_decision"] = False
    row["intelligence_delivery_status"] = status
    blockers = [str(value) for value in (row.get("blockers") or []) if str(value).strip()]
    for reason in reasons:
        marker = f"INTELLIGENCE_GATE:{reason}"
        if marker not in blockers:
            blockers.append(marker)
    row["blockers"] = blockers


def _token_summary(token: dict) -> dict:
    family_scores = token.get("family_scores") if isinstance(token.get("family_scores"), dict) else {}
    positive = sorted(
        ((name, float(score)) for name, score in family_scores.items() if float(score) > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    negative = sorted(
        ((name, float(score)) for name, score in family_scores.items() if float(score) < 0),
        key=lambda item: item[1],
    )
    return {
        "score": float(token.get("score") or 0),
        "label": str(token.get("label") or "WATCH"),
        "independent_positive_families": int(token.get("independent_positive_families") or 0),
        "positive_family_names": list(token.get("positive_family_names") or []),
        "evidence_count": int(token.get("evidence_count") or 0),
        "hard_risks": list(token.get("hard_risks") or []),
        "family_scores": family_scores,
        "top_positive_families": [{"family": name, "score": score} for name, score in positive[:6]],
        "top_negative_families": [{"family": name, "score": score} for name, score in negative[:4]],
        "updated_at": token.get("updated_at"),
    }


def apply_gate(payload: dict, intelligence: dict, policy: dict, now_dt: datetime | None = None) -> tuple[dict, dict]:
    now_dt = now_dt or datetime.now(timezone.utc)
    gate_policy = policy.get("production_gate") if isinstance(policy.get("production_gate"), dict) else {}
    enabled = gate_policy.get("enabled") is True
    fail_closed = gate_policy.get("fail_closed", True) is True
    minimum_score = float(gate_policy.get("minimum_score", 55))
    minimum_families = int(gate_policy.get("minimum_independent_positive_families", 4))
    minimum_evidence = int(gate_policy.get("minimum_evidence_count", 4))
    max_snapshot_age = int(gate_policy.get("maximum_snapshot_age_seconds", 2700))
    max_token_age = int(gate_policy.get("maximum_token_age_seconds", max_snapshot_age))
    allowed_labels = set(gate_policy.get("allowed_labels") or ["CONFLUENCE", "STRONG_CONFLUENCE", "EXCEPTIONAL_CONFLUENCE"])
    waiting_status = str(gate_policy.get("missing_or_stale_status") or "WAITING_FOR_INTELLIGENCE")

    result = deepcopy(payload) if isinstance(payload, dict) else {}
    tokens = [row for row in (intelligence.get("tokens") or []) if isinstance(row, dict)] if isinstance(intelligence, dict) else []
    token_index = {_identity(row): row for row in tokens if _identity(row) is not None}
    snapshot_age = _age_seconds(intelligence.get("generated_at") if isinstance(intelligence, dict) else None, now_dt)
    snapshot_fresh = snapshot_age is not None and -120 <= snapshot_age <= max_snapshot_age

    passed_rows = []
    blocked_rows = []
    untouched_rows = 0
    actionable_before = 0
    actionable_after = 0

    alerts = result.get("alerts") if isinstance(result.get("alerts"), list) else []
    for row in alerts:
        if not isinstance(row, dict):
            continue
        if row.get("actionable_research_alert") is not True:
            untouched_rows += 1
            continue
        actionable_before += 1

        reasons = []
        identity = _identity(row)
        token = token_index.get(identity) if identity is not None else None
        if not enabled:
            reasons.append("PRODUCTION_GATE_DISABLED")
        if not snapshot_fresh:
            reasons.append("INTELLIGENCE_SNAPSHOT_MISSING_OR_STALE")
        if identity is None:
            reasons.append("CANONICAL_ALERT_EXACT_IDENTITY_MISSING")
        if token is None:
            reasons.append("EXACT_INTELLIGENCE_IDENTITY_MISSING")

        summary = None
        if token is not None:
            summary = _token_summary(token)
            token_age = _age_seconds(token.get("updated_at"), now_dt)
            if token_age is None or token_age < -120 or token_age > max_token_age:
                reasons.append("TOKEN_INTELLIGENCE_MISSING_OR_STALE")
            if summary["score"] < minimum_score:
                reasons.append("FUSION_SCORE_BELOW_MINIMUM")
            if summary["label"] not in allowed_labels:
                reasons.append("FUSION_LABEL_NOT_ACTIONABLE")
            if summary["independent_positive_families"] < minimum_families:
                reasons.append("INSUFFICIENT_INDEPENDENT_FAMILIES")
            if summary["evidence_count"] < minimum_evidence:
                reasons.append("INSUFFICIENT_FRESH_EVIDENCE")
            if gate_policy.get("hard_risks_must_be_empty", True) is True and summary["hard_risks"]:
                reasons.append("HARD_RISK_PRESENT")

        row["intelligence_fusion"] = summary or {
            "score": None,
            "label": "MISSING",
            "independent_positive_families": 0,
            "evidence_count": 0,
            "hard_risks": [],
            "updated_at": None,
        }
        row["intelligence_gate"] = {
            "passed": not reasons,
            "reasons": reasons,
            "policy_version": policy.get("version"),
            "minimum_score": minimum_score,
            "minimum_independent_positive_families": minimum_families,
            "minimum_evidence_count": minimum_evidence,
            "maximum_snapshot_age_seconds": max_snapshot_age,
            "snapshot_generated_at": intelligence.get("generated_at") if isinstance(intelligence, dict) else None,
            "snapshot_age_seconds": round(snapshot_age, 1) if snapshot_age is not None else None,
            "checked_at": now_dt.isoformat(),
            "exact_identity_key": _identity_key(identity) if identity is not None else None,
        }

        if reasons:
            if fail_closed:
                _block(row, reasons, waiting_status)
            blocked_rows.append({
                "symbol": row.get("symbol"),
                "identity_key": _identity_key(identity) if identity else None,
                "reasons": reasons,
            })
            continue

        row["intelligence_used_in_actionable_decision"] = True
        row["intelligence_delivery_status"] = "FULL_INTELLIGENCE_ACTIONABLE"
        row["intelligence_revalidated_at"] = summary["updated_at"]
        _append_unique(row, "source_lanes", ["INTELLIGENCE_FUSION"])
        positive_lines = [f"INTEL {item['family']} {item['score']:+.2f}" for item in summary["top_positive_families"]]
        _append_unique(row, "evidence_positive_lanes", positive_lines)
        _append_unique(
            row,
            "evidence_verified_lanes",
            [
                f"INTELLIGENCE_GATE PASS {summary['score']:.1f}/100 {summary['label']}",
                f"INTEL_FAMILIES {summary['independent_positive_families']}",
                f"INTELLIGENCE_UPDATED {summary['updated_at']}",
            ],
        )
        actionable_after += 1
        passed_rows.append({
            "symbol": row.get("symbol"),
            "identity_key": _identity_key(identity),
            "score": summary["score"],
            "label": summary["label"],
            "independent_positive_families": summary["independent_positive_families"],
            "evidence_count": summary["evidence_count"],
        })

    result["production_intelligence_gate"] = {
        "version": 1,
        "checked_at": now_dt.isoformat(),
        "policy_version": policy.get("version"),
        "fail_closed": fail_closed,
        "exact_identity_required": True,
        "snapshot_generated_at": intelligence.get("generated_at") if isinstance(intelligence, dict) else None,
        "snapshot_age_seconds": round(snapshot_age, 1) if snapshot_age is not None else None,
        "snapshot_fresh": snapshot_fresh,
        "actionable_before": actionable_before,
        "actionable_after": actionable_after,
        "blocked": len(blocked_rows),
        "passed": len(passed_rows),
        "untouched_non_actionable": untouched_rows,
    }
    result["intelligence_gate_counts"] = {
        "actionable_before": actionable_before,
        "actionable_after": actionable_after,
        "blocked": len(blocked_rows),
        "passed": len(passed_rows),
    }

    report = {
        "version": 1,
        "generated_at": now_dt.isoformat(),
        "policy_version": policy.get("version"),
        "fail_closed": fail_closed,
        "snapshot_fresh": snapshot_fresh,
        "snapshot_generated_at": intelligence.get("generated_at") if isinstance(intelligence, dict) else None,
        "snapshot_age_seconds": round(snapshot_age, 1) if snapshot_age is not None else None,
        "actionable_before": actionable_before,
        "actionable_after": actionable_after,
        "passed": passed_rows,
        "blocked": blocked_rows,
        "truth_contract": {
            "exact_identity_match_required": True,
            "missing_or_stale_intelligence_blocks_actionable_delivery": True,
            "hard_risk_blocks_actionable_delivery": True,
            "automatic_trade": False,
            "rows_are_preserved_not_deleted": True,
        },
    }
    return result, report


def main() -> int:
    input_name = os.getenv("WALLET500_INTELLIGENCE_GATE_INPUT", "pre-alert-forensics-real-alerts.json")
    output_name = os.getenv("WALLET500_INTELLIGENCE_GATE_OUTPUT", "intelligence-gated-real-alerts.json")
    report_name = os.getenv("WALLET500_INTELLIGENCE_GATE_REPORT", "intelligence-gate-report.json")
    input_path = DATA / input_name
    output_path = DATA / output_name
    report_path = DATA / report_name

    payload = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else {}
    intelligence = json.loads(INTELLIGENCE_PATH.read_text(encoding="utf-8")) if INTELLIGENCE_PATH.exists() else {}
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    gated, report = apply_gate(payload, intelligence, policy)
    output_path.write_text(json.dumps(gated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "actionable_before": report["actionable_before"], "actionable_after": report["actionable_after"], "blocked": len(report["blocked"]), "snapshot_fresh": report["snapshot_fresh"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
