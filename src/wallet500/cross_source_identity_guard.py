from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA = Path("data")
CORRELATION = DATA / "cross-source-correlation.json"
WATCHLIST = DATA / "manual-watchlist.json"
CATALYST_LEDGER = DATA / "catalyst-wire-ledger.json"
CEX_REGISTRY = DATA / "cex-identity-registry.json"
EVM_CHAINS = {"ethereum", "bsc", "arbitrum", "base"}
EVM_ZERO = "0x0000000000000000000000000000000000000000"
EXCHANGE_OWNERS = {
    "binance", "coinbase", "kraken", "bybit", "okx", "kucoin", "bitget",
    "gate", "mexc", "bithumb", "coinex", "htx", "lbank", "bingx",
    "bitmart", "weex", "crypto.com", "upbit",
}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _invalid_exact_identity(chain: object, token: object) -> bool:
    c = str(chain or "").strip().lower()
    t = str(token or "").strip().lower()
    return c in EVM_CHAINS and t == EVM_ZERO


def _strip_cross_source_enrichment(row: dict) -> dict:
    clean = dict(row)
    for key in list(clean):
        if key.startswith("cross_source_"):
            clean.pop(key, None)
    return clean


def _parse_ts(value: object) -> datetime | None:
    try:
        text = str(value or "").strip()
        return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None
    except Exception:
        return None


def _tier(count: int) -> str:
    if count >= 5:
        return "HIGH_DENSITY_MULTI_SOURCE"
    if count >= 3:
        return "MULTI_SOURCE_CONFIRMED"
    if count == 2:
        return "DOUBLE_SOURCE_CONFIRMED"
    return "SINGLE_SOURCE"


def _blocked_catalyst_evidence_ids(catalyst_ledger: Any, registry: Any) -> tuple[set[str], dict[str, int]]:
    """Return correlation evidence IDs whose CEX symbol->contract link fails exact registry truth.

    This reuses the Catalyst identity guard but never mutates the source ledger. It also
    catches stale pre-guard ledger rows, so a bad ticker collision cannot regain cross-source
    credit between workflow runs.
    """
    try:
        from wallet500 import catalyst_identity_guard as cig
    except Exception:
        return set(), {}

    records = catalyst_ledger.get("events") if isinstance(catalyst_ledger, dict) else {}
    if not isinstance(records, dict):
        return set(), {}
    symbols = cig._registry_symbols(registry)
    blocked: set[str] = set()
    reasons: dict[str, int] = {}
    for event_id, rec in records.items():
        event = rec.get("event") if isinstance(rec, dict) else None
        if not isinstance(event, dict):
            continue
        sanitized, _, reason = cig.sanitize_event(event, symbols)
        if sanitized.get("identity_guard_fail_closed") is True and sanitized.get("symbol_contract_link_verified") is not True:
            blocked.add(f"catalyst:{event_id}")
            reasons[reason] = reasons.get(reason, 0) + 1
    return blocked, reasons


def _recompute_asset(raw: dict, blocked_evidence_ids: set[str]) -> tuple[dict | None, int]:
    asset = dict(raw)
    evidence = asset.get("evidence")
    if not isinstance(evidence, list) or not blocked_evidence_ids:
        return asset, 0

    kept = [e for e in evidence if isinstance(e, dict) and str(e.get("evidence_id") or "") not in blocked_evidence_ids]
    removed = len([e for e in evidence if isinstance(e, dict)]) - len(kept)
    if removed <= 0:
        return asset, 0
    if not kept:
        return None, removed

    owners = sorted({str(e.get("source_owner") or "").strip().lower() for e in kept if e.get("source_owner")})
    source_ids = sorted({str(e.get("source_id") or "") for e in kept if e.get("source_id")})
    lanes = sorted({str(e.get("lane") or "") for e in kept if e.get("lane")})
    categories = sorted({str(e.get("source_category") or "other") for e in kept})
    exchange_owners = sorted({
        str(e.get("source_owner") or "").strip().lower()
        for e in kept
        if str(e.get("source_owner") or "").strip().lower() in EXCHANGE_OWNERS
        or str(e.get("source_category") or "").lower() == "exchange"
    })
    first_values = [x for x in (_parse_ts(e.get("first_seen_at")) for e in kept) if x]
    last_values = [x for x in (_parse_ts(e.get("last_seen_at")) for e in kept) if x]
    count = len(owners)

    asset.update(
        evidence=kept,
        source_confirmation_count=count,
        exchange_confirmation_count=len(exchange_owners),
        surface_count=len(source_ids),
        event_count=len(kept),
        source_category_count=len(categories),
        sources_seen=owners,
        exchange_sources_seen=exchange_owners,
        source_surfaces_seen=source_ids,
        lanes_seen=lanes,
        source_categories_seen=categories,
        confirmation_tier=_tier(count),
        discovery_confirmation_multiplier=float(min(4, max(1, count))),
        first_seen_any_source_at=min(first_values).isoformat() if first_values else asset.get("first_seen_any_source_at"),
        last_seen_any_source_at=max(last_values).isoformat() if last_values else asset.get("last_seen_any_source_at"),
        source_first_seen_spread_seconds=(
            int((max(first_values) - min(first_values)).total_seconds()) if len(first_values) >= 2 else 0
        ),
    )
    return asset, removed


def _watch_fields(asset: dict) -> dict:
    return {
        "cross_source_asset_key": asset.get("asset_key"),
        "cross_source_confirmation_tier": asset.get("confirmation_tier"),
        "cross_source_confirmation_count": asset.get("source_confirmation_count"),
        "cross_source_exchange_confirmation_count": asset.get("exchange_confirmation_count"),
        "cross_source_multiplier": asset.get("discovery_confirmation_multiplier"),
        "cross_source_sources": asset.get("sources_seen"),
        "cross_source_first_seen_at": asset.get("first_seen_any_source_at"),
        "cross_source_last_seen_at": asset.get("last_seen_any_source_at"),
        "cross_source_continuous_rescan": True,
    }


def sanitize(
    correlation: dict,
    watchlist: list,
    catalyst_ledger: Any = None,
    registry: Any = None,
) -> tuple[dict, list, dict]:
    corr = dict(correlation or {})
    assets_raw = corr.get("assets") if isinstance(corr.get("assets"), dict) else {}
    blocked_evidence_ids, blocked_reasons = _blocked_catalyst_evidence_ids(catalyst_ledger or {}, registry or {})
    assets: dict[str, dict] = {}
    dropped_keys: list[str] = []
    evidence_removed = 0
    catalyst_assets_dropped = 0
    catalyst_assets_downgraded = 0

    for key, raw in assets_raw.items():
        if not isinstance(raw, dict):
            continue
        if _invalid_exact_identity(raw.get("chain"), raw.get("token")):
            dropped_keys.append(str(key))
            continue
        cleaned, removed = _recompute_asset(raw, blocked_evidence_ids)
        evidence_removed += removed
        if cleaned is None:
            dropped_keys.append(str(key))
            catalyst_assets_dropped += 1
            continue
        if removed:
            catalyst_assets_downgraded += 1
        assets[str(key)] = cleaned

    corr["assets"] = assets
    counts = dict(corr.get("counts") or {})
    counts["correlated_assets"] = len(assets)
    counts["exact_identity_assets"] = sum(
        1 for row in assets.values() if row.get("identity_confidence") == "EXACT_CHAIN_CONTRACT"
    )
    counts["multi_source_assets"] = sum(
        1 for row in assets.values() if int(row.get("source_confirmation_count") or 0) >= 2
    )
    counts["double_or_better_exchange_assets"] = sum(
        1 for row in assets.values() if int(row.get("exchange_confirmation_count") or 0) >= 2
    )
    counts["invalid_exact_identity_dropped"] = sum(
        1 for raw in assets_raw.values()
        if isinstance(raw, dict) and _invalid_exact_identity(raw.get("chain"), raw.get("token"))
    )
    counts["blocked_catalyst_evidence_removed"] = evidence_removed
    corr["counts"] = counts

    policy = dict(corr.get("policy") or {})
    policy["invalid_identity"] = (
        "EVM zero/native sentinel is never an exact token contract; generated correlation/watchlist surfaces fail closed while source ledgers remain immutable"
    )
    policy["catalyst_symbol_identity"] = (
        "CEX catalyst evidence contributes cross-source confirmation only after exact symbol+chain+contract registry verification; symbol-only collisions are removed before publication"
    )
    corr["policy"] = policy
    corr["identity_guard"] = {
        "fail_closed": True,
        "source_ledgers_modified": False,
        "invalid_exact_identity_dropped": counts["invalid_exact_identity_dropped"],
        "blocked_catalyst_evidence_removed": evidence_removed,
        "blocked_catalyst_event_ids": sorted(blocked_evidence_ids),
        "blocked_catalyst_reasons": blocked_reasons,
        "catalyst_assets_dropped": catalyst_assets_dropped,
        "catalyst_assets_downgraded": catalyst_assets_downgraded,
        "dropped_asset_keys": dropped_keys,
    }

    dropped_lower = {x.lower() for x in dropped_keys}
    out_watch: list[dict] = []
    removed_generated = 0
    stripped_enrichment = 0
    refreshed_enrichment = 0
    for raw in watchlist if isinstance(watchlist, list) else []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        invalid = _invalid_exact_identity(row.get("chain"), row.get("token") or row.get("contract") or row.get("mint"))
        cross_key = str(row.get("cross_source_asset_key") or "")
        dropped_cross_key = cross_key.lower() in dropped_lower if cross_key else False
        if (invalid or dropped_cross_key) and row.get("source") == "CROSS_SOURCE_CORRELATION":
            removed_generated += 1
            continue
        if invalid or dropped_cross_key:
            cleaned = _strip_cross_source_enrichment(row)
            if cleaned != row:
                stripped_enrichment += 1
            row = cleaned
        elif cross_key and cross_key in assets:
            before = dict(row)
            row.update(_watch_fields(assets[cross_key]))
            if row != before:
                refreshed_enrichment += 1
        out_watch.append(row)

    stats = {
        "invalid_exact_identity_dropped": counts["invalid_exact_identity_dropped"],
        "blocked_catalyst_evidence_removed": evidence_removed,
        "catalyst_assets_dropped": catalyst_assets_dropped,
        "catalyst_assets_downgraded": catalyst_assets_downgraded,
        "generated_watch_rows_removed": removed_generated,
        "non_generated_rows_enrichment_stripped": stripped_enrichment,
        "watch_rows_enrichment_refreshed": refreshed_enrichment,
    }
    return corr, out_watch, stats


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    corr_path = data / CORRELATION.name
    watch_path = data / WATCHLIST.name
    catalyst_path = data / CATALYST_LEDGER.name
    registry_path = data / CEX_REGISTRY.name
    corr = _load(corr_path, {})
    watch = _load(watch_path, [])
    catalyst = _load(catalyst_path, {"events": {}})
    registry = _load(registry_path, {})
    out_corr, out_watch, stats = sanitize(corr, watch, catalyst, registry)
    _write(corr_path, out_corr)
    _write(watch_path, out_watch)
    return stats


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
