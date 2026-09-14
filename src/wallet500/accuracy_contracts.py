from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable

ALERT_SCORE_THRESHOLD = 85.0


class AuthorityState(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"


def authority_state(payload: dict | None, field: str, *, provider_ok: bool = True) -> AuthorityState:
    """Tri-state authority truth; absent/malformed data is never interpreted as revoked."""
    if not provider_ok or not isinstance(payload, dict) or field not in payload:
        return AuthorityState.UNKNOWN
    value = payload.get(field)
    if value is None:
        return AuthorityState.REVOKED
    if isinstance(value, str) and value.strip():
        return AuthorityState.ACTIVE
    return AuthorityState.UNKNOWN


def candidate_authority_states(candidate: dict) -> dict[str, str]:
    """Normalize already-enriched Solana candidate authority truth without optimistic defaults."""
    verified = candidate.get("mintability_verified") is True
    status = str(candidate.get("mintability_status") or candidate.get("status") or "")
    if verified and status == "NON_MINTABLE_VERIFIED" and candidate.get("mint_authority") is None:
        mint = AuthorityState.REVOKED
    elif (verified and candidate.get("mintable") is True) or candidate.get("mint_authority") not in (None, ""):
        mint = AuthorityState.ACTIVE
    else:
        mint = AuthorityState.UNKNOWN

    if "freeze_authority" in candidate:
        freeze = authority_state(candidate, "freeze_authority", provider_ok=verified)
    elif "freeze_authority_state" in candidate:
        try:
            freeze = AuthorityState(str(candidate.get("freeze_authority_state")))
        except ValueError:
            freeze = AuthorityState.UNKNOWN
    else:
        freeze = AuthorityState.UNKNOWN
    return {"mint": mint.value, "freeze": freeze.value}


def _number(row: dict, *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        try:
            n = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(n):
            return n
    return None


def _utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalized_acceleration(samples: Iterable[dict], *, now: datetime | None = None, value_field: str = "value") -> dict:
    """Time-normalized acceleration that rejects future, duplicate and out-of-order observations."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    points: list[tuple[datetime, float]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            return {"valid": False, "reason": "MALFORMED_SAMPLE", "acceleration_per_min2": None}
        dt = _utc(sample.get("observed_at") or sample.get("timestamp") or sample.get("generated_at"))
        value = _number(sample, value_field)
        if dt is None or value is None:
            return {"valid": False, "reason": "MISSING_TIMESTAMP_OR_VALUE", "acceleration_per_min2": None}
        if dt > now:
            return {"valid": False, "reason": "FUTURE_SAMPLE", "acceleration_per_min2": None}
        if points and dt <= points[-1][0]:
            return {"valid": False, "reason": "NON_MONOTONIC_TIMESTAMP", "acceleration_per_min2": None}
        points.append((dt, value))
    if len(points) < 3:
        return {"valid": False, "reason": "INSUFFICIENT_POINTS", "acceleration_per_min2": None}
    rates: list[tuple[datetime, float]] = []
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        minutes = (t1 - t0).total_seconds() / 60.0
        if minutes <= 0:
            return {"valid": False, "reason": "NON_POSITIVE_WINDOW", "acceleration_per_min2": None}
        rates.append((t1, (v1 - v0) / minutes))
    accelerations = []
    for (t0, r0), (t1, r1) in zip(rates, rates[1:]):
        minutes = (t1 - t0).total_seconds() / 60.0
        if minutes <= 0:
            return {"valid": False, "reason": "NON_POSITIVE_RATE_WINDOW", "acceleration_per_min2": None}
        accelerations.append((r1 - r0) / minutes)
    return {
        "valid": True,
        "reason": "OK",
        "points": len(points),
        "latest_rate_per_min": rates[-1][1],
        "acceleration_per_min2": accelerations[-1],
    }


def _pair_exact(row: dict) -> bool:
    truth = row.get("truth") if isinstance(row.get("truth"), dict) else {}
    return bool(
        row.get("exact_pair_verified") is True
        or row.get("pair_identity_locked") is True
        or row.get("identity_verified") is True
        or str(row.get("identity_status") or "").startswith("DEX_VERIFIED")
        or row.get("dex_link_type") == "DEXSCREENER_VERIFIED_PAIR"
        or truth.get("exact_pair_verified") is True
    )


def pair_quality_key(row: dict, *, now: datetime | None = None) -> tuple:
    """Deterministic exact-pair ranking; token-wide TVL is deliberately ignored."""
    if not isinstance(row, dict) or not _pair_exact(row):
        return (0, 0, 0, 0, 0, 0, "")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observed = _utc(row.get("observed_at") or row.get("generated_at") or row.get("updated_at"))
    age_seconds = max(0.0, (now - observed).total_seconds()) if observed and observed <= now else math.inf
    freshness = 1 if age_seconds <= 45 * 60 else 0
    liquidity = _number(row, "execution_pool_liquidity_usd", "dex_pair_liquidity_usd", "dex_liquidity_usd", "liquidity_usd") or 0.0
    volume = _number(row, "dex_volume_h1", "volume_h1", "live_volume_h1") or 0.0
    buys = _number(row, "buys_h1", "live_buys_h1") or 0.0
    sells = _number(row, "sells_h1", "live_sells_h1") or 0.0
    txns = buys + sells
    pair_age = _number(row, "pair_age_minutes", "age_minutes") or 0.0
    complete = sum(row.get(k) not in (None, "") for k in ("pair_address", "price_usd", "execution_pool_liquidity_usd", "volume_h1"))
    pair = str(row.get("pair_address") or row.get("dex_pair_address") or "")
    return (1, freshness, complete, txns, volume, liquidity, pair_age, pair)


def choose_best_exact_pair(rows: Iterable[dict], *, now: datetime | None = None) -> dict | None:
    eligible = [row for row in rows if isinstance(row, dict) and pair_quality_key(row, now=now)[0] == 1]
    return max(eligible, key=lambda row: pair_quality_key(row, now=now), default=None)


def wallet_shadow_evidence(row: dict) -> dict:
    """Wallet-led discovery evidence can rank research, never promote a live alert by itself."""
    cluster = _number(row, "wallet_cluster_score", "smart_wallet_cluster_score", "wallet_intent_score") or 0.0
    wallets = int(_number(row, "strong_wallet_count", "smart_wallet_count", "wallet_count") or 0)
    accumulation = bool(row.get("cluster_accumulation") is True or str(row.get("wallet_intent") or "").upper() == "CLUSTER_ACCUMULATION")
    detected = accumulation or (wallets >= 2 and cluster > 0)
    return {
        "detected": detected,
        "ranking_only": True,
        "research_shadow": detected,
        "real_alert_eligible": False,
        "automatic_buy": False,
        "auto_promote": False,
        "strong_wallet_count": wallets,
        "wallet_cluster_score": cluster,
    }
