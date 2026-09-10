#!/usr/bin/env python3
"""Static + data integrity audit for Wallet500 pipeline ownership and truth rules."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
SRC = ROOT / "src" / "wallet500"

CANONICAL_DECISION_FILES = {
    "data/candidate-evidence-envelope.json",
    "data/real-alerts.json",
    "data/revival-funnel-diagnostics.json",
    "data/cross-signal-fusion-v2.json",
    "data/system-health.json",
    "data/strict-validation.json",
    "data/production-status.json",
    "data/decision-snapshot-integrity.json",
    "data/decision-generation.json",
}
ALLOWED_CANONICAL_PUBLISHERS = {
    "candidate-evidence-envelope.yml",
    "live-scan.yml",
}
CANONICAL_CONCURRENCY_GROUP = "wallet500-live-scan-publisher"


def _workflow_direct_writes(text: str) -> set[str]:
    """Conservative writer detection.

    A workflow counts as a writer only when it contains a git publication
    primitive and references the file. This catches multiline atomic_publish
    invocations as well as direct git-add publishers.
    """
    publishing = any(x in text for x in ("git push", "atomic_publish.py", "publish_verified_snapshot.py"))
    if not publishing:
        return set()
    return {f for f in CANONICAL_DECISION_FILES if f in text}


def audit() -> dict:
    findings: list[dict] = []
    writers: dict[str, list[str]] = {}
    workflow_count = 0
    concurrency: dict[str, str | None] = {}
    for p in sorted(WF.glob("*.yml")):
        workflow_count += 1
        text = p.read_text(encoding="utf-8")
        for f in _workflow_direct_writes(text):
            writers.setdefault(f, []).append(p.name)
        m = re.search(r"(?ms)^concurrency:\s*\n(?:\s+.*\n)*?\s+group:\s*([^\n#]+)", text)
        concurrency[p.name] = m.group(1).strip().strip("'\"") if m else None

    for f in sorted(CANONICAL_DECISION_FILES):
        owners = sorted(set(writers.get(f, [])))
        illegal = [x for x in owners if x not in ALLOWED_CANONICAL_PUBLISHERS]
        if illegal:
            findings.append({"severity": "CRITICAL", "code": "CANONICAL_MULTI_WRITER", "file": f, "writers": owners, "illegal": illegal})
        serialized = [x for x in owners if concurrency.get(x) == CANONICAL_CONCURRENCY_GROUP]
        if len(owners) > 1 and len(serialized) != len(owners):
            findings.append({"severity": "CRITICAL", "code": "CANONICAL_WRITERS_NOT_SERIALIZED", "file": f, "writers": owners, "serialized": serialized})

    legacy_hits = []
    for p in sorted(SRC.glob("*.py")):
        text = p.read_text(encoding="utf-8")
        if "market_age_verified_60d_plus" in text and p.name not in {"truth_contract.py", "normalize_age_aliases.py"}:
            legacy_hits.append(str(p.relative_to(ROOT)))
    if legacy_hits:
        findings.append({"severity": "WARN", "code": "LEGACY_60D_ALIAS_REMAINS_READ_COMPAT", "files": legacy_hits})

    silent_truth_loaders = []
    truth_modules = {
        "candidate_evidence_envelope.py", "real_alerts.py", "decision_snapshot_guard.py",
        "production_status.py", "strict_validation.py", "system_health.py",
    }
    for name in truth_modules:
        p = SRC / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if re.search(r"except Exception:\s*\n\s*return (default|\{\}|\[\])", text):
            silent_truth_loaders.append(str(p.relative_to(ROOT)))
    if silent_truth_loaders:
        findings.append({"severity": "WARN", "code": "SILENT_TRUTH_JSON_DEFAULT_REMAINS", "files": silent_truth_loaders})

    policy = {
        "research_min_age_days": 90,
        "research_min_liquidity_usd": 15000,
        "production_min_age_days": 180,
        "production_min_liquidity_usd": 50000,
        "new_token_attention_pct": 0,
    }
    critical = [x for x in findings if x["severity"] == "CRITICAL"]
    return {
        "version": 2,
        "status": "FAIL" if critical else "PASS_WITH_WARNINGS" if findings else "PASS",
        "workflow_count": workflow_count,
        "canonical_writer_map": {k: sorted(set(v)) for k, v in sorted(writers.items()) if k in CANONICAL_DECISION_FILES},
        "canonical_writer_concurrency": {x: concurrency.get(x) for x in sorted(ALLOWED_CANONICAL_PUBLISHERS)},
        "policy_expected": policy,
        "findings": findings,
        "critical_count": len(critical),
        "warning_count": sum(1 for x in findings if x["severity"] == "WARN"),
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    Path("data/pipeline-integrity-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1 if result["critical_count"] else 0)
