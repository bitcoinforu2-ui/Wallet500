from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
HORIZONS = ((5,"5m"),(15,"15m"),(30,"30m"),(60,"1h"),(240,"4h"),(720,"12h"),(1440,"24h"))
EVM_CHAINS = {"ethereum","eth","bsc","bnb","base","arbitrum","polygon","optimism","avalanche"}
PRICE_IDENTITY_CONTRACT_VERSION = 2


def _load(path: Path, default):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _norm_chain(chain):
    return str(chain or "").lower()


def _norm_token(chain, token):
    token = str(token or "")
    return token.lower() if _norm_chain(chain) in EVM_CHAINS else token


def _norm_pair(chain, pair):
    pair = str(pair or "")
    return pair.lower() if _norm_chain(chain) in EVM_CHAINS else pair


def _same_id(chain, left, right):
    return bool(left and right) and _norm_token(chain, left) == _norm_token(chain, right)


def _key(chain, token):
    return f"{_norm_chain(chain)}:{_norm_token(chain, token)}"


def _pair_key(chain, token, pair):
    return f"{_key(chain, token)}:{_norm_pair(chain, pair)}"


def _pct(cur, base):
    try:
        cur=float(cur); base=float(base)
        return round((cur/base-1.0)*100.0, 4) if base > 0 else None
    except Exception:
        return None


def _dt(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception:
        return None


def _explicit_zero_liquidity(row):
    if not isinstance(row, dict) or row.get("liquidity_usd") is None:
        return False
    try:
        return float(row.get("liquidity_usd")) <= 0.0
    except Exception:
        return False


def _finite_positive_price(value):
    try:
        value=float(value)
        return math.isfinite(value) and value > 0.0
    except Exception:
        return False


def _identity_verified_snapshot(chain, token, row):
    """Accept a price only when the target-token identity is provable.

    New snapshots carry token_identity_verified=True. For legacy snapshots we
    may safely accept a base-side row when base_token_address proves that the
    tracked token is DexScreener baseToken, because priceUsd is defined for the
    base side. Legacy quote-side rows are rejected: old code may have copied the
    base price into the quote token.
    """
    if not isinstance(row, dict):
        return False
    if row.get("token_identity_verified") is True:
        side = str(row.get("target_token_side") or "").upper()
        if side == "BASE":
            return _same_id(chain, token, row.get("base_token_address"))
        if side == "QUOTE":
            return _same_id(chain, token, row.get("quote_token_address"))
        return False
    return _same_id(chain, token, row.get("base_token_address"))


def _snapshot_sources():
    """Return exact-pair rows without collapsing pools or trusting pair-only prices."""
    by_pair = {}
    token_pairs = {}
    identity_rejected = 0
    files = (
        "market-snapshots.json","revival-snapshots.json","fresh-solana-survival.json",
        "active-qualified-candidates.json","live-survival-pending.json","live-survival-failed.json",
        "production-risk-evaluations.json","production-risk-blocked.json"
    )
    for name in files:
        data = _load(DATA/name, [])
        if not isinstance(data, list):
            continue
        for x in data:
            if not isinstance(x, dict) or x.get("price_usd") in (None,0,0.0):
                continue
            chain=x.get("chain"); token=x.get("token") or x.get("mint"); pair=x.get("pair_address")
            if not chain or not token or not pair:
                continue
            if not _identity_verified_snapshot(chain, token, x):
                identity_rejected += 1
                continue
            pk = _pair_key(chain, token, pair)
            by_pair[pk] = x
            tk = _key(chain, token)
            token_pairs.setdefault(tk, set()).add(_norm_pair(chain, pair))
    return by_pair, token_pairs, identity_rejected


def _leader_row(x):
    hist=x.get("history") if isinstance(x.get("history"),list) else []
    last=hist[-1] if hist else {}
    return {
        "chain":x.get("chain"),"token":x.get("token"),"pair_address":x.get("entry_pair_address"),
        "dex":x.get("entry_dex") or last.get("dex"),"discovery_time":x.get("first_seen"),
        "tracking_started_at":x.get("tracking_started_at"),"entry_price_usd":x.get("entry_price_usd"),
        "current_price_usd":x.get("current_price_usd"),"current_return_pct":x.get("current_return_pct"),
        "peak_price_usd":x.get("peak_price_usd"),"peak_return_pct":x.get("peak_return_pct"),
        "low_price_usd":x.get("low_price_usd"),"low_return_pct":x.get("low_return_pct"),
        "liquidity_usd":last.get("liquidity_usd"),"volume_h1":last.get("volume_h1"),
        "updated_at":x.get("updated_at"),"measurement_status":x.get("measurement_status"),
        "price_identity_contract_version":x.get("price_identity_contract_version"),
        "checkpoints":x.get("checkpoints") or {}
    }


def run():
    now=datetime.now(timezone.utc); now_s=now.isoformat()
    state=_load(DATA/"discovery-state.json",{})
    tokens=state.get("tokens") if isinstance(state,dict) and isinstance(state.get("tokens"),dict) else {}
    old=_load(DATA/"outcome-tracker.json",{})
    old_records=old.get("tokens") if isinstance(old,dict) and isinstance(old.get("tokens"),dict) else {}
    live_by_pair, live_token_pairs, identity_rejected = _snapshot_sources()
    records=dict(old_records); seeded=updated=0; recoverable_multi_pool=0; quarantined_non_executable=0

    for state_key,meta in tokens.items():
        if not isinstance(meta,dict): continue
        try: entry=float(meta.get("entry_price_usd") or 0)
        except Exception: entry=0.0
        if entry<=0: continue
        chain=meta.get("chain"); token=meta.get("token")
        if not chain or not token: continue
        canonical_key=_key(chain,token)
        rec=records.get(state_key) if isinstance(records.get(state_key),dict) else records.get(canonical_key) if isinstance(records.get(canonical_key),dict) else {}
        if not rec: seeded+=1
        entry_pair=meta.get("entry_pair_address") or rec.get("entry_pair_address")
        tracking_started=meta.get("tracking_started_at") or rec.get("tracking_started_at") or meta.get("first_seen")
        currow=live_by_pair.get(_pair_key(chain,token,entry_pair)) if entry_pair else None
        current=None; verified=False; current_pair=None; non_executable=False
        if isinstance(currow,dict):
            current_pair=currow.get("pair_address")
            if _norm_pair(chain,current_pair)==_norm_pair(chain,entry_pair) and _identity_verified_snapshot(chain, token, currow):
                current=currow.get("price_usd")
                verified=current not in (None,0,0.0) and _finite_positive_price(current)
                non_executable=verified and _explicit_zero_liquidity(currow)
                if non_executable:
                    verified=False
                    quarantined_non_executable+=1
        if entry_pair and not verified and not non_executable and len(live_token_pairs.get(canonical_key,set()))>1:
            recoverable_multi_pool+=1

        history=rec.get("history") if isinstance(rec.get("history"),list) else []
        checkpoints=rec.get("checkpoints") if isinstance(rec.get("checkpoints"),dict) else {}
        peak=float(rec.get("peak_price_usd") or entry); low=float(rec.get("low_price_usd") or entry)
        if non_executable:
            bad_price=float(current)
            history.append({"observed_at":now_s,"price_usd":bad_price,"return_pct":_pct(bad_price,entry),"pair_address":current_pair,"dex":currow.get("dex"),"liquidity_usd":currow.get("liquidity_usd"),"volume_h1":currow.get("volume_h1"),"buys_h1":currow.get("buys_h1"),"sells_h1":currow.get("sells_h1"),"measurement_eligible":False,"token_identity_verified":True,"target_token_side":currow.get("target_token_side"),"price_identity_contract_version":PRICE_IDENTITY_CONTRACT_VERSION,"quarantine_reason":"ZERO_OR_NON_POSITIVE_LIQUIDITY"})
            history=history[-500:]
            current=rec.get("current_price_usd"); ret=rec.get("current_return_pct"); age=rec.get("age_minutes")
        elif verified:
            current=float(current); updated+=1; peak=max(peak,current); low=min(low,current); ret=_pct(current,entry)
            history.append({"observed_at":now_s,"price_usd":current,"return_pct":ret,"pair_address":current_pair,"dex":currow.get("dex"),"liquidity_usd":currow.get("liquidity_usd"),"volume_h1":currow.get("volume_h1"),"buys_h1":currow.get("buys_h1"),"sells_h1":currow.get("sells_h1"),"measurement_eligible":True,"token_identity_verified":True,"target_token_side":currow.get("target_token_side") or "BASE_LEGACY_VERIFIED","price_identity_contract_version":PRICE_IDENTITY_CONTRACT_VERSION})
            history=history[-500:]
            start=_dt(tracking_started); age=max(0.0,(now-start).total_seconds()/60.0) if start else 0.0
            for mins,label in HORIZONS:
                if age>=mins and label not in checkpoints:
                    checkpoints[label]={"price_usd":current,"return_pct":ret,"captured_at":now_s,"pair_address":current_pair,"price_identity_contract_version":PRICE_IDENTITY_CONTRACT_VERSION}
        else:
            # Old pair-only measurements are never carried forward as VERIFIED.
            current=rec.get("current_price_usd"); ret=rec.get("current_return_pct"); age=rec.get("age_minutes")

        target_key=state_key if state_key in records or canonical_key not in records else canonical_key
        records[target_key]={**rec,"chain":chain,"token":token,"first_seen":meta.get("first_seen") or rec.get("first_seen"),
            "tracking_started_at":tracking_started,"legacy_price_tracking":bool(meta.get("legacy_price_tracking",rec.get("legacy_price_tracking",False))),
            "entry_price_usd":entry,"entry_pair_address":entry_pair,"entry_dex":meta.get("entry_dex") or rec.get("entry_dex"),
            "pair_identity_status":"LOCKED" if entry_pair else "LEGACY_MISSING_IMMUTABLE_PAIR",
            "current_pair_address":current_pair if (verified or non_executable) else rec.get("current_pair_address"),"current_price_usd":current,
            "current_return_pct":ret,"peak_price_usd":peak,"peak_return_pct":_pct(peak,entry),"low_price_usd":low,
            "low_return_pct":_pct(low,entry),"age_minutes":round(age,2) if isinstance(age,(int,float)) else age,
            "checkpoints":checkpoints,"history":history,"updated_at":now_s if (verified or non_executable) else rec.get("updated_at"),
            "measurement_status":"QUARANTINED_NON_EXECUTABLE_PRICE" if non_executable else ("VERIFIED_EXACT_PAIR" if verified else ("AWAITING_IDENTITY_VERIFIED_EXACT_PAIR" if entry_pair else "LEGACY_UNVERIFIABLE_PAIR")),
            "price_identity_contract_version":PRICE_IDENTITY_CONTRACT_VERSION if (verified or non_executable) else None,
            "measurement_quarantine_reason":"ZERO_OR_NON_POSITIVE_LIQUIDITY" if non_executable else (None if verified else "TOKEN_IDENTITY_OR_CURRENT_PAIR_NOT_VERIFIED")}

    if not records and old_records: records=old_records
    verified=[x for x in records.values() if x.get("measurement_status")=="VERIFIED_EXACT_PAIR" and x.get("price_identity_contract_version")==PRICE_IDENTITY_CONTRACT_VERSION and x.get("current_return_pct") is not None]
    positive=sum(1 for x in verified if float(x.get("current_return_pct") or 0)>0); negative=sum(1 for x in verified if float(x.get("current_return_pct") or 0)<0); flat=len(verified)-positive-negative
    all_investment=float(len(records)); verified_investment=float(len(verified)); verified_value=round(sum(1.0+float(x.get("current_return_pct") or 0)/100.0 for x in verified),6)
    verified_profit=round(verified_value-verified_investment,6); verified_roi=round((verified_profit/verified_investment)*100.0,4) if verified_investment else None
    unverified=max(0,len(records)-len(verified))
    payload={"version":8,"method":"IMMUTABLE_PERFORMANCE_SINCE_DISCOVERY_EXACT_PAIR_TOKEN_IDENTITY_V2","updated_at":now_s,"tracked_tokens":len(records),"seeded_from_discovery_state":seeded,"updated_this_run":updated,"verified_positive_now":positive,"verified_negative_now":negative,"verified_flat_now":flat,"quarantined_non_executable_now":quarantined_non_executable,"identity_rejected_source_rows":identity_rejected,"price_identity_contract_version":PRICE_IDENTITY_CONTRACT_VERSION,"exact_pair_index_mode":"CHAIN_TOKEN_PAIR_CASE_SAFE","multi_pool_tokens_seen":sum(1 for v in live_token_pairs.values() if len(v)>1),"anti_erasure_rule":"NON_EMPTY_TRACK_RECORD_MAY NEVER BE REPLACED BY EMPTY OUTPUT","valuation_rule":"CURRENT P/L REQUIRES EXACT PAIR + TARGET TOKEN SIDE IDENTITY. PAIR-ONLY OR LEGACY QUOTE-SIDE PRICES ARE WITHHELD.","tokens":records}
    _write(DATA/"outcome-tracker.json",payload); _write(DATA/"signal-outcomes.json",list(records.values()))
    leaders=sorted((_leader_row(x) for x in verified),key=lambda x:float(x.get("current_return_pct") or 0),reverse=True); win_rate=round(positive/(positive+negative)*100,2) if positive+negative else 0.0
    leaderboard={"updated_at":now_s,"verified_count":len(leaders),"verified_winners":positive,"verified_losers":negative,"verified_flat":flat,"quarantined_non_executable_now":quarantined_non_executable,"identity_rejected_source_rows":identity_rejected,"price_identity_contract_version":PRICE_IDENTITY_CONTRACT_VERSION,"win_rate_pct":win_rate,"best_current_return_pct":leaders[0].get("current_return_pct") if leaders else None,"best_peak_return_pct":max((float(x.get("peak_return_pct") or 0) for x in leaders),default=None),"all_discoveries_hypothetical_investment_usd":all_investment,"verified_cohort_investment_usd":verified_investment,"verified_cohort_current_value_usd":verified_value,"verified_cohort_profit_usd":verified_profit,"verified_cohort_roi_pct":verified_roi,"unverified_or_not_currently_measurable_count":unverified,"portfolio_rule":"$1 AT IMMUTABLE DISCOVERY ENTRY; CURRENT P/L ONLY COUNTED WHEN EXACT PAIR AND TARGET TOKEN IDENTITY ARE CURRENTLY VERIFIED","rows":leaders}
    _write(DATA/"performance-leaderboard.json",leaderboard)
    _write(DATA/"performance-measurement-report.json",{"updated_at":now_s,"tracked_tokens":len(records),"seeded":seeded,"updated":updated,"verified_positive_now":positive,"verified_negative_now":negative,"verified_flat_now":flat,"verified_exact_pair_now":len(verified),"quarantined_non_executable_now":quarantined_non_executable,"identity_rejected_source_rows":identity_rejected,"price_identity_contract_version":PRICE_IDENTITY_CONTRACT_VERSION,"win_rate_pct":win_rate,"legacy_missing_pair":sum(1 for x in records.values() if x.get("pair_identity_status")!="LOCKED"),"exact_pair_index_mode":"CHAIN_TOKEN_PAIR_CASE_SAFE","multi_pool_tokens_seen":sum(1 for v in live_token_pairs.values() if len(v)>1),"all_discoveries_hypothetical_investment_usd":all_investment,"verified_cohort_investment_usd":verified_investment,"verified_cohort_current_value_usd":verified_value,"verified_cohort_profit_usd":verified_profit,"verified_cohort_roi_pct":verified_roi,"unverified_or_not_currently_measurable_count":unverified})
    print(json.dumps({"tracked_tokens":len(records),"updated_this_run":updated,"verified_exact_pair_now":len(verified),"identity_rejected_source_rows":identity_rejected,"quarantined_non_executable_now":quarantined_non_executable,"multi_pool_tokens_seen":sum(1 for v in live_token_pairs.values() if len(v)>1),"win_rate_pct":win_rate},indent=2))
    return payload


if __name__=="__main__": run()
