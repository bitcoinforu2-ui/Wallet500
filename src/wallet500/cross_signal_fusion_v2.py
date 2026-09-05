from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
OUTPUT = DATA / "cross-signal-fusion-v2.json"
MODE = "RESEARCH_ONLY_CROSS_SIGNAL_FUSION_V2"


def _load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _n(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _social_map(payload: dict) -> dict[str, dict]:
    return {str(x.get("token_address")): x for x in (payload.get("tokens") or []) if isinstance(x, dict) and x.get("token_address")}


def score_row(row: dict, social: dict | None) -> dict:
    social = social or {}
    market = row.get("market") or {}
    adaptive = row.get("adaptive_discovery") or {}
    families = row.get("families") or {}
    holder = families.get("holder_growth") or {}
    wallet = families.get("wallet_accumulation") or {}
    smart = families.get("smart_money") or {}
    s = social.get("scores") or {}

    channels = {}
    market_score = max(_n(market.get("revival_score_verified")), _n(adaptive.get("anomaly_score")))
    channels["market"] = {"available": True, "score": min(100.0, market_score), "weight": 30.0}

    holder_verified = holder.get("verified") is True
    hg = (holder.get("metrics") or {}).get("growth_24h_pct")
    holder_score = 0.0
    if holder_verified and hg is not None:
        growth = _n(hg)
        holder_score = min(100.0, max(0.0, growth) * 20.0)
    channels["holders"] = {"available": holder_verified, "score": holder_score, "weight": 20.0}

    wallet_verified = wallet.get("verified") is True
    wm = wallet.get("metrics") or {}
    wallet_score = 0.0
    if wallet_verified:
        wallet_score += min(45.0, _n(wm.get("first_seen_buyers_h1")) * 7.5)
        wallet_score += min(35.0, max(0.0, _n(wm.get("net_accumulating_wallets_h1"))) * 7.0)
        ratio = _n(wm.get("wallet_buy_sell_ratio_h1"))
        if ratio >= 1.5: wallet_score += 10.0
        if ratio >= 2.0: wallet_score += 10.0
    channels["wallets"] = {"available": wallet_verified, "score": min(100.0, wallet_score), "weight": 20.0}

    smart_verified = smart.get("verified") is True
    smart_score = 65.0 if smart_verified and smart.get("positive") is True else (15.0 if smart_verified else 0.0)
    channels["smart_money"] = {"available": smart_verified, "score": smart_score, "weight": 10.0}

    social_confidence = max(0.0, min(100.0, _n(s.get("confidence"))))
    narrative_raw = max(0.0, min(100.0, _n(s.get("narrative"))))
    narrative_effective = narrative_raw * social_confidence / 100.0
    narrative_available = bool(social) and social_confidence >= 20.0
    channels["narrative"] = {
        "available": narrative_available,
        "score": narrative_effective,
        "raw_score": narrative_raw,
        "confidence": social_confidence,
        "weight": 20.0,
    }

    denom = sum(x["weight"] for x in channels.values() if x["available"])
    raw = sum(x["weight"] * x["score"] / 100.0 for x in channels.values() if x["available"])
    normalized = raw / denom * 100.0 if denom else 0.0
    coverage = denom

    manipulation = _n(s.get("hype_manipulation_risk")) if narrative_available else 0.0
    risk_penalty = manipulation * 0.25
    if row.get("blockers"):
        risk_penalty += 30.0
    late = bool(adaptive.get("late_move_risk"))
    if late:
        risk_penalty += 25.0
    score = max(0.0, min(100.0, normalized - risk_penalty))

    positive_families = sum(1 for x in channels.values() if x["available"] and x["score"] >= 55)
    if row.get("blockers"):
        status = "HARD_TRUTH_BLOCKED"
    elif coverage < 50:
        status = "INSUFFICIENT_COVERAGE"
    elif score >= 75 and positive_families >= 3 and not late:
        status = "FUSION_HOT"
    elif score >= 60 and positive_families >= 2:
        status = "FUSION_WARM"
    elif score >= 45:
        status = "FUSION_WATCH"
    else:
        status = "FUSION_QUIET"

    why = []
    if _n(adaptive.get("velocity_score")) >= 40: why.append(f"MARKET_VELOCITY_{_n(adaptive.get('velocity_score')):.0f}")
    if _n(adaptive.get("persistence_score")) >= 60: why.append(f"PERSISTENCE_{_n(adaptive.get('persistence_score')):.0f}")
    if holder_verified and holder_score >= 40: why.append(f"HOLDER_GROWTH_SCORE_{holder_score:.0f}")
    if wallet_verified and wallet_score >= 40: why.append(f"WALLET_ACCUMULATION_{wallet_score:.0f}")
    if narrative_available and social_confidence >= 40 and _n(s.get("social_momentum")) >= 50: why.append(f"SOCIAL_{_n(s.get('social_momentum')):.0f}")
    if narrative_available and social_confidence >= 40 and _n(s.get("kol_quality")) >= 35: why.append(f"KOL_{_n(s.get('kol_quality')):.0f}")
    if narrative_available and social_confidence >= 40 and _n(s.get("news_catalyst")) >= 35: why.append(f"NEWS_{_n(s.get('news_catalyst')):.0f}")
    if narrative_available and narrative_raw >= 60 and social_confidence < 40: why.append(f"NARRATIVE_LOW_CONFIDENCE_{social_confidence:.0f}")
    if manipulation >= 40: why.append(f"HYPE_RISK_{manipulation:.0f}")
    if not why: why.append("NO_MULTI_SIGNAL_CONVERGENCE_YET")

    change = {
        "pair_volume_change_pct": market.get("pair_volume_change_pct"),
        "liquidity_change_pct": market.get("liquidity_change_pct"),
        "holder_growth_24h_pct": hg if holder_verified else None,
        "first_seen_buyers_h1": wm.get("first_seen_buyers_h1") if wallet_verified else None,
        "net_accumulating_wallets_h1": wm.get("net_accumulating_wallets_h1") if wallet_verified else None,
        "social_acceleration_vs_6h": (social.get("organic") or {}).get("acceleration_vs_prior_6h") if narrative_available else None,
    }

    public_channels = {}
    for k, v in channels.items():
        public_channels[k] = {"available": v["available"], "score": round(v["score"], 1)}
        if k == "narrative":
            public_channels[k]["raw_score"] = round(v["raw_score"], 1)
            public_channels[k]["confidence"] = round(v["confidence"], 1)

    return {
        "token_address": row.get("token_address"),
        "symbol": row.get("symbol"),
        "pair_address": row.get("pair_address"),
        "dex_url": row.get("dex_url"),
        "source_status": row.get("status"),
        "discovery_tier": row.get("discovery_tier"),
        "fusion_status": status,
        "fusion_score": round(score, 1),
        "coverage_weight_pct": round(coverage, 1),
        "positive_family_count": positive_families,
        "channels": public_channels,
        "risk": {"manipulation": round(manipulation, 1), "late_move": late, "hard_blockers": row.get("blockers") or []},
        "why_now": why,
        "change": change,
        "production_effect": False,
        "automatic_buy": False,
    }


def build(data_dir: Path = DATA) -> dict:
    envelope = _load(data_dir / "candidate-evidence-envelope.json", {})
    social = _social_map(_load(data_dir / "social-intelligence-v2.json", {}))
    rows = []
    for row in envelope.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        token = str(row.get("token_address") or "")
        rows.append(score_row(row, social.get(token)))
    priority = {"FUSION_HOT":0,"FUSION_WARM":1,"FUSION_WATCH":2,"FUSION_QUIET":3,"INSUFFICIENT_COVERAGE":4,"HARD_TRUTH_BLOCKED":5}
    rows.sort(key=lambda x:(priority.get(x["fusion_status"],9),-x["fusion_score"],-x["coverage_weight_pct"]))
    return {
        "version": 2,
        "mode": MODE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "no_hindsight": True,
        "truth_contract": {
            "shadow_lane_only": True,
            "does_not_modify_real_alert_gate": True,
            "missing_channel_reduces_coverage_not_negative_score": True,
            "hard_truth_blockers_cannot_be_overridden": True,
            "social_cannot_override_identity_pair_liquidity_security": True,
            "narrative_is_confidence_weighted_before_fusion": True,
        },
        "counts": {
            "tokens": len(rows),
            "hot": sum(1 for x in rows if x["fusion_status"] == "FUSION_HOT"),
            "warm": sum(1 for x in rows if x["fusion_status"] == "FUSION_WARM"),
            "watch": sum(1 for x in rows if x["fusion_status"] == "FUSION_WATCH"),
            "insufficient_coverage": sum(1 for x in rows if x["fusion_status"] == "INSUFFICIENT_COVERAGE"),
        },
        "tokens": rows,
    }


def run(data_dir: str | Path = "data") -> dict:
    data = Path(data_dir)
    p = build(data)
    _write(data / OUTPUT.name, p)
    return p


def main() -> None:
    p = run()
    print(json.dumps(p["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
