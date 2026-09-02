from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
INPUT = DATA / "social-catalyst-ledger.json"
OUTPUT = DATA / "social-organic-acceleration.json"

MODE = "SOCIAL_ORGANIC_ACCELERATION_V1"
RULE = "SOCIAL_MENTIONS_NEQ_ORGANIC_SOCIAL_ACCELERATION"

EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

INCENTIVE_RE = re.compile(
    r"\b(?:paid\s*(?:post|promo|promotion|partnership|campaign)|sponsored|advertorial|"
    r"shill(?:ing)?\s*(?:contest|campaign)?|raid\s*(?:contest|to\s*earn|for\s*rewards?)|"
    r"post\s*(?:to|and)\s*(?:win|earn)|rewards?\s*for\s*(?:posting|shilling|raiding)|"
    r"engage\s*(?:to|and)\s*(?:win|earn)|airdrop\s*for\s*(?:posting|engagement)|"
    r"giveaway\s*(?:for|to)\s*(?:post|engage|shill|raid))\b",
    re.IGNORECASE,
)

PROJECT_ROLE_VALUES = {
    "official", "project", "project_account", "team", "developer", "dev", "founder", "creator", "cto_team"
}


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dt(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "paid", "sponsored"}


def _valid_contract(chain: str | None, contract: str) -> bool:
    if not contract:
        return False
    c = str(chain or "").lower()
    if c in {"ethereum", "bsc", "base", "arbitrum", "polygon"}:
        return bool(EVM_RE.fullmatch(contract))
    if c == "solana":
        return bool(SOL_RE.fullmatch(contract)) and not contract.startswith("0x")
    return bool(EVM_RE.fullmatch(contract) or SOL_RE.fullmatch(contract))


def _event_time(event: dict) -> datetime | None:
    return _dt(event.get("published_at")) or _dt(event.get("first_seen_by_wallet500"))


def _normalized_text(event: dict) -> str:
    text = str(event.get("text") or "").lower()
    # Strip exact CAs and URLs before clone detection. Copy-pasted campaign wording
    # should still cluster even when the same template carries different tracking URLs.
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"0x[a-f0-9]{40}", " <ca> ", text)
    text = re.sub(r"[1-9A-HJ-NP-Za-km-z]{32,44}", " <ca> ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clone_key(event: dict) -> str | None:
    text = _normalized_text(event)
    if len(text) < 24:
        return None
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def _is_project_owned(event: dict) -> bool:
    for key in ("project_owned", "official", "is_project_account", "project_account", "team_account"):
        if _bool(event.get(key)):
            return True
    role = str(event.get("author_role") or event.get("account_role") or "").strip().lower()
    return role in PROJECT_ROLE_VALUES


def _is_paid_or_incentivized(event: dict) -> tuple[bool, str | None]:
    for key in ("paid", "sponsored", "incentivized", "is_paid", "is_sponsored", "paid_promotion"):
        if _bool(event.get(key)):
            return True, f"FLAG_{key.upper()}"
    promotion = str(event.get("promotion_type") or event.get("campaign_type") or "").strip().lower()
    if promotion and promotion not in {"organic", "none", "unknown"}:
        return True, "PROMOTION_METADATA"
    if INCENTIVE_RE.search(str(event.get("text") or "")):
        return True, "INCENTIVE_TEXT_HEURISTIC"
    return False, None


def classify_event(event: dict, *, clone_count: int = 1, author_recent_count: int = 1) -> dict:
    """Classify one exact-contract social event without deleting raw evidence.

    Weighting is intentionally conservative. Paid/project/clone events remain visible
    in raw counts, but cannot masquerade as independent organic acceleration.
    """
    contract = str(event.get("contract") or "")
    exact_contract = _valid_contract(event.get("chain"), contract)
    project_owned = _is_project_owned(event)
    paid, paid_reason = _is_paid_or_incentivized(event)
    clone = clone_count > 1
    author = str(event.get("author") or "").strip()

    weight = 1.0
    reasons: list[str] = []
    if not exact_contract:
        weight = 0.0
        reasons.append("NO_EXACT_CONTRACT_ATTRIBUTION")
    if not author:
        weight *= 0.35
        reasons.append("AUTHOR_UNKNOWN")
    if project_owned:
        weight *= 0.15
        reasons.append("PROJECT_OWNED")
    if paid:
        weight *= 0.05
        reasons.append(paid_reason or "PAID_OR_INCENTIVIZED")
    if clone:
        # A clone campaign is still evidence that promotion exists, not evidence of
        # many independent discoveries. Preserve it with tiny weight instead of zero.
        weight *= 0.10
        reasons.append("COPY_PASTE_CLUSTER")
    if author_recent_count > 3:
        # Cap burst spam from one author. The first few observations are preserved;
        # repeated hourly flooding gets rapidly discounted.
        weight *= max(0.05, 3.0 / float(author_recent_count))
        reasons.append("SAME_AUTHOR_BURST")

    weight = round(max(0.0, min(1.0, weight)), 4)
    independently_organic = bool(
        exact_contract and author and not project_owned and not paid and not clone and weight >= 0.75
    )
    return {
        "exact_contract": exact_contract,
        "project_owned": project_owned,
        "paid_or_incentivized": paid,
        "clone": clone,
        "independently_organic": independently_organic,
        "organic_weight": weight,
        "quality_reasons": reasons or ["INDEPENDENT_ORGANIC_CANDIDATE"],
    }


def _window_metrics(rows: list[dict], start: datetime, end: datetime) -> dict:
    selected = [r for r in rows if r.get("event_time") and start <= r["event_time"] < end]
    raw = len(selected)
    weighted = sum(float(r.get("organic_weight") or 0.0) for r in selected)
    organic = [r for r in selected if r.get("independently_organic")]
    authors = {r.get("author") for r in organic if r.get("author")}
    sources = {r.get("source") for r in organic if r.get("source")}
    return {
        "raw_mentions": raw,
        "organic_weighted_mentions": round(weighted, 4),
        "independent_organic_mentions": len(organic),
        "independent_authors": len(authors),
        "independent_sources": len(sources),
    }


def _status(current: dict, baseline_per_hour: float, contamination_ratio: float) -> tuple[str, int, float]:
    weighted = float(current.get("organic_weighted_mentions") or 0.0)
    authors = int(current.get("independent_authors") or 0)
    sources = int(current.get("independent_sources") or 0)
    ratio = weighted / max(0.25, baseline_per_hour)

    # Raw post volume is deliberately absent from the promotion conditions.
    if weighted >= 6 and authors >= 5 and sources >= 2 and ratio >= 3.0 and contamination_ratio <= 0.40:
        status = "STRONG_ORGANIC_ACCELERATION"
    elif weighted >= 3 and authors >= 3 and ratio >= 2.0 and contamination_ratio <= 0.60:
        status = "ORGANIC_ACCELERATION"
    elif weighted >= 1.5 and authors >= 2:
        status = "ORGANIC_ACTIVITY"
    else:
        status = "NO_ORGANIC_SIGNAL"

    score = 0.0
    score += min(35.0, weighted * 5.0)
    score += min(25.0, authors * 5.0)
    score += min(15.0, sources * 7.5)
    score += min(20.0, max(0.0, ratio - 1.0) * 6.0)
    score -= min(35.0, contamination_ratio * 35.0)
    return status, int(round(max(0.0, min(100.0, score)))), round(ratio, 3)


def analyze_events(events: list[dict], now: datetime) -> list[dict]:
    valid: list[dict] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        contract = str(e.get("contract") or "")
        if not _valid_contract(e.get("chain"), contract):
            continue
        t = _event_time(e)
        if t is None or t > now + timedelta(minutes=5) or t < now - timedelta(days=30):
            continue
        valid.append({**e, "event_time": t})

    by_token: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in valid:
        chain = str(e.get("chain") or "unknown").lower()
        contract = str(e.get("contract") or "")
        norm = contract.lower() if contract.startswith("0x") else contract
        by_token[(chain, norm)].append(e)

    out: list[dict] = []
    for (chain, norm), rows in by_token.items():
        rows.sort(key=lambda x: x["event_time"])
        clone_counts = Counter(k for k in (_clone_key(x) for x in rows) if k)
        author_hour_counts: Counter[tuple[str, str]] = Counter()
        for r in rows:
            author = str(r.get("author") or "")
            hour = r["event_time"].replace(minute=0, second=0, microsecond=0).isoformat()
            if author:
                author_hour_counts[(author.lower(), hour)] += 1

        classified = []
        for r in rows:
            ck = _clone_key(r)
            author = str(r.get("author") or "")
            hour = r["event_time"].replace(minute=0, second=0, microsecond=0).isoformat()
            q = classify_event(
                r,
                clone_count=clone_counts.get(ck, 1) if ck else 1,
                author_recent_count=author_hour_counts.get((author.lower(), hour), 1) if author else 1,
            )
            classified.append({**r, **q})

        current = _window_metrics(classified, now - timedelta(hours=1), now + timedelta(seconds=1))
        prior6 = _window_metrics(classified, now - timedelta(hours=7), now - timedelta(hours=1))
        h24 = _window_metrics(classified, now - timedelta(hours=24), now + timedelta(seconds=1))
        raw24 = max(1, h24["raw_mentions"])
        contaminated = sum(
            1 for r in classified
            if now - timedelta(hours=24) <= r["event_time"] <= now
            and (r.get("project_owned") or r.get("paid_or_incentivized") or r.get("clone"))
        )
        contamination_ratio = round(contaminated / raw24, 4)
        baseline_per_hour = float(prior6["organic_weighted_mentions"]) / 6.0
        status, score, accel = _status(current, baseline_per_hour, contamination_ratio)

        latest = max((r["event_time"] for r in classified), default=None)
        out.append({
            "chain": chain,
            "contract": rows[-1].get("contract"),
            "status": status,
            "organic_acceleration_score": score,
            "acceleration_vs_prior_6h_hourly_baseline": accel,
            "contamination_ratio_24h": contamination_ratio,
            "current_1h": current,
            "prior_6h": prior6,
            "last_24h": h24,
            "latest_event_at": latest.isoformat() if latest else None,
            "rule": RULE,
            "promotion_rule": "raw_mentions_never_promote_without_independent_authors_and_organic_weight",
        })

    out.sort(
        key=lambda x: (x.get("organic_acceleration_score", 0), x.get("current_1h", {}).get("organic_weighted_mentions", 0)),
        reverse=True,
    )
    return out


def run(output_dir: str | Path = "data", now: str | None = None) -> dict:
    data = Path(output_dir)
    ledger_path = data / "social-catalyst-ledger.json"
    output_path = data / "social-organic-acceleration.json"
    ledger = _load(ledger_path, {})
    events = ledger.get("events", []) if isinstance(ledger, dict) else []
    reference = _dt(now) if now else datetime.now(timezone.utc)
    reference = reference or datetime.now(timezone.utc)
    tokens = analyze_events(events if isinstance(events, list) else [], reference)
    payload = {
        "version": 1,
        "mode": MODE,
        "updated_at": reference.isoformat(),
        "input": "social-catalyst-ledger.json",
        "raw_evidence_mutated": False,
        "rule": RULE,
        "method_note": (
            "Raw mentions are preserved. Organic acceleration requires exact-contract attribution, independent authors, "
            "and time acceleration. Project-owned, paid/incentivized, copy-paste, and same-author burst activity is discounted."
        ),
        "thresholds_are_research_heuristics": True,
        "token_count": len(tokens),
        "strong_count": sum(1 for x in tokens if x["status"] == "STRONG_ORGANIC_ACCELERATION"),
        "accelerating_count": sum(1 for x in tokens if x["status"] == "ORGANIC_ACCELERATION"),
        "tokens": tokens[:1000],
    }
    _write(output_path, payload)
    return {
        "status": "OK",
        "tokens": len(tokens),
        "strong": payload["strong_count"],
        "accelerating": payload["accelerating_count"],
        "output": str(output_path),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
