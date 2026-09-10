#!/usr/bin/env python3
"""Static + data integrity audit for Wallet500 pipeline ownership and truth rules."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
SRC = ROOT / "src" / "wallet500"

# Production-authoritative / dashboard-decision files belong to one publication
# boundary. Research/advisory surfaces may refresh separately but never authorize
# production.
CANONICAL_DECISION_FILES = {
    "data/candidate-evidence-envelope.json",
    "data/real-alerts.json",
    "data/revival-funnel-diagnostics.json",
    "data/system-health.json",
    "data/strict-validation.json",
    "data/production-status.json",
    "data/decision-snapshot-integrity.json",
    "data/decision-generation.json",
}
SOLE_CANONICAL_PUBLISHER = "verified-publisher.yml"
PATH_RE = re.compile(r"data/[A-Za-z0-9_.\-/]+\.json")


def _workflow_direct_writes(text: str) -> set[str]:
    out: set[str] = set()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if "git add " in stripped:
            out.update(PATH_RE.findall(stripped))
        if "atomic_publish.py" in stripped:
            block = [stripped]
            while block[-1].rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                block.append(lines[i].strip())
            out.update(PATH_RE.findall("\n".join(block)))
        i += 1
    return out & CANONICAL_DECISION_FILES


def audit() -> dict:
    findings: list[dict] = []
    direct_writers: dict[str, list[str]] = {}
    workflow_count = 0
    for p in sorted(WF.glob("*.yml")):
        workflow_count += 1
        text = p.read_text(encoding="utf-8")
        for f in _workflow_direct_writes(text):
            direct_writers.setdefault(f, []).append(p.name)

    # verified-publisher applies the immutable Live Scan artifact via
    # publish_verified_snapshot.py, so it owns every canonical decision surface
    # even though those paths are enumerated in the artifact manifest rather than
    # literally in the workflow YAML.
    writer_map: dict[str, list[str]] = {}
    for f in sorted(CANONICAL_DECISION_FILES):
        owners = sorted(set(direct_writers.get(f, [])) | {SOLE_CANONICAL_PUBLISHER})
        writer_map[f] = owners
        illegal = [x for x in owners if x != SOLE_CANONICAL_PUBLISHER]
        if illegal:
            findings.append({
                "severity": "CRITICAL",
                "code": "CANONICAL_MULTI_WRITER",
                "file": f,
                "writers": owners,
                "illegal": illegal,
                "required_owner": SOLE_CANONICAL_PUBLISHER,
            })

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
        findings.append({"severity": "WARN", "code": "SILENT_TRUTH_JSON_DEFAULT_REMAINS_FENCED_BY_PREFLIGHT", "files": silent_truth_loaders})

    policy = {
        "research_min_age_days": 90,
        "research_min_liquidity_usd": 15000,
        "production_min_age_days": 180,
        "production_min_liquidity_usd": 50000,
        "new_token_attention_pct": 0,
        "exact_pair_required": True,
        "automatic_buy": False,
    }
    critical = [x for x in findings if x["severity"] == "CRITICAL"]
    return {
        "version": 5,
        "status": "FAIL" if critical else "PASS_WITH_WARNINGS" if findings else "PASS",
        "workflow_count": workflow_count,
        "sole_canonical_publisher": SOLE_CANONICAL_PUBLISHER,
        "canonical_writer_map": writer_map,
        "policy_expected": policy,
        "advisory_excluded_from_canonical_generation": [
            "data/cross-signal-fusion-v2.json",
            "data/research-decision-engine.json",
            "data/liquidity-recovery-shadow.json",
        ],
        "findings": findings,
        "critical_count": len(critical),
        "warning_count": sum(1 for x in findings if x["severity"] == "WARN"),
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    Path("data/pipeline-integrity-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1 if result["critical_count"] else 0)
