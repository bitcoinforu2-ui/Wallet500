import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _key(chain: str, token: str) -> str:
    token = token or ""
    if chain in {"ethereum", "bsc"}:
        token = token.lower()
    return f"{chain}:{token}"


def _dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def evaluate(candidate: dict, outcomes: dict, now: datetime | None = None) -> dict:
    """Live survival gate.

    Qualification is immutable audit history. ACTIVE is temporary and must
    continuously survive drawdown, liquidity and reversal checks. Failed
    candidates remain in audit/learning files but are removed from live display.
    """
    now = now or datetime.now(timezone.utc)
    chain = candidate.get("chain")
    token = candidate.get("token") or candidate.get("mint") or ""
    pair_ms = candidate.get("pair_created_at")
    rec = ((outcomes or {}).get("tokens") or {}).get(_key(chain, token), {}) or {}
    history = rec.get("history") if isinstance(rec.get("history"), list) else []

    result = {
        **candidate,
        "fresh_solana_gate": "NOT_APPLICABLE",
        "fresh_solana_reasons": [],
        "pair_age_minutes": None,
        "observation_span_minutes": 0.0,
        "liquidity_retention": None,
        "peak_drawdown_pct": None,
        "current_return_pct": rec.get("current_return_pct"),
    }

    liq = float(candidate.get("liquidity_usd") or 0)
    buys = int(candidate.get("buys_h1") or 0)
    sells = int(candidate.get("sells_h1") or 0)
    tx = buys + sells
    ratio = buys / max(sells, 1)
    h1 = float(candidate.get("price_change_h1") or 0)
    m5 = float(candidate.get("price_change_m5") or 0)
    hard_fail = []
    reasons = []

    # GLOBAL ACTIVE-DISPLAY KILL SWITCHES — all chains, all ages.
    if candidate.get("pump_dump_blocked") or float(candidate.get("pump_dump_risk_score") or 0) >= 70:
        hard_fail.append("PUMP_DUMP_RISK_BLOCKED")
    current_ret = rec.get("current_return_pct")
    if current_ret is not None and float(current_ret) <= -25:
        hard_fail.append("VERIFIED_RETURN_BELOW_MINUS_25PCT")
    peak = float(rec.get("peak_price_usd") or 0)
    cur = float(rec.get("current_price_usd") or candidate.get("price_usd") or 0)
    if peak > 0 and cur > 0:
        dd = (cur / peak - 1.0) * 100.0
        result["peak_drawdown_pct"] = round(dd, 2)
        if dd <= -25:
            hard_fail.append("PEAK_DRAWDOWN_GT_25PCT")
    if h1 >= 100 and m5 <= -15:
        hard_fail.append("PUMP_THEN_SHARP_5M_REVERSAL")
    if liq < 20000:
        hard_fail.append("LIVE_LIQUIDITY_LT_20K")

    if history:
        first, last = history[0], history[-1]
        t0, t1 = _dt(first.get("observed_at")), _dt(last.get("observed_at"))
        if t0 and t1:
            result["observation_span_minutes"] = round(max(0.0, (t1 - t0).total_seconds() / 60.0), 2)
        first_liq = float(first.get("liquidity_usd") or 0)
        cur_liq = float(last.get("liquidity_usd") or liq)
        if first_liq > 0:
            retention = cur_liq / first_liq
            result["liquidity_retention"] = round(retention, 4)
            if retention < 0.70:
                hard_fail.append("LIQUIDITY_RETENTION_LT_70PCT")

    # Determine fresh-Solana age only for the extra launch-survival lane.
    pair_age = None
    if chain == "solana" and pair_ms:
        try:
            pair_dt = datetime.fromtimestamp(float(pair_ms) / 1000.0, tz=timezone.utc)
            pair_age = max(0.0, (now - pair_dt).total_seconds() / 60.0)
            result["pair_age_minutes"] = round(pair_age, 2)
        except Exception:
            pair_age = None

    if pair_age is not None and pair_age < 120:
        if pair_age < 60 and liq < 50000 and tx >= 500 and ratio >= 6.0:
            hard_fail.append("EXTREME_BUY_SKEW_THIN_FRESH_LIQUIDITY")
        if liq < 30000:
            reasons.append("FRESH_SOLANA_LIQUIDITY_LT_30K")
        if pair_age < 45:
            reasons.append("PAIR_AGE_LT_45M")
        if len(history) < 2:
            reasons.append("NEED_2_VERIFIED_OBSERVATIONS")
        if result["observation_span_minutes"] < 10:
            reasons.append("OBSERVATION_SPAN_LT_10M")
        if liq < 30000:
            reasons.append("NEED_LIQUIDITY_GE_30K")
        if ratio < 1.10 and sells >= 50:
            reasons.append("BUYER_PRESSURE_NOT_SURVIVING")

    if hard_fail:
        result["fresh_solana_gate"] = "FAILED"
        result["fresh_solana_reasons"] = list(dict.fromkeys(hard_fail + reasons))
    elif reasons:
        result["fresh_solana_gate"] = "PENDING"
        result["fresh_solana_reasons"] = list(dict.fromkeys(reasons))
    elif pair_age is not None and pair_age < 120:
        result["fresh_solana_gate"] = "ACTIVE"
        result["fresh_solana_reasons"] = ["PASSED_FRESH_SOLANA_SURVIVAL_GATE"]
    else:
        result["fresh_solana_gate"] = "ACTIVE"
        result["fresh_solana_reasons"] = ["PASSED_GLOBAL_LIVE_SURVIVAL_GATE"]
    return result


def apply(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    qualified = _load(out / "qualified-candidates.json", [])
    outcomes = _load(out / "outcome-tracker.json", {})
    watch = _load(out / "watchlist.json", [])
    summary = _load(out / "run-summary.json", {})
    now = datetime.now(timezone.utc)

    evaluations = [evaluate(x, outcomes, now) for x in qualified]
    active = [x for x in evaluations if x.get("fresh_solana_gate") == "ACTIVE"]
    pending = [x for x in evaluations if x.get("fresh_solana_gate") == "PENDING"]
    failed = [x for x in evaluations if x.get("fresh_solana_gate") == "FAILED"]
    active_keys = {(x.get("chain"), x.get("token") or x.get("mint")) for x in active}

    filtered_watch = []
    for x in watch:
        if x.get("watch_source") != "QUALIFIED_ANOMALY":
            filtered_watch.append(x)
            continue
        k = (x.get("chain"), x.get("token") or x.get("mint"))
        if k in active_keys:
            filtered_watch.append(x)

    review = [{**x, "stage": "HISTORICAL_DEEP_SCAN_QUEUED", "queued_at": now.isoformat(), "next_stage": "WALLET_DISCOVERY_FORENSICS"} for x in filtered_watch]

    _write(out / "fresh-solana-survival.json", evaluations)
    _write(out / "fresh-solana-pending.json", pending)
    _write(out / "fresh-solana-failed.json", failed)
    _write(out / "active-qualified-candidates.json", active)
    _write(out / "watchlist.json", filtered_watch)
    _write(out / "historical-review-queue.json", review)

    if isinstance(summary, dict):
        summary["quality_gate_qualified"] = len(qualified)
        summary["active_qualified"] = len(active)
        summary["fresh_solana_pending"] = len(pending)
        summary["fresh_solana_failed"] = len(failed)
        summary["watchlist"] = len(filtered_watch)
        summary["historical_review_queued"] = len(review)
        summary["live_display_policy"] = {
            "max_verified_loss_pct": -25,
            "max_peak_drawdown_pct": -25,
            "min_live_liquidity_usd": 20000,
            "block_pump_then_5m_reversal": True,
            "audit_history_is_never_deleted": True,
        }
        summary["fresh_solana_policy"] = {
            "max_special_lane_age_minutes": 120,
            "min_pair_age_for_active_minutes": 45,
            "min_verified_observation_span_minutes": 10,
            "min_fresh_liquidity_usd": 30000,
            "min_liquidity_retention": 0.70,
            "max_peak_drawdown_pct": -25,
            "extreme_buy_skew_ratio": 6.0,
        }
        _write(out / "run-summary.json", summary)

    result = {
        "quality_gate_qualified": len(qualified),
        "active_qualified": len(active),
        "pending": len(pending),
        "failed_live_survival": len(failed),
        "watchlist": len(filtered_watch),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    apply()
