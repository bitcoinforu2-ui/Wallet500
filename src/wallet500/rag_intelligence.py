from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RAGConfig:
    """Conservative defaults for the Wallet500 historical-memory layer.

    The RAG layer is intentionally SHADOW-only.  It may calculate a bounded
    counterfactual score, but it is not allowed to alter production actions.
    """

    enabled: bool = True
    top_k: int = 12
    min_samples: int = 5
    min_confidence: float = 0.55
    max_score_delta: float = 5.0
    max_ledger_events: int = 5000


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_json(path: Path, default: Any) -> Any:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


def _identity_key(chain: Any, token: Any, pair: Any) -> str:
    return f"{str(chain or '').lower()}:{str(token or '').lower()}:{str(pair or '').lower()}"


def _candidate_key(row: dict) -> str:
    return _identity_key(
        row.get("chain"),
        row.get("token") or row.get("token_address"),
        row.get("pair_address") or row.get("locked_pair_address"),
    )


def _chain_from_key(key: str) -> str:
    return str(key or "").split(":", 1)[0].lower()


def _score_similarity(current: dict, historical: dict) -> float:
    """Similarity of two decision-time score vectors, never of future returns."""

    fields = ("opportunity", "survival", "execution", "timing")
    distances: list[float] = []
    for field in fields:
        a = _num(current.get(field))
        b = _num(historical.get(field))
        if a is None or b is None:
            continue
        distances.append(min(1.0, abs(a - b) / 100.0))
    if len(distances) < 3:
        return 0.0
    similarity = 1.0 - (sum(distances) / len(distances))

    # Composite is useful as a secondary tie-breaker, but never enough by itself.
    a_comp = _num(current.get("composite"))
    b_comp = _num(historical.get("composite"))
    if a_comp is not None and b_comp is not None:
        composite_similarity = 1.0 - min(1.0, abs(a_comp - b_comp) / 100.0)
        similarity = 0.85 * similarity + 0.15 * composite_similarity
    return max(0.0, min(1.0, similarity))


def _known_horizon(outcome: dict, as_of: datetime) -> tuple[str, float, str] | None:
    """Return the longest already-observed checkpoint without temporal leakage."""

    checkpoints = outcome.get("checkpoints")
    if isinstance(checkpoints, dict):
        for horizon in ("24h", "12h", "4h", "1h", "30m", "15m", "5m"):
            point = checkpoints.get(horizon)
            if not isinstance(point, dict):
                continue
            captured = _parse_ts(point.get("captured_at"))
            ret = _num(point.get("return_pct"))
            if captured is not None and captured < as_of and ret is not None:
                return horizon, ret, captured.isoformat()

    # Conservative fallback for records without checkpoint structure.  The mark
    # itself must have existed before the current decision and be at least 1h old.
    updated = _parse_ts(outcome.get("updated_at"))
    age_minutes = _num(outcome.get("age_minutes"), 0.0) or 0.0
    ret = _num(outcome.get("current_return_pct"))
    if updated is not None and updated < as_of and age_minutes >= 60.0 and ret is not None:
        return "current_known_mark", ret, updated.isoformat()
    return None


class Wallet500RAG:
    """Leakage-safe local RAG memory over Wallet500's own historical evidence.

    Retrieval is deliberately deterministic and dependency-free so the live
    scanner cannot be broken by a vector DB, LLM, network, LangChain or
    LlamaIndex outage.  A semantic backend can be added later behind this same
    contract once prospective shadow validation proves incremental value.
    """

    def __init__(self, data_dir: str | Path = "data", config: RAGConfig | None = None):
        self.data_dir = Path(data_dir)
        self.config = config or RAGConfig(enabled=_env_bool("W500_RAG_ENABLED", True))
        self._loaded = False
        self._load_error: str | None = None
        self._events: list[dict] = []
        self._outcomes: dict[str, dict] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            ledger_payload = _safe_json(self.data_dir / "decision-engine-v1-ledger.json", {})
            events = ledger_payload.get("events") if isinstance(ledger_payload, dict) else []
            if isinstance(events, list):
                self._events = [x for x in events[-self.config.max_ledger_events :] if isinstance(x, dict)]

            outcome_payload = _safe_json(self.data_dir / "signal-outcomes.json", [])
            if isinstance(outcome_payload, dict):
                rows = outcome_payload.get("tokens") or outcome_payload.get("outcomes") or []
                if isinstance(rows, dict):
                    rows = list(rows.values())
            else:
                rows = outcome_payload
            if not isinstance(rows, list):
                rows = []

            # Index exact chain+token+pair identities only.  Never merge same ticker
            # across chains or pools.
            for row in rows:
                if not isinstance(row, dict):
                    continue
                chain = row.get("chain")
                token = row.get("token") or row.get("token_address")
                pairs = {
                    str(row.get("entry_pair_address") or "").lower(),
                    str(row.get("current_pair_address") or "").lower(),
                    str(row.get("pair_address") or "").lower(),
                }
                for pair in pairs:
                    if not chain or not token or not pair:
                        continue
                    key = _identity_key(chain, token, pair)
                    old = self._outcomes.get(key)
                    old_ts = _parse_ts(old.get("updated_at")) if isinstance(old, dict) else None
                    new_ts = _parse_ts(row.get("updated_at"))
                    if old is None or (new_ts is not None and (old_ts is None or new_ts >= old_ts)):
                        self._outcomes[key] = row
        except Exception as exc:  # fail-open by contract: intelligence cannot stop scanning
            self._load_error = f"{type(exc).__name__}: {exc}"[:240]
            self._events = []
            self._outcomes = {}

    def retrieve(self, row: dict, base_scores: dict, as_of: str | datetime | None = None) -> dict:
        if not self.config.enabled:
            return self._empty("DISABLED", as_of)
        self._load()
        if self._load_error:
            result = self._empty("ERROR", as_of)
            result["error"] = self._load_error
            return result
        if not self._events or not self._outcomes:
            return self._empty("EMPTY", as_of)

        if isinstance(as_of, datetime):
            now = as_of.astimezone(timezone.utc) if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
        else:
            now = _parse_ts(as_of) or datetime.now(timezone.utc)

        current_key = _candidate_key(row)
        current_chain = str(row.get("chain") or "").lower()
        ranked: list[dict] = []
        seen_keys: set[str] = set()

        # Newest first makes deduplication deterministic and prevents one asset
        # with many state transitions from dominating the analogue sample.
        events = sorted(
            self._events,
            key=lambda x: _parse_ts(x.get("at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        for event in events:
            key = str(event.get("key") or "").lower()
            event_time = _parse_ts(event.get("at"))
            if not key or event_time is None or event_time >= now:
                continue
            if key == current_key.lower() or key in seen_keys:
                continue
            if current_chain and _chain_from_key(key) != current_chain:
                continue
            historical_scores = event.get("scores")
            if not isinstance(historical_scores, dict):
                continue
            similarity = _score_similarity(base_scores, historical_scores)
            if similarity <= 0:
                continue
            outcome = self._outcomes.get(key)
            if not isinstance(outcome, dict):
                continue
            target = _known_horizon(outcome, now)
            if target is None:
                continue
            horizon, return_pct, known_at = target
            seen_keys.add(key)
            ranked.append(
                {
                    "key": key,
                    "decision_at": event_time.isoformat(),
                    "known_at": known_at,
                    "similarity": round(similarity, 4),
                    "horizon": horizon,
                    "return_pct": round(return_pct, 4),
                    "outcome": outcome.get("outcome") or outcome.get("measurement_status"),
                    "source": "decision-ledger+signal-outcomes",
                }
            )

        ranked.sort(key=lambda x: (-float(x["similarity"]), str(x["decision_at"]), str(x["key"])))
        top = ranked[: self.config.top_k]
        if not top:
            return self._empty("EMPTY", now)

        weights = [max(0.01, float(x["similarity"])) for x in top]
        returns = [float(x["return_pct"]) for x in top]
        total_weight = sum(weights)
        weighted_return = sum(w * r for w, r in zip(weights, returns)) / total_weight
        weighted_win_rate = sum(w for w, r in zip(weights, returns) if r > 0.0) / total_weight
        weighted_downside_rate = sum(w for w, r in zip(weights, returns) if r <= -20.0) / total_weight
        mean_similarity = sum(weights) / len(weights)
        sample_factor = min(1.0, len(top) / max(1, self.config.min_samples))
        confidence = max(0.0, min(1.0, mean_similarity * sample_factor))
        median_return = statistics.median(returns)

        score_delta = 0.0
        if len(top) >= self.config.min_samples and confidence >= self.config.min_confidence:
            directional_edge = (weighted_win_rate - 0.5) * 2.0
            return_edge = math.tanh(weighted_return / 50.0)
            downside_penalty = weighted_downside_rate
            raw = self.config.max_score_delta * confidence * (
                0.55 * directional_edge + 0.30 * return_edge - 0.35 * downside_penalty
            )
            score_delta = max(-self.config.max_score_delta, min(self.config.max_score_delta, raw))

        return {
            "status": "READY",
            "mode": "SHADOW",
            "production_influence": False,
            "sample_count": len(top),
            "retrieval_confidence": round(confidence, 4),
            "mean_similarity": round(mean_similarity, 4),
            "weighted_win_rate": round(weighted_win_rate, 4),
            "weighted_return_pct": round(weighted_return, 4),
            "median_return_pct": round(float(median_return), 4),
            "downside_20_rate": round(weighted_downside_rate, 4),
            "score_delta": round(score_delta, 4),
            "score_delta_bound": self.config.max_score_delta,
            "top_cases": top,
            "provenance": {
                "sources": ["decision-engine-v1-ledger.json", "signal-outcomes.json"],
                "as_of": now.isoformat(),
                "retrieval_backend": "LOCAL_HYBRID_STRUCTURED",
                "temporal_leakage_guard": "STRICT_PRIOR_ONLY",
                "identity_guard": "EXACT_CHAIN_TOKEN_PAIR",
                "same_candidate_history_excluded": True,
                "semantic_backend": "OPTIONAL_NOT_REQUIRED_FOR_LIVE_SAFETY",
            },
        }

    def _empty(self, status: str, as_of: str | datetime | None) -> dict:
        if isinstance(as_of, datetime):
            stamp = as_of.isoformat()
        else:
            stamp = str(as_of or "")
        return {
            "status": status,
            "mode": "SHADOW",
            "production_influence": False,
            "sample_count": 0,
            "retrieval_confidence": 0.0,
            "score_delta": 0.0,
            "score_delta_bound": self.config.max_score_delta,
            "top_cases": [],
            "provenance": {
                "sources": ["decision-engine-v1-ledger.json", "signal-outcomes.json"],
                "as_of": stamp,
                "retrieval_backend": "LOCAL_HYBRID_STRUCTURED",
                "temporal_leakage_guard": "STRICT_PRIOR_ONLY",
                "identity_guard": "EXACT_CHAIN_TOKEN_PAIR",
            },
        }
