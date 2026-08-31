from __future__ import annotations

"""Truth-preserving runner for the Hybrid V1 engine.

Market/pair snapshots and on-chain evidence are collected by different providers, so
perfect timestamp equality is unrealistic. This runner allows recent exact-mint
external evidence collected shortly after the market snapshot while rejecting
future-dated, stale, wrong-network, or malformed evidence.
"""

from datetime import datetime, timedelta, timezone

from . import hybrid_token_profile as engine
from .revival_1000 import looks_like_solana_address

MAX_EXTERNAL_AGE = timedelta(hours=30)
MAX_AFTER_SOURCE_LAG = timedelta(hours=2)
FUTURE_CLOCK_TOLERANCE = timedelta(minutes=2)


def _load_external_truth(source_generated_at: str) -> dict[str, dict]:
    payload = engine._load(engine.EXTERNAL, {})
    rows = payload.get("observations") or [] if isinstance(payload, dict) else []
    source_dt = engine._dt(source_generated_at)
    now = datetime.now(timezone.utc)
    if source_dt is None:
        return {}
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
        if observed < earliest or observed > latest_allowed:
            continue
        old = latest.get(address)
        if old is None or observed > old[0]:
            latest[address] = (observed, row)
    return {k: v[1] for k, v in latest.items()}


def run() -> dict:
    engine._load_external = _load_external_truth
    payload = engine.run()
    if isinstance(payload, dict):
        payload["external_evidence_timing_contract"] = {
            "method": "ASYNCHRONOUS_PROVIDER_TIMEBOX",
            "max_age_hours_before_market_snapshot": MAX_EXTERNAL_AGE.total_seconds() / 3600,
            "max_lag_hours_after_market_snapshot": MAX_AFTER_SOURCE_LAG.total_seconds() / 3600,
            "future_clock_tolerance_minutes": FUTURE_CLOCK_TOLERANCE.total_seconds() / 60,
            "rule": "exact-mint external evidence may be asynchronous but must be fresh and never future-dated relative to the Hybrid run",
        }
        engine.LATEST.write_text(engine.json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run()
    print("HYBRID_TOKEN_PROFILE_RUNNER_OK", result.get("counts") if isinstance(result, dict) else None)
