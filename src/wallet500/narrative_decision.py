from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MODE = "RESEARCH_ONLY_NARRATIVE_DECISION_V1"


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def classify(row: dict) -> dict:
    scores = row.get("scores") or {}
    coverage = row.get("coverage") or {}
    catalysts = row.get("catalysts") or {}
    narrative = float(scores.get("narrative") or 0)
    social = float(scores.get("social_momentum") or 0)
    confidence = float(scores.get("confidence") or 0)
    hype = float(scores.get("hype_manipulation_risk") or 0)
    sources = int(coverage.get("independent_sources") or 0)
    authors = int(coverage.get("independent_authors") or 0)
    news = int(coverage.get("news_events") or 0)
    freshness = float(coverage.get("freshness_score") or 0)
    negative = list(catalysts.get("negative") or [])

    reasons = []
    if hype >= 60:
        light = "RED"; reasons.append("HIGH_HYPE_MANIPULATION_RISK")
    elif negative and narrative < 55:
        light = "RED"; reasons.append("NEGATIVE_CATALYST_WITHOUT_STRONG_CONFIRMATION")
    elif confidence >= 60 and narrative >= 65 and social >= 60 and sources >= 2 and authors >= 2 and freshness >= 60 and hype < 40:
        light = "GREEN"; reasons.append("CROSS_SOURCE_NARRATIVE_CONFIRMED")
    else:
        light = "ORANGE"; reasons.append("PARTIAL_OR_INSUFFICIENT_CROSS_SOURCE_CONFIRMATION")

    if social >= 60: reasons.append("ORGANIC_SOCIAL_ACCELERATION")
    if sources >= 2: reasons.append("MULTI_SOURCE")
    if news: reasons.append("NEWS_CONTEXT_PRESENT")
    if freshness < 60: reasons.append("FRESHNESS_WEAK")
    if confidence < 60: reasons.append("CONFIDENCE_BELOW_GREEN")

    return {
        "token_address": row.get("token_address"),
        "pair_address": row.get("pair_address"),
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "dex_url": row.get("dex_url"),
        "traffic_light": light,
        "narrative_score": narrative,
        "social_acceleration": social,
        "source_confidence": confidence,
        "market_context": "CONFIRMING" if narrative >= 65 and social >= 60 else "MIXED_OR_UNCONFIRMED",
        "independent_sources": sources,
        "independent_authors": authors,
        "news_events": news,
        "freshness_score": freshness,
        "hype_risk": hype,
        "positive_catalysts": list(catalysts.get("positive") or []),
        "negative_catalysts": negative,
        "reasons": reasons,
        "production_effect": False,
        "automatic_buy": False,
    }


def build(data_dir: Path) -> dict:
    src = _load(data_dir / "social-intelligence-v2.json", {})
    rows = [classify(x) for x in (src.get("tokens") or []) if isinstance(x, dict) and x.get("token_address")]
    order = {"GREEN": 0, "ORANGE": 1, "RED": 2}
    rows.sort(key=lambda x: (order.get(x["traffic_light"], 9), -x["source_confidence"], -x["narrative_score"]))
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": 1,
        "mode": MODE,
        "generated_at": now,
        "source_generated_at": src.get("generated_at"),
        "cadence_minutes": 30,
        "production_effect": False,
        "automatic_buy": False,
        "no_hindsight": True,
        "truth_contract": {
            "research_only": True,
            "social_never_overrides_production_gates": True,
            "exact_pair_identity_is_inherited_not_rewritten": True,
            "unknown_is_not_zero_for_production": True,
            "green_is_context_not_buy_signal": True,
            "thresholds_do_not_modify_wallet500_production_truth": True,
        },
        "counts": {k: sum(1 for x in rows if x["traffic_light"] == k) for k in ("GREEN", "ORANGE", "RED")},
        "tokens": rows,
    }


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    out = build(data)
    p = data / "narrative-decision.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    run()
