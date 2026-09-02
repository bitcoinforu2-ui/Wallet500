from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import revival_forensics_v2 as core

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
WAKING = DATA / "waking-confirmation-latest.json"
HOLDERS = DATA / "revival-holder-latest.json"
LIQUIDITY_LATEST = DATA / "revival-liquidity-learning.json"
STATE = DATA / "revival-forensics-state.json"
LATEST = DATA / "revival-forensics-latest.json"
DASHBOARD = DATA / "revival-forensics-dashboard.json"
FEATURES = DATA / "revival-feature-analysis.json"

T0_SOURCE_CONTRACT = "REVIVAL_GENERATED_AT_EXACT_PUBLICATION_V1"
T0_INVALIDATION_REASON = (
    "LEGACY_FORENSICS_T0_USED_CONFIRMATION_TIMESTAMP_OLDER_THAN_REVIVAL_PRICE_SOURCE"
)


def _validate_authoritative_revival(revival: dict) -> datetime:
    if revival.get("network") != core.NETWORK:
        raise SystemExit("REVIVAL_FORENSICS_NETWORK_NOT_SOLANA")
    if revival.get("no_hindsight") is not True:
        raise SystemExit("REVIVAL_FORENSICS_NO_HINDSIGHT_SOURCE_INVALID")
    if revival.get("production_portfolio_impact") != "NONE":
        raise SystemExit("REVIVAL_FORENSICS_SOURCE_PRODUCTION_IMPACT_INVALID")
    gate = revival.get("age_gate") or {}
    if (
        gate.get("status") != "ENFORCED_FAIL_CLOSED"
        or int(gate.get("minimum_market_age_days") or 0) < core.MIN_AGE_DAYS
    ):
        raise SystemExit("REVIVAL_FORENSICS_AGE_GATE_NOT_ENFORCED")
    generated_at = core.parse_dt(revival.get("generated_at"))
    if not generated_at:
        raise SystemExit("REVIVAL_FORENSICS_REVIVAL_GENERATED_AT_INVALID")
    return generated_at


def _confirmation_map(waking: dict) -> dict[str, dict]:
    if not isinstance(waking, dict):
        return {}
    if waking.get("network") != core.NETWORK or waking.get("no_hindsight") is not True:
        return {}
    out: dict[str, dict] = {}
    for target in waking.get("targets") or []:
        mint = core.token_key(target)
        if mint:
            out[mint] = target
    return out


def _current_waking_from_revival(
    revival: dict,
    waking: dict,
) -> list[tuple[dict, dict]]:
    """Revival Radar is authoritative; confirmation is optional enrichment."""
    confirmations = _confirmation_map(waking)
    out: list[tuple[dict, dict]] = []
    for coin in revival.get("coins") or []:
        mint = core.token_key(coin)
        if not mint or coin.get("watch_status") != core.WAKING_STATUS:
            continue
        out.append((coin, confirmations.get(mint, {})))
    return out


def _migrate_state(raw: dict) -> dict:
    if raw.get("t0_source_contract") == T0_SOURCE_CONTRACT:
        raw.setdefault("invalidated_events", [])
        return raw

    invalidated = list(raw.get("invalidated_events") or [])
    for event in (raw.get("events") or {}).values():
        if not isinstance(event, dict):
            continue
        audit = dict(event)
        audit["invalidated_at"] = core.now_iso()
        audit["invalidated_reason"] = T0_INVALIDATION_REASON
        audit["eligible_for_learning"] = False
        invalidated.append(audit)

    return {
        "version": 2,
        "mode": core.MODE,
        "contract": core.CONTRACT,
        "network": core.NETWORK,
        "t0_source_contract": T0_SOURCE_CONTRACT,
        "events": {},
        "active_by_token": {},
        "invalidated_events": invalidated,
        "migration_note": (
            "Invalid legacy v2 events are retained for audit but excluded from all learning."
        ),
    }


def _fetch_exact_pair(pair_address: str, token_address: str) -> dict | None:
    if not pair_address or not token_address:
        return None
    url = (
        "https://api.dexscreener.com/latest/dex/pairs/solana/"
        + quote(pair_address)
    )
    try:
        req = Request(
            url,
            headers={"User-Agent": "Wallet500-Revival-Forensics/2.1"},
        )
        with urlopen(req, timeout=18) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    for row in payload.get("pairs") or []:
        if str(row.get("pairAddress") or "") != pair_address:
            continue
        if str((row.get("baseToken") or {}).get("address") or "") != token_address:
            continue
        price = core.n(row.get("priceUsd"))
        liquidity = core.n((row.get("liquidity") or {}).get("usd"))
        if price is None or price <= 0 or liquidity is None or liquidity < 0:
            return None
        return {
            "observed_at": core.now_iso(),
            "token_address": token_address,
            "pair_address": pair_address,
            "price_usd": price,
            "liquidity_usd": liquidity,
            "market_cap_usd": core.n(row.get("marketCap")),
            "source": "DEXSCREENER_EXACT_LOCKED_PAIR_FORENSICS_FALLBACK",
        }
    return None


def _append_observation(event: dict, row: dict | None) -> None:
    if not row:
        return
    t0 = event.get("t0") or {}
    pair = str(t0.get("pair_address") or "")
    if str(row.get("pair_address") or "") != pair:
        return
    at = str(row.get("observed_at") or row.get("at") or "")
    observed = core.parse_dt(at)
    waking_t0 = core.parse_dt(t0.get("waking_t0"))
    if not observed or not waking_t0 or observed < waking_t0:
        return

    observations = event.setdefault("observations", [])
    key = (at, pair)
    if any(
        (
            str(x.get("at") or x.get("observed_at") or ""),
            str(x.get("pair_address") or ""),
        )
        == key
        for x in observations
    ):
        return

    observations.append(
        {
            "at": at,
            "pair_address": pair,
            "price_usd": core.n(row.get("price_usd")),
            "liquidity_usd": core.n(row.get("liquidity_usd")),
            "market_cap_usd": core.n(row.get("market_cap_usd")),
            "source": row.get("source")
            or "REVIVAL_LIQUIDITY_LEARNING_CURRENT_EXACT_PAIR",
        }
    )
    observations.sort(
        key=lambda x: core.parse_dt(x.get("at"))
        or datetime.min.replace(tzinfo=timezone.utc)
    )
    if len(observations) > 340:
        del observations[:-340]


def _liquidity_current(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in payload.get("current_signals") or []:
        mint = core.token_key(row)
        if mint:
            out[mint] = row
    return out


def _reopen_retryable_horizons(event: dict, now: datetime) -> None:
    """Retry a temporarily missing horizon until its tolerance window closes."""
    horizons = event.get("horizons") or {}
    for minutes in core.HORIZONS_MIN:
        key = f"{minutes}m"
        row = horizons.get(key)
        if not isinstance(row, dict) or row.get("available") is not False:
            continue
        target = core.parse_dt(row.get("target_at"))
        if not target:
            continue
        deadline = target + timedelta(minutes=core.horizon_tolerance(minutes))
        if now <= deadline:
            horizons.pop(key, None)


def _confirmation_freshness_minutes(waking: dict, now: datetime) -> float | None:
    generated = core.parse_dt(waking.get("generated_at")) if isinstance(waking, dict) else None
    if not generated:
        return None
    return round((now - generated).total_seconds() / 60.0, 3)


def _write_outputs(
    state: dict,
    revival: dict,
    waking: dict,
    observed_at: str,
    now: datetime,
) -> dict:
    events = state.get("events") or {}
    active = state.get("active_by_token") or {}
    invalidated = state.get("invalidated_events") or []
    ordered = sorted(
        events.values(),
        key=lambda event: str((event.get("t0") or {}).get("waking_t0") or ""),
        reverse=True,
    )
    active_events = [events[event_id] for event_id in active.values() if event_id in events]
    analysis = core.feature_analysis(ordered)

    counts = {
        "events_total": len(ordered),
        "waking_active": len(active_events),
        "completed_24h": sum(1 for event in ordered if event.get("completed")),
        "x2_plus": sum(
            1
            for event in ordered
            if event.get("outcome_class")
            in {"REVIVAL_X2", "REVIVAL_X4", "REVIVAL_X10"}
        ),
        "failed_liquidity": sum(
            1
            for event in ordered
            if event.get("outcome_class") == "FAILED_LIQUIDITY_SURVIVAL"
        ),
        "no_revival_24h": sum(
            1
            for event in ordered
            if event.get("outcome_class") == "NO_REVIVAL_24H"
        ),
        "followup_after_waking_exit": sum(
            1
            for event in ordered
            if event.get("waking_ended_at") and not event.get("completed")
        ),
        "invalidated_audit_only": len(invalidated),
    }

    payload = {
        "version": 2,
        "revision": "2.1",
        "mode": core.MODE,
        "contract": core.CONTRACT,
        "network": core.NETWORK,
        "generated_at": observed_at,
        "t0_source_contract": T0_SOURCE_CONTRACT,
        "source_revival_generated_at": revival.get("generated_at"),
        "source_waking_confirmation_generated_at": waking.get("generated_at"),
        "confirmation_freshness_minutes": _confirmation_freshness_minutes(waking, now),
        "waking_authority": "REVIVAL_1000_LATEST_WATCH_STATUS",
        "confirmation_role": "OPTIONAL_ENRICHMENT_NEVER_ENTRY_GATE",
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "no_hindsight": True,
        "future_leakage_guard": (
            "T0_EQUALS_REVIVAL_PUBLICATION_TIME_AND_ONLY_FORWARD_EXACT_PAIR_OBSERVATIONS"
        ),
        "pair_identity_rule": "LOCK_REVIVAL_DEX_PAIR_AT_WAKING_T0_AND_NEVER_SWITCH",
        "age_rule": "MARKET_AGE_VERIFIED_GTE_180_DAYS_FAIL_CLOSED",
        "full_lifecycle_rule": (
            "CONTINUE_EXACT_PAIR_FOLLOWUP_TO_24H_EVEN_AFTER_WAKING_EXIT"
        ),
        "holder_rule": (
            "HOLDER_BASELINE_MAY_BE_POST_T0_AND_IS_NEVER_RELABELED_AS_PRICE_T0"
        ),
        "wallet500_status": "NOT_CONNECTED_TO_WAKING_PIPELINE_YET",
        "horizons_minutes": list(core.HORIZONS_MIN),
        "counts": counts,
        "events": ordered,
        "invalidated_events_audit": invalidated,
    }
    core.write(LATEST, payload)
    core.write(FEATURES, analysis)
    core.write(
        DASHBOARD,
        {
            "version": 2,
            "revision": "2.1",
            "mode": core.MODE,
            "generated_at": observed_at,
            "counts": counts,
            "claim_status": analysis.get("claim_status"),
            "wallet500_status": payload["wallet500_status"],
            "confirmation_freshness_minutes": payload[
                "confirmation_freshness_minutes"
            ],
            "active": [
                {
                    "event_id": event.get("event_id"),
                    "symbol": event.get("symbol"),
                    "token_address": event.get("token_address"),
                    "t0": (event.get("t0") or {}).get("waking_t0"),
                    "entry_price_usd": (event.get("t0") or {}).get("price_usd"),
                    "pair_address": (event.get("t0") or {}).get("pair_address"),
                    "revival_score_t0": (event.get("t0") or {}).get(
                        "revival_score_verified"
                    ),
                    "peak_return_pct": event.get("peak_return_pct"),
                    "max_drawdown_from_t0_pct": event.get(
                        "max_drawdown_from_t0_pct"
                    ),
                    "outcome_class": event.get("outcome_class"),
                    "holder_confirmation": event.get("holder_confirmation"),
                    "horizons": event.get("horizons"),
                    "evidence_sha256": (event.get("t0") or {}).get(
                        "evidence_sha256"
                    ),
                }
                for event in active_events
            ],
            "recent_completed": [
                {
                    "event_id": event.get("event_id"),
                    "symbol": event.get("symbol"),
                    "outcome_class": event.get("outcome_class"),
                    "peak_return_pct": event.get("peak_return_pct"),
                }
                for event in ordered
                if event.get("completed")
            ][:30],
        },
    )
    return payload


def run() -> dict:
    revival = core.load(REVIVAL, {})
    waking = core.load(WAKING, {})
    holders = core.load(HOLDERS, {})
    liquidity = core.load(LIQUIDITY_LATEST, {})
    revival_generated = _validate_authoritative_revival(revival)

    raw_state = core.load(
        STATE,
        {"version": 2, "events": {}, "active_by_token": {}},
    )
    state = _migrate_state(raw_state)
    events = state.setdefault("events", {})
    active = state.setdefault("active_by_token", {})
    holder_by = {
        core.token_key(row): row
        for row in holders.get("coins") or []
        if core.token_key(row)
    }
    current_pairs = _liquidity_current(liquidity)
    current_targets = _current_waking_from_revival(revival, waking)
    target_by = {
        core.token_key(coin): target
        for coin, target in current_targets
    }
    current_mints = set(target_by)
    now = datetime.now(timezone.utc)
    observed_at = now.isoformat()

    # Leaving WAKING closes only the WAKING state, never the 24h outcome follow-up.
    for mint, event_id in list(active.items()):
        if mint in current_mints:
            continue
        event = events.get(event_id)
        if event and not event.get("waking_ended_at"):
            event["waking_ended_at"] = observed_at
        active.pop(mint, None)

    # T0 is exactly the publication timestamp of the Revival record that supplies price.
    source_t0 = revival_generated.isoformat()
    for coin, target in current_targets:
        mint = core.token_key(coin)
        event_id = active.get(mint)
        if not event_id:
            event_id = "WAKING-" + core.sha256(
                {"mint": mint, "source_t0": source_t0}
            )[:16].upper()
            if event_id not in events:
                t0 = core.build_t0(coin, target, source_t0, observed_at)
                t0["t0_source"] = "REVIVAL_1000_LATEST_GENERATED_AT"
                t0["price_source_generated_at"] = source_t0
                t0["tracking_started_at"] = observed_at
                t0["pre_tracking_horizons_may_be_unavailable"] = (
                    now > revival_generated + timedelta(minutes=5)
                )
                t0["evidence_sha256"] = core.sha256(
                    {k: v for k, v in t0.items() if k != "evidence_sha256"}
                )
                events[event_id] = {
                    "event_id": event_id,
                    "token_address": mint,
                    "symbol": coin.get("symbol"),
                    "name": coin.get("name"),
                    "t0": t0,
                    "horizons": {},
                    "observations": [],
                    "outcome_class": "PENDING_24H",
                    "completed": False,
                    "production_portfolio_impact": "NONE",
                    "automatic_buy": False,
                }
            active[mint] = event_id

    # Follow every non-completed event through 24h, even after WAKING ends.
    for event in events.values():
        if event.get("completed"):
            continue
        _reopen_retryable_horizons(event, now)
        mint = str(event.get("token_address") or "")
        t0 = event.get("t0") or {}
        pair = str(t0.get("pair_address") or "")
        row = current_pairs.get(mint)
        if not row or str(row.get("pair_address") or "") != pair:
            row = _fetch_exact_pair(pair, mint)
        _append_observation(event, row)
        target = target_by.get(mint) or {}
        holder_ev = core.holder_evidence(holder_by, target, mint)
        core.update_event(
            event,
            list(event.get("observations") or []),
            holder_ev,
            now,
        )
        if target:
            event["confirmation_status_latest"] = target.get("confirmation_status")
            event["confirmation_score_latest"] = core.n(
                target.get("confirmation_score")
            )
            event["confirmation_strong_families_latest"] = (
                target.get("strong_families") or []
            )

    state.update(
        {
            "version": 2,
            "revision": "2.1",
            "mode": core.MODE,
            "contract": core.CONTRACT,
            "network": core.NETWORK,
            "updated_at": observed_at,
            "no_hindsight": True,
            "future_leakage_guard": True,
            "minimum_market_age_days": core.MIN_AGE_DAYS,
            "t0_source_contract": T0_SOURCE_CONTRACT,
            "events": events,
            "active_by_token": active,
        }
    )
    core.write(STATE, state)
    return _write_outputs(state, revival, waking, observed_at, now)


def main() -> None:
    payload = run()
    print(
        json.dumps(
            {
                "mode": payload["mode"],
                "revision": payload["revision"],
                "counts": payload["counts"],
                "wallet500_status": payload["wallet500_status"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
