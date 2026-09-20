#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PROD_DIRS = (ROOT / "src" / "wallet500", ROOT / "scripts")
DATA = ROOT / "data"

SEV = {"INFO": 0, "WARN": 1, "HIGH": 2, "CRITICAL": 3}
CORE_HINTS = (
    "real_alert", "decision", "production", "telegram", "cex", "revival",
    "unified", "watch", "candidate", "identity", "publisher", "guard",
    "discovery", "holder", "wallet", "liquidity", "signal",
)
WRITE_HINT_RE = re.compile(
    r"(serialized_publish\.py|atomic_publish\.py|publish_verified_snapshot\.py|"
    r"\bgit\s+add\b|\bgit\s+commit\b|\bgit\s+push\b|\.write_text\(|write_text\()",
    re.I,
)
DATA_PATH_RE = re.compile(r"data/[A-Za-z0-9_.\-/]+\.json")
TELEGRAM_RE = re.compile(r"(api\.telegram\.org|sendMessage|TELEGRAM_BOT_TOKEN)", re.I)
NETWORK_NAMES = {
    "urlopen", "get", "post", "request", "put", "delete", "head", "patch",
}
STATEFUL_FILE_HINTS = (
    "state", "dedupe", "ledger", "registry", "history", "report", "alerts",
    "watch", "decision", "candidate", "evidence",
)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def finding(code: str, severity: str, message: str, **context: Any) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "context": context,
    }


def is_core(path: Path) -> bool:
    low = str(path).lower()
    return any(x in low for x in CORE_HINTS)


def handler_is_silent(node: ast.ExceptHandler) -> bool:
    meaningful = []
    for item in node.body:
        if isinstance(item, (ast.Pass, ast.Continue, ast.Break)):
            continue
        if isinstance(item, ast.Return):
            v = item.value
            if v is None or isinstance(v, (ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Set)):
                continue
        if isinstance(item, ast.Assign) and isinstance(item.value, (ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Set)):
            continue
        meaningful.append(item)
    return not meaningful


def call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts = [f.attr]
        cur = f.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def has_timeout(node: ast.Call) -> bool:
    return any(k.arg == "timeout" for k in node.keywords if k.arg)


def scan_python() -> tuple[list[dict], dict]:
    findings: list[dict] = []
    metrics = {
        "files": 0,
        "syntax_errors": 0,
        "bare_except": 0,
        "silent_broad_except": 0,
        "network_without_timeout": 0,
        "telegram_code_files": [],
        "core_caps": [],
    }
    for base in PROD_DIRS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            metrics["files"] += 1
            rel = str(path.relative_to(ROOT))
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as exc:
                findings.append(finding("PYTHON_READ_FAILURE", "CRITICAL", f"Cannot read {rel}", error=type(exc).__name__))
                continue
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError as exc:
                metrics["syntax_errors"] += 1
                findings.append(finding("PYTHON_SYNTAX_ERROR", "CRITICAL", f"Syntax error in {rel}", line=exc.lineno, detail=str(exc)))
                continue

            if TELEGRAM_RE.search(text):
                metrics["telegram_code_files"].append(rel)

            if is_core(path):
                for m in re.finditer(r"(?m)^\s*([A-Z][A-Z0-9_]*(?:MAX|MIN|LIMIT|CAP|THRESHOLD)[A-Z0-9_]*)\s*=\s*([^\n#]+)", text):
                    metrics["core_caps"].append({"file": rel, "name": m.group(1), "value": m.group(2).strip()[:120]})

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        metrics["bare_except"] += 1
                        findings.append(finding(
                            "BARE_EXCEPT_IN_PRODUCTION",
                            "HIGH" if is_core(path) else "WARN",
                            f"Bare except can hide a real engine failure in {rel}",
                            file=rel, line=getattr(node, "lineno", None),
                        ))
                    elif isinstance(node.type, ast.Name) and node.type.id == "Exception" and handler_is_silent(node):
                        metrics["silent_broad_except"] += 1
                        findings.append(finding(
                            "SILENT_BROAD_EXCEPTION",
                            "HIGH" if is_core(path) else "WARN",
                            f"Broad Exception is converted to a default/skip in {rel}",
                            file=rel, line=getattr(node, "lineno", None),
                        ))
                elif isinstance(node, ast.Call):
                    name = call_name(node)
                    tail = name.split(".")[-1]
                    networkish = (
                        "urlopen" in name
                        or name.startswith("requests.")
                        or name.startswith("httpx.")
                    )
                    if networkish and tail in NETWORK_NAMES and not has_timeout(node):
                        metrics["network_without_timeout"] += 1
                        findings.append(finding(
                            "NETWORK_CALL_WITHOUT_TIMEOUT",
                            "HIGH" if is_core(path) else "WARN",
                            f"Network call has no explicit timeout in {rel}",
                            file=rel, line=getattr(node, "lineno", None), call=name,
                        ))
    return findings, metrics


def parse_workflow_name(text: str, fallback: str) -> str:
    m = re.search(r"(?m)^name:\s*(.+?)\s*$", text)
    return (m.group(1).strip().strip("'\"") if m else fallback)


def scan_workflows() -> tuple[list[dict], dict]:
    findings: list[dict] = []
    metrics: dict[str, Any] = {
        "workflow_count": 0,
        "write_workflows": [],
        "workflow_run_without_success_guard": [],
        "pull_request_checkout_main": [],
        "cancel_stateful_writers": [],
        "potential_writers": {},
        "telegram_workflows": [],
    }
    potential_writers: dict[str, set[str]] = defaultdict(set)

    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        metrics["workflow_count"] += 1
        rel = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8")
        name = parse_workflow_name(text, path.name)
        contents_write = bool(re.search(r"(?m)^\s*contents:\s*write\s*$", text))
        has_concurrency = bool(re.search(r"(?m)^concurrency:\s*$", text))
        cancel_true = bool(re.search(r"cancel-in-progress:\s*true", text))
        workflow_run = "workflow_run:" in text
        success_guard = bool(re.search(r"workflow_run\.conclusion\s*==\s*['\"]success['\"]", text))
        pull_request = bool(re.search(r"(?m)^\s*pull_request:\s*$", text))
        checkout_main = bool(re.search(r"actions/checkout@[^\n]+[\s\S]{0,350}?ref:\s*main\b", text))
        ignore_error = bool(re.search(r"continue-on-error:\s*true|\|\|\s*true|\bset\s+\+e\b", text))
        telegram = bool(TELEGRAM_RE.search(text))

        if contents_write:
            metrics["write_workflows"].append(rel)
            if not has_concurrency:
                findings.append(finding(
                    "WRITER_WORKFLOW_WITHOUT_CONCURRENCY",
                    "HIGH",
                    f"{name} writes repository content without a workflow concurrency boundary",
                    workflow=rel,
                ))
        if workflow_run and not success_guard:
            metrics["workflow_run_without_success_guard"].append(rel)
            findings.append(finding(
                "WORKFLOW_RUN_DOES_NOT_REQUIRE_SUCCESS",
                "HIGH",
                f"{name} can run after a failed upstream workflow",
                workflow=rel,
            ))
        if pull_request and checkout_main:
            metrics["pull_request_checkout_main"].append(rel)
            findings.append(finding(
                "PR_CI_CHECKS_OUT_MAIN",
                "CRITICAL",
                f"{name} is a PR workflow but explicitly checks out main, so it can validate the wrong code",
                workflow=rel,
            ))
        if contents_write and cancel_true:
            metrics["cancel_stateful_writers"].append(rel)
            findings.append(finding(
                "STATEFUL_WRITER_CANCEL_IN_PROGRESS",
                "HIGH",
                f"{name} can cancel a writer run while it may be updating state/external delivery",
                workflow=rel,
            ))
        if ignore_error and is_core(path):
            findings.append(finding(
                "CORE_WORKFLOW_IGNORES_COMMAND_FAILURE",
                "WARN",
                f"{name} contains explicit error suppression; verify the later gate really re-enforces failure",
                workflow=rel,
            ))
        if telegram:
            metrics["telegram_workflows"].append(rel)

        if WRITE_HINT_RE.search(text):
            refs=set(DATA_PATH_RE.findall(text))
            for ref in refs:
                potential_writers[ref].add(rel)

    multi = []
    for data_path, owners in sorted(potential_writers.items()):
        if len(owners) > 1:
            row={"path": data_path, "writers": sorted(owners)}
            multi.append(row)
            stateful = any(h in data_path.lower() for h in STATEFUL_FILE_HINTS)
            findings.append(finding(
                "POTENTIAL_MULTI_WRITER_DATA_FILE",
                "HIGH" if stateful else "WARN",
                f"{data_path} is referenced by multiple write-capable workflows",
                file=data_path, workflows=sorted(owners),
            ))
    metrics["potential_writers"] = {k: sorted(v) for k, v in potential_writers.items()}
    metrics["multi_writer_count"] = len(multi)
    metrics["multi_writers"] = multi
    return findings, metrics


def dt(value: Any) -> datetime | None:
    raw=str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw=raw[:-1]+"+00:00"
        x=datetime.fromisoformat(raw)
        if x.tzinfo is None:
            x=x.replace(tzinfo=timezone.utc)
        return x.astimezone(timezone.utc)
    except Exception:
        return None


def runtime_audit() -> tuple[list[dict], dict]:
    findings: list[dict] = []
    files = {
        "system_health": "system-health.json",
        "discovery": "discovery-health.json",
        "identity": "cex-spot-identity-radar.json",
        "revival": "cex-revival-radar.json",
        "fast_promotion": "cex-fast-promotion-report.json",
        "fast_alerts": "cex-fast-real-alerts.json",
        "handoff": "cex-sensor-handoff.json",
        "final_buy": "user-watch-final-buy-report.json",
        "funnel": "revival-funnel-diagnostics.json",
        "decision_integrity": "decision-snapshot-integrity.json",
    }
    docs={k: load_json(DATA / v) for k,v in files.items()}
    metrics: dict[str, Any] = {}

    discovery=docs["discovery"] or {}
    caps=discovery.get("cap_saturated") if isinstance(discovery,dict) else {}
    saturated=sorted([k for k,v in (caps or {}).items() if v is True])
    metrics["discovery_cap_saturated"] = saturated
    if saturated:
        findings.append(finding(
            "DISCOVERY_HARD_CAP_SATURATED",
            "HIGH",
            "Discovery is filling its per-chain result cap; eligible candidates can be missed purely by truncation",
            chains=saturated, effective_limits=discovery.get("effective_limits"),
        ))
    errors=list(discovery.get("recent_errors") or []) if isinstance(discovery,dict) else []
    if errors and all(v=="HEALTHY" for v in (discovery.get("health") or {}).values()):
        findings.append(finding(
            "DISCOVERY_HEALTH_MASKS_PROVIDER_FAILURES",
            "HIGH",
            "Discovery reports HEALTHY while live providers are returning errors",
            errors=errors[:12],
        ))

    identity=docs["identity"] or {}
    pc=identity.get("platform_catalog") if isinstance(identity,dict) else {}
    metrics["identity_platform_catalog"] = pc
    if isinstance(pc,dict) and str(pc.get("status") or "").upper().startswith("DEGRADED"):
        sev="CRITICAL" if int(pc.get("requested_coin_ids") or 0)>0 and int(pc.get("resolved_coin_ids") or 0)==0 else "HIGH"
        findings.append(finding(
            "CEX_IDENTITY_PLATFORM_CATALOG_DEGRADED",
            sev,
            "CEX exact-identity resolution is degraded; promotion can fail even when the market signal is real",
            platform_catalog=pc,
        ))

    handoff=docs["handoff"] or {}
    rows=[x for x in (handoff.get("rows") or []) if isinstance(x,dict)] if isinstance(handoff,dict) else []
    cex_led=[x for x in rows if (x.get("cex_sensor") or {}).get("cex_led") is True]
    escalated=[x for x in rows if str(x.get("status") or "").upper() in {"CEX_LED_REVIVAL_CLOSE_WATCH","CEX_IDENTITY_PENDING_CLOSE_WATCH"}]
    metrics["cex_handoff"]={"rows":len(rows),"cex_led":len(cex_led),"escalated":len(escalated)}

    final_buy=docs["final_buy"] or {}
    cex_candidates=final_buy.get("cex_candidate_count") if isinstance(final_buy,dict) else None
    cex_decisions=final_buy.get("cex_decisions") if isinstance(final_buy,dict) else None
    metrics["final_buy"]={
        "generated_at": final_buy.get("generated_at") if isinstance(final_buy,dict) else None,
        "buy_zone_count": final_buy.get("buy_zone_count") if isinstance(final_buy,dict) else None,
        "pre_buy_count": final_buy.get("pre_buy_count") if isinstance(final_buy,dict) else None,
        "cex_candidate_count": cex_candidates,
        "has_cex_decisions": isinstance(cex_decisions,list),
    }
    if cex_led and cex_candidates is None and not isinstance(cex_decisions,list):
        findings.append(finding(
            "CEX_HANDOFF_DISCONNECTED_FROM_FINAL_BUY",
            "CRITICAL",
            "CEX-led signals are reaching the handoff, but the final BUY report has no CEX execution lane at all",
            cex_led=len(cex_led), escalated=len(escalated),
        ))

    fast=docs["fast_promotion"] or {}
    fast_alerts=docs["fast_alerts"] or {}
    metrics["fast_promotion"]={
        "eligible_count": fast.get("eligible_count") if isinstance(fast,dict) else None,
        "alerts": len(fast_alerts.get("alerts") or []) if isinstance(fast_alerts,dict) else None,
    }
    revival=docs["revival"] or {}
    rev_alerts=[x for x in (revival.get("alerts") or []) if isinstance(x,dict)] if isinstance(revival,dict) else []
    strong_pending=[
        x for x in rev_alerts
        if (float(x.get("cex_revival_score") or x.get("spot_revival_score") or x.get("score") or 0) >= 45)
        and x.get("actionable") is False
        and str(x.get("identity_status") or "") in {"IDENTITY_PENDING","IDENTITY_RESOLVED_PAIR_PENDING"}
    ]
    if strong_pending:
        findings.append(finding(
            "STRONG_CEX_SIGNALS_BLOCKED_AT_IDENTITY_PROMOTION",
            "HIGH",
            "Strong multi-exchange signals are present but remain non-actionable at the identity/pair promotion boundary",
            count=len(strong_pending),
            sample=[{
                "symbol": x.get("base_symbol") or x.get("symbol"),
                "score": x.get("cex_revival_score") or x.get("spot_revival_score") or x.get("score"),
                "identity_status": x.get("identity_status"),
                "identity_blocker": x.get("identity_blocker"),
            } for x in strong_pending[:12]],
        ))

    funnel=docs["funnel"] or {}
    lanes=funnel.get("lanes") if isinstance(funnel,dict) else {}
    evidence=(lanes or {}).get("evidence_promotion") or {}
    verified_holder=int(evidence.get("verified_holder_lane") or 0)
    verified_wallet=int(evidence.get("verified_wallet_lane") or 0)
    universe=int(evidence.get("universe_with_exact_pair") or 0)
    metrics["coverage"]={"universe":universe,"verified_holder":verified_holder,"verified_wallet":verified_wallet}
    if universe and verified_wallet / max(1,universe) < 0.10:
        findings.append(finding(
            "WALLET_INTELLIGENCE_COVERAGE_STARVATION",
            "HIGH",
            "Wallet evidence reaches too small a fraction of the exact-pair universe and can become a structural promotion bottleneck",
            universe=universe, verified_wallet=verified_wallet,
            coverage_pct=round(100*verified_wallet/max(1,universe),2),
        ))

    syshealth=docs["system_health"] or {}
    if str(syshealth.get("overall") or "").upper()=="HEALTHY":
        masked=[]
        if saturated:
            masked.append("DISCOVERY_CAP_SATURATED")
        if isinstance(pc,dict) and str(pc.get("status") or "").upper().startswith("DEGRADED"):
            masked.append("CEX_IDENTITY_DEGRADED")
        if errors:
            masked.append("DISCOVERY_PROVIDER_ERRORS")
        if masked:
            findings.append(finding(
                "SYSTEM_HEALTH_FALSE_GREEN",
                "HIGH",
                "Top-level system health is HEALTHY while material capability degradations are active",
                masked_conditions=masked,
            ))

    # Cross-snapshot skew on files that participate in promotion.
    stamps={}
    for key,doc in docs.items():
        if not isinstance(doc,dict):
            continue
        stamp=next((doc.get(k) for k in ("generated_at","updated_at","source_generated_at") if doc.get(k)),None)
        parsed=dt(stamp)
        if parsed:
            stamps[key]=parsed
    if stamps:
        oldest=min(stamps.items(), key=lambda x:x[1])
        newest=max(stamps.items(), key=lambda x:x[1])
        skew=(newest[1]-oldest[1]).total_seconds()
        metrics["snapshot_skew_seconds"]=round(skew,1)
        metrics["snapshot_oldest"]=oldest[0]
        metrics["snapshot_newest"]=newest[0]
        if skew>30*60:
            findings.append(finding(
                "CROSS_LANE_SNAPSHOT_SKEW",
                "HIGH",
                "Decision lanes are consuming snapshots separated by more than 30 minutes",
                skew_seconds=round(skew,1), oldest=oldest[0], newest=newest[0],
            ))

    return findings, metrics


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--fail-on", choices=("critical","high","never"), default="critical")
    parser.add_argument("--output", default="data/engine-architecture-audit.json")
    args=parser.parse_args()

    all_findings=[]
    py_findings, py_metrics=scan_python()
    wf_findings, wf_metrics=scan_workflows()
    rt_findings, rt_metrics=runtime_audit()
    all_findings.extend(py_findings)
    all_findings.extend(wf_findings)
    all_findings.extend(rt_findings)

    # De-duplicate exact repetitions while preserving distinct locations/context.
    seen=set()
    dedup=[]
    for x in all_findings:
        key=json.dumps(x, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(x)
    dedup.sort(key=lambda x:(-SEV.get(x["severity"],0),x["code"],json.dumps(x.get("context") or {},sort_keys=True,default=str)))
    counts=Counter(x["severity"] for x in dedup)
    status="FAIL" if counts["CRITICAL"] else ("DEGRADED" if counts["HIGH"] else ("WARN" if counts["WARN"] else "PASS"))
    report={
        "version":1,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "mode":"ENGINE_END_TO_END_ARCHITECTURE_AUDIT_V1",
        "status":status,
        "scope":{
            "python":"all production Python under src/wallet500 and scripts",
            "workflows":"all GitHub Actions workflows",
            "runtime":"current discovery, CEX identity/promotion, Unified Watch, final-BUY and health snapshots",
        },
        "severity_counts":dict(counts),
        "metrics":{
            "python":py_metrics,
            "workflows":wf_metrics,
            "runtime":rt_metrics,
        },
        "top_findings":[x for x in dedup if x["severity"] in {"CRITICAL","HIGH"}][:80],
        "findings":dedup,
        "fail_policy":"CRITICAL blocks CI; HIGH is a mandatory hardening backlog item",
    }
    out=ROOT/args.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":status,
        "severity_counts":dict(counts),
        "top_findings":report["top_findings"][:30],
        "python_files_scanned":py_metrics["files"],
        "workflow_files_scanned":wf_metrics["workflow_count"],
    },ensure_ascii=False,indent=2))

    if args.fail_on=="never":
        return 0
    threshold=SEV["CRITICAL"] if args.fail_on=="critical" else SEV["HIGH"]
    return 1 if any(SEV.get(x["severity"],0)>=threshold for x in dedup) else 0


if __name__=="__main__":
    raise SystemExit(main())
