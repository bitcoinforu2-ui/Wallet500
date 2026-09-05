from __future__ import annotations

import json
from pathlib import Path

from .liquidity_truth import liquidity_truth

DATA = Path("data")
CONCENTRATED_BLOCKER = "EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(v, default=None):
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _identity_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("chain") or row.get("network") or "").strip().lower(),
        str(row.get("token_address") or row.get("token") or row.get("mint") or "").strip().lower(),
        str(row.get("pair_address") or row.get("dex_pair_address") or row.get("exact_pair") or "").strip().lower(),
    )


def annotate_row(row: dict) -> dict:
    out = dict(row)
    truth = liquidity_truth(out)
    reported = _num(out.get("pool_tvl_usd"))
    if reported is None:
        reported = _num(out.get("execution_pool_liquidity_usd"))
    if reported is None:
        reported = _num(out.get("dex_liquidity_usd"))
    if reported is None:
        reported = _num(out.get("liquidity_usd"))
    if reported is not None and truth.get("pool_tvl_usd") is None:
        truth["pool_tvl_usd"] = round(reported, 2)

    out.update(truth)
    out["provider_reported_pool_value_usd"] = round(reported, 2) if reported is not None else None

    if truth.get("concentrated_liquidity_pool") and not truth.get("execution_depth_verified"):
        out["pool_tvl_usd"] = truth.get("pool_tvl_usd") or (round(reported, 2) if reported is not None else None)
        out["execution_pool_liquidity_usd"] = None
        out["liquidity_usd"] = None
        out["dex_liquidity_usd"] = None
        out["liquidity_gate_metric"] = "VERIFIED_EXECUTION_DEPTH_USD_5PCT"
        out["liquidity_truth_source"] = "DEPTH_UNVERIFIED_FAIL_CLOSED"
        out["liquidity_execution_gate_eligible"] = False
        out["liquidity_execution_gate_status"] = "CONCENTRATED_POOL_DEPTH_UNVERIFIED_FAIL_CLOSED"
    return out


def sanitize_cex_radar(path: Path = DATA / "cex-revival-radar.json") -> dict:
    payload = _load(path, {})
    rows = [annotate_row(x) if isinstance(x, dict) and x.get("identity_status") == "DEX_VERIFIED" else x for x in payload.get("alerts") or []]
    payload["alerts"] = rows
    payload["liquidity_truth_contract"] = {
        "version": "LIQUIDITY_TRUTH_V1",
        "pool_tvl_never_equals_execution_depth": True,
        "concentrated_pool_requires_verified_execution_depth": True,
        "unverified_concentrated_depth_policy": "FAIL_CLOSED_NO_EXECUTION_LIQUIDITY",
        "gate_metric": "VERIFIED_EXECUTION_DEPTH_USD_5PCT",
        "dex_total_liquidity_is_informational_only": True,
    }
    payload["liquidity_truth_counts"] = {
        "concentrated_depth_unverified": sum(
            1 for x in rows if isinstance(x, dict)
            and x.get("concentrated_liquidity_pool") is True
            and x.get("execution_depth_verified") is not True
        ),
        "verified_execution_depth": sum(1 for x in rows if isinstance(x, dict) and x.get("execution_depth_verified") is True),
    }
    _write(path, payload)
    return payload["liquidity_truth_counts"]


def _cex_pair_metadata(real_alert_path: Path) -> dict[tuple[str, str, str], dict]:
    radar = _load(real_alert_path.parent / "cex-revival-radar.json", {})
    out: dict[tuple[str, str, str], dict] = {}
    for row in radar.get("alerts") or []:
        if not isinstance(row, dict):
            continue
        key = _identity_key(row)
        if not all(key):
            continue
        out[key] = row
    return out


def _merge_liquidity_metadata(row: dict, source: dict | None) -> dict:
    if not source:
        return dict(row)
    out = dict(row)
    for key in (
        "dex", "pool_type", "protocol", "market_protocol", "market_program",
        "pool_tvl_usd", "provider_reported_pool_value_usd",
        "active_liquidity_usd", "execution_depth_usd_1pct", "execution_depth_usd_2pct",
        "execution_depth_usd_5pct", "execution_depth_verified", "execution_depth_source",
        "concentrated_liquidity_pool", "liquidity_execution_gate_eligible",
        "liquidity_execution_gate_status", "liquidity_semantics_version",
    ):
        if out.get(key) in (None, "") and source.get(key) not in (None, ""):
            out[key] = source.get(key)
    return out


def _demote_row(row: dict, metadata: dict | None = None) -> dict:
    out = annotate_row(_merge_liquidity_metadata(row, metadata))
    if out.get("concentrated_liquidity_pool") is True and out.get("execution_depth_verified") is not True:
        blockers = list(out.get("blockers") or [])
        if CONCENTRATED_BLOCKER not in blockers:
            blockers.append(CONCENTRATED_BLOCKER)
        out["blockers"] = sorted(set(blockers))
        out["actionable_research_alert"] = False
        out["status"] = "VERIFIED_WATCH_NOT_REAL_ALERT"
    return out


def sanitize_real_alerts(path: Path = DATA / "real-alerts.json") -> dict:
    payload = _load(path, {})
    metadata = _cex_pair_metadata(path)
    original_alerts = [x for x in payload.get("alerts") or [] if isinstance(x, dict)]
    original_watch = [x for x in payload.get("verified_watch") or [] if isinstance(x, dict)]

    alerts = []
    demoted = []
    for row in original_alerts:
        clean = _demote_row(row, metadata.get(_identity_key(row)))
        if CONCENTRATED_BLOCKER in (clean.get("blockers") or []):
            demoted.append(clean)
        else:
            alerts.append(clean)
    watch = [_demote_row(x, metadata.get(_identity_key(x))) for x in original_watch] + demoted

    seen = set()
    uniq_watch = []
    for row in watch:
        key = _identity_key(row)
        if key in seen:
            continue
        seen.add(key)
        uniq_watch.append(row)

    payload["alerts"] = alerts
    payload["verified_watch"] = uniq_watch[:50]
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    counts["real_alerts"] = len(alerts)
    counts["verified_watch_not_real"] = len(uniq_watch)
    payload["counts"] = counts
    payload["latest_real_alert"] = alerts[0] if alerts else None
    truth = payload.get("truth_contract") if isinstance(payload.get("truth_contract"), dict) else {}
    truth.update({
        "pool_tvl_never_equals_execution_depth": True,
        "concentrated_pool_requires_verified_execution_depth": True,
        "unverified_concentrated_depth_policy": "FAIL_CLOSED_NO_REAL_ALERT",
        "liquidity_gate_metric": "VERIFIED_EXECUTION_DEPTH_USD_5PCT_OR_NON_CONCENTRATED_LEGACY_GATE",
    })
    payload["truth_contract"] = truth
    payload["liquidity_truth_guard"] = {
        "version": "LIQUIDITY_TRUTH_GUARD_V1",
        "demoted_real_alerts": len(demoted),
        "concentrated_depth_unverified_blocker": CONCENTRATED_BLOCKER,
        "exact_pair_metadata_join": True,
    }
    _write(path, payload)
    return {"real_alerts": len(alerts), "verified_watch": len(uniq_watch), "demoted": len(demoted)}


def safe_production_liquidity(candidate: dict) -> tuple[float, str, bool]:
    truth = liquidity_truth(candidate)
    if truth.get("execution_depth_verified") is True:
        return float(truth.get("execution_depth_usd_5pct") or 0), "VERIFIED_EXECUTION_DEPTH_USD_5PCT", True
    if truth.get("concentrated_liquidity_pool") is True:
        return 0.0, "CONCENTRATED_POOL_DEPTH_UNVERIFIED_FAIL_CLOSED", False
    for key in ("execution_pool_liquidity_usd", "live_liquidity_usd", "liquidity_usd", "dex_liquidity_usd"):
        v = _num(candidate.get(key))
        if v is not None and v >= 0:
            return v, f"LEGACY_NON_CONCENTRATED_EXACT_PAIR:{key}", True
    return 0.0, "EXECUTION_LIQUIDITY_UNAVAILABLE", False
