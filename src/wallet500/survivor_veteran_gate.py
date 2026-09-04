from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data")
WATCH = DATA / "survivor-wave-watch.json"
HOT_HEALTHY = DATA / "hot-healthy-radar.json"
VETERAN_MIN_DAYS = 180.0


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def norm(value) -> str:
    return str(value or "").lower()


def token_of(row: dict) -> str:
    return str(row.get("token") or row.get("token_address") or row.get("mint") or row.get("address") or "")


def age_truth_index() -> tuple[dict, dict]:
    radar = load(HOT_HEALTHY, {})
    verified: dict[str, dict] = {}
    under_180: dict[str, dict] = {}

    for bucket in ("hot_healthy", "healthy_watch"):
        for row in radar.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            token = token_of(row)
            if not token:
                continue
            try:
                age = float(row.get("market_age_days"))
            except (TypeError, ValueError):
                continue
            if row.get("veteran_age_verified") is True and age >= VETERAN_MIN_DAYS:
                verified[norm(token)] = {
                    "market_age_days": age,
                    "source": "HOT_HEALTHY_V3_LIVE_VETERAN_TRUTH",
                }

    for row in radar.get("quarantined_fail_closed") or []:
        if not isinstance(row, dict) or row.get("reason") != "UNDER_180D_MARKET_AGE":
            continue
        token = token_of(row)
        if token:
            under_180[norm(token)] = {
                "source": "HOT_HEALTHY_V3_LIVE_VETERAN_TRUTH",
                "reason": "UNDER_180D_MARKET_AGE",
            }

    return verified, under_180


def main() -> None:
    watch = load(WATCH, {})
    if not watch:
        raise SystemExit("SURVIVOR_WATCH_OUTPUT_MISSING")

    verified, under_180 = age_truth_index()
    actionable_high = 0
    actionable_medium = 0
    suppressed = []
    eligibility: dict[str, bool] = {}

    for row in watch.get("tokens") or []:
        if not isinstance(row, dict):
            continue
        token = token_of(row)
        key = norm(token)
        if key in verified:
            row["veteran_alert_eligible"] = True
            row["veteran_age_status"] = "VERIFIED_180D_PLUS"
            row["market_age_days_verified"] = verified[key].get("market_age_days")
        elif key in under_180:
            row["veteran_alert_eligible"] = False
            row["veteran_age_status"] = "UNDER_180D_BLOCKED"
            row["market_age_days_verified"] = None
        else:
            row["veteran_alert_eligible"] = False
            row["veteran_age_status"] = "VETERAN_AGE_UNVERIFIED_FAIL_CLOSED"
            row["market_age_days_verified"] = None

        eligibility[key] = bool(row["veteran_alert_eligible"])
        dna = str(row.get("winner_dna_match") or "LOW")
        if row["veteran_alert_eligible"]:
            if dna == "HIGH":
                actionable_high += 1
            elif dna == "MEDIUM":
                actionable_medium += 1
        elif dna in {"HIGH", "MEDIUM"}:
            suppressed.append({
                "token": token,
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
        "unknown_age_policy": "FAIL_CLOSED_NO_ALERT",
        "historical_young_winner_policy": "RESEARCH_ONLY_MAY_REMAIN_IN_COHORT_NEVER_ACTIONABLE",
    }
    watch["actionable_veteran_dna_high_n"] = actionable_high
    watch["actionable_veteran_dna_medium_n"] = actionable_medium
    watch["actionable_veteran_signal_n"] = actionable_high + actionable_medium
    watch["suppressed_non_veteran_or_unverified_signal_n"] = len(suppressed)
    watch["suppressed_signals"] = suppressed[:50]
    watch["note"] = (
        "Winner-DNA cohort remains research-only. Telegram/actionable counts are now fail-closed to tokens with "
        "verified market age >=180 days. Young historical winners may remain for learning but can never become "
        "a Wallet500 Revival alert."
    )

    WATCH.write_text(json.dumps(watch, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "actionable_veteran_dna_high_n": actionable_high,
        "actionable_veteran_dna_medium_n": actionable_medium,
        "suppressed": len(suppressed),
    }, indent=2))


if __name__ == "__main__":
    main()
