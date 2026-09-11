from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "wallet-insight-review.json"
VERSION = "WALLET500_WALLET_INSIGHT_REVIEW_V1"
MODE = "RESEARCH_ONLY_EXACT_PAIR_WALLET_BOTTLENECK_REVIEW"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _token(row: dict) -> str:
    return str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip()


def _pair(row: dict) -> str:
    return str(row.get("pair_address") or row.get("exact_pair") or row.get("dex_pair_address") or "").strip()


def _key(row: dict) -> str:
    token, pair = _token(row), _pair(row)
    return f"{token}|{pair.lower()}" if token and pair else ""


def _rows(payload: dict, key: str) -> list[dict]:
    value = payload.get(key) if isinstance(payload, dict) else None
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [x for x in value.values() if isinstance(x, dict)]
    return []


def _classify(candidate: dict, wallet: dict | None, probe: dict | None) -> tuple[str, list[str], dict]:
    blockers: list[str] = []
    metrics: dict[str, Any] = {}
    wallet_family = ((candidate.get("families") or {}).get("wallet_accumulation") or {})
    smart_family = ((candidate.get("families") or {}).get("smart_money") or {})

    current_probe_verified = bool(probe and probe.get("coverage_verified") is True)
    historical_probe_verified = bool(probe and probe.get("historical_coverage_verified") is True)
    coverage_degraded = bool(probe and probe.get("coverage_degraded") is True)
    metrics.update({
        "current_probe_verified": current_probe_verified,
        "historical_probe_verified": historical_probe_verified,
        "coverage_degraded": coverage_degraded,
        "probe_status": (probe or {}).get("status"),
        "wallet_family_verified": wallet_family.get("verified") is True,
        "wallet_family_positive": wallet_family.get("positive") is True,
        "smart_money_positive": smart_family.get("positive") is True,
        "historically_qualified_pre_waking_buyers": ((smart_family.get("metrics") or {}).get("historically_qualified_pre_waking_buyers")),
    })

    if coverage_degraded:
        blockers.append("CURRENT_COVERAGE_DEGRADED")
    elif not current_probe_verified:
        blockers.append("CURRENT_COVERAGE_UNVERIFIED")

    if wallet is None:
        blockers.append("NO_LIVE_PREWAKING_WALLET_ROW")
        if current_probe_verified or historical_probe_verified:
            return "DATA_PIPELINE_BOTTLENECK", sorted(set(blockers)), metrics
        return "NEEDS_WALLET_OBSERVATION", sorted(set(blockers)), metrics

    coverage = wallet.get("coverage") if isinstance(wallet.get("coverage"), dict) else {}
    windows = wallet.get("windows") if isinstance(wallet.get("windows"), dict) else {}
    h1 = windows.get("h1") if isinstance(windows.get("h1"), dict) else {}
    quality = str(coverage.get("coverage_quality") or "")
    resolution = _num(coverage.get("last_run_resolution_pct"))
    minimum_resolution = _num(coverage.get("minimum_resolution_pct"))
    if minimum_resolution is None:
        minimum_resolution = 80.0
    resolved = _integer(h1.get("resolved_swaps"))
    first_buyers = _integer(h1.get("first_seen_buyers_since_monitor_t0"))
    accumulators = _integer(h1.get("net_accumulating_wallets"))
    distributors = _integer(h1.get("net_distributing_wallets"))
    ratio = _num(h1.get("wallet_buy_sell_ratio"))
    metrics.update({
        "coverage_quality": quality or None,
        "coverage_gap": coverage.get("coverage_gap"),
        "resolution_pct": resolution,
        "minimum_resolution_pct": minimum_resolution,
        "h1_resolved_swaps": resolved,
        "h1_first_seen_buyers": first_buyers,
        "h1_net_accumulating_wallets": accumulators,
        "h1_net_distributing_wallets": distributors,
        "h1_wallet_buy_sell_ratio": ratio,
    })

    if quality != "ACCEPTABLE" or coverage.get("coverage_gap") is True:
        blockers.append("LIVE_COVERAGE_QUALITY_INSUFFICIENT")
    if resolution is None:
        blockers.append("NO_CURRENT_RESOLUTION_SAMPLE")
    elif resolution < minimum_resolution:
        blockers.append("RESOLUTION_BELOW_MINIMUM")
    if resolved < 6:
        blockers.append("INSUFFICIENT_H1_RESOLVED_SWAPS")
    if first_buyers < 3:
        blockers.append("INSUFFICIENT_FIRST_SEEN_BUYERS")
    if accumulators < 3:
        blockers.append("INSUFFICIENT_NET_ACCUMULATORS")
    if accumulators - distributors < 1:
        blockers.append("ACCUMULATION_MINUS_DISTRIBUTION_LT_1")
    if ratio is None or ratio < 1.15:
        blockers.append("BUY_SELL_RATIO_BELOW_1_15")
    if smart_family.get("positive") is not True:
        blockers.append("NO_QUALIFIED_SMART_MONEY")

    if wallet_family.get("positive") is True:
        classification = "ACCUMULATION_CONFIRMED"
    elif current_probe_verified and (resolution is None or quality != "ACCEPTABLE"):
        classification = "DATA_PIPELINE_BOTTLENECK"
    elif coverage_degraded:
        classification = "CURRENT_COVERAGE_DEGRADED"
    elif wallet_family.get("verified") is True:
        classification = "MARKET_WALLET_EVIDENCE_WEAK"
    elif current_probe_verified or historical_probe_verified:
        classification = "COVERAGE_TO_ACCUMULATION_GAP"
    else:
        classification = "NEEDS_WALLET_OBSERVATION"
    return classification, sorted(set(blockers)), metrics


def build(data_dir: Path = DATA) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    envelope = _load(data_dir / "candidate-evidence-envelope.json", {})
    wallet_payload = _load(data_dir / "revival-prewaking-wallet-evidence.json", {})
    probe_payload = _load(data_dir / "revival-wallet-coverage-probe.json", {})

    wallet_index = {_key(row): row for row in _rows(wallet_payload, "tokens") if _key(row)}
    probe_index = {_key(row): row for row in _rows(probe_payload, "tokens") if _key(row)}
    rows: list[dict] = []
    class_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()

    for candidate in _rows(envelope, "candidates"):
        key = _key(candidate)
        if not key:
            continue
        classification, blockers, metrics = _classify(candidate, wallet_index.get(key), probe_index.get(key))
        class_counts[classification] += 1
        blocker_counts.update(blockers)
        rows.append({
            "identity": f"solana|{_token(candidate)}|{_pair(candidate)}",
            "symbol": candidate.get("symbol"),
            "candidate_status": candidate.get("status"),
            "discovery_tier": candidate.get("discovery_tier"),
            "classification": classification,
            "blockers": blockers,
            "metrics": metrics,
            "production_effect": False,
            "automatic_buy": False,
        })

    priority = {
        "DATA_PIPELINE_BOTTLENECK": 0,
        "COVERAGE_TO_ACCUMULATION_GAP": 1,
        "CURRENT_COVERAGE_DEGRADED": 2,
        "MARKET_WALLET_EVIDENCE_WEAK": 3,
        "NEEDS_WALLET_OBSERVATION": 4,
        "ACCUMULATION_CONFIRMED": 5,
    }
    status_priority = {"EVIDENCE_READY": 0, "VERIFIED_WATCH": 1, "DEEP_WATCH": 2, "BLOCKED_TRUTH": 3}
    rows.sort(key=lambda r: (priority.get(r["classification"], 9), status_priority.get(str(r.get("candidate_status")), 9), str(r.get("symbol") or "")))

    actionable_diagnostics = [r for r in rows if r["classification"] in {"DATA_PIPELINE_BOTTLENECK", "COVERAGE_TO_ACCUMULATION_GAP", "CURRENT_COVERAGE_DEGRADED"}][:40]
    insights = {
        "coverage_to_accumulation_gap": sum(1 for r in rows if r["metrics"].get("historical_probe_verified") and not r["metrics"].get("wallet_family_verified")),
        "current_probe_verified_but_wallet_family_unverified": sum(1 for r in rows if r["metrics"].get("current_probe_verified") and not r["metrics"].get("wallet_family_verified")),
        "historically_verified_but_currently_degraded": sum(1 for r in rows if r["metrics"].get("coverage_degraded")),
        "wallet_family_verified_but_behavior_not_positive": sum(1 for r in rows if r["metrics"].get("wallet_family_verified") and not r["metrics"].get("wallet_family_positive")),
        "qualified_smart_money_positive": sum(1 for r in rows if r["metrics"].get("smart_money_positive")),
    }

    return {
        "version": VERSION,
        "mode": MODE,
        "generated_at": now,
        "production_effect": False,
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "no_hindsight": True,
        "truth_contract": {
            "exact_pair_required": True,
            "historical_coverage_never_counts_as_current_positive": True,
            "coverage_probe_never_counts_as_accumulation_alpha": True,
            "wallet_thresholds_are_diagnostic_mirrors_not_changed": True,
            "promotion_allowed": False,
            "production_threshold_change_allowed": False,
            "missing_evidence_never_positive": True,
        },
        "source_generated_at": {
            "candidate_evidence_envelope": envelope.get("generated_at"),
            "prewaking_wallet_evidence": wallet_payload.get("generated_at"),
            "wallet_coverage_probe": probe_payload.get("generated_at"),
        },
        "counts": {
            "candidates": len(rows),
            "classifications": dict(sorted(class_counts.items())),
            "blockers": dict(blocker_counts.most_common()),
        },
        "new_insights": insights,
        "diagnostic_priority": actionable_diagnostics,
        "rows": rows,
    }


def run(data_dir: Path = DATA) -> dict:
    payload = build(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / OUTPUT.name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = run()
    print(json.dumps({"counts": payload["counts"], "new_insights": payload["new_insights"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
