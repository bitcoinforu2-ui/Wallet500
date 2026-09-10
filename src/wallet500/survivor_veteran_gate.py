from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
HOT_HEALTHY = DATA / "hot-healthy-radar.json"
VETERAN_MIN_DAYS = 90.0


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def norm(value) -> str:
    return str(value or "").lower()


def token_of(row: dict) -> str:
    return str(row.get("token") or row.get("token_address") or row.get("mint") or row.get("address") or "")


def pair_of(row: dict) -> str:
    return str(row.get("pair_address") or row.get("exact_pair") or row.get("pair") or "")


def identity_key(row: dict) -> str:
    token = token_of(row)
    pair = pair_of(row)
    if not token or not pair:
        return ""
    return f"{norm(token)}|{norm(pair)}"


def _radar_rows(radar: dict):
    """Yield every top-level radar row without using its scoring bucket as age truth."""
    for bucket, values in radar.items():
        if not isinstance(values, list):
            continue
        for row in values:
            if isinstance(row, dict):
                yield bucket, row


def age_truth_index() -> tuple[dict, dict]:
    radar = load(HOT_HEALTHY, {})
    verified: dict[str, dict] = {}
    under_90: dict[str, dict] = {}

    # Age is an identity fact, not a HOT/HEALTHY score. A row may be quarantined
    # for liquidity/momentum/other reasons while still carrying valid veteran age
    # evidence. Preserve exact token+pair identity so no pool can inherit age truth.
    for bucket, row in _radar_rows(radar):
        key = identity_key(row)
        if not key:
            continue
        try:
            age = float(row.get("market_age_days"))
        except (TypeError, ValueError):
            age = None

        exact_pair_verified = (
            row.get("live_token_identity_verified") is True
            or row.get("exact_pair_verified") is True
            or "LIVE_EXACT_PAIR_REVERIFIED" in (row.get("reasons") or [])
        )
        age_verified = (
            row.get("veteran_age_verified") is True
            or row.get("market_age_verified") is True
            or "VETERAN_AGE_VERIFIED" in (row.get("reasons") or [])
        )

        if exact_pair_verified and age_verified and age is not None and age >= VETERAN_MIN_DAYS:
            current = verified.get(key)
            if current is None or age > float(current.get("market_age_days") or 0):
                verified[key] = {
                    "market_age_days": age,
                    "source": "HOT_HEALTHY_V3_EXACT_PAIR_VETERAN_TRUTH",
                    "source_bucket": bucket,
                }

        reason = str(row.get("reason") or "")
        reasons = {str(x) for x in (row.get("reasons") or [])}
        under_age = reason in {"UNDER_90D_MARKET_AGE", "UNDER_180D_MARKET_AGE"} or bool(
            reasons.intersection({"UNDER_90D_MARKET_AGE", "UNDER_180D_MARKET_AGE"})
        )
        if exact_pair_verified and under_age and (age is None or age < VETERAN_MIN_DAYS):
            under_90[key] = {
                "source": "HOT_HEALTHY_V3_EXACT_PAIR_VETERAN_TRUTH",
                "source_bucket": bucket,
                "reason": "UNDER_90D_MARKET_AGE",
            }

    return verified, under_90


def main() -> None:
    watch = load(WATCH, {})
    if not watch:
        raise SystemExit("SURVIVOR_WATCH_OUTPUT_MISSING")

    verified, under_90 = age_truth_index()
    actionable_high = 0
    actionable_medium = 0
    suppressed = []
    eligibility: dict[str, bool] = {}

    for row in watch.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        token = token_of(row)
        key = identity_key(row)
        token_key = norm(token)
        evidence = verified.get(key)
        under = under_90.get(key)

        if evidence:
            row["veteran_alert_eligible"] = True
            row["veteran_age_status"] = "VERIFIED_90D_PLUS"
            row["market_age_days_verified"] = evidence.get("market_age_days")
            row["veteran_age_source"] = evidence.get("source")
            row["veteran_age_source_bucket"] = evidence.get("source_bucket")
            row["veteran_pair_identity_match"] = True
        elif under:
            row["veteran_alert_eligible"] = False
            row["veteran_age_status"] = "UNDER_90D_BLOCKED"
            row["market_age_days_verified"] = None
            row["veteran_age_source"] = under.get("source")
            row["veteran_age_source_bucket"] = under.get("source_bucket")
            row["veteran_pair_identity_match"] = True
        else:
            row["veteran_alert_eligible"] = False
            row["veteran_age_status"] = "VETERAN_AGE_UNVERIFIED_FAIL_CLOSED"
            row["market_age_days_verified"] = None
            row["veteran_age_source"] = None
            row["veteran_age_source_bucket"] = None
            row["veteran_pair_identity_match"] = False

        eligibility[token_key] = bool(row["veteran_alert_eligible"])
        dna = str(row.get("winner_dna_match") or "LOW")
        if row["veteran_alert_eligible"]:
            if dna == "HIGH":
                actionable_high += 1
            elif dna == "MEDIUM":
                actionable_medium += 1
        elif dna in {"HIGH", "MEDIUM"}:
            suppressed.append({
                "token": token,
                "pair_address": pair_of(row),
                "chain": row.get("chain"),
                "dna": dna,
                "wave_status": row.get("wave_status"),
                "reason": row["veteran_age_status"],
            })

    raw_events = watch.get("telegram_events") or []
    watch["telegram_events_raw_research"] = raw_events
    watch["telegram_events"] = [
        event for event in raw_events
        if isinstance(event, dict) and eligibility.get(norm(event.get("token")), False)
    ]
    watch["veteran_truth_contract"] = {
        "focus": "VETERAN_COIN_REVIVAL_ONLY",
        "minimum_market_age_days": VETERAN_MIN_DAYS,
        "age_verification_required_for_alert": True,
        "identity_scope": "EXACT_TOKEN_PLUS_EXACT_PAIR_NO_POOL_MIXING",
        "age_truth_independent_of_radar_score_bucket": True,
        "unknown_age_policy": "FAIL_CLOSED_NO_ALERT",
        "historical_young_winner_policy": "RESEARCH_ONLY_MAY_REMAIN_IN_COHORT_NEVER_ACTIONABLE",
    }
    watch["veteran_age_verified_exact_pair_n"] = sum(1 for x in (watch.get("tokens") or []) if isinstance(x, dict) and x.get("veteran_age_status") == "VERIFIED_90D_PLUS")
    watch["actionable_veteran_dna_high_n"] = actionable_high
    watch["actionable_veteran_dna_medium_n"] = actionable_medium
    watch["actionable_veteran_signal_n"] = actionable_high + actionable_medium
    watch["suppressed_non_veteran_or_unverified_signal_n"] = len(suppressed)
    watch["suppressed_signals"] = suppressed[:50]
    watch["note"] = (
        "Winner-DNA cohort remains research-only. Veteran age truth is propagated independently of HOT/HEALTHY "
        "score bucket and only on exact token+pair identity. Telegram/actionable counts remain fail-closed to "
        "verified market age >=90 days."
    )

    WATCH.write_text(json.dumps(watch, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "verified_exact_pair_veteran_n": watch["veteran_age_verified_exact_pair_n"],
        "actionable_veteran_dna_high_n": actionable_high,
        "actionable_veteran_dna_medium_n": actionable_medium,
        "suppressed": len(suppressed),
    }, indent=2))


if __name__ == "__main__":
    main()
