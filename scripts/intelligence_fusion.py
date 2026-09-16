from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "data/close-watch-intelligence-policy.json"
EVENTS = ROOT / "data/close-watch-events.json"
OUTPUT = ROOT / "data/close-watch-intelligence.json"

EVM_NETWORKS = {
    "ethereum", "eth", "bsc", "bnb", "base", "arbitrum", "optimism",
    "polygon", "avalanche", "fantom", "linea", "zksync", "mantle",
    "scroll", "blast",
}
NETWORK_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def _network(value: object) -> str:
    raw = str(value or "").strip().lower()
    return NETWORK_ALIASES.get(raw, raw)


def _address(value: object, network: str) -> str:
    raw = str(value or "").strip()
    return raw.lower() if network in EVM_NETWORKS else raw


def _identity(event: dict) -> tuple[str, str, str] | None:
    network = _network(event.get("network") or event.get("chain"))
    contract = _address(event.get("contract") or event.get("token_address") or event.get("token") or event.get("mint"), network)
    pair = _address(event.get("pair") or event.get("pair_address"), network)
    if not network or not contract or not pair:
        return None
    return network, contract, pair


def _identity_key(identity: tuple[str, str, str]) -> str:
    return "|".join(identity)


def _fingerprint(event: dict, identity: tuple[str, str, str]) -> str:
    # Reposts of the same real-world event must not become independent votes.
    root = str(event.get("canonical_event_id") or event.get("source_url") or "").strip()
    if not root:
        root = "|".join(
            str(event.get(k) or "")
            for k in ("family", "kind", "subject", "event_time")
        )
    return hashlib.sha256(f"{_identity_key(identity)}|{root.lower()}".encode()).hexdigest()[:20]


def _age_minutes(event: dict, now_dt: datetime) -> float | None:
    t = _parse(event.get("event_time") or event.get("observed_at"))
    if t is None:
        return None
    return (now_dt - t).total_seconds() / 60.0


def _freshness(age_minutes: float, half_life: float) -> float:
    return math.pow(0.5, max(0.0, age_minutes) / max(1.0, half_life))


def _label(score: int, labels: dict) -> str:
    for band, name in labels.items():
        lo, hi = map(int, band.split("-"))
        if lo <= score <= hi:
            return name
    return "WATCH"


def fuse(identity: tuple[str, str, str], events: list[dict], policy: dict) -> dict:
    family_cfg = policy["signal_families"]
    fusion = policy["fusion"]
    half_life = float(fusion["freshness_half_life_minutes"])
    window_minutes = float(fusion.get("window_minutes", 180))
    duplicate_discount = float(fusion["source_duplicate_discount"])
    now_dt = _now()

    seen: dict[str, int] = {}
    family_points: dict[str, float] = {}
    production_positive: dict[str, float] = {}
    evidence: list[dict] = []
    contradictions = 0.0
    hard_risks: list[str] = []
    symbol = "UNKNOWN"

    for event in events:
        if not isinstance(event, dict) or _identity(event) != identity:
            continue
        family = event.get("family")
        if family not in family_cfg:
            continue
        age_minutes = _age_minutes(event, now_dt)
        # Production intelligence is point-in-time only: missing, future or stale
        # evidence is not silently converted into a neutral/positive vote.
        if age_minutes is None or age_minutes < -2 or age_minutes > window_minutes:
            continue

        symbol = str(event.get("symbol") or symbol).upper()
        fp = _fingerprint(event, identity)
        duplicate = fp in seen
        seen[fp] = seen.get(fp, 0) + 1

        confidence = _clamp(event.get("confidence", 50)) / 100.0
        strength = _clamp(abs(float(event.get("strength", 0)))) / 100.0
        direction = -1 if float(event.get("direction", 1)) < 0 else 1
        freshness = _freshness(age_minutes, half_life)
        independence = duplicate_discount if duplicate else 1.0
        raw = confidence * strength * freshness * independence

        family_points[family] = family_points.get(family, 0.0) + direction * raw
        production_independent = event.get("production_independent") is not False
        if direction > 0 and production_independent and not duplicate:
            production_positive[family] = production_positive.get(family, 0.0) + raw
        if direction < 0 and event.get("contradicts_bullish"):
            contradictions += raw * 100.0
        if event.get("hard_risk"):
            hard_risks.append(str(event.get("kind") or "hard_risk"))

        evidence.append(
            {
                "family": family,
                "kind": event.get("kind"),
                "direction": direction,
                "raw": round(raw, 4),
                "duplicate": duplicate,
                "production_independent": production_independent,
                "source": event.get("source"),
                "event_time": event.get("event_time"),
                "age_minutes": round(age_minutes, 2),
            }
        )

    weighted: dict[str, float] = {}
    positive_families: list[str] = []
    for family, cfg in family_cfg.items():
        normalized = max(-1.0, min(1.0, family_points.get(family, 0.0)))
        points = normalized * float(cfg["weight"])
        weighted[family] = round(points, 2)
        if points > 0.5 and production_positive.get(family, 0.0) > 0:
            positive_families.append(family)

    positive = sum(max(0.0, value) for value in weighted.values())
    negative = sum(abs(min(0.0, value)) for value in weighted.values())
    score = _clamp(
        positive
        - negative
        - min(float(fusion["contradiction_penalty_max"]), contradictions)
    )

    if len(positive_families) < int(fusion["minimum_independent_families_for_strong"]):
        score = min(score, float(fusion["single_family_score_cap"]))
    if hard_risks:
        score = min(score, 29.0)

    network, contract, pair = identity
    rounded_score = round(score, 1)
    return {
        "identity_key": _identity_key(identity),
        "symbol": symbol,
        "network": network,
        "contract": contract,
        "pair": pair,
        "score": rounded_score,
        "label": _label(int(round(rounded_score)), fusion["labels"]),
        "independent_positive_families": len(positive_families),
        "positive_family_names": sorted(positive_families),
        "family_scores": weighted,
        "hard_risks": sorted(set(hard_risks)),
        "evidence_count": len(evidence),
        "evidence": sorted(evidence, key=lambda row: row["raw"], reverse=True)[:30],
        "updated_at": now_dt.isoformat(),
    }


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    doc = json.loads(EVENTS.read_text(encoding="utf-8")) if EVENTS.exists() else {"events": []}
    events = [row for row in (doc.get("events") or []) if isinstance(row, dict)]

    identities = sorted({_identity(event) for event in events if _identity(event) is not None})
    dropped = sum(1 for event in events if _identity(event) is None)
    tokens = [fuse(identity, events, policy) for identity in identities]
    out = {
        "version": 2,
        "generated_at": _now().isoformat(),
        "exact_identity_required": True,
        "dropped_events_without_exact_identity": dropped,
        "tokens": tokens,
    }
    OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
