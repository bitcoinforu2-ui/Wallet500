from __future__ import annotations

import json
from datetime import datetime, timezone
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


def _fetch_exact_pair(pair_address: str, token_address: str) -> dict | None:
    if not pair_address or not token_address:
        return None
    url = "https://api.dexscreener.com/latest/dex/pairs/solana/" + quote(pair_address)
    try:
        req = Request(url, headers={"User-Agent": "Wallet500-Revival-Forensics/2.0"})
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
        liq = core.n((row.get("liquidity") or {}).get("usd"))
        if price is None or price <= 0 or liq is None or liq < 0:
            return None
        return {
            "observed_at": core.now_iso(),
            "token_address": token_address,
            "pair_address": pair_address,
            "price_usd": price,
            "liquidity_usd": liq,
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
    if not core.parse_dt(at):
        return
    observations = event.setdefault("observations", [])
    key = (at, pair)
    if any((str(x.get("at") or x.get("observed_at") or ""), str(x.get("pair_address") or "")) == key for x in observations):
        return
    observations.append({
        "at": at,
        "pair_address": pair,
        "price_usd": core.n(row.get("price_usd")),
        "liquidity_usd": core.n(row.get("liquidity_usd")),
        "market_cap_usd": core.n(row.get("market_cap_usd")),
        "source": row.get("source") or "REVIVAL_LIQUIDITY_LEARNING_CURRENT_EXACT_PAIR",
    })
    observations.sort(key=lambda x: core.parse_dt(x.get("at")) or datetime.min.replace(tzinfo=timezone.utc))
    if len(observations) > 340:
        del observations[:-340]


def _liquidity_current(payload: dict) -> dict[str, dict]:
    out = {}
    for row in payload.get("current_signals") or []:
        mint = core.token_key(row)
        if mint:
            out[mint] = row
    return out


def _write_outputs(events: dict, active: dict, revival: dict, waking: dict, observed_at: str) -> dict:
    ordered = sorted(events.values(), key=lambda e: str((e.get("t0") or {}).get("waking_t0") or ""), reverse=True)
    active_events = [events[eid] for eid in active.values() if eid in events]
    analysis = core.feature_analysis(ordered)
    counts = {
        "events_total": len(ordered),
        "waking_active": len(active_events),
        "completed_24h": sum(1 for e in ordered if e.get("completed")),
        "x2_plus": sum(1 for e in ordered if e.get("outcome_class") in {"REVIVAL_X2", "REVIVAL_X4", "REVIVAL_X10"}),
        "failed_liquidity": sum(1 for e in ordered if e.get("outcome_class") == "FAILED_LIQUIDITY_SURVIVAL"),
        "no_revival_24h": sum(1 for e in ordered if e.get("outcome_class") == "NO_REVIVAL_24H"),
        "followup_after_waking_exit": sum(1 for e in ordered if e.get("waking_ended_at") and not e.get("completed")),
    }
    payload = {
        "version": 2,
        "mode": core.MODE,
        "contract": core.CONTRACT,
        "network": core.NETWORK,
        "generated_at": observed_at,
        "source_revival_generated_at": revival.get("generated_at"),
        "source_waking_generated_at": waking.get("generated_at"),
        "production_portfolio_impact": "NONE",
        "automatic_buy": False,
        "no_hindsight": True,
        "future_leakage_guard": "ONLY_PUBLISHED_WAKING_T0_AND_FORWARD_EXACT_PAIR_OBSERVATIONS",
        "pair_identity_rule": "LOCK_REVIVAL_DEX_PAIR_AT_WAKING_T0_AND_NEVER_SWITCH",
        "age_rule": "MARKET_AGE_VERIFIED_GTE_180_DAYS_FAIL_CLOSED",
        "full_lifecycle_rule": "CONTINUE_EXACT_PAIR_FOLLOWUP_TO_24H_EVEN_AFTER_WAKING_EXIT",
        "holder_rule": "HOLDER_BASELINE_MAY_BE_POST_T0_AND_IS_NEVER_RELABELED_AS_PRICE_T0",
        "wallet500_status": "NOT_CONNECTED_TO_WAKING_PIPELINE_YET",
        "horizons_minutes": list(core.HORIZONS_MIN),
        "counts": counts,
        "events": ordered,
    }
    core.write(LATEST, payload)
    core.write(FEATURES, analysis)
    core.write(DASHBOARD, {
        "version": 2,
        "mode": core.MODE,
        "generated_at": observed_at,
        "counts": counts,
        "claim_status": analysis.get("claim_status"),
        "wallet500_status": payload["wallet500_status"],
        "active": [{
            "event_id": e.get("event_id"),
            "symbol": e.get("symbol"),
            "token_address": e.get("token_address"),
            "t0": (e.get("t0") or {}).get("waking_t0"),
            "entry_price_usd": (e.get("t0") or {}).get("price_usd"),
            "pair_address": (e.get("t0") or {}).get("pair_address"),
            "revival_score_t0": (e.get("t0") or {}).get("revival_score_verified"),
            "peak_return_pct": e.get("peak_return_pct"),
            "max_drawdown_from_t0_pct": e.get("max_drawdown_from_t0_pct"),
            "outcome_class": e.get("outcome_class"),
            "holder_confirmation": e.get("holder_confirmation"),
            "horizons": e.get("horizons"),
            "evidence_sha256": (e.get("t0") or {}).get("evidence_sha256"),
        } for e in active_events],
        "recent_completed": [{
            "event_id": e.get("event_id"), "symbol": e.get("symbol"),
            "outcome_class": e.get("outcome_class"), "peak_return_pct": e.get("peak_return_pct"),
        } for e in ordered if e.get("completed")][:30],
    })
    return payload


def run() -> dict:
    revival = core.load(REVIVAL, {})
    waking = core.load(WAKING, {})
    holders = core.load(HOLDERS, {})
    liquidity = core.load(LIQUIDITY_LATEST, {})
    core.validate_source(revival, waking)

    state = core.load(STATE, {"version": 2, "events": {}, "active_by_token": {}})
    events = state.setdefault("events", {})
    active = state.setdefault("active_by_token", {})
    holder_by = {core.token_key(x): x for x in holders.get("coins") or [] if core.token_key(x)}
    current_pairs = _liquidity_current(liquidity)
    current_targets = core.current_waking_targets(revival, waking)
    target_by = {core.token_key(coin): target for coin, target in current_targets}
    current_mints = set(target_by)
    now = datetime.now(timezone.utc)
    observed_at = now.isoformat()

    # Leaving WAKING closes only the WAKING state, not the outcome follow-up.
    for mint, event_id in list(active.items()):
        if mint in current_mints:
            continue
        event = events.get(event_id)
        if event and not event.get("waking_ended_at"):
            event["waking_ended_at"] = observed_at
        active.pop(mint, None)

    source_t0 = str(waking.get("source_generated_at") or revival.get("generated_at") or observed_at)
    for coin, target in current_targets:
        mint = core.token_key(coin)
        event_id = active.get(mint)
        if not event_id:
            event_id = "WAKING-" + core.sha256({"mint": mint, "source_t0": source_t0})[:16].upper()
            if event_id not in events:
                events[event_id] = {
                    "event_id": event_id, "token_address": mint, "symbol": coin.get("symbol"), "name": coin.get("name"),
                    "t0": core.build_t0(coin, target, source_t0, observed_at),
                    "horizons": {}, "observations": [], "outcome_class": "PENDING_24H", "completed": False,
                    "production_portfolio_impact": "NONE", "automatic_buy": False,
                }
            active[mint] = event_id

    # Follow every not-yet-completed event to 24h, whether or not it remains WAKING.
    for event in events.values():
        if event.get("completed"):
            continue
        mint = str(event.get("token_address") or "")
        t0 = event.get("t0") or {}
        pair = str(t0.get("pair_address") or "")
        row = current_pairs.get(mint)
        if not row or str(row.get("pair_address") or "") != pair:
            row = _fetch_exact_pair(pair, mint)
        _append_observation(event, row)
        target = target_by.get(mint) or {}
        holder_ev = core.holder_evidence(holder_by, target, mint)
        core.update_event(event, list(event.get("observations") or []), holder_ev, now)
        if target:
            event["confirmation_status_latest"] = target.get("confirmation_status")
            event["confirmation_score_latest"] = core.n(target.get("confirmation_score"))
            event["confirmation_strong_families_latest"] = target.get("strong_families") or []

    state.update({
        "version": 2, "mode": core.MODE, "contract": core.CONTRACT, "network": core.NETWORK,
        "updated_at": observed_at, "no_hindsight": True, "future_leakage_guard": True,
        "minimum_market_age_days": core.MIN_AGE_DAYS, "events": events, "active_by_token": active,
    })
    core.write(STATE, state)
    return _write_outputs(events, active, revival, waking, observed_at)


def main() -> None:
    payload = run()
    print(json.dumps({"mode": payload["mode"], "counts": payload["counts"], "wallet500_status": payload["wallet500_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
