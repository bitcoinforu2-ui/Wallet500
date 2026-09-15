"""Wallet500 Early Revival Intelligence contract.

Research/manual-review layer only. This module MUST NOT promote REAL_ALERT,
change production thresholds, or reconstruct historical checkpoints.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping

SCHEMA_VERSION = 1
CHECKPOINT_LEVELS_PCT = (15.0, 25.0, 35.0, 45.0)
LANE = "EARLY_REVIVAL_WATCH"
SEMANTICS = "RESEARCH_MANUAL_REVIEW_ONLY_NOT_BUY_NOT_REAL_ALERT"


@dataclass(frozen=True)
class ExactIdentity:
    chain: str
    token_address: str
    pair_address: str

    def validate(self) -> None:
        if not all(isinstance(v, str) and v.strip() for v in asdict(self).values()):
            raise ValueError("EARLY_REVIVAL_FAIL_CLOSED_EXACT_IDENTITY_REQUIRED")

    @property
    def key(self) -> str:
        self.validate()
        return f"{self.chain.lower()}:{self.token_address}:{self.pair_address}"


def crossed_levels(first_price: float, current_price: float) -> list[float]:
    if first_price <= 0 or current_price <= 0:
        return []
    move = ((current_price / first_price) - 1.0) * 100.0
    return [level for level in CHECKPOINT_LEVELS_PCT if move >= level]


def build_checkpoint(*, identity: ExactIdentity, observed_at: str, first_price_usd: float,
                     current_price_usd: float, evidence: Mapping[str, Any],
                     source_fresh: bool, exact_pair_verified: bool) -> dict[str, Any]:
    """Create an append-only checkpoint from contemporaneous evidence.

    Missing/stale identity evidence fails closed. Unknown evidence remains unknown;
    callers must never coerce missing values to zero.
    """
    identity.validate()
    if not source_fresh or not exact_pair_verified:
        raise ValueError("EARLY_REVIVAL_FAIL_CLOSED_UNVERIFIED_OR_STALE")
    if first_price_usd <= 0 or current_price_usd <= 0:
        raise ValueError("EARLY_REVIVAL_FAIL_CLOSED_PRICE_REQUIRED")
    dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("EARLY_REVIVAL_FAIL_CLOSED_TIMESTAMP_TZ_REQUIRED")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "lane": LANE,
        "semantics": SEMANTICS,
        "identity": asdict(identity),
        "identity_key": identity.key,
        "observed_at": dt.astimezone(timezone.utc).isoformat(),
        "first_price_usd": first_price_usd,
        "current_price_usd": current_price_usd,
        "move_from_first_pct": ((current_price_usd / first_price_usd) - 1.0) * 100.0,
        "crossed_checkpoint_levels_pct": crossed_levels(first_price_usd, current_price_usd),
        "evidence": dict(evidence),
        "production_promotion_allowed": False,
        "retroactive_t0_allowed": False,
        "mutable": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["truth_hash_sha256"] = sha256(canonical.encode()).hexdigest()
    return payload


def ain_golden_identity() -> ExactIdentity:
    """Identity fixture only; never supplies historical market evidence."""
    return ExactIdentity(
        chain="bsc",
        token_address="0x9558a9254890b2a8b057a789f413631b9084f4a3",
        pair_address="0xf4262C4dbF524f53851A5176bdC7D6C1e0fA82D8",
    )
