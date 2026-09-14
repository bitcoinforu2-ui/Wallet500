from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Iterable, Mapping

SOCIAL_PRECURSOR_VERSION = "WALLET500_SOCIAL_PRECURSOR_SHADOW_V1"
SOCIAL_STALE_AFTER_SECONDS = 6 * 60 * 60
CATALYST_EXACT_HORIZON_SECONDS = 7 * 24 * 60 * 60

_PROVIDER_KEYS = {
    "lunarcrush": "LUNARCRUSH_API_KEY",
    "santiment": "SANTIMENT_API_KEY",
    "coinmarketcal": "COINMARKETCAL_API_KEY",
}

_FEATURE_WEIGHTS = {
    "mention_velocity": 1.00,
    "creator_convergence": 0.90,
    "social_dominance": 0.80,
    "sentiment_shift": 0.65,
    "social_volume": 0.75,
    "catalyst_proximity": 0.70,
}


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _utc(value: object, *, allow_naive: bool = False) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if dt.tzinfo is None:
        if not allow_naive:
            return None
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now_utc(now: object | None) -> datetime:
    parsed = _utc(now, allow_naive=True)
    return parsed or datetime.now(timezone.utc)


def _chain(value: object) -> str:
    raw = str(value or "").strip().lower()
    aliases = {"eth": "ethereum", "bnb": "bsc", "binance": "bsc", "sol": "solana"}
    return aliases.get(raw, raw)


def _contract(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    if chain in {"ethereum", "bsc", "base", "arbitrum", "polygon", "optimism"}:
        return raw.lower()
    return raw


def exact_identity(payload: Mapping[str, object] | None) -> tuple[str, str] | None:
    """Return exact chain+contract identity only; names/tickers are deliberately ignored."""
    if not isinstance(payload, Mapping):
        return None
    chain = _chain(payload.get("chain") or payload.get("network"))
    contract = _contract(
        chain,
        payload.get("contract")
        or payload.get("token_address")
        or payload.get("mint")
        or payload.get("token"),
    )
    if not chain or not contract:
        return None
    status = str(payload.get("identity_status") or "").upper()
    if status in {"UNRESOLVED", "AMBIGUOUS", "TICKER_ONLY", "NAME_ONLY"}:
        return None
    return chain, contract


def provider_configuration(provider: str, environ: Mapping[str, str] | None = None) -> dict:
    """Optional providers are neutral when credentials are absent."""
    normalized = str(provider or "").strip().lower()
    env_name = _PROVIDER_KEYS.get(normalized)
    env = environ if environ is not None else os.environ
    configured = bool(env_name and str(env.get(env_name) or "").strip())
    return {
        "provider": normalized,
        "supported": env_name is not None,
        "env_var": env_name,
        "configured": configured,
        "missing_credentials_is_positive_evidence": False,
        "production_effect": False,
    }


def normalized_social_velocity(
    samples: Iterable[Mapping[str, object]], *, now: object | None = None, value_field: str = "value"
) -> dict:
    """Normalize mention/engagement growth by real elapsed time and reject time leakage."""
    current = _now_utc(now)
    points: list[tuple[datetime, float]] = []
    for sample in samples:
        if not isinstance(sample, Mapping):
            return {"valid": False, "reason": "MALFORMED_SAMPLE", "rate_per_min": None}
        observed = _utc(sample.get("observed_at") or sample.get("timestamp"))
        value = _number(sample.get(value_field))
        if observed is None or value is None:
            return {"valid": False, "reason": "MISSING_TIMESTAMP_OR_VALUE", "rate_per_min": None}
        if observed > current:
            return {"valid": False, "reason": "FUTURE_SAMPLE", "rate_per_min": None}
        if points and observed <= points[-1][0]:
            return {"valid": False, "reason": "NON_MONOTONIC_TIMESTAMP", "rate_per_min": None}
        points.append((observed, value))
    if len(points) < 2:
        return {"valid": False, "reason": "INSUFFICIENT_POINTS", "rate_per_min": None}
    (t0, v0), (t1, v1) = points[-2], points[-1]
    minutes = (t1 - t0).total_seconds() / 60.0
    if minutes <= 0:
        return {"valid": False, "reason": "NON_POSITIVE_WINDOW", "rate_per_min": None}
    return {
        "valid": True,
        "reason": "OK",
        "points": len(points),
        "elapsed_minutes": minutes,
        "delta": v1 - v0,
        "rate_per_min": (v1 - v0) / minutes,
    }


def _canonical_evidence(raw: Mapping[str, object], *, now: datetime) -> tuple[dict | None, str | None]:
    provider = str(raw.get("provider") or raw.get("source") or "").strip().lower()
    event_id = str(raw.get("external_id") or raw.get("event_id") or raw.get("post_id") or raw.get("id") or "").strip()
    feature = str(raw.get("feature") or raw.get("kind") or "").strip().lower()
    identity = exact_identity(raw)
    published = _utc(raw.get("published_at") or raw.get("observed_at") or raw.get("created_at"))
    fetched = _utc(raw.get("fetched_at"))
    if not provider or not event_id or feature not in _FEATURE_WEIGHTS:
        return None, "MISSING_PROVIDER_EVENT_ID_OR_FEATURE"
    if identity is None:
        return None, "IDENTITY_UNRESOLVED_OR_AMBIGUOUS"
    if published is None:
        return None, "TIMESTAMP_MISSING_OR_TIMEZONE_AMBIGUOUS"
    if published > now or (fetched is not None and fetched > now):
        return None, "FUTURE_TIMESTAMP"
    strength = _number(raw.get("strength"))
    confidence = _number(raw.get("confidence"))
    if strength is None or confidence is None:
        return None, "MISSING_STRENGTH_OR_CONFIDENCE"
    strength = min(1.0, max(0.0, strength))
    confidence = min(1.0, max(0.0, confidence))
    event_at = _utc(raw.get("event_at"))
    event_time_is_exact = raw.get("event_time_is_exact") is True
    return {
        "provider": provider,
        "external_id": event_id,
        "feature": feature,
        "chain": identity[0],
        "contract": identity[1],
        "published_at": published,
        "fetched_at": fetched,
        "strength": strength,
        "confidence": confidence,
        "event_at": event_at,
        "event_time_is_exact": event_time_is_exact,
        "source_url": str(raw.get("source_url") or raw.get("url") or "").strip() or None,
    }, None


def parse_coinmarketcal_event(
    event: Mapping[str, object], *, fetched_at: object, chain: str | None = None, contract: str | None = None
) -> dict:
    """Normalize CoinMarketCal v2 semantics without treating estimated deadlines as exact event times."""
    estimated = event.get("isEstimated") is True or event.get("is_estimated") is True
    date_value = event.get("date")
    event_at = None if estimated else date_value
    confidence = _number(event.get("confidence"))
    if confidence is None:
        confidence = 0.5
    confidence = min(1.0, max(0.0, confidence))
    result = {
        "provider": "coinmarketcal",
        "external_id": str(event.get("id") or event.get("event_id") or ""),
        "feature": "catalyst_proximity",
        "published_at": event.get("published_at") or fetched_at,
        "fetched_at": fetched_at,
        "chain": chain or event.get("chain"),
        "contract": contract or event.get("contract") or event.get("token_address"),
        "identity_status": "EXACT" if (chain or event.get("chain")) and (contract or event.get("contract") or event.get("token_address")) else "UNRESOLVED",
        "strength": min(1.0, max(0.0, _number(event.get("strength")) or 0.5)),
        "confidence": confidence,
        "event_at": event_at,
        "event_time_is_exact": not estimated,
        "displayed_date": event.get("displayedDate") or event.get("displayed_date"),
        "estimated_window_deadline": date_value if estimated else None,
        "source_url": event.get("source") or event.get("url"),
    }
    return result


def assess_social_precursors(
    candidate: Mapping[str, object], evidence: Iterable[Mapping[str, object]] | None, *, now: object | None = None
) -> dict:
    """Score exact-identity social evidence in shadow only; never alter live eligibility."""
    current = _now_utc(now)
    candidate_identity = exact_identity(candidate)
    rows = list(evidence or [])
    accepted: list[dict] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    rejected: dict[str, int] = {}
    duplicates = stale = mismatched = 0

    for raw in rows:
        if not isinstance(raw, Mapping):
            rejected["MALFORMED_EVIDENCE"] = rejected.get("MALFORMED_EVIDENCE", 0) + 1
            continue
        row, reason = _canonical_evidence(raw, now=current)
        if row is None:
            rejected[reason or "INVALID"] = rejected.get(reason or "INVALID", 0) + 1
            continue
        key = (row["provider"], row["external_id"], row["chain"], row["contract"], row["feature"])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if candidate_identity is None or (row["chain"], row["contract"]) != candidate_identity:
            mismatched += 1
            continue
        age_seconds = (current - row["published_at"]).total_seconds()
        if row["feature"] == "catalyst_proximity":
            event_at = row.get("event_at")
            if not row.get("event_time_is_exact") or event_at is None:
                rejected["ESTIMATED_CATALYST_NOT_EXACT_TIMING"] = rejected.get("ESTIMATED_CATALYST_NOT_EXACT_TIMING", 0) + 1
                continue
            seconds_to_event = (event_at - current).total_seconds()
            if seconds_to_event < 0 or seconds_to_event > CATALYST_EXACT_HORIZON_SECONDS:
                stale += 1
                continue
            recency = max(0.20, 1.0 - seconds_to_event / CATALYST_EXACT_HORIZON_SECONDS)
        else:
            if age_seconds > SOCIAL_STALE_AFTER_SECONDS:
                stale += 1
                continue
            recency = max(0.0, 1.0 - age_seconds / SOCIAL_STALE_AFTER_SECONDS)
        weighted = row["strength"] * row["confidence"] * _FEATURE_WEIGHTS[row["feature"]] * recency
        accepted.append({**row, "weighted_shadow_strength": weighted})

    if accepted:
        aggregate = sum(row["weighted_shadow_strength"] for row in accepted)
        provider_count = len({row["provider"] for row in accepted})
        convergence_multiplier = min(1.20, 1.0 + 0.05 * max(0, provider_count - 1))
        score = min(100.0, 100.0 * (1.0 - math.exp(-aggregate * convergence_multiplier)))
    else:
        provider_count = 0
        score = 0.0

    return {
        "version": SOCIAL_PRECURSOR_VERSION,
        "detected": bool(accepted),
        "shadow_score": round(score, 4),
        "ranking_only": True,
        "research_shadow": True,
        "research_only": True,
        "actionable": False,
        "real_alert_eligible": False,
        "automatic_buy": False,
        "auto_promote": False,
        "production_score_effect": 0.0,
        "candidate_exact_identity": candidate_identity is not None,
        "input_count": len(rows),
        "accepted_exact_count": len(accepted),
        "provider_count": provider_count,
        "duplicate_count": duplicates,
        "stale_count": stale,
        "identity_mismatch_count": mismatched,
        "rejected": rejected,
        "features": sorted({row["feature"] for row in accepted}),
        "providers": sorted({row["provider"] for row in accepted}),
        "rule": "SOCIAL_EVIDENCE_MAY_RANK_RESEARCH_ONLY; NEVER_AUTO_PROMOTE_OR_CREATE_REAL_ALERT",
    }
