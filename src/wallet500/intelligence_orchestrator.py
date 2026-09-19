"""Research-only parallel intelligence orchestration.

This layer ranks and explains candidates. It MUST NOT promote production,
weaken truth gates, coerce missing evidence to zero, or rewrite T0.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Mapping
import concurrent.futures
import math
import time


class ProviderState(str, Enum):
    OK="OK"; DEGRADED="DEGRADED"; RATE_LIMITED="RATE_LIMITED"
    UNAVAILABLE="UNAVAILABLE"; STALE="STALE"; SCHEMA_CHANGED="SCHEMA_CHANGED"


@dataclass(frozen=True)
class ProviderCapability:
    provider_id: str
    kinds: frozenset[str]
    chains: frozenset[str]
    max_freshness_seconds: int
    exact_pair_capable: bool = False
    production_eligible: bool = False


@dataclass
class ProviderObservation:
    provider_id: str
    state: ProviderState
    observed_at: str
    evidence: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None
    error: str | None = None


class ProviderRegistry:
    def __init__(self) -> None:
        self._caps: dict[str, ProviderCapability] = {}
        self._health: dict[str, ProviderObservation] = {}

    def register(self, capability: ProviderCapability) -> None:
        if not capability.provider_id or capability.max_freshness_seconds <= 0:
            raise ValueError("PROVIDER_CONTRACT_INVALID")
        self._caps[capability.provider_id] = capability

    def capability(self, provider_id: str) -> ProviderCapability:
        return self._caps[provider_id]

    def record(self, observation: ProviderObservation) -> None:
        if observation.provider_id not in self._caps:
            raise KeyError("UNREGISTERED_PROVIDER")
        self._health[observation.provider_id] = observation

    def health(self) -> Mapping[str, ProviderObservation]:
        return dict(self._health)

    def eligible(self, *, kind: str, chain: str) -> list[ProviderCapability]:
        chain=chain.lower()
        return [c for c in self._caps.values()
                if kind in c.kinds and ("*" in c.chains or chain in c.chains)]


def _utc(ts: str) -> datetime:
    dt=datetime.fromisoformat(ts.replace("Z","+00:00"))
    if dt.tzinfo is None: raise ValueError("TIMESTAMP_TZ_REQUIRED")
    return dt.astimezone(timezone.utc)


def classify_freshness(observed_at: str, *, now: str, max_age_seconds: int) -> ProviderState:
    age=(_utc(now)-_utc(observed_at)).total_seconds()
    if age < 0: raise ValueError("FUTURE_EVIDENCE_REJECTED")
    return ProviderState.OK if age <= max_age_seconds else ProviderState.STALE


@dataclass(frozen=True)
class AgentTask:
    name: str
    run: Callable[[], ProviderObservation]


def run_parallel(tasks: Iterable[AgentTask], *, timeout_seconds: float = 20.0,
                 max_workers: int = 6) -> dict[str, ProviderObservation]:
    """Run research collectors concurrently; failures stay explicit, never zero."""
    tasks=list(tasks)
    out: dict[str, ProviderObservation]={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures={pool.submit(t.run):t for t in tasks}
        done, pending=concurrent.futures.wait(futures, timeout=timeout_seconds)
        for f in done:
            t=futures[f]
            try:
                out[t.name]=f.result()
            except Exception as exc:
                out[t.name]=ProviderObservation(t.name, ProviderState.UNAVAILABLE,
                    datetime.now(timezone.utc).isoformat(), error=type(exc).__name__)
        for f in pending:
            t=futures[f]; f.cancel()
            out[t.name]=ProviderObservation(t.name, ProviderState.UNAVAILABLE,
                datetime.now(timezone.utc).isoformat(), error="TIMEOUT")
    return out


def acceleration(previous: float | None, current: float | None) -> float | None:
    """Relative velocity. Missing stays missing; zero baseline is undefined."""
    if previous is None or current is None or previous <= 0 or current < 0:
        return None
    return (current / previous) - 1.0


def convergence_score(signals: Mapping[str, float | None]) -> dict[str, Any]:
    """Research ranking only: bounded independent-signal convergence."""
    valid={k:v for k,v in signals.items() if v is not None and math.isfinite(v)}
    positive={k:v for k,v in valid.items() if v > 0}
    # Saturating contribution prevents one extreme source dominating.
    strength=sum(min(1.0, math.log1p(v)/math.log(2.0)) for v in positive.values())
    score=round(100.0 * strength / max(1, len(signals)), 2)
    return {"score":score,"positive_signals":sorted(positive),
            "observed_signals":sorted(valid),"missing_signals":sorted(set(signals)-set(valid)),
            "semantics":"RESEARCH_RANKING_ONLY_NOT_PRODUCTION"}


def build_research_bundle(*, identity_key: str, observed_at: str,
                          observations: Mapping[str, ProviderObservation],
                          signal_velocities: Mapping[str, float | None]) -> dict[str, Any]:
    if not identity_key or identity_key.count(":") < 2:
        raise ValueError("EXACT_IDENTITY_KEY_REQUIRED")
    _utc(observed_at)
    return {
        "schema_version":1,
        "lane":"PARALLEL_INTELLIGENCE_RESEARCH",
        "identity_key":identity_key,
        "observed_at":observed_at,
        "providers":{k:{"state":v.state.value,"observed_at":v.observed_at,
                        "latency_ms":v.latency_ms,"error":v.error,"evidence":v.evidence}
                     for k,v in observations.items()},
        "convergence":convergence_score(signal_velocities),
        "production_promotion_allowed":False,
        "may_weaken_truth_contract":False,
        "missing_is_zero":False,
        "retroactive_t0_allowed":False,
    }
