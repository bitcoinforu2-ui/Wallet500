from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
LEDGER = DATA / "veteran-dna-forward-ledger.json"
REVIVAL = DATA / "revival-1000-latest.json"
HOLDER = DATA / "holder-concentration-shadow.json"
SOCIAL = DATA / "social-organic-acceleration.json"
KOL = DATA / "kol-revival-convergence-summary.json"
MODE = "VETERAN_DNA_T0_CONTEXT_FREEZE_V1"
MAX_FREEZE_LAG_MINUTES = 5.0


def load(path: Path, default):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def token_of(row: dict):
    return row.get("token_address") or row.get("token") or row.get("mint") or row.get("contract") or row.get("address")


def rows(payload: dict, *names: str) -> list[dict]:
    for name in names:
        value = payload.get(name)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            return [x for x in value.values() if isinstance(x, dict)]
    return []


def exact_token_index(payload: dict, *names: str) -> dict[str, dict]:
    out = {}
    for row in rows(payload, *names):
        token = str(token_of(row) or "").strip()
        if token:
            out[token] = row
    return out


def revival_index(payload: dict) -> dict[tuple[str, str], dict]:
    out = {}
    for coin in rows(payload, "coins"):
        token = str(coin.get("token_address") or "").strip()
        pair = str(coin.get("dex_pair_address") or "").strip()
        if token and pair:
            out[(token, pair.lower())] = coin
    return out


def freeze_revival(coin: dict | None) -> dict | None:
    if not isinstance(coin, dict):
        return None
    flow = coin.get("order_flow_absorption") or {}
    strength = coin.get("strict_strength") or {}
    strict = coin.get("strict_discovery") or {}
    return {
        "source": coin.get("source"),
        "watch_status": coin.get("watch_status"),
        "research_watch_eligible": coin.get("research_watch_eligible"),
        "revival_score_verified": coin.get("revival_score_verified"),
        "revival_score": coin.get("revival_score"),
        "drawdown_from_ath_pct": coin.get("drawdown_from_ath_pct"),
        "pair_age_days": coin.get("pair_age_days"),
        "absorption_candidate_proxy": coin.get("absorption_candidate_proxy"),
        "absorption_signal": flow.get("signal"),
        "absorption_score": flow.get("score"),
        "sell_buy_count_ratio_h24": flow.get("sell_buy_count_ratio_h24"),
        "strict_level": flow.get("strict_level") or strength.get("strict_level"),
        "strict_grade": flow.get("strict_grade") or strength.get("strict_grade"),
        "strict_strength_score": flow.get("strict_strength_score") or strength.get("strict_strength_score"),
        "strict_first_seen_at": strict.get("strict_first_seen_at"),
        "strict_discovery_price_usd": strict.get("discovery_price_usd"),
        "strict_source": strict.get("source"),
    }


def freeze_holder(row: dict | None) -> dict | None:
    if not isinstance(row, dict):
        return None
    if not any(row.get(k) is not None for k in ("holder_count_shadow", "top1_pct", "top10_pct", "concentration_risk_score")):
        return None
    return {
        "holder_count_shadow": row.get("holder_count_shadow"),
        "holder_shadow_observed_at": row.get("holder_shadow_observed_at") or row.get("observed_at"),
        "holder_change_pct_shadow": row.get("holder_change_since_previous_scan_pct_shadow"),
        "top1_pct": row.get("top1_pct"),
        "top5_pct": row.get("top5_pct"),
        "top10_pct": row.get("top10_pct"),
        "top20_pct": row.get("top20_pct"),
        "concentration_risk_score": row.get("concentration_risk_score"),
        "retained_from_previous_verified_observation": row.get("retained_from_previous_verified_observation"),
        "growth_signal_eligible": False,
        "positive_signal_eligible": False,
        "semantics": "SHADOW_CONTEXT_ONLY_NEVER_POSITIVE_SIGNAL",
    }


def freeze_social(row: dict | None) -> dict | None:
    if not isinstance(row, dict):
        return None
    current = row.get("current_1h") or {}
    return {
        "status": row.get("status"),
        "organic_acceleration_score": row.get("organic_acceleration_score"),
        "acceleration_vs_prior_6h_hourly_baseline": row.get("acceleration_vs_prior_6h_hourly_baseline"),
        "contamination_ratio_24h": row.get("contamination_ratio_24h"),
        "independent_authors_1h": current.get("independent_authors"),
        "independent_sources_1h": current.get("independent_sources"),
        "organic_weighted_mentions_1h": current.get("organic_weighted_mentions"),
        "latest_event_at": row.get("latest_event_at"),
        "rule": "SOCIAL_MENTIONS_NEQ_ORGANIC_SOCIAL_ACCELERATION",
    }


def freeze_kol(row: dict | None) -> dict | None:
    if not isinstance(row, dict):
        return None
    return {
        "status": row.get("status") or row.get("watch_status"),
        "independent_wallet_groups": row.get("independent_wallet_groups"),
        "independent_sources": row.get("independent_sources"),
        "wallet_count": row.get("wallet_count") or row.get("wallets"),
        "first_threshold_cross_at": row.get("first_threshold_cross_at"),
        "forward_only": True,
    }


def main() -> None:
    ledger = load(LEDGER, {})
    if ledger.get("mode") != "VETERAN_DNA_FORWARD_NO_HINDSIGHT_V1":
        raise SystemExit("VETERAN_DNA_CONTEXT_LEDGER_CONTRACT_INVALID")
    records = ledger.get("records") or {}
    now = now_utc()

    revival = load(REVIVAL, {})
    holder = load(HOLDER, {})
    social = load(SOCIAL, {})
    kol = load(KOL, {})

    rix = revival_index(revival)
    hix = exact_token_index(holder, "rows", "tokens", "coins")
    six = exact_token_index(social, "tokens", "rows")
    kix = exact_token_index(kol, "active", "rows", "tokens")

    frozen = 0
    backfill_blocked = 0
    invalid_context_removed = 0
    missing_revival_context = 0

    for rec in records.values():
        t0 = parse_ts(rec.get("t0_at"))
        if not t0:
            rec["t0_context_status"] = "T0_TIMESTAMP_INVALID"
            continue
        lag_min = (now - t0).total_seconds() / 60.0
        existing = rec.get("t0_context")

        if isinstance(existing, dict):
            frozen_at = parse_ts(existing.get("frozen_at"))
            existing_lag = n = None
            try:
                existing_lag = float(existing.get("freeze_lag_minutes"))
            except (TypeError, ValueError):
                if frozen_at is not None:
                    existing_lag = (frozen_at - t0).total_seconds() / 60.0
            if existing_lag is None or existing_lag > MAX_FREEZE_LAG_MINUTES:
                rec.pop("t0_context", None)
                rec["t0_context_status"] = "REMOVED_RETROACTIVE_CONTEXT_OUTSIDE_T0_WINDOW"
                rec["t0_context_freeze_lag_minutes"] = None if existing_lag is None else round(existing_lag, 3)
                invalid_context_removed += 1
            else:
                rec["t0_context_status"] = "FROZEN_AT_T0"
                continue

        if lag_min < -1:
            rec["t0_context_status"] = "T0_IN_FUTURE_INVALID"
            continue
        if lag_min > MAX_FREEZE_LAG_MINUTES:
            if rec.get("t0_context_status") != "REMOVED_RETROACTIVE_CONTEXT_OUTSIDE_T0_WINDOW":
                rec["t0_context_status"] = "BACKFILL_FORBIDDEN_AFTER_T0_WINDOW"
            rec["t0_context_freeze_lag_minutes"] = round(lag_min, 3)
            backfill_blocked += 1
            continue

        token = str(rec.get("token_address") or "").strip()
        pair = str(rec.get("pair_address") or "").strip()
        coin = rix.get((token, pair.lower()))
        if coin is None:
            missing_revival_context += 1

        context = {
            "mode": MODE,
            "frozen_at": now.isoformat(),
            "freeze_lag_minutes": round(max(0.0, lag_min), 3),
            "immutable_after_freeze": True,
            "no_hindsight": True,
            "same_checkout_as_t0_market_run": True,
            "exact_token": token,
            "exact_pair": pair,
            "revival": freeze_revival(coin),
            "holder_shadow": freeze_holder(hix.get(token)),
            "organic_social": freeze_social(six.get(token)),
            "kol_convergence": freeze_kol(kix.get(token)),
            "truth_notes": [
                "context is frozen only inside the same-run T0 window and is never retroactively backfilled",
                "holder shadow is risk/context only and never a positive growth signal",
                "raw social mentions never equal organic acceleration",
                "missing context remains missing and is never imputed",
            ],
        }
        rec["t0_context"] = context
        rec["t0_context_status"] = "FROZEN_AT_T0"
        rec.pop("t0_context_freeze_lag_minutes", None)
        frozen += 1

    ledger["context_freeze_contract"] = {
        "mode": MODE,
        "max_freeze_lag_minutes": MAX_FREEZE_LAG_MINUTES,
        "retroactive_feature_backfill": "FORBIDDEN",
        "existing_context_outside_window": "REMOVE_AS_HINDSIGHT_CONTAMINATION",
        "exact_token_and_pair_required_for_revival_context": True,
        "holder_shadow_positive_signal": False,
        "missing_features_imputed": False,
        "production_change": False,
    }
    ledger["last_context_freeze"] = {
        "at": now.isoformat(),
        "frozen": frozen,
        "backfill_blocked": backfill_blocked,
        "invalid_context_removed": invalid_context_removed,
        "missing_revival_context": missing_revival_context,
    }
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(ledger["last_context_freeze"], indent=2))


if __name__ == "__main__":
    main()
