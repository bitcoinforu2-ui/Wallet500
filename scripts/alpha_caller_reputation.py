from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "data/close-watch-events.json"
REP = ROOT / "data/alpha-caller-reputation.json"
CALLS = ROOT / "data/alpha-caller-call-history.json"
CANDIDATES = ROOT / "data/alpha-caller-candidates.json"
UA = "Wallet500-AlphaCallerReputation/1.3"
HORIZONS_MINUTES = (15, 30, 60, 180, 360, 1440)
RELIABILITY_MATURITY_MINUTES = 30


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_json(url: str, timeout: int = 12):
    try:
        with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def n(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def minutes_between(start, end):
    a, b = dt(start), dt(end)
    if not a or not b:
        return None
    return max(0.0, (b - a).total_seconds() / 60.0)


def median(values):
    xs = sorted(x for x in values if x is not None)
    if not xs:
        return None
    return xs[len(xs) // 2]


def clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(value)))


def normalized_call_key(row: dict):
    source = str(row.get("source") or "").strip().lower()
    caller = str(row.get("caller") or row.get("subject") or "").strip().lower()
    contract = str(row.get("contract") or "").strip().lower()
    called = dt(row.get("called_at") or row.get("event_time"))
    if not source or not caller or not contract or called is None:
        return None
    return source, caller, contract, called.isoformat()


def intake_reliability(candidate_rows: list[dict], verified_calls: list[dict], current_dt=None) -> dict:
    current_dt = current_dt or datetime.now(timezone.utc)
    verified_keys = {
        key for key in (normalized_call_key(x) for x in verified_calls) if key is not None
    }
    groups: dict[tuple[str, str], dict] = {}
    seen: set[tuple] = set()

    for row in candidate_rows:
        if not isinstance(row, dict) or str(row.get("signal_role") or "candidate_discovery") == "confirmation_only":
            continue
        key = normalized_call_key(row)
        if key is None or key in seen:
            continue
        seen.add(key)
        source, caller, _, _ = key
        group = groups.setdefault(
            (source, caller),
            {
                "observed_calls": 0,
                "ever_verified": 0,
                "mature_unverified": 0,
                "pending_unverified": 0,
                "rejection_reasons": {},
            },
        )
        group["observed_calls"] += 1
        is_verified = key in verified_keys or row.get("status") == "GATED_RESEARCH_CANDIDATE"
        if is_verified:
            group["ever_verified"] += 1
            continue

        called = dt(row.get("called_at"))
        age_minutes = (
            max(0.0, (current_dt - called).total_seconds() / 60.0)
            if called is not None
            else RELIABILITY_MATURITY_MINUTES
        )
        if age_minutes < RELIABILITY_MATURITY_MINUTES:
            group["pending_unverified"] += 1
            continue

        group["mature_unverified"] += 1
        for reason in row.get("reasons") or ["UNKNOWN_REJECTION"]:
            reason = str(reason)
            group["rejection_reasons"][reason] = group["rejection_reasons"].get(reason, 0) + 1

    result = {}
    for key, group in groups.items():
        evaluable = group["ever_verified"] + group["mature_unverified"]
        rate = group["ever_verified"] / evaluable if evaluable else None
        bayes = (group["ever_verified"] + 2) / (evaluable + 4) if evaluable else 0.5
        reasons = sorted(
            group["rejection_reasons"].items(), key=lambda item: (-item[1], item[0])
        )[:5]
        result[key] = {
            **group,
            "mature_evaluable_calls": evaluable,
            "ever_verified_rate": None if rate is None else round(rate, 4),
            "bayesian_verification_rate": round(bayes, 4),
            "top_rejection_reasons": [
                {"reason": reason, "count": count} for reason, count in reasons
            ],
        }
    return result


def source_quality_v2(reliability: dict, *, shrunk_early: float, shrunk_5x: float, median_multiple, resolved_count: int) -> dict:
    validation = 100.0 * float(reliability.get("bayesian_verification_rate", 0.5))
    early = 100.0 * float(shrunk_early)
    big_win = 100.0 * float(shrunk_5x)
    med = n(median_multiple)
    median_edge = 0.0 if med is None else clamp((min(2.0, max(1.0, med)) - 1.0) * 100.0)
    raw = 0.45 * validation + 0.30 * early + 0.15 * big_win + 0.10 * median_edge
    evidence_n = max(int(reliability.get("mature_evaluable_calls") or 0), int(resolved_count or 0))
    confidence = min(1.0, evidence_n / 30.0)
    score = 50.0 * (1.0 - confidence) + raw * confidence
    return {
        "source_quality_score_v2": round(clamp(score), 2),
        "source_quality_raw_v2": round(clamp(raw), 2),
        "source_quality_confidence_v2": round(confidence, 4),
        "source_quality_components_v2": {
            "intake_reliability": round(validation, 2),
            "early_2x": round(early, 2),
            "five_x": round(big_win, 2),
            "median_edge": round(median_edge, 2),
        },
    }


def main() -> None:
    bus = json.loads(EVENTS.read_text()) if EVENTS.exists() else {"events": []}
    rep = json.loads(REP.read_text()) if REP.exists() else {"version": 1, "callers": {}, "policy": {}}
    hist = json.loads(CALLS.read_text()) if CALLS.exists() else {"version": 1, "calls": {}}
    candidates_doc = json.loads(CANDIDATES.read_text()) if CANDIDATES.exists() else {"candidates": []}
    callers = {}
    rep["callers"] = callers
    calls = hist.setdefault("calls", {})

    for event in bus.get("events") or []:
        if event.get("kind") != "verified_alpha_caller_call":
            continue
        cid = event.get("canonical_event_id")
        caller = str(event.get("subject") or "UNKNOWN")
        source = str(event.get("source") or "UNKNOWN")
        if cid not in calls:
            calls[cid] = {
                "caller": caller,
                "source": source,
                "symbol": event.get("symbol"),
                "network": event.get("network"),
                "contract": event.get("contract"),
                "pair": event.get("pair"),
                "called_at": event.get("event_time"),
                "entry_price": None,
                "entry_liquidity": event.get("liquidity_usd_at_intake"),
                "peak_price": None,
                "latest_price": None,
                "max_multiple": None,
                "first_2x_at": None,
                "first_5x_at": None,
                "first_10x_at": None,
                "horizon_snapshots": {},
                "status": "TRACKING",
                "last_observed_at": now(),
            }

        call = calls[cid]
        contract = call.get("contract")
        data = get_json("https://api.dexscreener.com/latest/dex/tokens/" + str(contract)) if contract else None
        pairs = (data or {}).get("pairs") or []
        pair = next(
            (
                p
                for p in pairs
                if str(p.get("pairAddress", "")).lower() == str(call.get("pair", "")).lower()
            ),
            None,
        )
        if not pair:
            continue
        price = n(pair.get("priceUsd"))
        if price is None or price <= 0:
            continue
        observed_at = now()
        if call.get("entry_price") is None:
            call["entry_price"] = price
        call["latest_price"] = price
        call["peak_price"] = max(price, n(call.get("peak_price")) or price)
        call["last_observed_at"] = observed_at
        if n(call.get("entry_price")):
            call["max_multiple"] = round(call["peak_price"] / call["entry_price"], 4)
            multiple = n(call.get("max_multiple")) or 0
            if multiple >= 2 and not call.get("first_2x_at"):
                call["first_2x_at"] = observed_at
            if multiple >= 5 and not call.get("first_5x_at"):
                call["first_5x_at"] = observed_at
            if multiple >= 10 and not call.get("first_10x_at"):
                call["first_10x_at"] = observed_at

            # Compare every source message with the forward price path.
            # No extra API request is used: snapshots reuse this observation.
            elapsed = minutes_between(call.get("called_at"), observed_at)
            snapshots = call.setdefault("horizon_snapshots", {})
            if elapsed is not None:
                entry = n(call.get("entry_price"))
                current_multiple = round(price / entry, 4) if entry else None
                observed_peak_multiple = round(call["peak_price"] / entry, 4) if entry else None
                for horizon in HORIZONS_MINUTES:
                    key = f"{horizon}m"
                    if elapsed >= horizon and key not in snapshots:
                        snapshots[key] = {
                            "target_minutes": horizon,
                            "captured_at": observed_at,
                            "actual_elapsed_minutes": round(elapsed, 2),
                            "price": price,
                            "multiple": current_multiple,
                            "observed_peak_multiple": observed_peak_multiple,
                        }

    # Reputation is prospective and descriptive. Marketing claims and historical self-reported wins do not count.
    reliability = intake_reliability(
        [x for x in (candidates_doc.get("candidates") or []) if isinstance(x, dict)],
        [x for x in calls.values() if isinstance(x, dict)],
    )
    grouped = {}
    for call in calls.values():
        grouped.setdefault((call["source"], call["caller"]), []).append(call)
    for source_caller in reliability:
        source_key, caller_key = source_caller
        matching = next(
            (
                (str(x.get("source") or ""), str(x.get("caller") or ""))
                for x in (candidates_doc.get("candidates") or [])
                if isinstance(x, dict)
                and str(x.get("source") or "").strip().lower() == source_key
                and str(x.get("caller") or "").strip().lower() == caller_key
            ),
            (source_key, caller_key),
        )
        grouped.setdefault(matching, [])

    for (source, caller), xs in grouped.items():
        resolved = [x for x in xs if n(x.get("max_multiple")) is not None]
        count = len(resolved)
        hits2 = sum((n(x.get("max_multiple")) or 0) >= 2 for x in resolved)
        hits5 = sum((n(x.get("max_multiple")) or 0) >= 5 for x in resolved)
        hits10 = sum((n(x.get("max_multiple")) or 0) >= 10 for x in resolved)
        mults = [n(x.get("max_multiple")) for x in resolved if n(x.get("max_multiple")) is not None]

        times2 = [minutes_between(x.get("called_at"), x.get("first_2x_at")) for x in resolved if x.get("first_2x_at")]
        times5 = [minutes_between(x.get("called_at"), x.get("first_5x_at")) for x in resolved if x.get("first_5x_at")]
        early2_60 = sum(t is not None and t <= 60 for t in times2)
        early2_180 = sum(t is not None and t <= 180 for t in times2)

        def horizon_values(minutes, field="multiple"):
            key = f"{minutes}m"
            return [
                n((x.get("horizon_snapshots") or {}).get(key, {}).get(field))
                for x in resolved
                if (x.get("horizon_snapshots") or {}).get(key)
            ]

        mult_60 = horizon_values(60)
        mult_180 = horizon_values(180)
        peak_60 = horizon_values(60, "observed_peak_multiple")
        peak_180 = horizon_values(180, "observed_peak_multiple")
        samples_60 = len(mult_60)
        samples_180 = len(mult_180)
        hit_15x_60 = sum((v or 0) >= 1.5 for v in peak_60)
        hit_2x_60 = sum((v or 0) >= 2.0 for v in peak_60)
        hit_2x_180 = sum((v or 0) >= 2.0 for v in peak_180)

        hit5_rate = hits5 / count if count else 0
        early2_rate_60 = early2_60 / count if count else 0
        shrunk_5x = (hits5 + 1) / (count + 4) if count else 0.25
        shrunk_early = (early2_60 + 1) / (count + 4) if count else 0.25
        confidence = min(90, 35 + count * 2) if count >= 5 else min(55, 30 + count * 5)
        strength = min(90, 25 + 45 * shrunk_5x + 20 * shrunk_early)

        reliability_card = reliability.get(
            (str(source).strip().lower(), str(caller).strip().lower()),
            {
                "observed_calls": len(xs),
                "ever_verified": count,
                "mature_unverified": 0,
                "pending_unverified": 0,
                "mature_evaluable_calls": count,
                "ever_verified_rate": 1.0 if count else None,
                "bayesian_verification_rate": (count + 2) / (count + 4) if count else 0.5,
                "top_rejection_reasons": [],
            },
        )
        quality_v2 = source_quality_v2(
            reliability_card,
            shrunk_early=shrunk_early,
            shrunk_5x=shrunk_5x,
            median_multiple=median(mults),
            resolved_count=count,
        )

        key = source + "::" + caller
        callers[key] = {
            "source": source,
            "caller": caller,
            "calls_seen": len(xs),
            "resolved_calls": count,
            "hits_2x": hits2,
            "hits_5x": hits5,
            "hits_10x": hits10,
            "hit_rate_5x": round(hit5_rate, 4),
            "early_2x_within_60m": early2_60,
            "early_2x_within_180m": early2_180,
            "early_hit_rate_2x_60m": round(early2_rate_60, 4),
            "forward_window_samples_60m": samples_60,
            "forward_window_samples_180m": samples_180,
            "hit_rate_1_5x_within_60m": round(hit_15x_60 / samples_60, 4) if samples_60 else None,
            "hit_rate_2x_within_60m": round(hit_2x_60 / samples_60, 4) if samples_60 else None,
            "hit_rate_2x_within_180m": round(hit_2x_180 / samples_180, 4) if samples_180 else None,
            "median_multiple_at_60m": median(mult_60),
            "median_multiple_at_180m": median(mult_180),
            "median_observed_peak_multiple_60m": median(peak_60),
            "median_observed_peak_multiple_180m": median(peak_180),
            "bayesian_hit_rate_5x": round(shrunk_5x, 4),
            "bayesian_early_2x_60m": round(shrunk_early, 4),
            "median_max_multiple": median(mults),
            "median_minutes_to_2x": median(times2),
            "median_minutes_to_5x": median(times5),
            "reputation_strength": round(strength, 1),
            "reputation_confidence": round(confidence, 1),
            "intake_reliability": reliability_card,
            **quality_v2,
            "status": "ESTABLISHED" if count >= 20 else ("EMERGING" if count >= 5 else "UNPROVEN"),
            "updated_at": now(),
        }

    rep["version"] = max(3, int(rep.get("version") or 1))
    rep["policy"] = {
        "forward_only": True,
        "historical_marketing_claims_count": False,
        "early_signal_metric": "Wallet500 first-seen to forward price jumps; scan cadence makes timing approximate",
        "forward_horizons_minutes": list(HORIZONS_MINUTES),
        "forward_window_metrics": [
            "multiple_at_horizon",
            "observed_peak_multiple_by_horizon",
            "1.5x_within_60m",
            "2x_within_60m",
            "2x_within_180m",
        ],
        "automatic_source_weighting": False,
        "historical_third_party_evidence_used_for_source_selection": True,
        "historical_evidence_affects_trade_score": False,
        "aggregator_scores_are_external_metadata_only": True,
        "survivorship_bias_correction": "MATURE_UNVERIFIED_CALLS_COUNT_AGAINST_SOURCE_RELIABILITY; PREVIOUSLY_VERIFIED_CALLS_REMAIN_VERIFIED_IF_MARKET_LATER_DIES",
        "reliability_maturity_minutes": RELIABILITY_MATURITY_MINUTES,
        "source_quality_v2_trade_effect": "RESEARCH_PRIORITY_ONLY",
        "source_quality_v2_formula": "45% intake reliability + 30% early 2x + 15% 5x + 10% capped median edge; confidence shrunk to neutral prior",
        "minimum_status_samples": {"EMERGING": 5, "ESTABLISHED": 20},
    }
    rep["updated_at"] = now()
    hist["version"] = max(3, int(hist.get("version") or 1))
    hist["updated_at"] = now()
    REP.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n")
    CALLS.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "OK", "callers": len(callers), "calls_tracking": len(calls), "forward_only": True}))


if __name__ == "__main__":
    main()
