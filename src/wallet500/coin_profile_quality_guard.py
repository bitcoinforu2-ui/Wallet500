from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

DATA = Path("data")
LATEST = DATA / "coin-intelligence-profiles.json"
LEDGER = DATA / "coin-intelligence-profile-ledger.json"
ARCHIVE = DATA / "coin-intelligence-profile-archive.json"
DNA = DATA / "coin-profile-dna-library.json"
REPORT = DATA / "coin-profile-data-quality.json"

PRICE_WINDOW_HOURS = 6
CATASTROPHIC_PRICE_RATIO = 1000.0

PRICE_KEYS = {
    "price_usd", "current_price_usd", "dex_price_usd", "reference_price",
    "t0_price_usd", "entry_price_usd", "price", "mark_price_usd",
}
LIQUIDITY_KEYS = {
    "liquidity_usd", "dex_liquidity_usd", "dex_pair_liquidity_usd",
    "execution_pool_liquidity_usd", "current_liquidity_usd",
}
VOLUME_KEYS = {
    "volume_h1", "volume_h24", "volume_24h_usd", "dex_pair_volume_24h_usd",
}
CONCENTRATION_KEYS = {
    "top1_pct", "top5_pct", "top10_pct", "adjusted_top1_pct",
    "adjusted_top5_pct", "adjusted_top10_pct", "cluster_pct",
    "largest_cluster_pct",
}
REVIVAL_SCORE_KEYS = {"revival_score", "revival_score_verified", "cex_revival_score", "cex_score"}
RISK_SCORE_KEYS = {"risk_score"}
SOURCE_COUNT_KEYS = {"source_confirmation_count", "exchange_confirmation_count"}

FAMILY_DIMENSIONS = {
    "price": {"price_structure"},
    "liquidity": {"liquidity_depth"},
    "holder_concentration": {"holder_safety"},
    "revival_score": {"revival_strength"},
    "risk_score": {"risk_inverse"},
    "source_count": {"source_confirmation", "exchange_confirmation"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _num(value: object) -> float | None:
    try:
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return None
        return x
    except (TypeError, ValueError):
        return None


def _parse_ts(value: object) -> datetime | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _leaf(path: str) -> str:
    return str(path).split(".")[-1].lower()


def _numeric_paths(value: Any, prefix: str = "", depth: int = 0) -> Iterable[tuple[str, float]]:
    if depth > 6 or not isinstance(value, dict):
        return
    for key, raw in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(raw, dict):
            yield from _numeric_paths(raw, path, depth + 1)
        else:
            n = _num(raw)
            if n is not None:
                yield path, n


def _event_prices(event: dict) -> list[tuple[str, float]]:
    facts = event.get("facts") if isinstance(event.get("facts"), dict) else {}
    out = []
    for path, value in _numeric_paths(facts):
        if _leaf(path) in PRICE_KEYS and value > 0:
            out.append((path, value))
    return out


def _quality(profile: dict) -> dict:
    flags: set[str] = set()
    families: set[str] = set()
    evidence: list[dict] = []
    timeline = [x for x in (profile.get("timeline") or []) if isinstance(x, dict)]

    timed_prices: list[tuple[datetime, str, str, float]] = []
    for event in timeline:
        at = _parse_ts(event.get("last_seen_at") or event.get("first_seen_at"))
        facts = event.get("facts") if isinstance(event.get("facts"), dict) else {}
        event_prices = _event_prices(event)
        if at:
            for path, value in event_prices:
                timed_prices.append((at, str(event.get("lane") or ""), path, value))

        if len(event_prices) >= 2:
            vals = [x[1] for x in event_prices]
            lo, hi = min(vals), max(vals)
            if lo > 0 and hi / lo >= CATASTROPHIC_PRICE_RATIO:
                flags.add("INTRA_EVENT_PRICE_CONFLICT_GT_1000X")
                families.add("price")
                evidence.append({
                    "type": "INTRA_EVENT_PRICE_CONFLICT_GT_1000X",
                    "lane": event.get("lane"),
                    "ratio": round(hi / lo, 6),
                    "min_price": lo,
                    "max_price": hi,
                })

        for path, value in _numeric_paths(facts):
            leaf = _leaf(path)
            if leaf in PRICE_KEYS and value < 0:
                flags.add("NEGATIVE_PRICE_METRIC")
                families.add("price")
            elif leaf in LIQUIDITY_KEYS and value < 0:
                flags.add("NEGATIVE_LIQUIDITY_METRIC")
                families.add("liquidity")
            elif leaf in VOLUME_KEYS and value < 0:
                flags.add("NEGATIVE_VOLUME_METRIC")
                families.add("volume")
            elif leaf in CONCENTRATION_KEYS and not (0 <= value <= 100):
                flags.add("HOLDER_CONCENTRATION_OUTSIDE_0_100")
                families.add("holder_concentration")
            elif leaf in REVIVAL_SCORE_KEYS and not (0 <= value <= 100):
                flags.add("REVIVAL_SCORE_OUTSIDE_0_100")
                families.add("revival_score")
            elif leaf in RISK_SCORE_KEYS and not (0 <= value <= 100):
                flags.add("RISK_SCORE_OUTSIDE_0_100")
                families.add("risk_score")
            elif leaf in SOURCE_COUNT_KEYS and value < 0:
                flags.add("NEGATIVE_SOURCE_CONFIRMATION_COUNT")
                families.add("source_count")

    if timed_prices:
        latest_at = max(x[0] for x in timed_prices)
        floor = latest_at - timedelta(hours=PRICE_WINDOW_HOURS)
        recent = [x for x in timed_prices if x[0] >= floor]
        values = [x[3] for x in recent if x[3] > 0]
        if len(values) >= 2:
            lo, hi = min(values), max(values)
            if lo > 0 and hi / lo >= CATASTROPHIC_PRICE_RATIO:
                flags.add("CROSS_EVENT_PRICE_CONFLICT_GT_1000X_WITHIN_6H")
                families.add("price")
                evidence.append({
                    "type": "CROSS_EVENT_PRICE_CONFLICT_GT_1000X_WITHIN_6H",
                    "window_hours": PRICE_WINDOW_HOURS,
                    "ratio": round(hi / lo, 6),
                    "min_price": lo,
                    "max_price": hi,
                    "lanes": sorted({x[1] for x in recent if x[1]}),
                })

    status = "CONFLICT_QUARANTINED" if families else "CLEAN"
    return {
        "status": status,
        "flags": sorted(flags),
        "quarantined_metric_families": sorted(families),
        "raw_evidence_retained": True,
        "quarantined_metrics_excluded_from_dna": True,
        "automatic_trade_effect": "NONE",
        "evidence": evidence[:20],
    }


def _sanitize_fingerprint(raw: Any, quality: dict) -> dict:
    fp = copy.deepcopy(raw) if isinstance(raw, dict) else {"dimensions": {}}
    dims = fp.get("dimensions") if isinstance(fp.get("dimensions"), dict) else {}
    dims = dict(dims)
    for family in quality.get("quarantined_metric_families") or []:
        for name in FAMILY_DIMENSIONS.get(str(family), set()):
            if name in dims:
                dims[name] = None
    fp["dimensions"] = dims
    total = len(dims)
    observed = sum(value is not None for value in dims.values())
    fp["feature_coverage_count"] = observed
    fp["feature_coverage_ratio"] = round(observed / total, 6) if total else 0.0
    fp["truth_rule"] = "MISSING_OR_QUARANTINED_DIMENSIONS_REMAIN_UNOBSERVED"
    fp["quality_quarantine_applied"] = bool(quality.get("quarantined_metric_families"))
    return fp


def _guard_full_profile(profile: dict) -> dict:
    quality = _quality(profile)
    profile["data_quality"] = quality
    profile["learning_fingerprint"] = _sanitize_fingerprint(profile.get("fingerprint"), quality)
    profile["research_similarity_eligible"] = (
        quality.get("status") == "CLEAN"
        and float((profile.get("learning_fingerprint") or {}).get("feature_coverage_ratio") or 0) >= 0.5
    )
    return quality


def _unknown_archive_quality() -> dict:
    return {
        "status": "QUALITY_NOT_REEVALUATED_COMPACT_ARCHIVE",
        "flags": ["FULL_TIMELINE_NOT_AVAILABLE_IN_COMPACT_ARCHIVE"],
        "quarantined_metric_families": [],
        "raw_evidence_retained": True,
        "quarantined_metrics_excluded_from_dna": True,
        "automatic_trade_effect": "NONE",
        "evidence": [],
    }


def run(root: Path = DATA) -> dict:
    latest_path = root / LATEST.name
    ledger_path = root / LEDGER.name
    archive_path = root / ARCHIVE.name
    dna_path = root / DNA.name
    report_path = root / REPORT.name

    latest = _load(latest_path, {})
    ledger = _load(ledger_path, {})
    archive = _load(archive_path, {"entries": {}})
    dna = _load(dna_path, {"profiles": {}})

    profiles = ledger.get("profiles") if isinstance(ledger, dict) else {}
    if not isinstance(profiles, dict):
        raise SystemExit("COIN_PROFILE_QUALITY_LEDGER_MISSING")

    quality_by_id: dict[str, dict] = {}
    for key, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        quality_by_id[str(key)] = _guard_full_profile(profile)

    latest_profiles = latest.get("profiles") if isinstance(latest, dict) else []
    if isinstance(latest_profiles, list):
        for profile in latest_profiles:
            if not isinstance(profile, dict):
                continue
            key = str(profile.get("profile_id") or "")
            q = quality_by_id.get(key)
            if q is None:
                q = _guard_full_profile(profile)
                quality_by_id[key] = q
            else:
                profile["data_quality"] = copy.deepcopy(q)
                source = profiles.get(key) or {}
                profile["learning_fingerprint"] = copy.deepcopy(
                    source.get("learning_fingerprint") or _sanitize_fingerprint(profile.get("fingerprint"), q)
                )
                profile["research_similarity_eligible"] = bool(source.get("research_similarity_eligible"))

    archive_entries = archive.get("entries") if isinstance(archive, dict) else {}
    if not isinstance(archive_entries, dict):
        archive_entries = {}
    for key, entry in archive_entries.items():
        if not isinstance(entry, dict):
            continue
        q = quality_by_id.get(str(key)) or entry.get("data_quality") or _unknown_archive_quality()
        entry["data_quality"] = copy.deepcopy(q)
        entry["research_similarity_eligible"] = False if str(q.get("status")) != "CLEAN" else bool(entry.get("research_similarity_eligible"))

    dna_profiles = dna.get("profiles") if isinstance(dna, dict) else {}
    if not isinstance(dna_profiles, dict):
        dna_profiles = {}
    eligible = 0
    for key, row in dna_profiles.items():
        if not isinstance(row, dict):
            continue
        full = profiles.get(str(key))
        q = quality_by_id.get(str(key))
        if isinstance(full, dict) and q:
            row["raw_fingerprint"] = copy.deepcopy(row.get("fingerprint"))
            row["fingerprint"] = copy.deepcopy(full.get("learning_fingerprint") or _sanitize_fingerprint(row.get("fingerprint"), q))
            row["data_quality"] = copy.deepcopy(q)
            row["research_similarity_eligible"] = bool(full.get("research_similarity_eligible"))
        else:
            q = (archive_entries.get(str(key)) or {}).get("data_quality") or _unknown_archive_quality()
            row["data_quality"] = copy.deepcopy(q)
            row["research_similarity_eligible"] = False
        if row.get("research_similarity_eligible"):
            eligible += 1

    quarantined = [
        (key, q) for key, q in quality_by_id.items()
        if q.get("status") == "CONFLICT_QUARANTINED"
    ]
    price_conflicts = sum("price" in (q.get("quarantined_metric_families") or []) for _, q in quarantined)

    counts = latest.setdefault("counts", {}) if isinstance(latest, dict) else {}
    if isinstance(counts, dict):
        counts["profiles_with_quarantined_metrics"] = len(quarantined)
        counts["profiles_with_price_conflicts"] = price_conflicts
        counts["research_similarity_eligible_profiles"] = eligible
    latest.setdefault("truth_contract", {})["quarantined_metrics_excluded_from_dna"] = True
    latest["data_quality_guard"] = {
        "status": "ENFORCED",
        "price_conflict_ratio": CATASTROPHIC_PRICE_RATIO,
        "price_conflict_window_hours": PRICE_WINDOW_HOURS,
        "raw_evidence_retained": True,
    }

    ledger.setdefault("truth_contract", {})["quarantined_metrics_excluded_from_dna"] = True
    ledger["data_quality_guard"] = copy.deepcopy(latest["data_quality_guard"])
    archive["entries"] = archive_entries
    archive["data_quality_policy"] = "COMPACT_ARCHIVE_WITHOUT_FULL_TIMELINE_IS_NOT_AUTO_ELIGIBLE_FOR_SIMILARITY"

    dna.setdefault("truth_contract", {})["quarantined_metrics_excluded_from_similarity"] = True
    dna.setdefault("truth_contract", {})["raw_profile_evidence_is_preserved_for_audit"] = True
    dna["data_quality_guard"] = copy.deepcopy(latest["data_quality_guard"])
    dna_counts = dna.setdefault("counts", {})
    if isinstance(dna_counts, dict):
        dna_counts["quality_quarantined"] = len(quarantined)
        dna_counts["research_similarity_eligible"] = eligible

    report = {
        "version": 1,
        "generated_at": _now(),
        "mode": "COIN_PROFILE_DATA_QUALITY_GUARD_V1",
        "automatic_trade": False,
        "production_change": False,
        "policy": {
            "raw_evidence_is_never_deleted": True,
            "catastrophic_price_conflict_ratio": CATASTROPHIC_PRICE_RATIO,
            "cross_event_window_hours": PRICE_WINDOW_HOURS,
            "quarantined_metric_families_are_removed_from_learning_fingerprint": True,
            "clean_low_coverage_profiles_are_not_similarity_eligible": True,
        },
        "counts": {
            "profiles_checked": len(quality_by_id),
            "profiles_quarantined": len(quarantined),
            "price_conflicts": price_conflicts,
            "research_similarity_eligible": eligible,
        },
        "quarantined_profiles": [
            {
                "profile_id": key,
                "flags": q.get("flags"),
                "quarantined_metric_families": q.get("quarantined_metric_families"),
                "evidence": q.get("evidence"),
            }
            for key, q in quarantined[:200]
        ],
    }

    _write(latest_path, latest)
    _write(ledger_path, ledger)
    _write(archive_path, archive)
    _write(dna_path, dna)
    _write(report_path, report)
    return report


if __name__ == "__main__":
    out = run()
    print("COIN_PROFILE_DATA_QUALITY_OK", json.dumps(out.get("counts"), separators=(",", ":")))
