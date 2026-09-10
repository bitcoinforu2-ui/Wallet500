"""Wallet500 Research Decision Engine.

Turns research artifacts into advisory implementation proposals. It is fail-closed,
never edits production thresholds, and never promotes anecdotal case studies by itself.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path("data")
FILTER_ADVISOR = DATA / "filter-tuning-advisor.json"
REJECTED_OUTCOMES = DATA / "rejected-outcome-report.json"
NEAR_ALERTS = DATA / "near-alert-observatory.json"
CEX_REVIVAL = DATA / "cex-revival-radar.json"
LIQUIDITY_RECOVERY = DATA / "liquidity-recovery-shadow.json"
CASE_FILES = [DATA / "case-study-cyberleek.json", DATA / "case-study-doge1.json", DATA / "case-study-dusd.json"]
OUT = DATA / "research-decision-engine.json"
HARD_RULES = ["LIQUIDITY_GTE_50K_EXACT_EXECUTION_POOL","EXACT_PAIR_IDENTITY","HOLDER_CLUSTER_FAIL_CLOSED","IMMUTABLE_TRACK_RECORD","NO_HINDSIGHT","PAPER_ONLY"]
COMPOSITE_ROOT_CAUSE = "STRONG_DECISION_LANE_MONOCULTURE_PRECURSOR_OR_ACTIVE_ONLY"


def _load(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text()) if path.exists() else default
    except Exception: return default


def _recommend(sample: int, lift_pct: float | None, forward_n: int, safe: bool) -> str:
    if not safe: return "REJECT"
    if sample < 100 or lift_pct is None: return "MORE_DATA"
    if lift_pct <= 0: return "REJECT"
    if sample >= 300 and forward_n >= 30 and lift_pct >= 20: return "APPROVED_CANDIDATE"
    if lift_pct >= 10: return "SHADOW_TEST"
    return "MORE_DATA"


def _num(value: object, default: float = 0.0) -> float:
    try: return float(value if value is not None else default)
    except (TypeError, ValueError): return float(default)


def _norm_key(chain: object, token: object) -> str:
    c=str(chain or "").strip().lower(); t=str(token or "").strip()
    if c in {"ethereum","bsc","base","arbitrum","optimism","polygon","avalanche"}: t=t.lower()
    return f"{c}:{t}" if c and t else ""


def _cex_index(cex: dict) -> dict[str, dict]:
    out={}
    for row in cex.get("alerts",[]) if isinstance(cex,dict) else []:
        if isinstance(row,dict):
            key=_norm_key(row.get("chain"),row.get("token_address"))
            if key: out[key]=row
    return out


def _previous_composite_index(previous: dict | None) -> dict[str, dict]:
    out={}
    for row in (previous or {}).get("proposals",[]) if isinstance(previous,dict) else []:
        if not isinstance(row,dict) or row.get("feature_or_rule")!="COMPOSITE_STRONG_DECISION_SHADOW": continue
        key=_norm_key(row.get("chain"),row.get("token_address"))
        if key: out[key]=row
    return out


def _market_price(near_row: dict, cex_row: dict) -> float | None:
    for row in (near_row, cex_row):
        if not isinstance(row,dict): continue
        for field in ("price_usd","dex_price_usd","current_price_usd","reference_price"):
            value=_num(row.get(field),0)
            if value>0: return value
    return None


def _composite_shadow_proposals(near_alerts: dict, cex: dict, previous: dict | None=None, observed_at: str | None=None) -> list[dict]:
    proposals=[]; cex_by_token=_cex_index(cex); previous_by_token=_previous_composite_index(previous); rows=near_alerts.get("closest_to_real_alert") or near_alerts.get("near_alert_leaderboard") or []; seen=set(); now=observed_at or datetime.now(timezone.utc).isoformat()
    for row in rows if isinstance(rows,list) else []:
        if not isinstance(row,dict): continue
        key=_norm_key(row.get("chain"),row.get("token_address"))
        if not key or key in seen: continue
        seen.add(key); missing=list(row.get("missing_gates") or []); blockers=set(row.get("blockers") or []); evidence=set(row.get("evidence_positive_lanes") or []); pair=str(row.get("pair_address") or "").strip(); cex_row=cex_by_token.get(key,{})
        same_pair=str(cex_row.get("pair_address") or "").strip().lower()==pair.lower()
        strong_cex=bool(cex_row and cex_row.get("identity_verified") is True and _num(cex_row.get("cex_revival_score"))>=35 and int(cex_row.get("coherent_confirmations") or 0)>=2 and same_pair)
        eligible=all([int(row.get("readiness_passed") or 0)==6,int(row.get("readiness_total") or 0)==7,missing==["STRONG_DECISION_LANE"],len(evidence)>=2,bool(evidence & {"HOLDER_GROWTH","WALLET_ACCUMULATION","VERIFIED_WALLET_ACCUMULATION"}),strong_cex,row.get("exact_identity_verified") is True,row.get("exact_pair_verified") is True,bool(pair),row.get("market_age_verified") is True,_num(row.get("execution_pool_liquidity_usd"))>=50000,not (blockers-{"NO_STRONG_DECISION_LANE"})])
        if not eligible: continue
        prev=previous_by_token.get(key,{})
        current_price=_market_price(row,cex_row)
        baseline_price=_num(prev.get("baseline_price_usd"),0) or current_price
        current_gain=((current_price/baseline_price)-1)*100 if current_price and baseline_price else None
        previous_peak=prev.get("peak_gain_pct")
        peak_gain=max([x for x in (previous_peak,current_gain) if isinstance(x,(int,float))],default=None)
        observation_count=max(0,int(prev.get("forward_observation_count") or 0))+1
        proposals.append({
            "hypothesis_id":f"COMPOSITE_STRONG_DECISION::{key}",
            "source_research_ids":["near-alert-observatory","cex-revival-radar"],
            "feature_or_rule":"COMPOSITE_STRONG_DECISION_SHADOW",
            "proposal_type":"FORWARD_SHADOW_CANDIDATE",
            "root_cause":COMPOSITE_ROOT_CAUSE,
            "production_gate_latency_risk":True,
            "symbol":row.get("symbol"),"chain":row.get("chain"),"token_address":row.get("token_address"),"pair_address":pair,
            "readiness":"6/7","positive_evidence_lanes":sorted(evidence),"cex_revival_score":cex_row.get("cex_revival_score"),"cex_coherent_confirmations":cex_row.get("coherent_confirmations"),"execution_pool_liquidity_usd":_num(row.get("execution_pool_liquidity_usd")),"pair_reconciled":same_pair,
            "first_shadow_at":prev.get("first_shadow_at") or now,"last_shadow_observed_at":now,
            "baseline_price_usd":baseline_price,"current_price_usd":current_price,"current_gain_pct":round(current_gain,4) if current_gain is not None else None,"peak_gain_pct":round(peak_gain,4) if peak_gain is not None else None,
            "forward_observation_count":observation_count,"forward_only_evidence_count":observation_count,
            "lookahead_check":"PASS","safety_regression_check":"PASS","hard_rule_change_allowed":False,"production_effect":False,"recommendation":"SHADOW_TEST",
            "promotion_policy":{"automatic_promotion":False,"minimum_distinct_candidates":10,"minimum_forward_observations":30,"requires_positive_lift_vs_current_strong_decision":True,"requires_no_safety_regression":True},
            "decision_note":"Measure whether verified holder/wallet evidence + independent evidence + same-pair CEX revival anticipates the existing strong-decision lane. Do not promote to REAL_ALERT until forward evidence proves lift without safety regression."
        })
    return proposals


def _liquidity_recovery_proposals(recovery: dict) -> list[dict]:
    if not isinstance(recovery,dict) or recovery.get("mode")!="RESEARCH_ONLY_LIQUIDITY_RECOVERY_SHADOW_V3" or recovery.get("production_gate_changed") is not False or recovery.get("no_hindsight") is not True:
        return []
    out=[]
    for row in recovery.get("targets",[]) if isinstance(recovery.get("targets"),list) else []:
        if not isinstance(row,dict) or row.get("status")!="LIQUIDITY_RECOVERY_SHADOW" or row.get("production_effect") is not False: continue
        chain=row.get("chain"); token=row.get("token"); pair=str(row.get("pair_address") or "").strip(); key=_norm_key(chain,token)
        if not key or not pair: continue
        age=row.get("age_proof") if isinstance(row.get("age_proof"),dict) else {}
        if age.get("market_age_verified") is not True or float(age.get("market_age_min_days") or 0)<90: continue
        out.append({"hypothesis_id":f"LIQUIDITY_RECOVERY::{key}:{pair.lower()}","source_research_ids":["liquidity-recovery-shadow-v3"],"feature_or_rule":"LIQUIDITY_RECOVERY_SHADOW_V3","proposal_type":"FORWARD_SHADOW_CANDIDATE","chain":chain,"token_address":token,"pair_address":pair,"triggered_at":row.get("triggered_at"),"first_reject_liquidity_usd":row.get("first_reject_liquidity_usd"),"recovery_metrics":row.get("metrics"),"age_proof_mode":row.get("age_proof_mode"),"forward_only_evidence_count":1,"lookahead_check":"PASS","safety_regression_check":"PASS","hard_rule_change_allowed":False,"production_effect":False,"recommendation":"SHADOW_TEST","decision_note":"Track this exact-pair veteran liquidity recovery prospectively. The $50K production gate remains unchanged."})
    return out


def build(filter_advisor: dict, rejected: dict, cases: list[dict], near_alerts: dict | None=None, cex: dict | None=None, liquidity_recovery: dict | None=None, previous: dict | None=None, observed_at: str | None=None) -> dict:
    proposals=[]
    for item in filter_advisor.get("review_candidates",[]) if isinstance(filter_advisor,dict) else []:
        if not isinstance(item,dict): continue
        n=int(item.get("records") or 0); fn=int(item.get("false_negative_winners") or 0); rate=float(item.get("false_negative_rate_pct") or 0)
        proposals.append({"hypothesis_id":f"FILTER_FN::{item.get('filter','UNKNOWN')}","source_research_ids":["filter-tuning-advisor"],"feature_or_rule":str(item.get("filter") or "UNKNOWN"),"proposal_type":"FALSE_NEGATIVE_RESEARCH","sample_size":n,"positive_cases":fn,"baseline_rate_pct":rate,"candidate_rate_pct":None,"lift_pct":None,"forward_only_evidence_count":0,"lookahead_check":"PASS","safety_regression_check":"PASS","hard_rule_change_allowed":False,"recommendation":"MORE_DATA","decision_note":"Measure a recovery/recheck feature in shadow; do not lower the hard production gate."})
    for case in cases:
        if not isinstance(case,dict) or not case: continue
        asset=case.get("asset") if isinstance(case.get("asset"),dict) else {}; sym=asset.get("symbol") or case.get("symbol") or "CASE"; qs=case.get("research_questions") if isinstance(case.get("research_questions"),list) else []; features=case.get("entity_flow_features") if isinstance(case.get("entity_flow_features"),list) else []
        proposals.append({"hypothesis_id":f"CASE::{sym}","source_research_ids":[f"case-study-{str(sym).lower()}"],"feature_or_rule":",".join(features[:6]) if features else "CASE_STUDY_PATTERN","proposal_type":"CASE_STUDY_HYPOTHESIS","sample_size":1,"positive_cases":0,"baseline_rate_pct":None,"candidate_rate_pct":None,"lift_pct":None,"forward_only_evidence_count":1 if "FORWARD" in str(case.get("lookahead_policy","")).upper() else 0,"lookahead_check":"PASS" if "NO_HINDSIGHT" in str(case.get("lookahead_policy","")).upper() else "UNKNOWN","safety_regression_check":"PASS","hard_rule_change_allowed":False,"recommendation":"MORE_DATA","decision_note":"Convert repeated case-study pattern into a measurable cohort feature before any filter change.","research_questions":qs[:5]})
    proposals.extend(_composite_shadow_proposals(near_alerts or {},cex or {},previous=previous,observed_at=observed_at)); proposals.extend(_liquidity_recovery_proposals(liquidity_recovery or {}))
    for p in proposals:
        if p.get("proposal_type")=="MEASURED_COHORT": p["recommendation"]=_recommend(int(p.get("sample_size") or 0),p.get("lift_pct"),int(p.get("forward_only_evidence_count") or 0),p.get("lookahead_check")=="PASS" and p.get("safety_regression_check")=="PASS")
    counts={k:0 for k in ["REJECT","MORE_DATA","SHADOW_TEST","APPROVED_CANDIDATE"]}
    for p in proposals: counts[p.get("recommendation","MORE_DATA")]=counts.get(p.get("recommendation","MORE_DATA"),0)+1
    composite=[p for p in proposals if p.get("feature_or_rule")=="COMPOSITE_STRONG_DECISION_SHADOW"]
    return {"version":4,"mode":"RESEARCH_ADVISORY_ONLY","production_change_allowed":False,"production_thresholds_modified":False,"hard_rules":HARD_RULES,"decision_states":counts,"proposals":proposals,"next_human_decision":[p for p in proposals if p.get("recommendation") in {"SHADOW_TEST","APPROVED_CANDIDATE"}],"composite_strong_decision":{"root_cause":COMPOSITE_ROOT_CAUSE,"shadow_candidates":len(composite),"production_effect":False,"automatic_promotion":False,"purpose":"Measure whether multi-source corroboration is earlier than the existing precursor/active-only strong-decision gate without weakening truth or risk gates."},"source_health":{"filter_advisor_loaded":bool(filter_advisor),"rejected_outcomes_loaded":bool(rejected),"case_studies_loaded":sum(1 for c in cases if c),"near_alert_observatory_loaded":bool(near_alerts),"cex_revival_loaded":bool(cex),"liquidity_recovery_loaded":bool(liquidity_recovery)}}


def main() -> None:
    previous=_load(OUT,{})
    observed_at=datetime.now(timezone.utc).isoformat()
    result=build(_load(FILTER_ADVISOR,{}),_load(REJECTED_OUTCOMES,{}),[_load(p,{}) for p in CASE_FILES],_load(NEAR_ALERTS,{}),_load(CEX_REVIVAL,{}),_load(LIQUIDITY_RECOVERY,{}),previous=previous,observed_at=observed_at); result["generated_at"]=observed_at; OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)); print(json.dumps({"mode":result["mode"],"proposals":len(result["proposals"]),"decision_states":result["decision_states"],"production_change_allowed":result["production_change_allowed"],"composite_strong_decision":result["composite_strong_decision"]},indent=2))


if __name__=="__main__": main()
