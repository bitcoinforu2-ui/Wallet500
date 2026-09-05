from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
OUT = DATA / "survivor-pre-wave-fusion-v6.json"


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def f(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def clamp(value):
    return max(0, min(100, int(round(value))))


def fusion(row: dict) -> dict:
    pre = f((row.get("pre_high") or {}).get("score")) or f(row.get("research_confidence")) or 0
    accel = f((row.get("acceleration") or {}).get("score")) or 0
    absorb = f((row.get("absorption") or {}).get("score")) or 0
    v3 = row.get("intelligence_v3") or {}
    rel = f((v3.get("relative_anomaly") or {}).get("score")) or 0
    anti = f((v3.get("failure_anti_dna") or {}).get("score")) or 0
    gov = row.get("model_governor_v4") or {}
    governed = f(gov.get("coverage_adjusted_opportunity_score")) or 0
    tx = row.get("wallet_transaction_intelligence_v5") or {}
    tx_score = f((tx.get("wallet_flow_score") or {}).get("score")) or 0
    tx_verified = ((tx.get("flow") or {}).get("coverage") == "VERIFIED_EXACT_PAIR_SWAPS")

    # Market/DNA remains the base. Transaction intelligence can confirm or
    # suppress confidence only when exact-pair swap evidence is verified.
    base = pre * 0.25 + accel * 0.18 + absorb * 0.17 + rel * 0.10 + governed * 0.20
    tx_component = tx_score * 0.10 if tx_verified else 0
    score = base + tx_component - anti * 0.25

    reasons = []
    missing = []
    if pre >= 65: reasons.append("PRE_HIGH_STRUCTURE")
    if accel >= 60: reasons.append("ACTIVITY_ACCELERATION")
    if absorb >= 60: reasons.append("ABSORPTION")
    if rel >= 50: reasons.append("RELATIVE_ANOMALY")
    if governed >= 55: reasons.append("GOVERNED_OPPORTUNITY")
    if tx_verified:
        flow = tx.get("flow") or {}
        if (f(flow.get("net_buy_usd")) or 0) > 0: reasons.append("VERIFIED_NET_CAPITAL_INFLOW")
        if (flow.get("unique_buyers") or 0) >= 8: reasons.append("VERIFIED_MULTI_BUYER_BASE")
        if tx_score >= 45: reasons.append("WALLET_FLOW_CONFIRMATION")
        smart = tx.get("smart_money") or {}
        if smart.get("coverage") == "VERIFIED_WALLET_LABELS_ONLY" and (f(smart.get("smart_money_net_usd")) or 0) > 0:
            reasons.append("VERIFIED_SMART_MONEY_NET_BUY")
        clusters = tx.get("buyer_clusters") or {}
        if clusters.get("coverage") == "VERIFIED_FEED_CLUSTER_LABELS" and (clusters.get("independent_buyer_clusters") or 0) >= 3:
            reasons.append("INDEPENDENT_BUYER_CLUSTERS")
        if (tx.get("wash_risk") or {}).get("status") == "HIGH_RISK":
            score -= 20
            reasons.append("WASH_RISK_SUPPRESSION")
    else:
        missing.extend(["BUY_SELL_USD", "UNIQUE_BUYERS", "WALLET_CLUSTER_FLOW", "SMART_MONEY_FLOW"])

    holder_ok = row.get("holder_delta_since_prior_hourly_snapshot") is not None
    social_ok = row.get("organic_acceleration_score") is not None
    if not holder_ok: missing.append("TIMESTAMP_SAFE_HOLDER_DELTA")
    if not social_ok: missing.append("ORGANIC_SOCIAL_ACCELERATION")

    score = clamp(score)
    independent_confirmations = 0
    if accel >= 60: independent_confirmations += 1
    if (f(row.get("buy_sell_ratio_h1")) or 0) >= 1.25: independent_confirmations += 1
    if tx_verified and tx_score >= 45: independent_confirmations += 1
    if holder_ok and (f(row.get("holder_delta_since_prior_hourly_snapshot")) or 0) > 0: independent_confirmations += 1
    if social_ok and (f(row.get("organic_acceleration_score")) or 0) >= 60: independent_confirmations += 1

    if score >= 78 and tx_verified:
        stage = "PRE_WAVE_CONFIRMED_RESEARCH"
    elif score >= 65:
        stage = "PRE_WAVE_CANDIDATE"
    elif score >= 50:
        stage = "BUILDING_EVIDENCE"
    else:
        stage = "WATCH"

    return {
        "score": score,
        "stage": stage,
        "verified_transaction_layer_active": tx_verified,
        "independent_confirmation_n": independent_confirmations,
        "reasons": reasons,
        "missing_confirmation_layers": missing,
        "components": {
            "pre_high": round(pre, 2),
            "acceleration": round(accel, 2),
            "absorption": round(absorb, 2),
            "relative_anomaly": round(rel, 2),
            "governed_opportunity": round(governed, 2),
            "wallet_flow": round(tx_score, 2) if tx_verified else None,
            "failure_anti_dna": round(anti, 2),
        },
        "probability": None,
        "probability_status": "INSUFFICIENT_SAMPLE",
        "production_effect": False,
    }


def main():
    watch = load(WATCH, {})
    if not watch:
        raise SystemExit("SURVIVOR_WATCH_OUTPUT_MISSING")
    summary = []
    counts = {}
    for row in watch.get("tokens") or []:
        layer = fusion(row)
        row["pre_wave_fusion_v6"] = layer
        counts[layer["stage"]] = counts.get(layer["stage"], 0) + 1
        summary.append({
            "chain": row.get("chain"),
            "token": row.get("token"),
            "pair_address": row.get("pair_address"),
            "score": layer["score"],
            "stage": layer["stage"],
            "verified_transaction_layer_active": layer["verified_transaction_layer_active"],
            "independent_confirmation_n": layer["independent_confirmation_n"],
        })
    watch["pre_wave_fusion_v6"] = {
        "version": "PRE_WAVE_FUSION_V6",
        "research_only": True,
        "production_gates_changed": False,
        "probability_model_enabled": False,
        "stage_counts": counts,
        "policy": "V6 is a shadow fusion layer. Transaction intelligence confirms the research score only with verified exact-pair swaps. Missing wallet/social/holder evidence reduces certainty but is never interpreted as negative evidence.",
    }
    dump(WATCH, watch)
    dump(OUT, {
        "version": 6,
        "generated_at": watch.get("generated_at"),
        "research_only": True,
        "production_gates_changed": False,
        "probability_model_enabled": False,
        "stage_counts": counts,
        "tokens": summary,
    })
    print(json.dumps({"fusion_v6_tokens": len(summary), "stage_counts": counts, "production_gates_changed": False}))


if __name__ == "__main__":
    main()
