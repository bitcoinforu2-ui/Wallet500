from __future__ import annotations
import json
from pathlib import Path

from .solana_mintability_gate import enforce_active

MIN_TRADABLE_LIQUIDITY_USD = 50_000.0
MAX_LIQUIDITY_DROP_FROM_PREV = 0.45
MAX_LIQUIDITY_DROP_FROM_OBSERVED_PEAK = 0.70
YOUNG_TOKEN_MINUTES = 60.0
EXTREME_TURNOVER = 8.0
HIGH_TURNOVER = 4.0
SELL_PRESSURE_RATIO = 0.75
EARLY_LIQUIDITY_RETENTION_WARN = 0.85
INSIDER_WARN_PCT = 20.0
INSIDER_BLOCK_PCT = 35.0
TOP10_WARN_PCT = 50.0
TOP10_BLOCK_PCT = 70.0

def _load(path: Path, default):
    try: return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception: return default

def _write(path: Path, payload): path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
def _key(chain, token): return f"{chain}:{(token or '').lower() if chain in {'ethereum','bsc'} else (token or '')}"
def _f(row, *names):
    for name in names:
        try:
            v=row.get(name)
            if v is not None: return float(v)
        except Exception: pass
    return 0.0

def _current_execution_liquidity(candidate):
    """Liquidity used for the $50K gate.

    Prefer the explicit deepest exact-token execution-pool measurement emitted by
    the identity resolver. `dex_total_liquidity_usd` is intentionally excluded:
    aggregate token TVL is useful context but cannot make an individually thin
    executable pool tradable.
    """
    return _f(candidate, 'execution_pool_liquidity_usd', 'live_liquidity_usd', 'liquidity_usd', 'dex_liquidity_usd')

def _history_metrics(candidate, outcomes):
    rec=((outcomes or {}).get('tokens') or {}).get(_key(candidate.get('chain'),candidate.get('token') or candidate.get('mint') or candidate.get('token_address') or ''),{}) or {}
    history=rec.get('history') if isinstance(rec.get('history'),list) else []
    ls=[_f(x,'execution_pool_liquidity_usd','liquidity_usd') for x in history if _f(x,'execution_pool_liquidity_usd','liquidity_usd')>0]
    current=_current_execution_liquidity(candidate)
    previous=ls[-2] if len(ls)>=2 else (ls[-1] if ls else 0.0)
    peak=max(ls+([current] if current>0 else []),default=0.0)
    return {'current':current,'previous':previous,'peak':peak,'history_points':len(history)}

def _concentration(candidate):
    insider=_f(candidate,'deployer_linked_supply_pct','insider_cluster_pct','creator_linked_supply_pct','deployer_supply_pct')
    top10=_f(candidate,'top10_holder_pct','top_10_holder_pct','top10_concentration_pct','top_holder_concentration_pct')
    verified=any(candidate.get(k) is True for k in ('holder_cluster_verified','holder_verification_complete','verification_complete'))
    signals=[]; critical=[]
    if not verified: signals.append('HOLDER_CLUSTER_NOT_VERIFIED')
    if insider>=INSIDER_BLOCK_PCT: critical.append('INSIDER_LINKED_SUPPLY_GE_35PCT_DRAIN_RISK')
    elif insider>=INSIDER_WARN_PCT: signals.append('INSIDER_LINKED_SUPPLY_GE_20PCT')
    if top10>=TOP10_BLOCK_PCT: critical.append('TOP10_SUPPLY_GE_70PCT_DRAIN_RISK')
    elif top10>=TOP10_WARN_PCT: signals.append('TOP10_SUPPLY_GE_50PCT')
    return {'verified':verified,'insider_pct':insider or None,'top10_pct':top10 or None,'signals':signals,'critical':critical}

def _pre_rug_signature(candidate,current,previous):
    volume=_f(candidate,'live_volume_h1','volume_h1'); buys=_f(candidate,'live_buys_h1','buys_h1'); sells=_f(candidate,'live_sells_h1','sells_h1')
    age=_f(candidate,'age_minutes','pair_age_minutes','token_age_minutes'); turnover=volume/current if current>0 else 0.0
    sell_buy=sells/buys if buys>0 else (999.0 if sells>0 else 0.0); retention=current/previous if previous>0 else None
    lp_verified=candidate.get('lp_verified') is True or candidate.get('liquidity_lock_verified') is True
    signals=[]
    if age and age<=YOUNG_TOKEN_MINUTES: signals.append('VERY_YOUNG_PAIR')
    if turnover>=EXTREME_TURNOVER: signals.append('EXTREME_VOLUME_TO_LIQUIDITY_TURNOVER')
    elif turnover>=HIGH_TURNOVER: signals.append('HIGH_VOLUME_TO_LIQUIDITY_TURNOVER')
    if sell_buy>=SELL_PRESSURE_RATIO: signals.append('SELL_PRESSURE_NEAR_BUY_FLOW')
    if retention is not None and retention<EARLY_LIQUIDITY_RETENTION_WARN: signals.append('LIQUIDITY_ALREADY_RECEDING')
    if not lp_verified: signals.append('LP_REMOVAL_PROTECTION_NOT_VERIFIED')
    danger=(2 if 'EXTREME_VOLUME_TO_LIQUIDITY_TURNOVER' in signals else 1 if 'HIGH_VOLUME_TO_LIQUIDITY_TURNOVER' in signals else 0)+('VERY_YOUNG_PAIR' in signals)+('SELL_PRESSURE_NEAR_BUY_FLOW' in signals)+2*('LIQUIDITY_ALREADY_RECEDING' in signals)+('LP_REMOVAL_PROTECTION_NOT_VERIFIED' in signals)
    return {'turnover_h1':turnover,'sell_buy_ratio_h1':sell_buy,'age_minutes':age or None,'lp_verified':lp_verified,'signals':signals,'danger_score':int(danger),'pre_rug_block':danger>=5,'exit_warning':danger>=4}

def evaluate(candidate,outcomes):
    m=_history_metrics(candidate,outcomes); current,previous,peak=m['current'],m['previous'],m['peak']; critical=[]; reasons=[]
    if current<MIN_TRADABLE_LIQUIDITY_USD: critical.append('EXECUTION_POOL_LIQUIDITY_BELOW_50K_HARD_BLOCK')
    if previous>=MIN_TRADABLE_LIQUIDITY_USD and current>0:
        rp=current/previous
        if rp<=MAX_LIQUIDITY_DROP_FROM_PREV: critical.append('LIQUIDITY_EVACUATION_GT_55PCT_ONE_OBSERVATION')
        elif rp<0.70: reasons.append('LIQUIDITY_RETENTION_LT_70PCT_ONE_OBSERVATION')
    elif previous>=MIN_TRADABLE_LIQUIDITY_USD and current<=0: critical.append('LIQUIDITY_EVACUATION_TO_ZERO')
    retention_peak=current/peak if peak>=MIN_TRADABLE_LIQUIDITY_USD and current>0 else None
    if retention_peak is not None:
        if retention_peak<=0.10: critical.append('LIQUIDITY_COLLAPSE_GT_90PCT_FROM_OBSERVED_PEAK')
        elif retention_peak<MAX_LIQUIDITY_DROP_FROM_OBSERVED_PEAK: reasons.append('LIQUIDITY_RETENTION_LT_70PCT_FROM_OBSERVED_PEAK')
    if peak>=MIN_TRADABLE_LIQUIDITY_USD and current<MIN_TRADABLE_LIQUIDITY_USD: reasons.append('TRADABLE_LIQUIDITY_LOST_AFTER_PREVIOUS_50K_PLUS')
    sig=_pre_rug_signature(candidate,current,previous); conc=_concentration(candidate)
    if sig['pre_rug_block']: critical.append('PRE_RUG_COMPOSITE_SIGNATURE_HARD_BLOCK')
    elif sig['exit_warning']: reasons.append('PRE_RUG_COMPOSITE_EXIT_WARNING')
    critical.extend(conc['critical']); reasons.extend(sig['signals']); reasons.extend(conc['signals'])
    blocked=bool(critical)
    return {**candidate,'production_risk_gate':'BLOCKED' if blocked else ('CAUTION' if reasons else 'PASS'),'production_risk_blocked':blocked,'production_risk_critical':list(dict.fromkeys(critical)),'production_risk_reasons':list(dict.fromkeys(critical+reasons)),'production_live_liquidity_usd':current,'production_execution_pool_liquidity_usd':current,'production_liquidity_gate_metric':'EXECUTION_POOL_LIQUIDITY_USD','production_dex_total_liquidity_usd':candidate.get('dex_total_liquidity_usd'),'production_previous_liquidity_usd':previous or None,'production_peak_observed_liquidity_usd':peak or None,'production_liquidity_retention_from_peak':round(retention_peak,6) if retention_peak is not None else None,'production_history_points':m['history_points'],'pre_rug_danger_score':sig['danger_score'],'pre_rug_exit_warning':sig['exit_warning'],'pre_rug_turnover_h1':round(sig['turnover_h1'],6),'pre_rug_sell_buy_ratio_h1':round(sig['sell_buy_ratio_h1'],6),'pre_rug_signals':sig['signals'],'lp_removal_protection_verified':sig['lp_verified'],'liquidity_drain_holder_cluster_verified':conc['verified'],'liquidity_drain_insider_linked_supply_pct':conc['insider_pct'],'liquidity_drain_top10_supply_pct':conc['top10_pct'],'liquidity_drain_signals':conc['signals']+conc['critical']}

def apply(output_dir='data'):
    out=Path(output_dir)
    # Solana candidates are removed before any production scoring unless the
    # on-chain mint account proves mintAuthority == null. Unknown also fails closed.
    enforce_active(out)
    outcomes=_load(out/'outcome-tracker.json',{}); active=_load(out/'active-qualified-candidates.json',[]); watch=_load(out/'watchlist.json',[]); existing=_load(out/'pump-dump-risk.json',[]); summary=_load(out/'run-summary.json',{})
    evaluations=[evaluate(x,outcomes) for x in active]; passed=[x for x in evaluations if not x.get('production_risk_blocked')]; blocked=[x for x in evaluations if x.get('production_risk_blocked')]
    passed_keys={(_key(x.get('chain'),x.get('token') or x.get('mint') or x.get('token_address') or '')) for x in passed}
    filtered=[x for x in watch if x.get('watch_source')!='QUALIFIED_ANOMALY' or _key(x.get('chain'),x.get('token') or x.get('mint') or x.get('token_address') or '') in passed_keys]
    merged={}
    for x in (existing if isinstance(existing,list) else [])+blocked:
        if x.get('chain') and (x.get('token') or x.get('mint') or x.get('token_address')): merged[_key(x.get('chain'),x.get('token') or x.get('mint') or x.get('token_address') or '')]=x
    _write(out/'active-qualified-candidates.json',passed); _write(out/'watchlist.json',filtered); _write(out/'production-risk-evaluations.json',evaluations); _write(out/'production-risk-blocked.json',blocked); _write(out/'pump-dump-risk.json',list(merged.values()))
    if isinstance(summary,dict):
        summary['production_risk_gate']={'min_execution_pool_liquidity_usd':50000,'min_live_liquidity_usd':50000,'liquidity_gate_metric':'EXECUTION_POOL_LIQUIDITY_USD','dex_total_liquidity_is_informational_only':True,'active_before_gate':len(active),'active_after_gate':len(passed),'blocked_now':len(blocked),'exit_warnings_now':sum(bool(x.get('pre_rug_exit_warning')) for x in evaluations),'hard_rule':'DEEPEST_VERIFIED_EXACT_TOKEN_EXECUTION_POOL_MUST_REMAIN_GE_50K','solana_mintability_rule':'MINT_AUTHORITY_MUST_BE_REVOKED_NULL; UNKNOWN_FAILS_CLOSED','evacuation_rule':'LOSS_OF_EXECUTABLE_LIQUIDITY_OVERRIDES PRICE VOLUME BUYS AND ANOMALY SCORE','lp_rule':'LP LOCK ONLY PROTECTS AGAINST LP REMOVAL; IT DOES NOT PROTECT QUOTE-SIDE LIQUIDITY FROM INSIDER/HOLDER DUMP DRAIN','drain_rule':'HOLDER/CLUSTER CONCENTRATION IS A SEPARATE REQUIRED DRAIN-RISK CONTROL; >=35% LINKED INSIDER OR >=70% TOP10 IS HARD BLOCK WHEN VERIFIED DATA IS PRESENT.'}; summary['active_qualified']=len(passed); summary['watchlist']=len(filtered); _write(out/'run-summary.json',summary)
    result={'active_before_gate':len(active),'active_after_gate':len(passed),'blocked_now':len(blocked),'watchlist':len(filtered)}; print(json.dumps(result,indent=2)); return result
if __name__=='__main__': apply()
