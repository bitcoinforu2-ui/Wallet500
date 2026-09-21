from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "data/close-watch-intelligence-policy.json"
EVENTS = ROOT / "data/close-watch-events.json"
CONFIG = ROOT / "data/unified-watch-config.json"
OUTPUT = ROOT / "data/close-watch-intelligence.json"

EVM = {"ethereum", "bsc", "bnb", "base", "arbitrum", "optimism", "polygon", "avalanche", "arc"}
CHAIN_ALIASES = {"eth": "ethereum", "bnb": "bsc"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts):
    try:
        raw = str(ts or "").strip()
        if not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def _chain(value: object) -> str:
    raw = str(value or "").strip().lower()
    return CHAIN_ALIASES.get(raw, raw)


def _addr(chain: str, value: object) -> str:
    raw = str(value or "").strip()
    return raw.lower() if chain in EVM else raw


def _identity_from_values(chain: object, token: object, pair: object) -> tuple[str, str, str, str] | None:
    c = _chain(chain)
    t = _addr(c, token)
    p = _addr(c, pair)
    if not c or not t or not p:
        return None
    return c, t, p, f"{c}:{t}:{p}"


def _event_identity(e: dict) -> tuple[str, str, str, str] | None:
    return _identity_from_values(
        e.get("chain") or e.get("network"),
        e.get("token_address") or e.get("contract") or e.get("mint"),
        e.get("pair_address") or e.get("pair"),
    )


def _target_identity(t: dict) -> tuple[str, str, str, str] | None:
    return _identity_from_values(t.get("chain") or t.get("network"), t.get("token_address") or t.get("contract"), t.get("pair_address") or t.get("pair"))


def _fingerprint(e: dict, identity_key: str) -> str:
    # An aggregator and the original Telegram/X caller are the same underlying
    # social opinion, not two independent confirmations. Upstream alpha intake
    # supplies an independence_key keyed to caller+asset whenever provenance is
    # known. Repeated surfaces therefore receive the normal duplicate discount.
    root = str(
        e.get("independence_key")
        or e.get("canonical_event_id")
        or e.get("source_url")
        or ""
    ).strip()
    if not root:
        root = "|".join(str(e.get(k) or "") for k in ("family", "kind", "subject", "event_time", "source"))
    return hashlib.sha256(f"{identity_key}|{root.lower()}".encode()).hexdigest()[:20]


def _event_age_minutes(e: dict, now_dt: datetime) -> float | None:
    t = _parse(e.get("event_time") or e.get("observed_at"))
    if not t:
        return None
    return max(0.0, (now_dt - t).total_seconds() / 60.0)


def _freshness(age_minutes: float | None, half_life: float) -> float:
    if age_minutes is None:
        return 0.0
    return math.pow(0.5, age_minutes / max(1.0, half_life))


def _label(score: int, labels: dict) -> str:
    for band, name in labels.items():
        lo, hi = map(int, band.split("-"))
        if lo <= score <= hi:
            return name
    return "WATCH"


def fuse(target: dict, events: list[dict], policy: dict, now_dt: datetime | None = None) -> dict:
    now_dt = now_dt or _now()
    ident = _target_identity(target)
    if ident is None:
        raise ValueError("target missing exact chain+contract+pair identity")
    chain, token, pair, identity_key = ident
    fam_cfg = policy["signal_families"]
    fusion = policy["fusion"]
    half = float(fusion["freshness_half_life_minutes"])
    window = float(fusion.get("window_minutes") or half)
    dedup = float(fusion["source_duplicate_discount"])

    seen: dict[str, int] = {}
    family_points: dict[str, float] = {}
    evidence: list[dict] = []
    contradictions = 0.0
    hard_risk_records: list[tuple[str, datetime | None]] = []
    hard_risk_superseded_after: dict[str, datetime] = {}
    stale_count = 0
    invalid_time_count = 0
    current_count = 0
    freshest_at: datetime | None = None

    for e in events:
        if not isinstance(e, dict):
            continue
        e_ident = _event_identity(e)
        if e_ident is None or e_ident[3] != identity_key:
            continue
        fam = e.get("family")
        if fam not in fam_cfg:
            continue
        age = _event_age_minutes(e, now_dt)
        if age is None:
            invalid_time_count += 1
            evidence.append({"family": fam, "kind": e.get("kind"), "source": e.get("source"), "event_time": e.get("event_time"), "current": False, "reason": "TIMESTAMP_MISSING_OR_INVALID"})
            continue
        event_dt = now_dt if age == 0 and _parse(e.get("event_time") or e.get("observed_at")) is None else _parse(e.get("event_time") or e.get("observed_at"))
        if event_dt and (freshest_at is None or event_dt > freshest_at):
            freshest_at = event_dt
        if age > window:
            stale_count += 1
            evidence.append({"family": fam, "kind": e.get("kind"), "source": e.get("source"), "event_time": e.get("event_time"), "age_minutes": round(age, 2), "current": False, "reason": "OUTSIDE_FUSION_WINDOW"})
            continue

        current_count += 1
        fp = _fingerprint(e, identity_key)
        duplicate = fp in seen
        seen[fp] = seen.get(fp, 0) + 1
        confidence = _clamp(e.get("confidence", 50)) / 100.0
        strength = _clamp(abs(float(e.get("strength", 0)))) / 100.0
        direction_value = float(e.get("direction", 0))
        direction = -1 if direction_value < 0 else (1 if direction_value > 0 else 0)
        freshness = _freshness(age, half)
        independence = dedup if duplicate else 1.0
        raw = confidence * strength * freshness * independence
        if direction:
            family_points[fam] = family_points.get(fam, 0.0) + direction * raw
        if direction < 0 and e.get("contradicts_bullish"):
            contradictions += raw * 100.0

        supersedes = e.get("supersedes_hard_risk_kinds")
        if isinstance(supersedes, (list, tuple)) and event_dt is not None:
            for risk_kind in supersedes:
                risk_kind = str(risk_kind or "").strip()
                if not risk_kind:
                    continue
                prev_dt = hard_risk_superseded_after.get(risk_kind)
                if prev_dt is None or event_dt > prev_dt:
                    hard_risk_superseded_after[risk_kind] = event_dt

        if e.get("hard_risk"):
            hard_risk_records.append((str(e.get("kind") or "hard_risk"), event_dt))
        evidence.append({
            "family": fam,
            "kind": e.get("kind"),
            "direction": direction,
            "raw": round(raw, 4),
            "duplicate": duplicate,
            "source": e.get("source"),
            "event_time": e.get("event_time"),
            "age_minutes": round(age, 2),
            "current": True,
        })

    hard_risks: list[str] = []
    for risk_kind, risk_dt in hard_risk_records:
        superseded_at = hard_risk_superseded_after.get(risk_kind)
        if superseded_at is not None and risk_dt is not None and risk_dt <= superseded_at:
            continue
        hard_risks.append(risk_kind)

    weighted: dict[str, float] = {}
    positive_families = 0
    for fam, cfg in fam_cfg.items():
        normalized = max(-1.0, min(1.0, family_points.get(fam, 0.0)))
        pts = normalized * float(cfg["weight"])
        weighted[fam] = round(pts, 2)
        if pts > 0.5:
            positive_families += 1

    positive = sum(max(0.0, x) for x in weighted.values())
    negative = sum(abs(min(0.0, x)) for x in weighted.values())
    score = _clamp(positive - negative - min(float(fusion["contradiction_penalty_max"]), contradictions))
    if positive_families < int(fusion["minimum_independent_families_for_strong"]):
        score = min(score, float(fusion["single_family_score_cap"]))
    if hard_risks:
        score = min(score, 29.0)

    label = _label(int(round(score)), fusion["labels"])
    status = "CURRENT" if current_count else ("STALE_ONLY" if stale_count else "NO_CURRENT_EVIDENCE")
    return {
        "symbol": str(target.get("symbol") or "").upper(),
        "chain": chain,
        "token_address": token,
        "pair_address": pair,
        "identity_key": identity_key,
        "score": round(score, 1),
        "label": label,
        "status": status,
        "independent_positive_families": positive_families,
        "family_scores": weighted,
        "hard_risks": sorted(set(hard_risks)),
        "contradiction_penalty": round(min(float(fusion["contradiction_penalty_max"]), contradictions), 2),
        "current_evidence_count": current_count,
        "stale_evidence_count": stale_count,
        "invalid_timestamp_evidence_count": invalid_time_count,
        "evidence_count": len(evidence),
        "window_minutes": int(window),
        "freshest_event_at": freshest_at.isoformat() if freshest_at else None,
        "evidence_age_minutes": round((now_dt - freshest_at).total_seconds() / 60.0, 2) if freshest_at else None,
        "evidence": sorted(evidence, key=lambda x: (x.get("current") is True, float(x.get("raw") or 0)), reverse=True)[:30],
        "updated_at": now_dt.isoformat(),
    }


def main() -> int:
    policy = json.loads(POLICY.read_text())
    doc = json.loads(EVENTS.read_text()) if EVENTS.exists() else {"events": []}
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {"tokens": []}
    events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]

    targets: dict[str, dict] = {}
    for t in config.get("tokens") or []:
        if not isinstance(t, dict):
            continue
        ident = _target_identity(t)
        if ident:
            targets[ident[3]] = t
    for e in events:
        ident = _event_identity(e)
        if ident and ident[3] not in targets:
            targets[ident[3]] = {
                "symbol": e.get("symbol"),
                "network": ident[0],
                "contract": ident[1],
                "pair": ident[2],
            }

    now_dt = _now()
    rows = [fuse(t, events, policy, now_dt=now_dt) for _, t in sorted(targets.items())]
    out = {
        "version": 2,
        "generated_at": now_dt.isoformat(),
        "identity_mode": "EXACT_CHAIN_CONTRACT_PAIR",
        "window_minutes": int(policy["fusion"].get("window_minutes") or 0),
        "configured_targets": len(config.get("tokens") or []),
        "event_count": len(events),
        "tokens": rows,
    }
    OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
