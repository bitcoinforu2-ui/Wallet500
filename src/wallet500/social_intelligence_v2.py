from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "social-intelligence-v2.json"
MODE = "RESEARCH_ONLY_SOCIAL_INTELLIGENCE_V2"
POSITIVE = {"listing","listed","partnership","partner","integration","launch","mainnet","buyback","burn","staking","upgrade","release","airdrop","funding","adoption"}
NEGATIVE = {"hack","hacked","exploit","breach","delist","delisting","lawsuit","investigation","unlock","rug","scam","shutdown"}


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _n(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _dt(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _freshness_score(ts: Any, now: datetime) -> float:
    d = _dt(ts)
    if not d:
        return 0.0
    hours = max(0.0, (now - d).total_seconds() / 3600.0)
    if hours <= 1: return 100.0
    if hours <= 4: return 85.0
    if hours <= 12: return 65.0
    if hours <= 24: return 45.0
    return 15.0


def _organic_map(payload: dict) -> dict[str, dict]:
    return {str(x.get("contract")): x for x in (payload.get("tokens") or []) if isinstance(x, dict) and x.get("contract")}


def _scan_map(payload: dict) -> dict[str, dict]:
    return {str(x.get("token_address")): x for x in (payload.get("targets") or []) if isinstance(x, dict) and x.get("token_address")}


def _revival_map(payload: dict) -> dict[str, dict]:
    return {str(x.get("token_address")): x for x in (payload.get("coins") or []) if isinstance(x, dict) and x.get("token_address")}


def _influencer_forward_reputation(ledger: dict) -> dict[str, dict]:
    # Reputation is intentionally unavailable until timestamp-safe forward outcomes exist.
    # Observed reach/mentions can describe coverage but never become historical skill.
    out = {}
    for row in ledger.get("influencers") or []:
        if not isinstance(row, dict):
            continue
        key = f"{row.get('source')}:{row.get('author')}"
        samples = int(row.get("forward_sample_count") or 0)
        score = row.get("forward_reputation_score") if samples >= 3 else None
        out[key] = {
            "forward_sample_count": samples,
            "forward_reputation_score": _n(score, None) if score is not None else None,
            "mentions": int(row.get("mentions") or 0),
            "unique_contracts": int(row.get("unique_contracts") or 0),
            "followers_latest": row.get("followers_latest"),
            "confidence": "MEASURED" if samples >= 10 else ("LIMITED" if samples >= 3 else "INSUFFICIENT_FORWARD_SAMPLE"),
        }
    return out


def _catalyst_terms(events: list[dict]) -> tuple[list[str], list[str]]:
    pos, neg = set(), set()
    for e in events:
        text = str(e.get("text") or "").lower()
        pos.update(x for x in POSITIVE if x in text)
        neg.update(x for x in NEGATIVE if x in text)
    return sorted(pos), sorted(neg)


def score_token(token: str, scan: dict | None, organic: dict | None, reputation: dict[str, dict], revival: dict | None, now: datetime) -> dict:
    scan = scan or {}; organic = organic or {}; revival = revival or {}
    events = [x for x in (scan.get("events") or []) if isinstance(x, dict)]
    social_events = [x for x in events if str(x.get("source") or "") in {"x","youtube","reddit","telegram"}]
    news_events = [x for x in events if str(x.get("source") or "") in {"news","google_news","google_news_rss"}]

    social_score = _n(organic.get("organic_acceleration_score"), 0.0)
    organic_available = bool(organic)
    contamination = max(0.0, min(1.0, _n(organic.get("contamination_ratio_24h"), 0.0))) if organic_available else None

    exact_social = [x for x in social_events if x.get("attribution") == "EXACT_CONTRACT"]
    independent_authors = {f"{x.get('source')}:{x.get('author')}" for x in exact_social if x.get("author")}
    independent_sources = {str(x.get("source")) for x in exact_social if x.get("source")}
    rep_scores = []
    rep_samples = 0
    for key in independent_authors:
        rep = reputation.get(key) or {}
        if rep.get("forward_reputation_score") is not None:
            rep_scores.append(_n(rep.get("forward_reputation_score")))
            rep_samples += int(rep.get("forward_sample_count") or 0)
    if rep_scores:
        kol_score = min(100.0, sum(rep_scores) / len(rep_scores) * 0.7 + min(30.0, len(independent_authors) * 6.0))
        kol_conf = "MEASURED_FORWARD_HISTORY"
    else:
        # Unknown influencers may create attention, but cannot receive a high skill score.
        kol_score = min(45.0, len(independent_authors) * 8.0 + len(independent_sources) * 5.0)
        kol_conf = "ATTENTION_ONLY_NO_FORWARD_REPUTATION"

    pos, neg = _catalyst_terms(news_events + [x for x in social_events if x.get("attribution") == "OFFICIAL_CHANNEL_CONTEXT"])
    exact_news = sum(1 for x in news_events if x.get("attribution") == "EXACT_CONTRACT")
    context_news = sum(1 for x in news_events if x.get("attribution") == "NAME_SYMBOL_CONTEXT")
    news_sources = {str(x.get("author") or x.get("source") or "") for x in news_events}
    news_score = min(100.0, exact_news * 18.0 + context_news * 6.0 + len(news_sources) * 5.0 + len(pos) * 10.0)
    if neg:
        news_score = max(0.0, news_score - min(35.0, len(neg) * 12.0))

    manipulation = 0.0
    if contamination is not None:
        manipulation += contamination * 70.0
    if organic_available:
        raw = int(((organic.get("last_24h") or {}).get("raw_mentions")) or 0)
        organic_n = int(((organic.get("last_24h") or {}).get("independent_organic_mentions")) or 0)
        if raw >= 5 and organic_n == 0:
            manipulation += 20.0
    manipulation = min(100.0, manipulation)

    available = {"social": organic_available, "kol": bool(exact_social), "news": bool(news_events)}
    weights = {"social": 45.0, "kol": 25.0, "news": 30.0}
    values = {"social": social_score, "kol": kol_score, "news": news_score}
    denom = sum(weights[k] for k, ok in available.items() if ok)
    narrative = sum(weights[k] * values[k] / 100.0 for k, ok in available.items() if ok) / denom * 100.0 if denom else 0.0
    narrative = max(0.0, min(100.0, narrative - manipulation * 0.25))

    freshness_values = []
    if organic_available: freshness_values.append(_freshness_score(organic.get("latest_event_at") or organic.get("updated_at"), now))
    for e in events[:20]: freshness_values.append(_freshness_score(e.get("published_at") or scan.get("generated_at"), now))
    freshness = round(sum(freshness_values) / len(freshness_values), 1) if freshness_values else 0.0
    coverage = round(sum(1 for x in available.values() if x) / 3.0 * 100.0, 1)
    confidence = round(min(100.0, coverage * 0.65 + freshness * 0.35), 1)

    reasons = []
    if social_score >= 60: reasons.append(f"ORGANIC_SOCIAL_{social_score:.0f}")
    if len(independent_authors) >= 2: reasons.append(f"INDEPENDENT_KOL_AUTHORS_{len(independent_authors)}")
    if pos: reasons.append("POSITIVE_CATALYST:" + ",".join(pos[:4]))
    if neg: reasons.append("NEGATIVE_CATALYST:" + ",".join(neg[:4]))
    if manipulation >= 40: reasons.append(f"MANIPULATION_RISK_{manipulation:.0f}")
    if not reasons: reasons.append("NO_MATERIAL_VERIFIED_NARRATIVE_SIGNAL")

    providers = {}
    for st in scan.get("provider_status") or []:
        if isinstance(st, dict) and st.get("provider"):
            providers[str(st.get("provider"))] = st.get("status")

    return {
        "token_address": token,
        "symbol": scan.get("symbol") or revival.get("symbol"),
        "name": scan.get("name") or revival.get("name"),
        "pair_address": scan.get("pair_address") or revival.get("dex_pair_address"),
        "dex_url": revival.get("dex_link"),
        "scores": {
            "social_momentum": round(social_score, 1),
            "kol_quality": round(kol_score, 1),
            "news_catalyst": round(news_score, 1),
            "hype_manipulation_risk": round(manipulation, 1),
            "narrative": round(narrative, 1),
            "confidence": confidence,
        },
        "coverage": {
            "score_pct": coverage,
            "freshness_score": freshness,
            "organic_social_available": organic_available,
            "exact_social_events": len(exact_social),
            "independent_authors": len(independent_authors),
            "independent_sources": len(independent_sources),
            "news_events": len(news_events),
            "forward_reputation_samples": rep_samples,
        },
        "organic": {
            "status": organic.get("status") if organic_available else "NOT_AVAILABLE",
            "acceleration_vs_prior_6h": organic.get("acceleration_vs_prior_6h_hourly_baseline") if organic_available else None,
            "contamination_ratio_24h": contamination,
        },
        "kol_confidence": kol_conf,
        "catalysts": {"positive": pos, "negative": neg},
        "provider_status": providers,
        "reasons": reasons,
        "production_effect": False,
        "automatic_buy": False,
    }


def build(data_dir: Path = DATA) -> dict:
    now = datetime.now(timezone.utc)
    scan_payload = _load(data_dir / "social-source-scan.json", {})
    organic_payload = _load(data_dir / "social-organic-acceleration.json", {})
    influencer_payload = _load(data_dir / "social-influencer-ledger.json", {})
    revival_payload = _load(data_dir / "revival-1000-latest.json", {})
    envelope = _load(data_dir / "candidate-evidence-envelope.json", {})
    scan = _scan_map(scan_payload); organic = _organic_map(organic_payload); revival = _revival_map(revival_payload)
    reputation = _influencer_forward_reputation(influencer_payload)
    tokens = []
    seen = set()
    for row in envelope.get("candidates") or []:
        if not isinstance(row, dict) or row.get("status") == "BLOCKED_TRUTH":
            continue
        token = str(row.get("token_address") or "")
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(score_token(token, scan.get(token), organic.get(token), reputation, revival.get(token), now))
    tokens.sort(key=lambda x: (x["scores"]["narrative"], x["scores"]["confidence"]), reverse=True)
    providers = Counter()
    for row in tokens:
        for provider, status in (row.get("provider_status") or {}).items():
            providers[f"{provider}:{status}"] += 1
    return {
        "version": 2,
        "mode": MODE,
        "generated_at": now.isoformat(),
        "network": "solana",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "no_hindsight": True,
        "truth_contract": {
            "raw_mentions_are_not_organic_acceleration": True,
            "unknown_influencer_never_receives_high_reputation": True,
            "forward_outcomes_required_for_influencer_skill": True,
            "name_symbol_news_context_is_lower_confidence_than_exact_contract": True,
            "social_never_overrides_identity_liquidity_security_or_pair_survival": True,
            "narrative_score_is_shadow_research_only": True,
        },
        "counts": {
            "tokens": len(tokens),
            "narrative_ge_60": sum(1 for x in tokens if x["scores"]["narrative"] >= 60),
            "social_momentum_ge_60": sum(1 for x in tokens if x["scores"]["social_momentum"] >= 60),
            "manipulation_risk_ge_40": sum(1 for x in tokens if x["scores"]["hype_manipulation_risk"] >= 40),
        },
        "provider_status_counts": dict(providers),
        "tokens": tokens,
    }


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    payload = build(data)
    _write(data / OUTPUT.name, payload)
    return payload


def main() -> None:
    p = run()
    print(json.dumps({"counts": p["counts"], "providers": p["provider_status_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
