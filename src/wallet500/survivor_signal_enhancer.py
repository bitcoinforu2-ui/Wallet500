from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
STATE = DATA / "survivor-signal-enhancer-state.json"
FORWARD = DATA / "survivor-forward-validation.json"
MAX_HISTORY = 6
HORIZONS_H = (1, 3, 6, 12, 24)


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def pct_delta(now, prev):
    a, b = f(now), f(prev)
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1.0) * 100.0, 3)


def utcnow():
    return datetime.now(timezone.utc)


def parse_dt(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def history_point(row, observed_at):
    return {
        "observed_at": observed_at,
        "price_usd": f(row.get("price_usd")),
        "liquidity_usd": f(row.get("liquidity_usd")),
        "volume_h1_usd": f(row.get("volume_h1_usd")),
        "turnover_h1": f(row.get("turnover_h1")),
        "buy_sell_ratio_h1": f(row.get("buy_sell_ratio_h1")),
        "price_change_h1_pct": f(row.get("price_change_h1_pct")),
        "winner_dna_match": row.get("winner_dna_match"),
        "wave_status": row.get("wave_status"),
        "wave_score": f(row.get("wave_score")),
    }


def persistence(history):
    recent = history[-3:]
    levels = [x.get("winner_dna_match") for x in recent]
    active = sum(x in {"MEDIUM", "HIGH"} for x in levels)
    high = sum(x == "HIGH" for x in levels)
    score = min(100, active * 25 + high * 15)
    if len(recent) < 2:
        status = "INSUFFICIENT_HISTORY"
    elif high >= 2:
        status = "PERSISTENT_HIGH"
    elif active >= 2:
        status = "PERSISTENT_DNA"
    else:
        status = "TRANSIENT"
    return score, status


def acceleration(history):
    if len(history) < 2:
        return {"status": "INSUFFICIENT_HISTORY", "score": 0}
    a, b = history[-2], history[-1]
    td = pct_delta(b.get("turnover_h1"), a.get("turnover_h1"))
    vd = pct_delta(b.get("volume_h1_usd"), a.get("volume_h1_usd"))
    bd = pct_delta(b.get("buy_sell_ratio_h1"), a.get("buy_sell_ratio_h1"))
    ld = pct_delta(b.get("liquidity_usd"), a.get("liquidity_usd"))
    score = 0
    reasons = []
    if td is not None and td >= 20: score += 30; reasons.append("TURNOVER_ACCEL")
    if vd is not None and vd >= 20: score += 25; reasons.append("VOLUME_ACCEL")
    if bd is not None and bd >= 10: score += 20; reasons.append("BUY_PRESSURE_ACCEL")
    if ld is not None and ld >= -5: score += 15; reasons.append("LIQUIDITY_SURVIVES")
    if f(b.get("price_change_h1_pct")) is not None and f(b.get("price_change_h1_pct")) <= 5:
        score += 10; reasons.append("PRICE_NOT_EXTENDED")
    return {"status": "ACCELERATING" if score >= 50 else "MIXED", "score": min(score, 100),
            "turnover_delta_pct": td, "volume_h1_delta_pct": vd, "buy_ratio_delta_pct": bd,
            "liquidity_delta_pct": ld, "reasons": reasons}


def absorption(row, accel):
    turnover = f(row.get("turnover_h1"))
    ratio = f(row.get("buy_sell_ratio_h1"))
    p1 = f(row.get("price_change_h1_pct"))
    liq = f(row.get("liquidity_usd"))
    if None in (turnover, ratio, p1, liq):
        return {"status": "INSUFFICIENT_COVERAGE", "score": 0, "reasons": []}
    score = 0; reasons = []
    if turnover >= 0.25: score += 25; reasons.append("ACTIVE_TURNOVER")
    if ratio >= 1.25: score += 25; reasons.append("BUY_PRESSURE")
    if p1 <= 5: score += 20; reasons.append("PRICE_NOT_EXTENDED")
    if p1 <= 0: score += 10; reasons.append("PRICE_FLAT_OR_NEGATIVE")
    if accel.get("liquidity_delta_pct") is None or accel.get("liquidity_delta_pct") >= -5:
        score += 10; reasons.append("LIQUIDITY_SURVIVAL")
    if accel.get("status") == "ACCELERATING": score += 10; reasons.append("ACTIVITY_ACCELERATING")
    status = "ABSORPTION_STRONG" if score >= 75 else "ABSORPTION_WATCH" if score >= 55 else "NO_ABSORPTION_SIGNAL"
    return {"status": status, "score": min(score, 100), "reasons": reasons}


def prehigh(row, accel, absorb, persistence_score):
    turnover = f(row.get("turnover_h1"))
    ratio = f(row.get("buy_sell_ratio_h1"))
    wave = f(row.get("wave_score")) or 0
    distance = {
        "turnover_to_high": round(max(0.0, 0.75 - turnover), 4) if turnover is not None else None,
        "buy_ratio_to_high": round(max(0.0, 1.25 - ratio), 4) if ratio is not None else None,
    }
    score = 0; reasons = []
    if turnover is not None:
        if turnover >= 0.75: score += 30; reasons.append("TURNOVER_HIGH_READY")
        elif turnover >= 0.50: score += 22; reasons.append("TURNOVER_NEAR_HIGH")
        elif turnover >= 0.25: score += 12; reasons.append("TURNOVER_ACTIVE")
    if ratio is not None:
        if ratio >= 1.25: score += 25; reasons.append("BUY_RATIO_HIGH_READY")
        elif ratio >= 1.10: score += 15; reasons.append("BUY_RATIO_NEAR_HIGH")
    score += min(15, int((accel.get("score") or 0) * 0.15))
    score += min(15, int((absorb.get("score") or 0) * 0.15))
    score += min(10, int(persistence_score * 0.10))
    if wave >= 40: score += 5; reasons.append("WAVE_ACTIVE")
    score = min(score, 100)
    if row.get("winner_dna_match") == "HIGH": stage = "CONFIRMED_WAVE" if row.get("wave_status") == "WAVE_BUILDING" else "DNA_HIGH"
    elif score >= 70: stage = "PRE_WAVE"
    elif score >= 50: stage = "PRE_HIGH_WATCH"
    else: stage = "BASELINE"
    return {"stage": stage, "score": score, "distance_to_high": distance, "reasons": reasons}


def update_forward(forward, row, observed_at):
    key = f"{str(row.get('chain')).lower()}:{str(row.get('token')).lower()}:{str(row.get('pair_address')).lower()}"
    events = forward.setdefault("events", {})
    level = row.get("winner_dna_match")
    if level not in {"MEDIUM", "HIGH"}:
        return
    event = events.get(key)
    if not event:
        event = events[key] = {"t0": observed_at, "chain": row.get("chain"), "token": row.get("token"),
            "pair_address": row.get("pair_address"), "t0_level": level, "t0_price_usd": f(row.get("price_usd")),
            "t0_liquidity_usd": f(row.get("liquidity_usd")), "horizons": {}}
    t0 = parse_dt(event.get("t0")); now = parse_dt(observed_at)
    if not t0 or not now: return
    elapsed = (now - t0).total_seconds() / 3600
    p0, p = f(event.get("t0_price_usd")), f(row.get("price_usd"))
    l0, l = f(event.get("t0_liquidity_usd")), f(row.get("liquidity_usd"))
    for h in HORIZONS_H:
        if elapsed >= h and str(h) not in event["horizons"]:
            event["horizons"][str(h)] = {"observed_at": observed_at, "return_pct": pct_delta(p, p0),
                "liquidity_delta_pct": pct_delta(l, l0), "liquidity_survived": bool(l is not None and l >= 50000),
                "dna_level": level, "wave_status": row.get("wave_status")}


def main():
    watch = load(WATCH, {})
    state = load(STATE, {"tokens": {}})
    forward = load(FORWARD, {"version": 1, "events": {}})
    observed_at = watch.get("generated_at") or utcnow().isoformat()
    state_tokens = state.setdefault("tokens", {})
    stage_counts = {}
    for row in watch.get("tokens") or []:
        key = f"{str(row.get('chain')).lower()}:{str(row.get('token')).lower()}:{str(row.get('pair_address')).lower()}"
        old = state_tokens.get(key, {})
        hist = list(old.get("history") or [])
        hist.append(history_point(row, observed_at))
        hist = hist[-MAX_HISTORY:]
        pscore, pstatus = persistence(hist)
        accel = acceleration(hist)
        absorb = absorption(row, accel)
        pre = prehigh(row, accel, absorb, pscore)
        row["dna_persistence_score"] = pscore
        row["dna_persistence_status"] = pstatus
        row["acceleration"] = accel
        row["absorption"] = absorb
        row["pre_high"] = pre
        row["research_stage"] = pre["stage"]
        row["research_confidence"] = pre["score"]
        row["sequence_dna_v2"] = {
            "status": "SEQUENCE_FORMING" if accel.get("score", 0) >= 50 and (absorb.get("score", 0) >= 55 or pscore >= 50) else "NO_CONFIRMED_SEQUENCE",
            "pattern": [x for x in ["TURNOVER_ACCEL" if "TURNOVER_ACCEL" in accel.get("reasons", []) else None,
                "BUY_PRESSURE" if f(row.get("buy_sell_ratio_h1")) is not None and f(row.get("buy_sell_ratio_h1")) >= 1.25 else None,
                "LIQUIDITY_SURVIVAL" if "LIQUIDITY_SURVIVES" in accel.get("reasons", []) else None,
                "ABSORPTION" if absorb.get("score", 0) >= 55 else None] if x],
        }
        stage_counts[pre["stage"]] = stage_counts.get(pre["stage"], 0) + 1
        state_tokens[key] = {"history": hist, "last_stage": pre["stage"], "last_confidence": pre["score"]}
        update_forward(forward, row, observed_at)
    watch["research_layers"] = {
        "version": "WINNER_DNA_RESEARCH_V2",
        "production_gates_changed": False,
        "history_snapshots": MAX_HISTORY,
        "features": ["DNA_PERSISTENCE", "ACCELERATION", "ABSORPTION", "PRE_HIGH", "FORWARD_VALIDATION", "SEQUENCE_DNA_V2"],
        "stage_counts": stage_counts,
        "note": "Shadow research only. No production gate or automatic BUY is changed."
    }
    state["generated_at"] = observed_at
    forward["updated_at"] = observed_at
    dump(WATCH, watch); dump(STATE, state); dump(FORWARD, forward)
    print(json.dumps({"enhanced": len(watch.get("tokens") or []), "stage_counts": stage_counts, "production_gates_changed": False}))


if __name__ == "__main__":
    main()
