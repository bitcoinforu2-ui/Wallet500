from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
OUTPUT = DATA / "decision-engine-v1.json"
LEDGER = DATA / "decision-engine-v1-ledger.json"
MIN_LIQUIDITY_USD = 50_000.0
VERSION = "DECISION_ENGINE_V1_SHADOW"
MAX_LEDGER_EVENTS = 5000


def load_json(path: Path, default):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def key_for(row: dict) -> str:
    chain = str(row.get("chain") or "").lower()
    token = str(row.get("token") or row.get("token_address") or "").lower()
    pair = str(row.get("pair_address") or row.get("locked_pair_address") or "").lower()
    return f"{chain}:{token}:{pair}"


def flag(row: dict, name: str) -> bool:
    return row.get(name) is True


def score_opportunity(row: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    anomaly = num(row.get("anomaly_score"))
    score += clamp((anomaly - 45.0) / 55.0 * 25.0, 0.0, 25.0)
    if anomaly >= 75:
        reasons.append("STRONG_ANOMALY")

    velocity = num(row.get("volume_velocity"))
    score += clamp(velocity / 12.0 * 15.0, 0.0, 15.0)
    if velocity >= 2.0:
        reasons.append("VOLUME_ACCELERATION")

    bsr = num(row.get("buy_sell_ratio"), 1.0)
    score += clamp((bsr - 0.8) / 1.0 * 15.0, 0.0, 15.0)
    if bsr >= 1.2:
        reasons.append("BUYER_PRESSURE")
    elif bsr < 0.9:
        score -= 8.0
        reasons.append("SELLER_PRESSURE")

    turnover = num(row.get("turnover_h1"))
    if 0.15 <= turnover <= 4.0:
        score += clamp(turnover / 1.5 * 15.0, 3.0, 15.0)
        reasons.append("HEALTHY_TURNOVER")
    elif turnover > 4.0:
        score += max(3.0, 12.0 - min(9.0, turnover - 4.0))
        reasons.append("EXTREME_TURNOVER_CAUTION")

    txns = num(row.get("live_activity_h1") or (num(row.get("buys_h1")) + num(row.get("sells_h1"))))
    score += clamp(txns / 500.0 * 10.0, 0.0, 10.0)
    if txns >= 250:
        reasons.append("HIGH_ACTIVITY")

    m5 = num(row.get("price_change_m5"))
    h1 = num(row.get("price_change_h1"))
    if -8.0 <= m5 <= 18.0:
        score += 8.0
    elif 18.0 < m5 <= 35.0:
        score += 4.0
        reasons.append("M5_CHASE_RISK")
    elif m5 > 35.0:
        score -= 8.0
        reasons.append("M5_EXTREME_CHASE")
    if -15.0 <= h1 <= 120.0:
        score += 4.0
    elif h1 > 300.0:
        score -= 8.0
        reasons.append("H1_EXTREME_EXTENSION")

    reality = num(row.get("liquidity_reality_score"))
    score += clamp(reality / 100.0 * 8.0, 0.0, 8.0)

    return round(clamp(score), 2), reasons


def score_survival(row: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    pair = str(row.get("pair_address") or "").lower()
    locked = str(row.get("locked_pair_address") or "").lower()
    if flag(row, "pair_identity_locked") and pair and pair == locked:
        score += 15.0
        reasons.append("EXACT_PAIR_LOCKED")
    else:
        reasons.append("PAIR_IDENTITY_UNVERIFIED")

    gate = str(row.get("live_survival_gate") or "").upper()
    if gate == "ACTIVE":
        score += 20.0
        reasons.append("LIVE_SURVIVAL_ACTIVE")
    else:
        reasons.append("LIVE_SURVIVAL_NOT_ACTIVE")

    liq = num(row.get("production_live_liquidity_usd") or row.get("live_liquidity_usd") or row.get("liquidity_usd"))
    if liq >= 500_000:
        score += 20.0
    elif liq >= 250_000:
        score += 18.0
    elif liq >= 100_000:
        score += 15.0
    elif liq >= MIN_LIQUIDITY_USD:
        score += 10.0
    else:
        reasons.append("SUB_50K_LIQUIDITY")
    if liq >= MIN_LIQUIDITY_USD:
        reasons.append("LIQUIDITY_FLOOR_PASSED")

    retention = num(row.get("production_liquidity_retention_from_peak") or row.get("liquidity_retention"), 0.0)
    if retention >= 0.95:
        score += 15.0
        reasons.append("LIQUIDITY_RETAINED")
    elif retention >= 0.80:
        score += 10.0
    elif retention >= 0.60:
        score += 5.0
        reasons.append("LIQUIDITY_DRAWDOWN")
    elif retention > 0:
        reasons.append("LIQUIDITY_SURVIVAL_WEAK")

    risk = str(row.get("production_risk_gate") or "").upper()
    if risk in {"PASS", "ACTIVE", "CLEAR"}:
        score += 15.0
    elif risk == "CAUTION":
        score += 7.0
        reasons.append("PRODUCTION_CAUTION")
    elif flag(row, "production_risk_blocked"):
        reasons.append("PRODUCTION_RISK_BLOCKED")

    pump = str(row.get("pump_dump_risk_level") or "").upper()
    if pump == "LOW" and not flag(row, "pump_dump_blocked"):
        score += 5.0
    elif flag(row, "pump_dump_blocked"):
        reasons.append("PUMP_DUMP_BLOCKED")

    if flag(row, "lp_removal_protection_verified"):
        score += 5.0
        reasons.append("LP_PROTECTION_VERIFIED")
    else:
        reasons.append("LP_PROTECTION_UNVERIFIED")

    if flag(row, "liquidity_drain_holder_cluster_verified"):
        score += 5.0
        reasons.append("HOLDER_CLUSTER_VERIFIED")
    else:
        reasons.append("HOLDER_CLUSTER_UNVERIFIED")

    return round(clamp(score), 2), reasons


def score_execution(row: dict) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    missing: list[str] = []
    score = 0.0

    liq = num(row.get("tradable_liquidity_usd") or row.get("dex_total_liquidity_usd") or row.get("liquidity_usd"))
    if liq >= 500_000:
        score += 30.0
    elif liq >= 250_000:
        score += 26.0
    elif liq >= 100_000:
        score += 22.0
    elif liq >= MIN_LIQUIDITY_USD:
        score += 16.0
    else:
        reasons.append("EXECUTION_LIQUIDITY_THIN")

    share = num(row.get("tradable_liquidity_share_pct"))
    score += clamp(share / 100.0 * 20.0, 0.0, 20.0)
    if share >= 80:
        reasons.append("MOST_LIQUIDITY_TRADABLE")

    mc_ratio = num(row.get("dex_liquidity_to_market_cap_pct"))
    if mc_ratio >= 10:
        score += 15.0
    elif mc_ratio >= 5:
        score += 12.0
    elif mc_ratio >= 2:
        score += 8.0
    elif mc_ratio > 0:
        score += 3.0
        reasons.append("LOW_LIQUIDITY_TO_MARKET_CAP")

    top_share = num(row.get("top_pool_share_pct"))
    if 0 < top_share <= 70:
        score += 10.0
    elif top_share <= 90:
        score += 7.0
    elif top_share > 90:
        score += 3.0
        reasons.append("TOP_POOL_CONCENTRATION")

    pools = num(row.get("tradable_pool_count"))
    score += clamp(pools / 3.0 * 10.0, 0.0, 10.0)

    depth = str(row.get("execution_depth_status") or "").upper()
    if depth.startswith("VERIFIED") or depth in {"OK", "MEASURED"}:
        score += 15.0
        reasons.append("EXIT_DEPTH_VERIFIED")
    else:
        missing.append("EXECUTABLE_EXIT_DEPTH")
        reasons.append("ROUTER_QUOTE_REQUIRED")

    return round(clamp(score), 2), reasons, missing


def score_timing(row: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 50.0

    m5 = num(row.get("price_change_m5"))
    if -5 <= m5 <= 12:
        score += 20
        reasons.append("ENTRY_NOT_EXTENDED")
    elif 12 < m5 <= 25:
        score += 8
    elif m5 > 25:
        score -= 25
        reasons.append("ENTRY_EXTENDED_M5")
    elif m5 < -15:
        score -= 15
        reasons.append("NEGATIVE_M5_IMPULSE")

    h1 = num(row.get("price_change_h1"))
    if 0 <= h1 <= 100:
        score += 10
    elif 100 < h1 <= 250:
        score += 2
        reasons.append("H1_EXTENSION_CAUTION")
    elif h1 > 250:
        score -= 20
        reasons.append("H1_OVEREXTENDED")

    bsr = num(row.get("buy_sell_ratio"), 1.0)
    if bsr >= 1.2:
        score += 10
    elif bsr < 0.9:
        score -= 15

    dd = num(row.get("live_peak_drawdown_pct") or row.get("peak_drawdown_pct"))
    if dd <= -25:
        score -= 15
        reasons.append("DEEP_DRAWDOWN")
    elif -10 <= dd <= 0:
        score += 5

    return round(clamp(score), 2), reasons


def score_exit_risk(row: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    risk = 0.0

    danger = num(row.get("pre_rug_danger_score"))
    risk += clamp(danger * 12.0, 0.0, 36.0)
    if danger >= 2:
        reasons.append("PRE_RUG_SIGNALS")

    if flag(row, "pre_rug_exit_warning"):
        risk += 35.0
        reasons.append("PRE_RUG_EXIT_WARNING")

    sell_buy = num(row.get("pre_rug_sell_buy_ratio_h1"))
    if sell_buy >= 1.25:
        risk += 20.0
        reasons.append("SELL_FLOW_DOMINANT")
    elif sell_buy >= 0.95:
        risk += 8.0

    retention = num(row.get("production_liquidity_retention_from_peak"), 1.0)
    if retention and retention < 0.60:
        risk += 30.0
        reasons.append("LIQUIDITY_COLLAPSE")
    elif retention and retention < 0.80:
        risk += 15.0
        reasons.append("LIQUIDITY_DRAIN")

    dd = num(row.get("live_peak_drawdown_pct") or row.get("peak_drawdown_pct"))
    if dd <= -40:
        risk += 25.0
        reasons.append("PEAK_DRAWDOWN_SEVERE")
    elif dd <= -20:
        risk += 12.0

    if flag(row, "production_risk_blocked"):
        risk += 40.0
        reasons.append("PRODUCTION_BLOCK")
    if str(row.get("live_survival_gate") or "").upper() not in {"", "ACTIVE"}:
        risk += 35.0
        reasons.append("SURVIVAL_GATE_LOST")

    return round(clamp(risk), 2), reasons


def hard_safety_failures(row: dict) -> list[str]:
    failures: list[str] = []
    pair = str(row.get("pair_address") or "").lower()
    locked = str(row.get("locked_pair_address") or "").lower()
    if not pair or not locked or pair != locked or not flag(row, "pair_identity_locked"):
        failures.append("PAIR_IDENTITY")
    liq = num(row.get("production_live_liquidity_usd") or row.get("live_liquidity_usd") or row.get("liquidity_usd"))
    if liq < MIN_LIQUIDITY_USD:
        failures.append("LIQUIDITY_BELOW_50K")
    if flag(row, "pump_dump_blocked"):
        failures.append("PUMP_DUMP_BLOCK")
    if flag(row, "production_risk_blocked"):
        failures.append("PRODUCTION_RISK_BLOCK")
    if str(row.get("live_survival_gate") or "").upper() not in {"ACTIVE"}:
        failures.append("LIVE_SURVIVAL_INACTIVE")
    return failures


def evidence_gaps(row: dict, execution_missing: list[str]) -> list[str]:
    gaps = list(execution_missing)
    if not flag(row, "lp_removal_protection_verified"):
        gaps.append("LP_REMOVAL_PROTECTION")
    if not flag(row, "liquidity_drain_holder_cluster_verified"):
        gaps.append("HOLDER_CLUSTER")
    return sorted(set(gaps))


def position_keys() -> set[str]:
    ledger = load_json(DATA / "first-eligible-paper-ledger.json", {})
    entries = ledger.get("entries") if isinstance(ledger, dict) else []
    return {key_for(x) for x in (entries or []) if isinstance(x, dict) and key_for(x).strip(":")}


def winner_dna_context() -> dict:
    dna = load_json(DATA / "winner-dna-study.json", {})
    if not isinstance(dna, dict):
        return {"status": "UNAVAILABLE"}
    return {
        "status": dna.get("status") or "UNKNOWN",
        "winner_n": dna.get("winner_n"),
        "control_n": dna.get("control_n"),
        "winner_to_control_median_ratio": dna.get("winner_to_control_median_ratio") or {},
        "affects_decision": False,
    }


def evaluate(row: dict, in_position: bool = False) -> dict:
    opportunity, opp_reasons = score_opportunity(row)
    survival, surv_reasons = score_survival(row)
    execution, exec_reasons, exec_missing = score_execution(row)
    timing, timing_reasons = score_timing(row)
    exit_risk, exit_reasons = score_exit_risk(row)
    hard = hard_safety_failures(row)
    gaps = evidence_gaps(row, exec_missing)

    composite = round(
        0.34 * opportunity
        + 0.31 * survival
        + 0.20 * execution
        + 0.15 * timing,
        2,
    )

    model_signal = "NO_BUY"
    if opportunity >= 78 and survival >= 78 and execution >= 65 and timing >= 65:
        model_signal = "STRONG_BUY"
    elif opportunity >= 68 and survival >= 68 and execution >= 55:
        model_signal = "BUY"
    elif composite >= 58:
        model_signal = "WATCH"

    if in_position:
        if hard or exit_risk >= 75 or survival < 45:
            action, state = "SELL", "SELL"
        elif exit_risk >= 50 or survival < 60:
            action, state = "REDUCE", "PROFIT_PROTECT"
        else:
            action, state = "HOLD", "HOLD"
    else:
        if hard:
            action, state = "REJECT", "REJECTED"
        elif gaps:
            action, state = "RESEARCH", "RESEARCH"
        elif model_signal in {"STRONG_BUY", "BUY"} and composite >= 70:
            action, state = "BUY", "BUY_ZONE"
        elif composite >= 58:
            action, state = "WATCH", "WATCH"
        else:
            action, state = "RESEARCH", "RESEARCH"

    confidence = min(100.0, composite)
    if gaps:
        confidence = min(confidence, 69.0)
    if hard:
        confidence = min(confidence, 35.0)

    return {
        "key": key_for(row),
        "chain": row.get("chain"),
        "token": row.get("token"),
        "symbol": row.get("base_token_symbol") or row.get("symbol"),
        "pair_address": row.get("pair_address"),
        "in_shadow_position": bool(in_position),
        "scores": {
            "opportunity": opportunity,
            "survival": survival,
            "execution": execution,
            "timing": timing,
            "exit_risk": exit_risk,
            "composite": composite,
            "confidence": round(confidence, 2),
        },
        "model_signal": model_signal,
        "recommended_action": action,
        "state": state,
        "hard_safety_failures": hard,
        "evidence_gaps": gaps,
        "why": {
            "opportunity": opp_reasons,
            "survival": surv_reasons,
            "execution": exec_reasons,
            "timing": timing_reasons,
            "exit": exit_reasons,
        },
        "market": {
            "price_usd": row.get("price_usd"),
            "liquidity_usd": row.get("production_live_liquidity_usd") or row.get("live_liquidity_usd") or row.get("liquidity_usd"),
            "tradable_liquidity_usd": row.get("tradable_liquidity_usd"),
            "liquidity_to_market_cap_pct": row.get("dex_liquidity_to_market_cap_pct"),
            "volume_h1": row.get("live_volume_h1") or row.get("volume_h1"),
            "buy_sell_ratio": row.get("buy_sell_ratio"),
            "price_change_m5": row.get("price_change_m5"),
            "price_change_h1": row.get("price_change_h1"),
            "live_return_pct": row.get("live_current_return_pct"),
        },
    }


def transition_events(previous: dict, decisions: list[dict], now_iso: str) -> list[dict]:
    old_rows = previous.get("decisions") if isinstance(previous, dict) else []
    old_map = {x.get("key"): x for x in (old_rows or []) if isinstance(x, dict) and x.get("key")}
    events = []
    for d in decisions:
        old = old_map.get(d["key"])
        if not old:
            events.append({
                "at": now_iso,
                "key": d["key"],
                "from_state": None,
                "to_state": d["state"],
                "action": d["recommended_action"],
                "scores": d["scores"],
            })
            continue
        if old.get("state") != d.get("state") or old.get("recommended_action") != d.get("recommended_action"):
            events.append({
                "at": now_iso,
                "key": d["key"],
                "from_state": old.get("state"),
                "to_state": d["state"],
                "action": d["recommended_action"],
                "scores": d["scores"],
            })
    return events


def run(output_dir: str = "data") -> dict:
    global DATA, OUTPUT, LEDGER
    DATA = Path(output_dir)
    OUTPUT = DATA / "decision-engine-v1.json"
    LEDGER = DATA / "decision-engine-v1-ledger.json"
    DATA.mkdir(parents=True, exist_ok=True)

    active = load_json(DATA / "active-qualified-candidates.json", [])
    if not isinstance(active, list):
        active = []

    positions = position_keys()
    previous = load_json(OUTPUT, {})
    now = datetime.now(timezone.utc).isoformat()

    decisions = [evaluate(row, key_for(row) in positions) for row in active if isinstance(row, dict)]
    priority = {"SELL": 0, "REDUCE": 1, "BUY": 2, "HOLD": 3, "WATCH": 4, "RESEARCH": 5, "REJECT": 6}
    decisions.sort(key=lambda x: (priority.get(x["recommended_action"], 9), -num((x.get("scores") or {}).get("confidence"))))

    events = transition_events(previous, decisions, now)
    ledger = load_json(LEDGER, {"events": []})
    old_events = ledger.get("events") if isinstance(ledger, dict) else []
    all_events = (old_events or []) + events
    if len(all_events) > MAX_LEDGER_EVENTS:
        all_events = all_events[-MAX_LEDGER_EVENTS:]

    counts: dict[str, int] = {}
    for d in decisions:
        counts[d["recommended_action"]] = counts.get(d["recommended_action"], 0) + 1

    payload = {
        "version": VERSION,
        "generated_at": now,
        "mode": "SHADOW_DECISION_ONLY_NO_REAL_MONEY_NO_PRODUCTION_GATE_CHANGE",
        "production_change": False,
        "minimum_liquidity_usd": MIN_LIQUIDITY_USD,
        "truth_contract": {
            "exact_pair_required": True,
            "liquidity_floor_required": True,
            "holder_cluster_fail_closed_for_buy": True,
            "lp_protection_fail_closed_for_buy": True,
            "executable_exit_depth_fail_closed_for_buy": True,
            "no_hindsight": True,
            "real_money_execution": False,
        },
        "learning": {
            "mode": "OBSERVE_AND_VALIDATE_ONLY",
            "winner_dna": winner_dna_context(),
            "auto_weight_changes": False,
            "minimum_rule": "No automatic scoring-weight promotion without prospective evidence and explicit production approval.",
        },
        "summary": {
            "active_candidates": len(decisions),
            "counts": counts,
            "transition_events": len(events),
            "open_shadow_positions_present_in_active_set": sum(1 for d in decisions if d["in_shadow_position"]),
        },
        "decisions": decisions,
    }

    ledger_payload = {
        "version": "DECISION_ENGINE_V1_TRANSITION_LEDGER",
        "generated_at": now,
        "production_change": False,
        "events": all_events,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LEDGER.write_text(json.dumps(ledger_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return payload


def main():
    run()


if __name__ == "__main__":
    main()
