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
    return f"{chain}:{token or ''}"


def _dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def evaluate(candidate: dict, outcomes: dict, now: datetime | None = None) -> dict:
    """Second-stage gate for very fresh Solana launches.

    The market quality gate may identify a real anomaly, but a fresh Solana
    launch is not promoted to ACTIVE until it survives time and structure
    checks. The qualification event is retained separately for audit/learning.
    """
    now = now or datetime.now(timezone.utc)
    chain = candidate.get("chain")
    token = candidate.get("token") or candidate.get("mint") or ""
    pair_ms = candidate.get("pair_created_at")

    result = {
        **candidate,
        "fresh_solana_gate": "NOT_APPLICABLE",
        "fresh_solana_reasons": [],
        "pair_age_minutes": None,
        "observation_span_minutes": 0.0,
        "liquidity_retention": None,
        "peak_drawdown_pct": None,
    }
    if chain != "solana" or not pair_ms:
        return result

    try:
        pair_dt = datetime.fromtimestamp(float(pair_ms) / 1000.0, tz=timezone.utc)
        pair_age = max(0.0, (now - pair_dt).total_seconds() / 60.0)
    except Exception:
        return result
    result["pair_age_minutes"] = round(pair_age, 2)

    # Established enough to leave the special fresh-launch lane.
    if pair_age >= 120:
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

    # Discovery signal from the BULLDOGE failure: extreme one-sided buying on
    # thin fresh liquidity can be bots/snipers rather than durable demand.
    if pair_age < 60 and liq < 50000 and tx >= 500 and ratio >= 6.0:
        hard_fail.append("EXTREME_BUY_SKEW_THIN_FRESH_LIQUIDITY")

    if liq < 30000:
        reasons.append("FRESH_SOLANA_LIQUIDITY_LT_30K")

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
        result["fresh_solana_gate"] = "FAILED"
        result["fresh_solana_reasons"] = hard_fail + reasons
        return result

    # No fresh launch becomes ACTIVE immediately. Require at least 45 minutes
    # since pair creation and >=10 minutes of our own verified observations.
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

    if reasons:
        result["fresh_solana_gate"] = "PENDING"
        result["fresh_solana_reasons"] = list(dict.fromkeys(reasons))
    else:
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
        gate = x.get("fresh_solana_gate")
        k = (x.get("chain"), x.get("token") or x.get("mint"))
        if gate in {"NOT_APPLICABLE", "ACTIVE"}:
            active.append(x)
            active_keys.add(k)
        elif gate == "PENDING":
            pending.append(x)
        elif gate == "FAILED":
            failed.append(x)

    filtered_watch = []
    for x in watch:
        if x.get("watch_source") != "QUALIFIED_ANOMALY":
            filtered_watch.append(x)
            continue
        k = (x.get("chain"), x.get("token") or x.get("mint"))
        # Only fresh-Solana items require the second-stage active key. Other
        # chains remain governed by the normal quality gate.
        if x.get("chain") != "solana" or k in active_keys:
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
        "fresh_solana_pending": len(pending),
        "fresh_solana_failed": len(failed),
        "watchlist": len(filtered_watch),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    apply()
