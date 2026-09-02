import json
from datetime import datetime, timezone
from pathlib import Path

MIN_LIVE_LIQUIDITY_USD = 50_000.0
FRESH_PAIR_WINDOW_MINUTES = 120.0
MIN_PAIR_AGE_FOR_ACTIVE_MINUTES = 45.0
MIN_VERIFIED_OBSERVATION_SPAN_MINUTES = 10.0


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


def _verified_survival(candidate: dict, outcomes: dict) -> tuple[bool, list[str], dict]:
    """Universal ACTIVE-board survival gate for every chain.

    Qualification is immutable history. ACTIVE requires current tradable market
    structure, including Wallet500's hard $50K live-liquidity floor.
    """
    chain = candidate.get("chain")
    token = candidate.get("token") or candidate.get("mint") or ""
    rec = ((outcomes or {}).get("tokens") or {}).get(_key(chain, token), {}) or {}
    reasons = []

    liq = float(candidate.get("liquidity_usd") or 0)
    vol = float(candidate.get("volume_h1") or 0)
    buys = int(candidate.get("buys_h1") or 0)
    sells = int(candidate.get("sells_h1") or 0)
    tx = buys + sells
    m5 = float(candidate.get("price_change_m5") or 0)
    h1 = float(candidate.get("price_change_h1") or 0)

    current_return = rec.get("current_return_pct")
    try:
        current_return = float(current_return) if current_return is not None else None
    except Exception:
        current_return = None

    peak = float(rec.get("peak_price_usd") or 0)
    cur = float(rec.get("current_price_usd") or candidate.get("price_usd") or 0)
    peak_dd = ((cur / peak - 1.0) * 100.0) if peak > 0 and cur > 0 else None

    if current_return is not None and current_return <= -25:
        reasons.append("VERIFIED_RETURN_BELOW_MINUS_25PCT")
    if peak_dd is not None and peak_dd <= -25:
        reasons.append("VERIFIED_PEAK_DRAWDOWN_BELOW_MINUS_25PCT")
    if liq < MIN_LIVE_LIQUIDITY_USD:
        reasons.append("CURRENT_LIQUIDITY_BELOW_50K")
    if vol < 15000:
        reasons.append("CURRENT_VOLUME_1H_BELOW_15K")
    if tx < 50:
        reasons.append("CURRENT_ACTIVITY_BELOW_50_TX_1H")
    if h1 > 120 and m5 <= -15:
        reasons.append("PUMP_THEN_FAST_REVERSAL")
    if h1 > 400 and m5 < 0:
        reasons.append("PARABOLIC_MOVE_ALREADY_REVERSING")

    metrics = {
        "live_current_return_pct": current_return,
        "live_peak_drawdown_pct": round(peak_dd, 2) if peak_dd is not None else None,
        "live_liquidity_usd": liq,
        "live_volume_h1": vol,
        "live_activity_h1": tx,
    }
    return not reasons, reasons, metrics


def evaluate(candidate: dict, outcomes: dict, now: datetime | None = None) -> dict:
    """Universal survival gate plus universal fresh-pair confirmation.

    The old implementation applied the age/observation hold only to Solana.
    That allowed a brand-new BSC/EVM pair to become ACTIVE on its first spike.
    Freshness confirmation is now chain-agnostic. Solana keeps its additional
    extreme-buy-skew rule, but every chain must survive the same 45m/10m hold.
    """
    now = now or datetime.now(timezone.utc)
    chain = candidate.get("chain")
    token = candidate.get("token") or candidate.get("mint") or ""
    pair_ms = candidate.get("pair_created_at")

    survives, live_reasons, metrics = _verified_survival(candidate, outcomes)
    result = {
        **candidate,
        **metrics,
        "live_survival_gate": "ACTIVE" if survives else "FAILED",
        "live_survival_reasons": ["PASSED_UNIVERSAL_LIVE_SURVIVAL_GATE"] if survives else live_reasons,
        "fresh_pair_gate": "NOT_APPLICABLE",
        "fresh_pair_reasons": [],
        "fresh_solana_gate": "NOT_APPLICABLE",
        "fresh_solana_reasons": [],
        "pair_age_minutes": None,
        "observation_span_minutes": 0.0,
        "liquidity_retention": None,
        "peak_drawdown_pct": metrics.get("live_peak_drawdown_pct"),
    }
    if not survives:
        return result

    if not pair_ms:
        return result

    try:
        pair_dt = datetime.fromtimestamp(float(pair_ms) / 1000.0, tz=timezone.utc)
        pair_age = max(0.0, (now - pair_dt).total_seconds() / 60.0)
    except Exception:
        return result
    result["pair_age_minutes"] = round(pair_age, 2)

    if pair_age >= FRESH_PAIR_WINDOW_MINUTES:
        result["fresh_pair_gate"] = "ACTIVE"
        result["fresh_pair_reasons"] = ["PAIR_AGE_GE_120M"]
        if chain == "solana":
            result["fresh_solana_gate"] = "ACTIVE"
            result["fresh_solana_reasons"] = ["PASSED_FRESH_SOLANA_SURVIVAL_GATE"]
        return result

    rec = ((outcomes or {}).get("tokens") or {}).get(_key(chain, token), {}) or {}
    history = rec.get("history") if isinstance(rec.get("history"), list) else []
    reasons = []
    hard_fail = []

    liq = float(candidate.get("liquidity_usd") or 0)
    buys = int(candidate.get("buys_h1") or 0)
    sells = int(candidate.get("sells_h1") or 0)
    tx = buys + sells
    ratio = buys / max(sells, 1)

    # Solana-specific manipulation pattern stays intact; the freshness hold below
    # is universal and protects BSC/Ethereum/new chains as well.
    if chain == "solana" and pair_age < 60 and liq < MIN_LIVE_LIQUIDITY_USD and tx >= 500 and ratio >= 6.0:
        hard_fail.append("EXTREME_BUY_SKEW_THIN_FRESH_LIQUIDITY")

    if history:
        first = history[0]
        last = history[-1]
        t0 = _dt(first.get("observed_at"))
        t1 = _dt(last.get("observed_at"))
        if t0 and t1:
            result["observation_span_minutes"] = round(max(0.0, (t1 - t0).total_seconds() / 60.0), 2)
        first_liq = float(first.get("liquidity_usd") or 0)
        cur_liq = float(last.get("liquidity_usd") or liq)
        if first_liq > 0:
            retention = cur_liq / first_liq
            result["liquidity_retention"] = round(retention, 4)
            if retention < 0.70:
                hard_fail.append("LIQUIDITY_RETENTION_LT_70PCT")

    peak = float(rec.get("peak_price_usd") or 0)
    cur = float(rec.get("current_price_usd") or candidate.get("price_usd") or 0)
    if peak > 0 and cur > 0:
        dd = (cur / peak - 1.0) * 100.0
        result["peak_drawdown_pct"] = round(dd, 2)
        if dd <= -25:
            hard_fail.append("FRESH_PEAK_DRAWDOWN_GT_25PCT")

    if hard_fail:
        result["fresh_pair_gate"] = "FAILED"
        result["fresh_pair_reasons"] = hard_fail + reasons
        if chain == "solana":
            result["fresh_solana_gate"] = "FAILED"
            result["fresh_solana_reasons"] = hard_fail + reasons
        result["live_survival_gate"] = "FAILED"
        result["live_survival_reasons"] = hard_fail + reasons
        return result

    if pair_age < MIN_PAIR_AGE_FOR_ACTIVE_MINUTES:
        reasons.append("PAIR_AGE_LT_45M")
    if len(history) < 2:
        reasons.append("NEED_2_VERIFIED_OBSERVATIONS")
    if result["observation_span_minutes"] < MIN_VERIFIED_OBSERVATION_SPAN_MINUTES:
        reasons.append("OBSERVATION_SPAN_LT_10M")
    if ratio < 1.10 and sells >= 50:
        reasons.append("BUYER_PRESSURE_NOT_SURVIVING")

    if reasons:
        reasons = list(dict.fromkeys(reasons))
        result["fresh_pair_gate"] = "PENDING"
        result["fresh_pair_reasons"] = reasons
        if chain == "solana":
            result["fresh_solana_gate"] = "PENDING"
            result["fresh_solana_reasons"] = reasons
        result["live_survival_gate"] = "PENDING"
        result["live_survival_reasons"] = reasons
    else:
        result["fresh_pair_gate"] = "ACTIVE"
        result["fresh_pair_reasons"] = ["PASSED_UNIVERSAL_FRESH_PAIR_CONFIRMATION"]
        if chain == "solana":
            result["fresh_solana_gate"] = "ACTIVE"
            result["fresh_solana_reasons"] = ["PASSED_FRESH_SOLANA_SURVIVAL_GATE"]
    return result


def apply(output_dir: str = "data") -> dict:
    out = Path(output_dir)
    qualified = _load(out / "qualified-candidates.json", [])
    outcomes = _load(out / "outcome-tracker.json", {})
    watch = _load(out / "watchlist.json", [])
    summary = _load(out / "run-summary.json", {})
    now = datetime.now(timezone.utc)

    evaluations = [evaluate(x, outcomes, now) for x in qualified]
    active_keys = set()
    pending = []
    failed = []
    active = []
    for x in evaluations:
        gate = x.get("live_survival_gate")
        k = (x.get("chain"), (x.get("token") or x.get("mint") or "").lower() if x.get("chain") in {"ethereum", "bsc"} else x.get("token") or x.get("mint"))
        if gate == "ACTIVE":
            active.append(x)
            active_keys.add(k)
        elif gate == "PENDING":
            pending.append(x)
        else:
            failed.append(x)

    filtered_watch = []
    for x in watch:
        if x.get("watch_source") != "QUALIFIED_ANOMALY":
            filtered_watch.append(x)
            continue
        token = x.get("token") or x.get("mint") or ""
        if x.get("chain") in {"ethereum", "bsc"}:
            token = token.lower()
        if (x.get("chain"), token) in active_keys:
            filtered_watch.append(x)

    review = [{**x, "stage": "HISTORICAL_DEEP_SCAN_QUEUED", "queued_at": now.isoformat(), "next_stage": "WALLET_DISCOVERY_FORENSICS"} for x in filtered_watch]

    _write(out / "fresh-solana-survival.json", evaluations)
    _write(out / "fresh-solana-pending.json", [x for x in pending if x.get("chain") == "solana"])
    _write(out / "fresh-solana-failed.json", [x for x in failed if x.get("chain") == "solana"])
    _write(out / "live-survival-pending.json", pending)
    _write(out / "live-survival-failed.json", failed)
    _write(out / "active-qualified-candidates.json", active)
    _write(out / "watchlist.json", filtered_watch)
    _write(out / "historical-review-queue.json", review)

    if isinstance(summary, dict):
        summary["quality_gate_qualified"] = len(qualified)
        summary["active_qualified"] = len(active)
        summary["live_survival_pending"] = len(pending)
        summary["live_survival_failed"] = len(failed)
        summary["fresh_solana_pending"] = len([x for x in pending if x.get("chain") == "solana"])
        summary["fresh_solana_failed"] = len([x for x in failed if x.get("chain") == "solana"])
        summary["watchlist"] = len(filtered_watch)
        summary["historical_review_queued"] = len(review)
        summary["live_survival_policy"] = {
            "max_verified_loss_pct": -25,
            "max_peak_drawdown_pct": -25,
            "min_liquidity_usd": int(MIN_LIVE_LIQUIDITY_USD),
            "min_volume_h1_usd": 15000,
            "min_activity_h1": 50,
            "pump_reversal_h1_pct": 120,
            "pump_reversal_m5_pct": -15,
            "fresh_pair_rule": "ALL_CHAINS_PENDING_UNTIL_45M_AND_10M_VERIFIED_OBSERVATION_SPAN",
        }
        summary["fresh_pair_policy"] = {
            "chains": "ALL",
            "max_special_lane_age_minutes": int(FRESH_PAIR_WINDOW_MINUTES),
            "min_pair_age_for_active_minutes": int(MIN_PAIR_AGE_FOR_ACTIVE_MINUTES),
            "min_verified_observation_span_minutes": int(MIN_VERIFIED_OBSERVATION_SPAN_MINUTES),
            "min_liquidity_usd": int(MIN_LIVE_LIQUIDITY_USD),
            "min_liquidity_retention": 0.70,
            "max_peak_drawdown_pct": -25,
        }
        summary["fresh_solana_policy"] = {
            "max_special_lane_age_minutes": int(FRESH_PAIR_WINDOW_MINUTES),
            "min_pair_age_for_active_minutes": int(MIN_PAIR_AGE_FOR_ACTIVE_MINUTES),
            "min_verified_observation_span_minutes": int(MIN_VERIFIED_OBSERVATION_SPAN_MINUTES),
            "min_fresh_liquidity_usd": int(MIN_LIVE_LIQUIDITY_USD),
            "min_liquidity_retention": 0.70,
            "max_peak_drawdown_pct": -25,
            "extreme_buy_skew_ratio": 6.0,
        }
        _write(out / "run-summary.json", summary)

    result = {
        "quality_gate_qualified": len(qualified),
        "active_qualified": len(active),
        "live_survival_pending": len(pending),
        "live_survival_failed": len(failed),
        "watchlist": len(filtered_watch),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    apply()
