from __future__ import annotations

"""Truth-preserving runner for the Hybrid V1 engine.

Market/pair snapshots and on-chain evidence are asynchronous.  This runner keeps
market baselines immutable per Revival snapshot while allowing fresh exact-mint
external evidence to update the Hybrid profile after that snapshot.  Re-running
the same market snapshot never increments the market baseline a second time.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import hybrid_token_profile as engine
from .revival_1000 import looks_like_solana_address

MAX_EXTERNAL_AGE = timedelta(hours=30)
MAX_AFTER_SOURCE_LAG = timedelta(hours=2)
FUTURE_CLOCK_TOLERANCE = timedelta(minutes=2)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _external_fingerprint(external: dict[str, dict]) -> str:
    canonical = json.dumps(external, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_external_truth(source_generated_at: str, profile_observed_at: datetime | None = None) -> dict[str, dict]:
    payload = engine._load(engine.EXTERNAL, {})
    rows = payload.get("observations") or [] if isinstance(payload, dict) else []
    source_dt = engine._dt(source_generated_at)
    now = profile_observed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    if source_dt is None:
        return {}
    source_dt = source_dt.astimezone(timezone.utc)
    earliest = source_dt - MAX_EXTERNAL_AGE
    latest_allowed = min(source_dt + MAX_AFTER_SOURCE_LAG, now + FUTURE_CLOCK_TOLERANCE)
    latest: dict[str, tuple[datetime, dict]] = {}
    for row in rows:
        if not isinstance(row, dict) or str(row.get("network") or "").lower() != engine.NETWORK:
            continue
        address = str(row.get("token_address") or "")
        observed = engine._dt(row.get("observed_at"))
        if not looks_like_solana_address(address) or observed is None:
            continue
        observed = observed.astimezone(timezone.utc)
        if observed < earliest or observed > latest_allowed:
            continue
        old = latest.get(address)
        if old is None or observed > old[0]:
            latest[address] = (observed, row)
    return {k: v[1] for k, v in latest.items()}


def _recompute_profile_with_external(profile: dict, external_row: dict | None, observed_at: str) -> dict:
    """Refresh only external channels; never replay market/pair baseline state."""
    out = dict(profile)
    channels = dict(out.get("channels") or {})
    for name in engine.EXTERNAL_CHANNELS:
        channels[name] = engine._external_channel(name, external_row)

    coverage = 0.0
    raw = 0.0
    strong: list[str] = []
    for name, weight in engine.CHANNEL_WEIGHTS.items():
        channel = channels.get(name) or {}
        if channel.get("available") is True and channel.get("verified") is True:
            score = max(0.0, min(100.0, engine._n(channel.get("score"), 0.0) or 0.0))
            coverage += weight
            raw += weight * score / 100.0
            if score >= 55:
                strong.append(name)

    normalized = raw / coverage * 100.0 if coverage > 0 else 0.0
    observations_before = int(out.get("baseline_observations_before") or 0)
    ext_strong = sum(1 for name in engine.EXTERNAL_CHANNELS if name in strong)
    baseline_ready = observations_before >= engine.MIN_BASELINE_OBSERVATIONS or ext_strong >= 2
    risk = max(0.0, min(100.0, engine._n(out.get("risk_score"), 0.0) or 0.0))

    if risk >= 50:
        status = "RISK_DISTRIBUTION"
    elif baseline_ready and normalized >= 70 and raw >= 35 and len(strong) >= 2 and risk < 35:
        status = "HYBRID_IGNITION"
    elif normalized >= 55 and raw >= 25 and len(strong) >= 1:
        status = "ABNORMAL_ACTIVITY"
    elif not baseline_ready:
        status = "BASELINE_LEARNING"
    else:
        status = "NORMAL"

    out.update(
        {
            "observed_at": observed_at,
            "channels": channels,
            "hybrid_score_raw": round(raw, 2),
            "hybrid_score_verified_normalized": round(normalized, 2),
            "evidence_coverage_pct": round(coverage, 2),
            "strong_channels": strong,
            "baseline_ready": baseline_ready,
            "status": status,
        }
    )
    return out


def _counts(profiles: list[dict]) -> dict:
    return {
        "profiles": len(profiles),
        "hybrid_ignition": sum(x.get("status") == "HYBRID_IGNITION" for x in profiles),
        "abnormal_activity": sum(x.get("status") == "ABNORMAL_ACTIVITY" for x in profiles),
        "risk_distribution": sum(x.get("status") == "RISK_DISTRIBUTION" for x in profiles),
        "baseline_learning": sum(x.get("status") == "BASELINE_LEARNING" for x in profiles),
        "normal": sum(x.get("status") == "NORMAL" for x in profiles),
        "external_evidence_tokens": sum(
            any(((x.get("channels") or {}).get(c) or {}).get("available") is True for c in engine.EXTERNAL_CHANNELS)
            for x in profiles
        ),
    }


def run() -> dict:
    source = engine._load(engine.SOURCE, {})
    source_generated_at = str(source.get("generated_at") or "")
    source_dt = engine._dt(source_generated_at)
    if source.get("mode") != "RESEARCH_ONLY_REVIVAL_SOLANA_500_V4" or source.get("network") != engine.NETWORK:
        raise RuntimeError("HYBRID_SOURCE_TRUTH_CONTRACT_REJECTED")
    if source_dt is None:
        raise RuntimeError("HYBRID_SOURCE_TIMESTAMP_INVALID")

    profile_time = datetime.now(timezone.utc)
    profile_observed_at = _iso(profile_time)
    external = _load_external_truth(source_generated_at, profile_time)
    fingerprint = _external_fingerprint(external)
    state_before = engine._load(engine.STATE, {"version": 1, "tokens": {}})
    same_source = str(state_before.get("last_source_generated_at") or "") == source_generated_at
    same_external = str(state_before.get("last_external_fingerprint") or "") == fingerprint

    if same_source and same_external and engine.LATEST.exists():
        return engine._load(engine.LATEST, {})

    # For a new market snapshot the engine performs the one legitimate baseline update.
    # For the same snapshot engine.run() returns the existing payload, and we refresh only
    # external channels below, so the baseline observation count cannot be duplicated.
    engine._load_external = lambda _: external
    payload = engine.run()
    if not isinstance(payload, dict):
        raise RuntimeError("HYBRID_PROFILE_PAYLOAD_INVALID")

    profiles = []
    for profile in payload.get("profiles") or []:
        address = str(profile.get("token_address") or "")
        profiles.append(_recompute_profile_with_external(profile, external.get(address), profile_observed_at))
    profiles.sort(
        key=lambda x: (
            x.get("status") == "HYBRID_IGNITION",
            engine._n(x.get("hybrid_score_raw"), 0.0) or 0.0,
            engine._n(x.get("hybrid_score_verified_normalized"), 0.0) or 0.0,
        ),
        reverse=True,
    )

    payload["generated_at"] = profile_observed_at
    payload["source_generated_at"] = source_generated_at
    payload["counts"] = _counts(profiles)
    payload["profiles"] = profiles
    payload["external_evidence_timing_contract"] = {
        "method": "ASYNCHRONOUS_PROVIDER_TIMEBOX",
        "profile_timestamp_rule": "EXTERNAL_EVIDENCE_MUST_BE_AT_OR_BEFORE_HYBRID_PROFILE_TIME_PLUS_CLOCK_TOLERANCE",
        "market_snapshot_rule": "MARKET_BASELINE_UPDATES_ONCE_PER_UNIQUE_REVIVAL_SOURCE_TIMESTAMP",
        "max_age_hours_before_market_snapshot": MAX_EXTERNAL_AGE.total_seconds() / 3600,
        "max_lag_hours_after_market_snapshot": MAX_AFTER_SOURCE_LAG.total_seconds() / 3600,
        "future_clock_tolerance_minutes": FUTURE_CLOCK_TOLERANCE.total_seconds() / 60,
        "external_fingerprint": fingerprint,
    }
    payload["truth_rules"] = [
        "each profile is keyed by exact Solana mint address",
        "self baseline uses only observations collected before the current market snapshot and updates once per unique source timestamp",
        "fresh exact-mint external evidence may arrive after the market snapshot but never after the Hybrid profile time beyond clock tolerance",
        "holders/wallet/social/news data is scored only when contract_match=true and verified=true",
        "missing evidence gets zero weight and is never invented",
    ]
    engine.LATEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    state_after = engine._load(engine.STATE, {"version": 1, "tokens": {}})
    state_after["last_source_generated_at"] = source_generated_at
    state_after["last_external_fingerprint"] = fingerprint
    state_after["last_profile_generated_at"] = profile_observed_at
    state_after["updated_at"] = profile_observed_at
    engine.STATE.write_text(json.dumps(state_after, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run()
    print("HYBRID_TOKEN_PROFILE_RUNNER_OK", result.get("counts") if isinstance(result, dict) else None)
