from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class MarketEvent:
    chain: str
    token: str
    event_type: str
    score: float
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Candidate:
    chain: str
    token: str
    anomaly_score: float
    reasons: list[str] = field(default_factory=list)
