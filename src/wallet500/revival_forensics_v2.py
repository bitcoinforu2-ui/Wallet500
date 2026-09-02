from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

DATA = Path("data")
REVIVAL = DATA / "revival-1000-latest.json"
WAKING = DATA / "waking-confirmation-latest.json"
HOLDERS = DATA / "revival-holder-latest.json"
LIQUIDITY_STATE = DATA / "revival-liquidity-learning-state.json"
STATE = DATA / "revival-forensics-state.json"
LATEST = DATA / "revival-forensics-latest.json"
DASHBOARD = DATA / "revival-forensics-dashboard.json"
FEATURES = DATA / "revival-feature-analysis.json"

MODE = "RESEARCH_ONLY_REVIVAL_FORENSICS_V2"
CONTRACT = "REVIVAL_FORENSICS_V2"
NETWORK = "solana"
MIN_AGE_DAYS = 180
HORIZONS_MIN = (5, 15, 30, 60, 240, 720, 1440)
WAKING_STATUS = "WAKING_MARKET_ONLY"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def n(value: object, default: float | None = None) -> float | None:
    try:
        x = float(value)
        if x != x or x in (float("inf"), float("-inf")):
            return default
        return x
    except (TypeError, ValueError):
        return default


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(base: object, current: object) -> float | None:
    b, c = n(base), n(current)
    if b is None or b <= 0 or c is None or c <= 0:
        return None
    return round((c / b - 1.0) * 100.0, 6)


def sha256(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def token_key(row: dict) -> str:
    return str(row.get("token_address") or row.get("mint") or "").strip()


def exact_pair(row: dict) -> str:
    return str(row.get("dex_pair_address") or row.get("pair_address") or "").strip()


def horizon_tolerance(minutes: int) -> int:
    if minutes <= 15:
        return 8
    if minutes <= 60:
        return 12
    if minutes <= 240:
        return 25
    if minutes <= 720:
        return 45
    return 90


def select_exact_pair_observation(history: list[dict], pair_address: str, target: datetime, tolerance_minutes: int) -> dict | None:
    best: tuple[float, dict] | None = None
    for row in history:
        if str(row.get("pair_address") or "") != pair_address:
            continue
        at = parse_dt(row.get("at") or row.get("observed_at"))
        if not at or at < target:
            continue
        lag = (at - target).total_seconds() / 60.0
        if lag > tolerance_minutes:
            continue
        if best is None or lag < best[0]:
            best = (lag, row)
    return best[1] if best else None


def observations_since(history: list[dict], pair_address: str, t0: datetime) -> list[dict]:
    out = []
    for row in history:
        if str(row.get("pair_address") or "") != pair_address:
            continue
        at = parse_dt(row.get("at") or row.get("observed_at"))
        if at and at >= t0:
            out.append(row)
    out.sort(key=lambda x: parse_dt(x.get("at") or x.get("observed_at")) or t0)
    return out


def current_waking_targets(revival: dict, waking: dict) -> list[tuple[dict, dict]]:
    by_token = {token_key(x): x for x in revival.get("coins") or [] if token_key(x)}
    out = []
    for target in waking.get("targets") or []:
        mint = token_key(target)
        coin = by_token.get(mint)
        if not coin:
            continue
        if target.get("base_watch_status") != WAKING_STATUS or coin.get("watch_status") != WAKING_STATUS:
            continue
        out.append((coin, target))
    return out


def validate_source(revival: dict, waking: dict) -> None:
    if revival.get("network") != NETWORK or waking.get("network") != NETWORK:
        raise SystemExit("REVIVAL_FORENSICS_NETWORK_NOT_SOLANA")
    if revival.get("no_hindsight") is not True or waking.get("no_hindsight") is not True:
        raise SystemExit("REVIVAL_FORENSICS_NO_HINDSIGHT_SOURCE_INVALID")
    if revival.get("production_portfolio_impact") != "NONE" or waking.get("production_portfolio_impact") != "NONE":
        raise SystemExit("REVIVAL_FORENSICS_SOURCE_PRODUCTION_IMPACT_INVALID")
    gate = revival.get("age_gate") or {}
    if gate.get("status") != "ENFORCED_FAIL_CLOSED" or int(gate.get("minimum_market_age_days") or 0) < MIN_AGE_DAYS:
        raise SystemExit("REVIVAL_FORENSICS_AGE_GATE_NOT_ENFORCED")


def build_t0(coin: dict, target: dict, source_generated_at: str, created_at: str) -> dict:
    age = n(coin.get("market_age_min_days"))
    pair = exact_pair(coin)
    price = n(coin.get("price_usd"))
    liquidity = n(coin.get("dex_pair_liquidity_usd"))
    market_cap = n(coin.get("market_cap_usd"))
    blockers = []
    if coin.get("market_age_verified") is not True or age is None or age < MIN_AGE_DAYS:
        blockers.append("AGE_NOT_VERIFIED_180D_PLUS")
    if not pair:
        blockers.append("PAIR_ID_MISSING")
    if price is None or price <= 0:
        blockers.append("ENTRY_PRICE_MISSING")
    if liquidity is None or liquidity < 0:
        blockers.append("ENTRY_LIQUIDITY_MISSING")
    t0 = {
        "token_address": token_key(coin), "symbol": coin.get("symbol"), "name": coin.get("name"),
        "waking_t0": source_generated_at, "locked_at": created_at,
        "t0_source": "PUBLISHED_REVIVAL_SOURCE_GENERATED_AT",
        "price_usd": price, "liquidity_usd": liquidity, "market_cap_usd": market_cap,
        "pair_address": pair, "dex_link": coin.get("dex_link"),
        "market_age_verified": coin.get("market_age_verified") is True,
        "market_age_min_days": int(age) if age is not None else None,
        "market_age_evidence_at": coin.get("market_age_evidence_at"),
        "market_age_evidence_source": coin.get("market_age_evidence_source"),
        "revival_score_verified": n(coin.get("revival_score_verified")),
        "drawdown_from_ath_pct": n(coin.get("drawdown_from_ath_pct")),
        "change_24h_pct": n(coin.get("change_24h_pct")), "change_7d_pct": n(coin.get("change_7d_pct")),
        "change_30d_pct": n(coin.get("change_30d_pct")), "volume_24h_usd": n(coin.get("volume_24h_usd")),
        "pair_volume_24h_usd": n(coin.get("dex_pair_volume_24h_usd")),
        "confirmation_status_at_lock": target.get("confirmation_status"),
        "confirmation_score_at_lock": n(target.get("confirmation_score")), "blockers": blockers,
    }
    t0["evidence_sha256"] = sha256({k: v for k, v in t0.items() if k != "evidence_sha256"})
    return t0


def holder_evidence(holder_by_token: dict[str, dict], target: dict, mint: str) -> dict:
    holder = holder_by_token.get(mint) or {}
    ch = ((target.get("channels") or {}).get("holders") or {})
    cm = ch.get("metrics") or {}
    wallet = ((target.get("channels") or {}).get("wallets") or {})
    distribution = target.get("distribution_evidence") or {}
    dm = distribution.get("metrics") or {}
    return {
        "holder_baseline_count": holder.get("first_holder_count"),
        "holder_baseline_observed_at": holder.get("first_holder_observed_at"),
        "holder_count_latest": holder.get("holder_count") if holder else cm.get("holder_count"),
        "holder_growth_from_baseline_pct": holder.get("holder_growth_pct"),
        "holder_latest_scan_change_pct": holder.get("latest_scan_change_pct") if holder else cm.get("holder_change_pct"),
        "holder_source": holder.get("source") if holder else ch.get("source"),
        "holder_is_true_price_t0": False,
        "wallet_activity_available": wallet.get("available") is True,
        "wallet_activity_verified": wallet.get("verified") is True,
        "wallet_activity_source": wallet.get("source"),
        "wallet_activity_metrics": wallet.get("metrics") or {},
        "wallet500_smart_money_connected": False,
        "wallet500_smart_money_status": "NOT_CONNECTED_TO_WAKING_PIPELINE",
        "top1_token_account_pct": holder.get("top1_pct") if holder else dm.get("top1_pct"),
        "top10_token_accounts_pct": holder.get("top10_pct") if holder else dm.get("top10_pct"),
        "concentration_risk_score": holder.get("concentration_risk_score") if holder else distribution.get("risk_score"),
    }


def update_event(event: dict, history: list[dict], holder_ev: dict, now: datetime) -> dict:
    t0 = parse_dt((event.get("t0") or {}).get("waking_t0"))
    if not t0:
        event.setdefault("blockers", []).append("T0_TIMESTAMP_INVALID")
        return event
    pair = str((event.get("t0") or {}).get("pair_address") or "")
    entry_price = n((event.get("t0") or {}).get("price_usd"))
    entry_liq = n((event.get("t0") or {}).get("liquidity_usd"))
    exact = observations_since(history, pair, t0)
    horizons = event.setdefault("horizons", {})
    for mins in HORIZONS_MIN:
        key = f"{mins}m"
        if key in horizons:
            continue
        target = t0 + timedelta(minutes=mins)
        if now < target:
            continue
        row = select_exact_pair_observation(history, pair, target, horizon_tolerance(mins))
        if row is None:
            horizons[key] = {"target_at": target.isoformat(), "available": False, "reason": "NO_EXACT_PAIR_OBSERVATION_WITHIN_TOLERANCE"}
            continue
        observed = parse_dt(row.get("at") or row.get("observed_at"))
        price, liq = n(row.get("price_usd")), n(row.get("liquidity_usd"))
        horizons[key] = {
            "target_at": target.isoformat(), "observed_at": observed.isoformat() if observed else None,
            "lag_minutes": round((observed-target).total_seconds()/60.0, 3) if observed else None,
            "pair_address": pair, "pair_identity": "STRICT_MATCH", "price_usd": price,
            "return_pct": pct(entry_price, price), "liquidity_usd": liq,
            "liquidity_return_pct": pct(entry_liq, liq), "available": price is not None and price > 0,
        }
    prices = [n(x.get("price_usd")) for x in exact]; prices = [x for x in prices if x is not None and x > 0]
    liqs = [n(x.get("liquidity_usd")) for x in exact]; liqs = [x for x in liqs if x is not None and x >= 0]
    peak_price = max(prices) if prices else entry_price
    low_price = min(prices) if prices else entry_price
    min_liq = min(liqs) if liqs else entry_liq
    event["peak_return_pct"] = pct(entry_price, peak_price)
    event["max_drawdown_from_t0_pct"] = pct(entry_price, low_price)
    event["minimum_liquidity_return_pct"] = pct(entry_liq, min_liq)
    event["holder_confirmation"] = holder_ev
    event["last_updated_at"] = now.isoformat()
    age_min = (now - t0).total_seconds() / 60.0
    peak = n(event.get("peak_return_pct"), -10000.0) or -10000.0
    liq_floor = n(event.get("minimum_liquidity_return_pct"), 0.0)
    if liq_floor is not None and liq_floor <= -80: outcome = "FAILED_LIQUIDITY_SURVIVAL"
    elif peak >= 900: outcome = "REVIVAL_X10"
    elif peak >= 300: outcome = "REVIVAL_X4"
    elif peak >= 100: outcome = "REVIVAL_X2"
    elif age_min >= 1440: outcome = "NO_REVIVAL_24H"
    else: outcome = "PENDING_24H"
    event["outcome_class"] = outcome
    event["completed"] = age_min >= 1440
    if event["completed"] and not event.get("completed_at"): event["completed_at"] = now.isoformat()
    return event


def feature_analysis(events: list[dict]) -> dict:
    completed = [e for e in events if e.get("completed")]
    winners = [e for e in completed if e.get("outcome_class") in {"REVIVAL_X2", "REVIVAL_X4", "REVIVAL_X10"}]
    failures = [e for e in completed if e.get("outcome_class") in {"NO_REVIVAL_24H", "FAILED_LIQUIDITY_SURVIVAL"}]
    fields = ("revival_score_verified","drawdown_from_ath_pct","change_24h_pct","change_7d_pct","change_30d_pct","liquidity_usd","market_cap_usd","volume_24h_usd","pair_volume_24h_usd")
    comparison = {}
    for field in fields:
        w = [n((e.get("t0") or {}).get(field)) for e in winners]; w = [x for x in w if x is not None]
        f = [n((e.get("t0") or {}).get(field)) for e in failures]; f = [x for x in f if x is not None]
        comparison[field] = {"winner_n":len(w),"failure_n":len(f),"winner_median":median(w) if w else None,"failure_median":median(f) if f else None,"sufficient_for_preliminary_comparison":len(w)>=5 and len(f)>=5}
    return {"version":2,"mode":MODE,"generated_at":now_iso(),"no_hindsight":True,"t0_only_features":True,"holders_excluded_from_t0_comparison":"holder baseline can be observed after WAKING T0; retained as confirmation evidence only","counts":{"completed":len(completed),"winners_x2_plus":len(winners),"failures":len(failures)},"claim_status":"ENOUGH_FOR_PRELIMINARY_COMPARISON" if len(winners)>=5 and len(failures)>=5 else "INSUFFICIENT_SAMPLE_FOR_STATISTICAL_CLAIM","feature_comparison":comparison}


def run(output_dir: str = "data") -> dict:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    state_path=out/"revival-forensics-state.json"; latest_path=out/"revival-forensics-latest.json"; dashboard_path=out/"revival-forensics-dashboard.json"; features_path=out/"revival-feature-analysis.json"
    revival=load(out/"revival-1000-latest.json",{}); waking=load(out/"waking-confirmation-latest.json",{}); holders=load(out/"revival-holder-latest.json",{}); liquidity=load(out/"revival-liquidity-learning-state.json",{})
    validate_source(revival,waking)
    state=load(state_path,{"version":2,"events":{},"active_by_token":{}}); events=state.setdefault("events",{}); active=state.setdefault("active_by_token",{})
    holder_by={token_key(x):x for x in holders.get("coins") or [] if token_key(x)}; histories=liquidity.get("observations") or {}; current=current_waking_targets(revival,waking)
    now=datetime.now(timezone.utc); at=now.isoformat(); current_mints={token_key(c) for c,_ in current}
    for mint,event_id in list(active.items()):
        if mint in current_mints: continue
        e=events.get(event_id)
        if isinstance(e,dict) and not e.get("waking_ended_at"): e["waking_ended_at"]=at
        active.pop(mint,None)
    source_t0=str(waking.get("source_generated_at") or revival.get("generated_at") or at)
    for coin,target in current:
        mint=token_key(coin); event_id=active.get(mint)
        if not event_id:
            event_id="WAKING-"+sha256({"mint":mint,"source_t0":source_t0})[:16].upper()
            if event_id not in events:
                events[event_id]={"event_id":event_id,"token_address":mint,"symbol":coin.get("symbol"),"name":coin.get("name"),"t0":build_t0(coin,target,source_t0,at),"horizons":{},"outcome_class":"PENDING_24H","completed":False,"production_portfolio_impact":"NONE","automatic_buy":False}
            active[mint]=event_id
        ev=events[event_id]; update_event(ev,list(histories.get(mint) or []),holder_evidence(holder_by,target,mint),now)
        ev["confirmation_status_latest"]=target.get("confirmation_status"); ev["confirmation_score_latest"]=n(target.get("confirmation_score")); ev["confirmation_strong_families_latest"]=target.get("strong_families") or []
    state.update({"version":2,"mode":MODE,"contract":CONTRACT,"network":NETWORK,"updated_at":at,"no_hindsight":True,"future_leakage_guard":True,"minimum_market_age_days":MIN_AGE_DAYS,"events":events,"active_by_token":active}); write(state_path,state)
    ordered=sorted(events.values(),key=lambda e:str((e.get("t0") or {}).get("waking_t0") or ""),reverse=True); active_events=[events[eid] for eid in active.values() if eid in events]; analysis=feature_analysis(ordered)
    counts={"events_total":len(ordered),"waking_active":len(active_events),"completed_24h":sum(1 for e in ordered if e.get("completed")),"x2_plus":sum(1 for e in ordered if e.get("outcome_class") in {"REVIVAL_X2","REVIVAL_X4","REVIVAL_X10"}),"failed_liquidity":sum(1 for e in ordered if e.get("outcome_class")=="FAILED_LIQUIDITY_SURVIVAL"),"no_revival_24h":sum(1 for e in ordered if e.get("outcome_class")=="NO_REVIVAL_24H")}
    payload={"version":2,"mode":MODE,"contract":CONTRACT,"network":NETWORK,"generated_at":at,"source_revival_generated_at":revival.get("generated_at"),"source_waking_generated_at":waking.get("generated_at"),"production_portfolio_impact":"NONE","automatic_buy":False,"no_hindsight":True,"future_leakage_guard":"ONLY_PUBLISHED_T0_AND_FORWARD_EXACT_PAIR_OBSERVATIONS","pair_identity_rule":"LOCK_REVIVAL_DEX_PAIR_AT_WAKING_T0_AND_NEVER_SWITCH","age_rule":"MARKET_AGE_VERIFIED_GTE_180_DAYS_FAIL_CLOSED","holder_rule":"HOLDER_BASELINE_MAY_BE_POST_T0_AND_IS_NEVER_RELABELED_AS_PRICE_T0","wallet500_status":"NOT_CONNECTED_TO_WAKING_PIPELINE_YET","horizons_minutes":list(HORIZONS_MIN),"counts":counts,"events":ordered}; write(latest_path,payload); write(features_path,analysis)
    dashboard={"version":2,"mode":MODE,"generated_at":at,"counts":counts,"claim_status":analysis.get("claim_status"),"wallet500_status":payload["wallet500_status"],"active":[{"event_id":e.get("event_id"),"symbol":e.get("symbol"),"token_address":e.get("token_address"),"t0":(e.get("t0") or {}).get("waking_t0"),"entry_price_usd":(e.get("t0") or {}).get("price_usd"),"pair_address":(e.get("t0") or {}).get("pair_address"),"revival_score_t0":(e.get("t0") or {}).get("revival_score_verified"),"peak_return_pct":e.get("peak_return_pct"),"max_drawdown_from_t0_pct":e.get("max_drawdown_from_t0_pct"),"outcome_class":e.get("outcome_class"),"holder_confirmation":e.get("holder_confirmation"),"horizons":e.get("horizons"),"evidence_sha256":(e.get("t0") or {}).get("evidence_sha256")} for e in active_events]}; write(dashboard_path,dashboard)
    return payload


def main() -> None:
    p=run(); print(json.dumps({"mode":p["mode"],"counts":p["counts"],"wallet500_status":p["wallet500_status"]},ensure_ascii=False))


if __name__ == "__main__": main()
