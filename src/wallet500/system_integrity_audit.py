from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
DOGE1_CA = "DpBzjtgGLF7QA9Ug3eUVGbnqa6j3jvYBn1XuQuktvfhm"
VETERAN_MIN_DAYS = 180
SURVIVOR_MODE = "HOURLY_WINNER_SURVIVOR_WAVE_WATCH_V1"
SURVIVOR_SOURCE = "WINNER_SEPARATOR_NO_HINDSIGHT_V1"
SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}
CONCENTRATED_HINTS = ("meteora", "dlmm", "clmm", "whirlpool", "uniswap_v3", "uniswap-v3", "algebra")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
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
    except Exception:
        return None


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _rows(payload: Any, *keys: str) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _identity_key(row: dict) -> tuple[str, str, str]:
    chain = str(row.get("chain") or row.get("network") or "").strip().lower()
    token = str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()
    pair = str(row.get("pair_address") or row.get("exact_pair") or row.get("dex_pair_address") or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast"}:
        token, pair = token.lower(), pair.lower()
    return chain, token, pair.lower()


def _event(code: str, severity: str, message: str, *, file: str | None = None, context: dict | None = None) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "file": file,
        "context": context or {},
    }


def _load_json(path: Path, findings: list[dict], *, required: bool = False) -> Any:
    if not path.exists():
        findings.append(_event(
            "REQUIRED_DATA_FILE_MISSING" if required else "OPTIONAL_DATA_FILE_MISSING",
            "CRITICAL" if required else "WARNING",
            f"Missing {'required' if required else 'optional'} data file: {path.name}",
            file=path.name,
        ))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(_event(
            "JSON_PARSE_FAILURE",
            "CRITICAL",
            f"Cannot parse {path.name}: {type(exc).__name__}: {exc}",
            file=path.name,
        ))
        return None


def _freshness(payload: Any, filename: str, findings: list[dict], now: datetime, max_age_seconds: int) -> None:
    if not isinstance(payload, dict):
        return
    stamp = next((payload.get(k) for k in ("generated_at", "updated_at", "observed_at", "created_at", "generated_identity_at") if payload.get(k)), None)
    dt = _parse_dt(stamp)
    if dt is None:
        findings.append(_event(
            "DATA_TIMESTAMP_MISSING_OR_INVALID",
            "HIGH",
            f"{filename} has no usable freshness timestamp",
            file=filename,
            context={"timestamp": stamp, "max_age_seconds": max_age_seconds},
        ))
        return
    age = max(0.0, (now - dt).total_seconds())
    if age > max_age_seconds:
        findings.append(_event(
            "DATA_SOURCE_STALE",
            "HIGH",
            f"{filename} is stale for its expected cadence",
            file=filename,
            context={"age_seconds": round(age, 1), "max_age_seconds": max_age_seconds, "timestamp": stamp},
        ))


def _audit_survivors(payload: Any, findings: list[dict]) -> dict:
    if not isinstance(payload, dict):
        return {"tokens": 0}
    filename = "survivor-wave-watch.json"
    contract = {
        "mode": payload.get("mode") == SURVIVOR_MODE,
        "research_only": payload.get("research_only") is True,
        "automatic_buy": payload.get("automatic_buy") is False,
        "exact_pair_only": payload.get("exact_pair_only") is True,
        "source_method": payload.get("source_method") == SURVIVOR_SOURCE,
    }
    for name, ok in contract.items():
        if not ok:
            findings.append(_event(
                "SURVIVOR_TRUTH_CONTRACT_BROKEN",
                "CRITICAL",
                f"Survivor truth-contract field failed: {name}",
                file=filename,
                context={"field": name, "actual": payload.get(name)},
            ))

    tokens = _rows(payload, "tokens")
    declared = int(payload.get("survivor_n") or 0)
    if declared != len(tokens):
        findings.append(_event(
            "SURVIVOR_COUNT_MISMATCH",
            "CRITICAL",
            "survivor_n does not match tokens length",
            file=filename,
            context={"declared": declared, "actual": len(tokens)},
        ))

    floor = _num(payload.get("liquidity_survival_floor_usd")) or 0.0
    if floor < 50_000:
        findings.append(_event(
            "SURVIVOR_LIQUIDITY_FLOOR_DRIFT",
            "CRITICAL",
            "Survivor liquidity floor dropped below Wallet500 safety floor",
            file=filename,
            context={"floor_usd": floor},
        ))

    seen_triplets: set[tuple[str, str, str]] = set()
    pair_to_token: dict[tuple[str, str], str] = {}
    high_n = medium_n = wave_n = 0
    for row in tokens:
        chain, token, pair = _identity_key(row)
        if not chain or not token or not pair:
            findings.append(_event(
                "SURVIVOR_IDENTITY_INCOMPLETE",
                "CRITICAL",
                "Survivor missing chain/token/exact pair",
                file=filename,
                context={"chain": chain, "token": token, "pair": pair},
            ))
            continue
        key = (chain, token, pair)
        if key in seen_triplets:
            findings.append(_event("DUPLICATE_SURVIVOR_EXACT_PAIR", "HIGH", "Duplicate survivor exact identity/pair", file=filename, context={"key": key}))
        seen_triplets.add(key)
        pair_key = (chain, pair)
        old_token = pair_to_token.get(pair_key)
        if old_token and old_token != token:
            findings.append(_event(
                "PAIR_IDENTITY_COLLISION",
                "CRITICAL",
                "Same exact pair is mapped to multiple token identities",
                file=filename,
                context={"chain": chain, "pair": pair, "tokens": [old_token, token]},
            ))
        pair_to_token[pair_key] = token

        liq = _num(row.get("liquidity_usd"))
        if liq is None or liq < floor:
            findings.append(_event(
                "SURVIVOR_BELOW_LIQUIDITY_SURVIVAL_FLOOR",
                "CRITICAL",
                "Token remained in survivor set without exact-pair liquidity survival",
                file=filename,
                context={"token": token, "pair": pair, "liquidity_usd": liq, "floor_usd": floor},
            ))
        if row.get("survival") != "EXACT_PAIR_LIQUIDITY_SURVIVED":
            findings.append(_event(
                "SURVIVOR_PAIR_SURVIVAL_FLAG_INVALID",
                "CRITICAL",
                "Survivor lacks exact-pair survival flag",
                file=filename,
                context={"token": token, "survival": row.get("survival")},
            ))
        dna = str(row.get("winner_dna_match") or "").upper()
        if dna == "HIGH":
            high_n += 1
        elif dna == "MEDIUM":
            medium_n += 1
        if str(row.get("wave_status") or "").upper() == "WAVE_BUILDING":
            wave_n += 1

    for field, actual in (("dna_high_n", high_n), ("dna_medium_n", medium_n), ("wave_building_n", wave_n)):
        declared_count = int(payload.get(field) or 0)
        if declared_count != actual:
            findings.append(_event(
                "SURVIVOR_DERIVED_COUNT_MISMATCH",
                "HIGH",
                f"{field} does not match token rows",
                file=filename,
                context={"field": field, "declared": declared_count, "actual": actual},
            ))
    return {"tokens": len(tokens), "high": high_n, "medium": medium_n, "wave_building": wave_n}


def _is_concentrated(row: dict, metadata: dict | None = None) -> bool:
    if row.get("concentrated_liquidity_pool") is True:
        return True
    merged = dict(metadata or {})
    merged.update(row)
    text = " ".join(str(merged.get(k) or "") for k in ("dex", "dex_id", "pool_type", "amm_type", "pair_provider", "dex_url")).lower()
    return any(hint in text for hint in CONCENTRATED_HINTS)


def _audit_liquidity_truth(payloads: dict[str, Any], findings: list[dict]) -> dict:
    metadata_index: dict[tuple[str, str, str], dict] = {}
    cex = payloads.get("cex-revival-radar.json")
    for row in _rows(cex, "alerts"):
        key = _identity_key(row)
        if all(key):
            metadata_index[key] = row

    checked = concentrated = 0
    surfaces = {
        "cex-revival-radar.json": ("alerts",),
        "real-alerts.json": ("alerts", "verified_watch"),
        "active-qualified-candidates.json": (),
        "production-risk-evaluations.json": (),
    }
    for filename, keys in surfaces.items():
        payload = payloads.get(filename)
        rows: list[dict] = []
        if keys:
            for key in keys:
                rows.extend(_rows(payload, key))
        else:
            rows = _rows(payload)
        for row in rows:
            checked += 1
            key = _identity_key(row)
            meta = metadata_index.get(key)
            if not _is_concentrated(row, meta):
                continue
            concentrated += 1
            depth_verified = row.get("execution_depth_verified") is True
            if not depth_verified and meta:
                depth_verified = meta.get("execution_depth_verified") is True
            execution_depth = _num(row.get("execution_depth_usd_5pct"))
            if execution_depth is None and meta:
                execution_depth = _num(meta.get("execution_depth_usd_5pct"))
            legacy_values = {
                name: _num(row.get(name))
                for name in ("execution_pool_liquidity_usd", "liquidity_usd", "dex_liquidity_usd")
            }
            positive_legacy = {k: v for k, v in legacy_values.items() if v is not None and v > 0}
            if not depth_verified and positive_legacy:
                findings.append(_event(
                    "CONCENTRATED_TVL_MASQUERADING_AS_EXECUTION_LIQUIDITY",
                    "CRITICAL",
                    "Concentrated-liquidity pool exposes legacy liquidity as executable without verified depth",
                    file=filename,
                    context={"identity": key, "legacy_values": positive_legacy, "metadata_dex": (meta or {}).get("dex")},
                ))
            if depth_verified and (execution_depth is None or execution_depth <= 0):
                findings.append(_event(
                    "EXECUTION_DEPTH_VERIFIED_WITHOUT_POSITIVE_DEPTH",
                    "CRITICAL",
                    "execution_depth_verified=true but 5% execution depth is missing/non-positive",
                    file=filename,
                    context={"identity": key, "execution_depth_usd_5pct": execution_depth},
                ))
    return {"rows_checked": checked, "concentrated_rows": concentrated}


def _audit_real_alerts(payload: Any, findings: list[dict]) -> dict:
    if not isinstance(payload, dict):
        return {"alerts": 0, "watch": 0}
    filename = "real-alerts.json"
    alerts = _rows(payload, "alerts")
    watch = _rows(payload, "verified_watch")
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    if int(counts.get("real_alerts") or 0) != len(alerts):
        findings.append(_event("REAL_ALERT_COUNT_MISMATCH", "CRITICAL", "real_alerts count does not match alert rows", file=filename))
    if int(counts.get("verified_watch_not_real") or 0) != len(watch):
        findings.append(_event("VERIFIED_WATCH_COUNT_MISMATCH", "HIGH", "verified watch count does not match watch rows", file=filename, context={"declared": counts.get("verified_watch_not_real"), "actual": len(watch)}))

    for row in alerts:
        age = _num(row.get("market_age_days"))
        blockers = list(row.get("blockers") or [])
        violations = []
        if row.get("exact_identity_verified") is not True:
            violations.append("EXACT_IDENTITY")
        if row.get("exact_pair_verified") is not True:
            violations.append("EXACT_PAIR")
        if row.get("market_age_verified") is not True or age is None or age < VETERAN_MIN_DAYS:
            violations.append("VETERAN_AGE")
        if blockers:
            violations.append("BLOCKERS_PRESENT")
        if row.get("automatic_buy") is True:
            violations.append("AUTOMATIC_BUY_TRUE")
        if violations:
            findings.append(_event(
                "ACTIONABLE_REAL_ALERT_TRUTH_VIOLATION",
                "CRITICAL",
                "Real alert violated a fail-closed production truth requirement",
                file=filename,
                context={"identity": _identity_key(row), "violations": violations, "age_days": age, "blockers": blockers},
            ))
    for row in watch:
        if row.get("actionable_research_alert") is True:
            findings.append(_event(
                "WATCH_ROW_ACTIONABLE_LEAK",
                "CRITICAL",
                "verified_watch row leaked actionable=true",
                file=filename,
                context={"identity": _identity_key(row)},
            ))
    return {"alerts": len(alerts), "watch": len(watch)}


def _audit_wallet_flow(payload: Any, survivor_count: int, findings: list[dict]) -> dict:
    if not isinstance(payload, dict):
        return {"verified_flow_token_n": 0}
    filename = "survivor-wallet-transaction-intelligence-v5.json"
    if payload.get("research_only") is not True or payload.get("production_gates_changed") is not False or payload.get("exact_pair_only") is not True:
        findings.append(_event(
            "WALLET_FLOW_TRUTH_CONTRACT_BROKEN",
            "CRITICAL",
            "Wallet/transaction V5 research truth contract drifted",
            file=filename,
        ))
    verified = int(payload.get("verified_flow_token_n") or 0)
    rows = _rows(payload, "tokens")
    if survivor_count > 0 and verified == 0:
        findings.append(_event(
            "WALLET_FLOW_ZERO_VERIFIED_COVERAGE",
            "HIGH",
            "Survivors exist but V5 has zero tokens with verified exact-pair swap flow",
            file=filename,
            context={"survivor_count": survivor_count, "v5_rows": len(rows), "verified_flow_token_n": verified, "recommended_action": "CHECK_TRANSACTION_FEED_CREDENTIALS_PROVIDER_AND_EXACT_PAIR_QUERY_YIELD"},
        ))
    if survivor_count and rows and len(rows) != survivor_count:
        findings.append(_event(
            "WALLET_FLOW_SURVIVOR_COVERAGE_COUNT_MISMATCH",
            "HIGH",
            "V5 token rows do not cover current survivor set one-for-one",
            file=filename,
            context={"survivor_count": survivor_count, "v5_rows": len(rows)},
        ))
    return {"verified_flow_token_n": verified, "rows": len(rows)}


def _audit_doge1(payload: Any, findings: list[dict]) -> dict:
    if not isinstance(payload, dict):
        return {"present": False}
    filename = "doge1-hourly-report.json"
    token = payload.get("token") if isinstance(payload.get("token"), dict) else {}
    ca = str(token.get("contract_address") or "")
    if ca != DOGE1_CA:
        findings.append(_event(
            "DOGE1_CANONICAL_CA_MISMATCH",
            "CRITICAL",
            "DOGE-1 canonical report contains the wrong contract address",
            file=filename,
            context={"expected": DOGE1_CA, "actual": ca},
        ))
    required_top = ("version", "observed_at", "token", "exact_pair", "holders", "whales", "social", "listings", "news", "catalysts", "game_changer", "changes_since_previous", "evidence_notes", "source_links")
    missing = [k for k in required_top if k not in payload]
    if missing:
        findings.append(_event("DOGE1_SCHEMA_DRIFT", "HIGH", "DOGE-1 canonical report schema is incomplete", file=filename, context={"missing": missing}))
    pair = payload.get("exact_pair") if isinstance(payload.get("exact_pair"), dict) else {}
    if not pair.get("pair_address"):
        findings.append(_event("DOGE1_EXACT_PAIR_MISSING", "HIGH", "DOGE-1 report has no exact pair address", file=filename))
    return {"present": True, "contract_address": ca, "pair_address": pair.get("pair_address")}


def _audit_cex_provider_health(payload: Any, findings: list[dict]) -> dict:
    if not isinstance(payload, dict):
        return {"healthy_sources": 0}
    healthy = int(payload.get("healthy_sources") or 0)
    errors = list(payload.get("errors") or [])
    if healthy < 4:
        findings.append(_event(
            "CEX_PROVIDER_COVERAGE_LOW",
            "HIGH",
            "Too few healthy CEX sources; anomaly confirmation may be biased or incomplete",
            file="cex-revival-radar.json",
            context={"healthy_sources": healthy, "errors": errors[:10]},
        ))
    elif errors:
        findings.append(_event(
            "CEX_PROVIDER_PARTIAL_DEGRADATION",
            "WARNING",
            "Some CEX providers are unavailable; coverage remains above minimum",
            file="cex-revival-radar.json",
            context={"healthy_sources": healthy, "errors": errors[:10]},
        ))
    return {"healthy_sources": healthy, "provider_errors": len(errors)}


def run(data_dir: Path = DATA, *, now: datetime | None = None, write_report: bool = True) -> dict:
    now = now or _now()
    findings: list[dict] = []
    specs = {
        "survivor-wave-watch.json": True,
        "survivor-wallet-transaction-intelligence-v5.json": False,
        "real-alerts.json": True,
        "cex-revival-radar.json": True,
        "active-qualified-candidates.json": False,
        "production-risk-evaluations.json": False,
        "run-summary.json": True,
        "doge1-hourly-report.json": False,
    }
    payloads = {name: _load_json(data_dir / name, findings, required=required) for name, required in specs.items()}

    freshness = {
        "survivor-wave-watch.json": 2 * 3600,
        "survivor-wallet-transaction-intelligence-v5.json": 2 * 3600,
        "real-alerts.json": 2 * 3600,
        "cex-revival-radar.json": 2 * 3600,
        "run-summary.json": 2 * 3600,
        "doge1-hourly-report.json": 2 * 3600,
    }
    for name, max_age in freshness.items():
        payload = payloads.get(name)
        if payload is not None:
            _freshness(payload, name, findings, now, max_age)

    survivor_metrics = _audit_survivors(payloads.get("survivor-wave-watch.json"), findings)
    real_metrics = _audit_real_alerts(payloads.get("real-alerts.json"), findings)
    liquidity_metrics = _audit_liquidity_truth(payloads, findings)
    wallet_metrics = _audit_wallet_flow(payloads.get("survivor-wallet-transaction-intelligence-v5.json"), survivor_metrics.get("tokens", 0), findings)
    doge_metrics = _audit_doge1(payloads.get("doge1-hourly-report.json"), findings)
    cex_metrics = _audit_cex_provider_health(payloads.get("cex-revival-radar.json"), findings)

    findings.sort(key=lambda x: (-SEVERITY_RANK.get(x["severity"], 0), x["code"], x.get("file") or ""))
    counts = {sev: sum(1 for f in findings if f["severity"] == sev) for sev in SEVERITY_RANK}
    critical = counts["CRITICAL"]
    high = counts["HIGH"]
    status = "FAIL" if critical else ("DEGRADED" if high else ("WARN" if counts["WARNING"] else "PASS"))
    report = {
        "version": 1,
        "generated_at": now.isoformat(),
        "mode": "WALLET500_CONTINUOUS_SYSTEM_INTEGRITY_AUDIT_V1",
        "status": status,
        "production_mutation": False,
        "automatic_buy": False,
        "severity_counts": counts,
        "metrics": {
            "survivors": survivor_metrics,
            "real_alerts": real_metrics,
            "liquidity_truth": liquidity_metrics,
            "wallet_flow": wallet_metrics,
            "doge1": doge_metrics,
            "cex_provider_health": cex_metrics,
        },
        "top_bottlenecks": [
            f for f in findings if f["severity"] in {"CRITICAL", "HIGH"}
        ][:25],
        "findings": findings,
        "exit_policy": "CI_FAILS_ON_CRITICAL; HIGH_IS_REPORTED_AS_BOTTLENECK_WITHOUT_MUTATING_PRODUCTION",
    }
    if write_report:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "system-integrity-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Wallet500 continuous system/data integrity audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--fail-on", choices=("critical", "high", "never"), default="critical")
    args = parser.parse_args()
    report = run(Path(args.data_dir))
    print(json.dumps({
        "status": report["status"],
        "severity_counts": report["severity_counts"],
        "top_bottlenecks": report["top_bottlenecks"][:10],
    }, ensure_ascii=False, indent=2))
    if args.fail_on == "never":
        return 0
    threshold = 3 if args.fail_on == "critical" else 2
    return 1 if any(SEVERITY_RANK.get(f["severity"], 0) >= threshold for f in report["findings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
