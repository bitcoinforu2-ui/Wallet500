from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA = Path("data")

PROGRAM_WEIGHTS = {
    "SPOT_LISTING_EXPECTED": 30,
    "EXCHANGE_ROADMAP": 24,
    "PREMARKET_OR_AUCTION": 22,
    "LAUNCHPOOL_ALPHA_AIRDROP": 20,
    "FUTURES_LISTING": 12,
    "OFFICIAL_CATALYST": 10,
}

PROGRAM_TERMS = {
    "BINANCE_ALPHA": r"\bbinance\s+alpha\b|\balpha\b",
    "LAUNCHPOOL": r"\blaunchpool\b",
    "MEGADROP": r"\bmegadrop\b",
    "HODLER_AIRDROP": r"\bhodler\s+airdrop\b",
    "PREMARKET": r"\bpre[- ]?market\b|\bpreopen\b|\bprelaunch\b",
    "SPOT_LISTING": r"\bspot\b.{0,80}\blist|\blist(?:ing|ed)?\b.{0,80}\bspot\b",
    "FUTURES": r"\bfutures?\b|\bperpetual\b",
}

INVOLVEMENT_TERMS = {
    "BINANCE_LABS_OR_YZI": r"\bbinance\s+labs\b|\byzi\s+labs\b",
    "INVESTMENT": r"\binvest(?:ed|ment|ing)?\b|\bstrategic\s+investment\b",
    "INCUBATION": r"\bincubat(?:e|ed|ion|or)\b|\baccelerator\b",
    "MVB": r"\bmost\s+valuable\s+builder\b|\bMVB\b",
    "BNB_CHAIN_ECOSYSTEM": r"\bbnb\s+chain\b.{0,100}\b(grant|program|builder|ecosystem|incubat|accelerat|partner)",
}


def _norm_chain(value: object) -> str:
    x = str(value or "").lower().strip()
    return {"eth": "ethereum", "bnb": "bsc", "binance-smart-chain": "bsc", "arbitrum-one": "arbitrum"}.get(x, x)


def _identity_matches(event: dict, current: dict) -> bool:
    token_a = str(event.get("contract") or event.get("token") or event.get("token_address") or "").strip().lower()
    token_b = str(current.get("contract") or current.get("token") or current.get("token_address") or "").strip().lower()
    chain_a = _norm_chain(event.get("chain"))
    chain_b = _norm_chain(current.get("chain"))
    if not token_a or not token_b or token_a != token_b or not chain_a or chain_a != chain_b:
        return False
    pair_a = str(event.get("pair_address") or "").strip().lower()
    pair_b = str(current.get("pair_address") or "").strip().lower()
    return not (pair_a and pair_b and pair_a != pair_b)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _historical_binance_events(current: dict, data_dir: Path) -> list[dict]:
    ledger = _load(data_dir / "catalyst-wire-ledger.json", {"events": {}})
    records = ledger.get("events") if isinstance(ledger, dict) else {}
    out = []
    for rec in (records or {}).values():
        if not isinstance(rec, dict):
            continue
        e = rec.get("event") if isinstance(rec.get("event"), dict) else {}
        if str(e.get("source_owner") or "").lower() != "binance" and not str(e.get("source_id") or "").upper().startswith("BINANCE_"):
            continue
        if not _identity_matches(e, current):
            continue
        out.append({
            "event_type": e.get("event_type"),
            "source_id": e.get("source_id"),
            "first_seen_at": rec.get("first_seen_at"),
            "last_seen_at": rec.get("last_seen_at"),
            "source_url": e.get("source_url"),
            "excerpt": str(e.get("excerpt") or "")[:220],
        })
    return out


def _exact_identity_text_evidence(current: dict, data_dir: Path) -> list[dict]:
    token = str(current.get("contract") or "").strip().lower()
    if not token:
        return []
    files = [
        "social-intelligence-v2.json",
        "coin-intelligence-profiles.json",
        "cex-identity-registry.json",
        "manual-watchlist.json",
    ]
    found = []
    for name in files:
        payload = _load(data_dir / name, {})
        raw = json.dumps(payload, ensure_ascii=False)
        lower = raw.lower()
        if token not in lower:
            continue
        # Keep this as evidence discovery only. We never infer involvement from symbol-only text.
        window_hits = []
        start = 0
        while True:
            pos = lower.find(token, start)
            if pos < 0:
                break
            a, b = max(0, pos - 1200), min(len(raw), pos + len(token) + 1200)
            window_hits.append(raw[a:b])
            start = pos + len(token)
            if len(window_hits) >= 8:
                break
        text = " ".join(window_hits)
        tags = []
        for tag, rx in INVOLVEMENT_TERMS.items():
            if re.search(rx, text, re.I | re.S):
                tags.append(tag)
        if tags:
            found.append({"source_file": name, "tags": sorted(set(tags)), "exact_token_identity": True})
    return found


def build_profile(current: dict, data_dir: Path = DATA) -> dict:
    is_binance = str(current.get("source_owner") or "").lower() == "binance" or str(current.get("source_id") or "").upper().startswith("BINANCE_")
    if not is_binance:
        return {"applicable": False, "production_effect": False}

    history = _historical_binance_events(current, data_dir)
    current_text = " ".join([
        str(current.get("event_type") or ""),
        str(current.get("excerpt") or ""),
        str(current.get("source_id") or ""),
    ])
    program_tags = []
    for tag, rx in PROGRAM_TERMS.items():
        if re.search(rx, current_text, re.I | re.S):
            program_tags.append(tag)
    for h in history:
        text = f"{h.get('event_type')} {h.get('excerpt')} {h.get('source_id')}"
        for tag, rx in PROGRAM_TERMS.items():
            if re.search(rx, text, re.I | re.S):
                program_tags.append(tag)
    program_tags = sorted(set(program_tags))

    involvement = _exact_identity_text_evidence(current, data_dir)
    involvement_tags = sorted({tag for row in involvement for tag in row.get("tags") or []})

    score = PROGRAM_WEIGHTS.get(str(current.get("event_type") or ""), 10)
    score += min(25, len(history) * 5)
    if len(program_tags) >= 2:
        score += 15
    if {"BINANCE_ALPHA", "LAUNCHPOOL", "MEGADROP", "HODLER_AIRDROP"} & set(program_tags) and "SPOT_LISTING" in program_tags:
        score += 15
    score += min(25, len(involvement_tags) * 7)
    score = max(0, min(100, score))

    if involvement_tags:
        relationship = "ECOSYSTEM_INVOLVEMENT_EVIDENCE"
    elif len(program_tags) >= 2 or len(history) >= 2:
        relationship = "MULTI_STAGE_BINANCE_JOURNEY"
    elif history:
        relationship = "REPEATED_BINANCE_CONTACT"
    else:
        relationship = "FIRST_OBSERVED_BINANCE_EVENT"

    if score >= 75:
        grade = "HIGH"
    elif score >= 50:
        grade = "MEDIUM"
    else:
        grade = "EARLY"

    return {
        "applicable": True,
        "priority": "FIRE_PRIORITY",
        "relationship_score": score,
        "relationship_grade": grade,
        "relationship_class": relationship,
        "historical_official_events": len(history),
        "program_journey": program_tags,
        "ecosystem_involvement": {
            "status": "EVIDENCE_PRESENT" if involvement_tags else "NOT_VERIFIED",
            "tags": involvement_tags,
            "evidence": involvement,
            "development_involvement_is_not_inferred_without_explicit_evidence": True,
        },
        "history": history[-12:],
        "production_effect": False,
        "automatic_buy": False,
        "truth_contract": {
            "exact_chain_token_identity_required_for_history": True,
            "pair_mismatch_rejected_when_both_pairs_known": True,
            "symbol_only_history_never_scores": True,
            "binance_priority_never_overrides_wallet500_gates": True,
            "score_is_context_not_probability": True,
        },
    }


def enrich_event(event: dict, data_dir: Path = DATA) -> dict:
    out = dict(event)
    out["binance_intelligence"] = build_profile(out, data_dir)
    return out


def format_binance_lines(event: dict) -> list[str]:
    p = event.get("binance_intelligence") if isinstance(event.get("binance_intelligence"), dict) else {}
    if not p.get("applicable"):
        return []
    tags = ", ".join(p.get("program_journey") or []) or "none verified yet"
    eco = p.get("ecosystem_involvement") if isinstance(p.get("ecosystem_involvement"), dict) else {}
    eco_text = ", ".join(eco.get("tags") or []) if eco.get("status") == "EVIDENCE_PRESENT" else "not verified"
    return [
        "🔥🔥 BINANCE PRIORITY ALERT",
        f"🔥 Binance relationship: {p.get('relationship_score')}/100 · {p.get('relationship_grade')} · {p.get('relationship_class')}",
        f"🧭 Binance journey: {tags}",
        f"🏗 Ecosystem/development involvement evidence: {eco_text}",
        f"📚 Prior exact-identity Binance events: {p.get('historical_official_events', 0)}",
        "ℹ️ Binance score = research context, not probability and not BUY",
    ]
