from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA = Path("data")
OUT = DATA / "deep-intelligence-edge.json"
LEDGER = DATA / "deep-intelligence-event-ledger.json"
MODE = "VETERAN_6_OF_7_EDGE_INTELLIGENCE_V1"

SOURCE_FILES = {
    "deep_live": "six-of-seven-live-intelligence.json",
    "social": "social-intelligence-v2.json",
    "social_scan": "social-source-scan.json",
    "organic": "social-organic-acceleration.json",
    "wallet": "wallet-candidate-evidence.json",
    "wallet_alt": "revival-wallet-latest.json",
    "holder": "revival-holder-latest.json",
    "cex": "cex-revival-radar.json",
    "moonshot_future": "moonshot-future-listing-ledger.json",
    "moonshot_verify": "moonshot-verification-ledger.json",
    "moonshot_radar": "moonshot-radar.json",
    "revival": "revival-1000-latest.json",
    "liquidity_recovery": "liquidity-recovery-shadow.json",
    "paid_attention": "paid-attention-watch.json",
    "external_signals": "external-signal-cohort.json",
}

POSITIVE_TERMS = {
    "listing", "listed", "future listing", "partnership", "partner", "integration",
    "mainnet", "buyback", "burn", "staking", "upgrade", "release", "airdrop",
    "funding", "adoption", "recommend", "recommendation", "accumulation", "accumulate",
    "whale", "smart money", "revival", "relaunch", "campaign", "promotion", "promoted",
}
NEGATIVE_TERMS = {
    "hack", "hacked", "exploit", "breach", "delist", "delisting", "lawsuit",
    "investigation", "rug", "scam", "shutdown", "lp removal", "unlock", "compromised",
}


def _load(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _norm(chain: Any, value: Any) -> str:
    c = str(chain or "").strip().lower()
    v = str(value or "").strip()
    if c in {"ethereum", "bsc", "base", "arbitrum", "optimism", "polygon", "avalanche", "fantom", "linea", "zksync", "mantle", "scroll", "blast"}:
        return v.lower()
    return v


def _candidate_key(row: dict) -> tuple[str, str, str]:
    chain = str(row.get("chain") or row.get("network") or "").strip().lower()
    token = _norm(chain, row.get("token_address") or row.get("token") or row.get("mint") or row.get("contract"))
    pair = _norm(chain, row.get("pair_address") or row.get("dex_pair_address") or row.get("entry_pair_address"))
    return chain, token, pair


def _iter_dicts(value: Any) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _matches_candidate(row: dict, candidate: dict) -> bool:
    chain, token, pair = _candidate_key(candidate)
    if not token:
        return False
    rchain, rtoken, rpair = _candidate_key(row)
    if rtoken and rtoken == token and (not rchain or not chain or rchain == chain):
        if pair and rpair:
            return rpair == pair
        return True
    text = json.dumps(row, ensure_ascii=False).lower()
    token_cmp = token.lower()
    pair_cmp = pair.lower()
    if token_cmp and token_cmp in text:
        return not pair_cmp or pair_cmp in text or not rpair
    return False


def _matched_rows(payload: Any, candidate: dict, limit: int = 200) -> list[dict]:
    out = []
    for row in _iter_dicts(payload):
        if _matches_candidate(row, candidate):
            out.append(row)
            if len(out) >= limit:
                break
    return out


def _latest_text(rows: list[dict]) -> str:
    chunks = []
    for row in rows:
        for key in ("text", "title", "headline", "description", "reason", "reasons", "status", "event_type", "signal", "kind"):
            value = row.get(key)
            if value not in (None, "", [], {}):
                chunks.append(str(value))
    return " ".join(chunks).lower()


def _social_component(candidate: dict, payloads: dict[str, Any]) -> tuple[float, list[str], list[dict]]:
    score = 0.0
    reasons: list[str] = []
    events: list[dict] = []
    rows = _matched_rows(payloads.get("social", {}), candidate) + _matched_rows(payloads.get("social_scan", {}), candidate)
    seen = set()
    authors = set()
    sources = set()
    exact_events = 0
    official_events = 0
    for row in rows:
        attr = str(row.get("attribution") or "")
        source = str(row.get("source") or row.get("provider") or "")
        author = str(row.get("author") or "")
        text = str(row.get("text") or row.get("title") or "")
        identity = str(row.get("id") or row.get("url") or f"{source}|{author}|{text[:160]}")
        fp = hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()
        if fp in seen:
            continue
        seen.add(fp)
        if attr in {"EXACT_CONTRACT", "EXACT_PAIR"}:
            exact_events += 1
            if author:
                authors.add(author.lower())
            if source:
                sources.add(source.lower())
            events.append({"category": "SOCIAL_EXACT", "source": source, "author": author, "text": text[:500], "published_at": row.get("published_at"), "url": row.get("url")})
        elif attr == "OFFICIAL_CHANNEL_CONTEXT":
            official_events += 1
            events.append({"category": "OFFICIAL_CONTEXT", "source": source, "author": author, "text": text[:500], "published_at": row.get("published_at"), "url": row.get("url")})
    social_rows = _matched_rows(payloads.get("social", {}), candidate)
    for row in social_rows:
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        narrative = max(_num(scores.get("narrative")), _num(row.get("narrative")))
        confidence = max(_num(scores.get("confidence")), _num(row.get("confidence")))
        if narrative:
            score = max(score, min(30.0, narrative * 0.22 + confidence * 0.08))
    score = max(score, min(30.0, exact_events * 5.0 + len(authors) * 3.0 + len(sources) * 2.0 + official_events * 2.0))
    if exact_events:
        reasons.append(f"EXACT_SOCIAL_EVENTS_{exact_events}")
    if len(authors) >= 2:
        reasons.append(f"INDEPENDENT_AUTHORS_{len(authors)}")
    if official_events:
        reasons.append(f"OFFICIAL_CONTEXT_{official_events}")
    return round(score, 2), reasons, events


def _wallet_component(candidate: dict, payloads: dict[str, Any]) -> tuple[float, list[str], list[dict]]:
    rows = []
    for key in ("wallet", "wallet_alt", "holder"):
        rows += _matched_rows(payloads.get(key, {}), candidate)
    text = _latest_text(rows)
    score = 0.0
    reasons: list[str] = []
    events: list[dict] = []
    numeric_max = 0.0
    wallet_count = 0
    for row in rows:
        for key in ("smart_wallet_count", "elite_wallets", "wallet_count", "accumulating_wallets", "new_buyers", "holder_growth_pct", "smart_money_score", "wallet_score"):
            if key in row:
                numeric_max = max(numeric_max, _num(row.get(key)))
        for key in ("wallets", "smart_wallets", "elite_wallets", "buyers"):
            if isinstance(row.get(key), list):
                wallet_count = max(wallet_count, len(row[key]))
    if any(term in text for term in ("smart money", "accumulation", "accumulate", "holder_growth", "holder growth")):
        score += 8.0
        reasons.append("WALLET_ACCUMULATION_CONTEXT")
    if wallet_count:
        score += min(8.0, wallet_count * 1.5)
        reasons.append(f"WALLET_EVIDENCE_COUNT_{wallet_count}")
    if numeric_max:
        score += min(6.0, math.log10(max(1.0, numeric_max) + 1.0) * 3.0)
    if rows:
        events.append({"category": "WALLET_HOLDER", "matched_rows": len(rows), "summary": reasons[:]})
    return round(min(20.0, score), 2), reasons, events


def _listing_component(candidate: dict, payloads: dict[str, Any]) -> tuple[float, list[str], list[dict]]:
    score = 0.0
    reasons: list[str] = []
    events: list[dict] = []
    for source, cap in (("moonshot_future", 18.0), ("moonshot_verify", 12.0), ("moonshot_radar", 8.0), ("paid_attention", 8.0), ("external_signals", 6.0)):
        rows = _matched_rows(payloads.get(source, {}), candidate)
        if not rows:
            continue
        text = _latest_text(rows)
        positive = any(term in text for term in POSITIVE_TERMS) or source.startswith("moonshot")
        if positive:
            contribution = cap
            score += contribution
            reasons.append(source.upper())
            events.append({"category": "LISTING_PROMOTION", "source": source, "matched_rows": len(rows), "contribution": contribution})
    return round(min(25.0, score), 2), reasons, events


def _market_component(candidate: dict, payloads: dict[str, Any]) -> tuple[float, list[str], list[dict]]:
    score = 0.0
    reasons: list[str] = []
    events: list[dict] = []
    cex_rows = _matched_rows(payloads.get("cex", {}), candidate)
    cex_score = max((_num(r.get("cex_revival_score")) for r in cex_rows), default=0.0)
    confirmations = max((int(_num(r.get("coherent_confirmations"))) for r in cex_rows), default=0)
    if cex_score >= 35 and confirmations >= 2:
        contribution = min(12.0, cex_score * 0.12 + min(5.0, confirmations * 0.7))
        score += contribution
        reasons.append(f"CEX_REVIVAL_{cex_score:.0f}_{confirmations}CONF")
        events.append({"category": "CEX_REVIVAL", "score": cex_score, "confirmations": confirmations})
    revival_rows = _matched_rows(payloads.get("revival", {}), candidate)
    best_revival = max((_num(r.get("revival_score_verified") or r.get("revival_score")) for r in revival_rows), default=0.0)
    if best_revival >= 50:
        score += min(8.0, best_revival * 0.08)
        reasons.append(f"MARKET_REVIVAL_{best_revival:.0f}")
    recovery_rows = _matched_rows(payloads.get("liquidity_recovery", {}), candidate)
    if recovery_rows:
        score += 5.0
        reasons.append("LIQUIDITY_RECOVERY_CONTEXT")
        events.append({"category": "LIQUIDITY_RECOVERY", "matched_rows": len(recovery_rows)})
    return round(min(20.0, score), 2), reasons, events


def _risk_penalty(candidate: dict, payloads: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    text = " ".join(
        _latest_text(_matched_rows(payloads.get(key, {}), candidate))
        for key in ("social", "social_scan", "wallet", "holder", "external_signals")
    )
    hits = sorted(term for term in NEGATIVE_TERMS if term in text)
    penalty = min(35.0, len(hits) * 8.0)
    if hits:
        reasons.extend(f"NEGATIVE_INTEL:{x}" for x in hits[:6])
    return round(penalty, 2), reasons


def _velocity_bonus(current_events: list[dict], prior_events: list[dict]) -> tuple[float, dict]:
    current = len(current_events)
    previous = len(prior_events)
    delta = max(0, current - previous)
    bonus = min(10.0, delta * 2.5)
    return bonus, {"current_verified_events": current, "previous_verified_events": previous, "new_verified_events": delta, "bonus": bonus}


def _edge_band(score: float) -> str:
    if score >= 85:
        return "EXTREME_EDGE"
    if score >= 65:
        return "HIGH_PRIORITY_EDGE"
    if score >= 45:
        return "BUILDING_EDGE"
    return "WAIT_FOR_MORE_EDGE"


def _event_fingerprint(candidate: dict, event: dict) -> str:
    key = "|".join(_candidate_key(candidate))
    raw = json.dumps(event, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{key}|{raw}".encode("utf-8", errors="ignore")).hexdigest()


def build(data_dir: Path = DATA) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    payloads = {name: _load(data_dir / filename, {}) for name, filename in SOURCE_FILES.items()}
    deep_live = payloads.get("deep_live", {}) if isinstance(payloads.get("deep_live"), dict) else {}
    candidates = [x for x in (deep_live.get("candidate_identities") or []) if isinstance(x, dict)]
    deep_targets = {_candidate_key(x): x for x in (deep_live.get("targets") or []) if isinstance(x, dict)}
    previous = _load(data_dir / OUT.name, {})
    previous_map = {_candidate_key(x): x for x in (previous.get("candidates") or []) if isinstance(x, dict)}
    ledger = _load(data_dir / LEDGER.name, {})
    old_events = [x for x in (ledger.get("events") or []) if isinstance(x, dict)]
    known = {str(x.get("fingerprint") or "") for x in old_events}
    new_events = []
    results = []

    for candidate in candidates:
        key = _candidate_key(candidate)
        social_score, social_reasons, social_events = _social_component(candidate, payloads)
        wallet_score, wallet_reasons, wallet_events = _wallet_component(candidate, payloads)
        listing_score, listing_reasons, listing_events = _listing_component(candidate, payloads)
        market_score, market_reasons, market_events = _market_component(candidate, payloads)
        penalty, risk_reasons = _risk_penalty(candidate, payloads)
        event_rows = social_events + wallet_events + listing_events + market_events
        previous_events = list((previous_map.get(key) or {}).get("verified_micro_events") or [])
        velocity_bonus, velocity = _velocity_bonus(event_rows, previous_events)
        raw = social_score + wallet_score + listing_score + market_score + velocity_bonus - penalty
        score = round(max(0.0, min(100.0, raw)), 2)
        band = _edge_band(score)
        row = {
            **candidate,
            "edge_score": score,
            "edge_band": band,
            "components": {
                "social_news": social_score,
                "wallet_holder": wallet_score,
                "listing_promotion": listing_score,
                "market_cex_liquidity": market_score,
                "fresh_event_velocity_bonus": velocity_bonus,
                "negative_intelligence_penalty": penalty,
            },
            "signals": sorted(set(social_reasons + wallet_reasons + listing_reasons + market_reasons)),
            "negative_intelligence": risk_reasons,
            "velocity": velocity,
            "verified_micro_events": event_rows[:80],
            "deep_live_target": deep_targets.get(key),
            "production_effect": False,
            "automatic_buy": False,
            "interpretation": (
                "ESCALATE_HUMAN_ATTENTION_NOT_GATE_BYPASS" if score >= 65
                else "CONTINUE_HIGH_FREQUENCY_INTELLIGENCE_COLLECTION"
            ),
        }
        results.append(row)
        for event in event_rows:
            fp = _event_fingerprint(candidate, event)
            if fp in known:
                continue
            known.add(fp)
            new_events.append({
                "fingerprint": fp,
                "observed_at": now,
                "chain": candidate.get("chain"),
                "symbol": candidate.get("symbol"),
                "token_address": candidate.get("token_address"),
                "pair_address": candidate.get("pair_address"),
                **event,
            })

    results.sort(key=lambda x: (x.get("edge_score") or 0, len(x.get("signals") or [])), reverse=True)
    all_events = (old_events + new_events)[-20000:]
    _write(data_dir / LEDGER.name, {
        "version": 1,
        "mode": "IMMUTABLE_6_OF_7_MICRO_EVENT_LEDGER",
        "updated_at": now,
        "events_count": len(all_events),
        "new_events_this_run": len(new_events),
        "events": all_events,
    })
    out = {
        "version": 1,
        "mode": MODE,
        "generated_at": now,
        "candidate_count": len(results),
        "high_priority_count": sum(1 for x in results if _num(x.get("edge_score")) >= 65),
        "extreme_edge_count": sum(1 for x in results if _num(x.get("edge_score")) >= 85),
        "new_micro_events": len(new_events),
        "candidates": results,
        "truth_contract": {
            "focus": "VETERAN_COIN_REVIVAL_ONLY",
            "trigger": "VERIFIED_6_OF_7_ONLY",
            "edge_score_is_not_profit_probability": True,
            "edge_score_never_bypasses_hard_gates": True,
            "symbol_name_only_never_counts_as_exact_evidence": True,
            "negative_intelligence_can_reduce_edge": True,
            "all_micro_events_timestamped_and_retained": True,
            "no_hindsight": True,
            "production_effect": False,
            "automatic_buy": False,
        },
        "next_learning_goal": "Measure which micro-event sequences occur before later REAL_ALERT, breakout, fade, or failed-survival outcomes.",
    }
    _write(data_dir / OUT.name, out)
    return out


def main() -> None:
    out = build(DATA)
    print(json.dumps({
        "candidate_count": out.get("candidate_count"),
        "high_priority_count": out.get("high_priority_count"),
        "extreme_edge_count": out.get("extreme_edge_count"),
        "new_micro_events": out.get("new_micro_events"),
        "leaders": [
            {"symbol": x.get("symbol"), "edge_score": x.get("edge_score"), "edge_band": x.get("edge_band")}
            for x in (out.get("candidates") or [])[:5]
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
