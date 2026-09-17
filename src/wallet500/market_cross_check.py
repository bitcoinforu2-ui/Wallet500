"""Wallet500 market-data cross-check layer.

This module compares normalized market snapshots from independent providers for the
same exact chain+contract/mint identity. It is deliberately advisory: agreement
can strengthen data confidence, while disagreement creates a discrepancy flag;
neither result bypasses Wallet500 risk/execution gates.

Provider adapters should normalize their payloads into ``MarketSnapshot`` fields
(or the equivalent JSON keys accepted by :func:`build`). This keeps vendor-specific
API logic outside the scoring core and makes it safe to add/remove verifiers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
INPUT = DATA / "market-source-snapshots.json"
OUT = DATA / "market-cross-check.json"

EVM_CHAINS = {"ethereum", "bsc", "arbitrum", "base"}
CHAIN_ALIASES = {
    "eth": "ethereum",
    "ethereum-mainnet": "ethereum",
    "bnb": "bsc",
    "bnb-chain": "bsc",
    "binance-smart-chain": "bsc",
    "arbitrum-one": "arbitrum",
    "sol": "solana",
}

DEFAULT_TOLERANCES = {
    "price_usd": 0.05,
    "market_cap_usd": 0.10,
    "fdv_usd": 0.10,
    "liquidity_usd": 0.12,
    "volume_24h_usd": 0.20,
    "holders": 0.12,
    "top10_pct": 0.10,
}
DEFAULT_WEIGHTS = {
    "price_usd": 0.25,
    "market_cap_usd": 0.15,
    "fdv_usd": 0.10,
    "liquidity_usd": 0.20,
    "volume_24h_usd": 0.10,
    "holders": 0.10,
    "top10_pct": 0.10,
}
MAX_AGE_SECONDS = 5 * 60


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_chain(value: object) -> str:
    chain = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(chain, chain)


def _norm_token(token: object, chain: object) -> str:
    value = str(token or "").strip()
    c = _norm_chain(chain)
    if c in EVM_CHAINS or value.startswith("0x"):
        return value.lower()
    return value


def _asset_key(chain: object, token: object) -> str:
    c = _norm_chain(chain)
    return f"{c}:{_norm_token(token, c)}"


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


def _num(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
        return out if out >= 0 else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MarketSnapshot:
    chain: str
    token: str
    source: str
    observed_at: str
    role: str = "verifier"
    price_usd: float | None = None
    market_cap_usd: float | None = None
    fdv_usd: float | None = None
    liquidity_usd: float | None = None
    volume_24h_usd: float | None = None
    holders: float | None = None
    top10_pct: float | None = None
    risk_flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def asset_key(self) -> str:
        return _asset_key(self.chain, self.token)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "MarketSnapshot | None":
        chain = _norm_chain(raw.get("chain") or raw.get("network"))
        token = _norm_token(
            raw.get("token") or raw.get("contract") or raw.get("mint") or raw.get("token_address"),
            chain,
        )
        source = str(raw.get("source") or raw.get("provider") or "").strip().lower()
        observed_at = str(raw.get("observed_at") or raw.get("timestamp") or "").strip()
        if not chain or not token or not source or _parse_ts(observed_at) is None:
            return None
        flags = raw.get("risk_flags") or []
        if not isinstance(flags, (list, tuple)):
            flags = [str(flags)]
        return cls(
            chain=chain,
            token=token,
            source=source,
            observed_at=observed_at,
            role=str(raw.get("role") or "verifier").strip().lower(),
            price_usd=_num(raw.get("price_usd")),
            market_cap_usd=_num(raw.get("market_cap_usd") or raw.get("market_cap")),
            fdv_usd=_num(raw.get("fdv_usd") or raw.get("fdv")),
            liquidity_usd=_num(raw.get("liquidity_usd") or raw.get("liquidity")),
            volume_24h_usd=_num(raw.get("volume_24h_usd") or raw.get("volume_24h")),
            holders=_num(raw.get("holders") or raw.get("holder_count")),
            top10_pct=_num(raw.get("top10_pct") or raw.get("top_10_pct")),
            risk_flags=tuple(sorted({str(x).strip() for x in flags if str(x).strip()})),
        )


def _relative_delta(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-12)


def _freshness_seconds(snapshot: MarketSnapshot, now: datetime) -> float | None:
    ts = _parse_ts(snapshot.observed_at)
    if ts is None:
        return None
    return max(0.0, (now - ts).total_seconds())


def _latest_per_source(rows: list[MarketSnapshot]) -> list[MarketSnapshot]:
    latest: dict[str, MarketSnapshot] = {}
    for row in rows:
        old = latest.get(row.source)
        if old is None or (_parse_ts(row.observed_at) or datetime.min.replace(tzinfo=timezone.utc)) > (
            _parse_ts(old.observed_at) or datetime.min.replace(tzinfo=timezone.utc)
        ):
            latest[row.source] = row
    return list(latest.values())


def cross_check_asset(
    rows: list[MarketSnapshot],
    *,
    now: datetime | None = None,
    max_age_seconds: int = MAX_AGE_SECONDS,
    tolerances: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    now = (now or _now_dt()).astimezone(timezone.utc)
    tolerances = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    rows = _latest_per_source(rows)
    sources = sorted({r.source for r in rows})
    if not rows:
        return {
            "status": "insufficient",
            "agreement_score": None,
            "sources": [],
            "fresh_sources": [],
            "stale_sources": [],
            "discrepancies": [],
            "compared_fields": [],
        }

    primary = next((r for r in rows if r.role == "primary"), None)
    if primary is None:
        primary = max(rows, key=lambda r: _parse_ts(r.observed_at) or datetime.min.replace(tzinfo=timezone.utc))

    fresh: list[MarketSnapshot] = []
    stale: list[MarketSnapshot] = []
    for row in rows:
        age = _freshness_seconds(row, now)
        (fresh if age is not None and age <= max_age_seconds else stale).append(row)

    fresh_sources = sorted(r.source for r in fresh)
    stale_sources = sorted(r.source for r in stale)
    fresh_primary = next((r for r in fresh if r.source == primary.source), None)
    fresh_verifiers = [r for r in fresh if r.source != primary.source]
    if fresh_primary is None or not fresh_verifiers:
        status = "stale" if stale and len(sources) >= 2 else "insufficient"
        return {
            "status": status,
            "agreement_score": None,
            "primary_source": primary.source,
            "sources": sources,
            "fresh_sources": fresh_sources,
            "stale_sources": stale_sources,
            "discrepancies": [],
            "compared_fields": [],
            "freshness_ms": int(min((_freshness_seconds(r, now) or 0) for r in rows) * 1000),
        }

    discrepancies: list[dict[str, Any]] = []
    compared_fields: set[str] = set()
    score_num = 0.0
    score_den = 0.0
    for verifier in fresh_verifiers:
        for field_name, tolerance in tolerances.items():
            a = getattr(fresh_primary, field_name)
            b = getattr(verifier, field_name)
            if a is None or b is None:
                continue
            compared_fields.add(field_name)
            delta = _relative_delta(float(a), float(b))
            weight = float(weights.get(field_name, 1.0))
            score_den += weight
            # Full credit inside tolerance; outside it decays to zero at 4x tolerance.
            metric_score = 1.0 if delta <= tolerance else max(0.0, 1.0 - (delta - tolerance) / max(3.0 * tolerance, 1e-12))
            score_num += weight * metric_score
            if delta > tolerance:
                discrepancies.append({
                    "field": field_name,
                    "primary_source": fresh_primary.source,
                    "verifier_source": verifier.source,
                    "primary_value": a,
                    "verifier_value": b,
                    "relative_delta": round(delta, 6),
                    "tolerance": tolerance,
                })

    if not compared_fields or score_den <= 0:
        status = "insufficient"
        agreement = None
    else:
        status = "diverged" if discrepancies else "ok"
        agreement = round(score_num / score_den, 4)

    all_flags = sorted({flag for row in fresh for flag in row.risk_flags})
    ages = [x for x in (_freshness_seconds(r, now) for r in fresh) if x is not None]
    return {
        "status": status,
        "agreement_score": agreement,
        "primary_source": fresh_primary.source,
        "sources": sources,
        "fresh_sources": fresh_sources,
        "stale_sources": stale_sources,
        "compared_fields": sorted(compared_fields),
        "discrepancies": discrepancies,
        "risk_flags": all_flags,
        "freshness_ms": int(max(ages) * 1000) if ages else None,
    }


def build(raw_snapshots: list[dict[str, Any]] | None = None, *, ts: str | None = None) -> dict[str, Any]:
    ts = ts or _now()
    if raw_snapshots is None:
        payload = _load(INPUT, {})
        if isinstance(payload, dict):
            raw_snapshots = payload.get("snapshots") or payload.get("records") or []
        else:
            raw_snapshots = payload if isinstance(payload, list) else []

    normalized = [MarketSnapshot.from_mapping(row) for row in raw_snapshots if isinstance(row, dict)]
    snapshots = [row for row in normalized if row is not None]
    grouped: dict[str, list[MarketSnapshot]] = {}
    for row in snapshots:
        grouped.setdefault(row.asset_key, []).append(row)

    now = _parse_ts(ts) or _now_dt()
    assets = {key: cross_check_asset(rows, now=now) for key, rows in grouped.items()}
    return {
        "version": 1,
        "updated_at": ts,
        "mode": "ADVISORY_MARKET_DATA_CROSS_CHECK",
        "automatic_trade": False,
        "policy": {
            "identity": "exact chain+contract/mint only",
            "freshness": f"snapshots older than {MAX_AGE_SECONDS}s are stale and do not vote",
            "agreement": "compare only overlapping normalized metrics from independent providers",
            "truth_boundary": "cross-check can confirm or flag data; it never bypasses Wallet500 risk/execution gates",
        },
        "counts": {
            "input_snapshots": len(raw_snapshots),
            "normalized_snapshots": len(snapshots),
            "assets": len(assets),
            "ok": sum(1 for x in assets.values() if x.get("status") == "ok"),
            "diverged": sum(1 for x in assets.values() if x.get("status") == "diverged"),
            "stale": sum(1 for x in assets.values() if x.get("status") == "stale"),
            "insufficient": sum(1 for x in assets.values() if x.get("status") == "insufficient"),
        },
        "assets": assets,
    }


def run() -> dict[str, Any]:
    DATA.mkdir(parents=True, exist_ok=True)
    payload = build()
    _write(OUT, payload)
    print("MARKET CROSS CHECK", json.dumps(payload["counts"], separators=(",", ":")))
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
