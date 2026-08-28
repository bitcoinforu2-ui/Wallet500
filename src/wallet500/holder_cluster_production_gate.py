"""Wallet500 production holder/cluster quarantine gate.

Truth-first policy:
- BLOCK: remove from live path.
- REVIEW or missing evidence: quarantine; never Live/Alert.
- PASS is allowed only with cluster_verified=true.

This module writes a separate production-safe candidate file first. The caller
must explicitly choose that output for downstream evidence/alerts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT = Path(os.getenv("HOLDER_CLUSTER_PRODUCTION_INPUT", "data/active-qualified-candidates.json"))
GATE = Path(os.getenv("HOLDER_CLUSTER_GATE_INPUT", "data/holder-cluster-gate.json"))
OUTPUT = Path(os.getenv("HOLDER_CLUSTER_PRODUCTION_OUTPUT", "data/holder-cluster-production-qualified.json"))
QUARANTINE = Path(os.getenv("HOLDER_CLUSTER_QUARANTINE_OUTPUT", "data/holder-cluster-quarantine.json"))
BLOCKED = Path(os.getenv("HOLDER_CLUSTER_BLOCKED_OUTPUT", "data/holder-cluster-production-blocked.json"))
REPORT = Path(os.getenv("HOLDER_CLUSTER_PRODUCTION_REPORT", "data/holder-cluster-production-report.json"))


def _load(path: Path) -> Any:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("rows", "candidates", "active", "qualified"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _key(row: dict[str, Any]) -> str:
    chain = str(row.get("chain") or "").strip().lower()
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or row.get("address") or "").strip().lower()
    pair = str(row.get("pair_address") or row.get("pair") or "").strip().lower()
    return f"{chain}|{token}|{pair}"


def apply_gate(candidates: list[dict[str, Any]], gate_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = {_key(r): r for r in gate_rows if _key(r) != "||"}
    promoted: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for candidate in candidates:
        key = _key(candidate)
        evidence = by_key.get(key)
        if evidence is None:
            quarantine.append({**candidate, "holder_cluster_production_status": "REVIEW", "holder_cluster_reason": "HOLDER_CLUSTER_EVIDENCE_MISSING"})
            continue

        status = str(evidence.get("status") or "REVIEW").upper()
        verified = evidence.get("cluster_verified") is True
        reasons = evidence.get("reasons") or []
        annotation = {
            "holder_cluster_production_status": status,
            "holder_cluster_verified": verified,
            "holder_cluster_reasons": reasons,
        }
        enriched = {**candidate, **annotation}

        if status == "BLOCK":
            blocked.append(enriched)
        elif status == "PASS" and verified:
            promoted.append(enriched)
        else:
            # REVIEW, malformed status, or PASS without verification all fail closed.
            enriched["holder_cluster_production_status"] = "REVIEW"
            if status == "PASS" and not verified:
                enriched["holder_cluster_reason"] = "PASS_WITHOUT_CLUSTER_VERIFICATION"
            quarantine.append(enriched)

    return promoted, quarantine, blocked


def main() -> None:
    candidates = _rows(_load(INPUT))
    gate_rows = _rows(_load(GATE))
    promoted, quarantine, blocked = apply_gate(candidates, gate_rows)
    now = datetime.now(timezone.utc).isoformat()

    OUTPUT.write_text(json.dumps(promoted, indent=2))
    QUARANTINE.write_text(json.dumps(quarantine, indent=2))
    BLOCKED.write_text(json.dumps(blocked, indent=2))
    report = {
        "updated_at": now,
        "mode": "PRODUCTION_FAIL_CLOSED",
        "input_count": len(candidates),
        "promoted_count": len(promoted),
        "quarantine_count": len(quarantine),
        "blocked_count": len(blocked),
        "downstream_input": str(OUTPUT),
        "policy": "Only PASS + cluster_verified=true may reach Live/Alert; REVIEW/missing evidence quarantined; BLOCK rejected.",
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print("HOLDER CLUSTER PRODUCTION:", report)


if __name__ == "__main__":
    main()
