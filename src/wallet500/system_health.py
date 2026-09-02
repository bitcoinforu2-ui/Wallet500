from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from .config import Settings


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _age_seconds(ts, now):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _diagnose(name, check, now):
    status = check.get('status', 'DEGRADED')
    diag = {'failure_code':'OK','severity':'INFO','blocks_production':False,'expected':None,'actual':None,'recommended_action':'NONE','diagnosed_at':now.isoformat()}
    if status == 'HEALTHY': return {**check, **diag}
    if name == 'primary_scan':
        diag.update(failure_code='SCAN_STALE_OR_TIMESTAMP_MISSING',severity='HIGH',blocks_production=True,expected={'max_age_seconds':check.get('max_age_seconds')},actual={'age_seconds':check.get('age_seconds')},recommended_action='CHECK_LIVE_SCAN_WORKFLOW_AND_RUN_SUMMARY_TIMESTAMP')
    elif name == 'publish_pipeline':
        diag.update(failure_code='PUBLISH_EVIDENCE_STALE_OR_MISSING',severity='HIGH',blocks_production=False,expected={'max_age_seconds':check.get('max_age_seconds'),'status':'READY_TO_PUBLISH'},actual={'age_seconds':check.get('age_seconds'),'status':check.get('evidence_status'),'source_sha':check.get('source_sha'),'run_id':check.get('run_id')},recommended_action='CHECK_STRICT_VALIDATION_AND_PUBLISH_STEP')
    elif name in {'old_coin_revival','new_token_lab'}:
        diag.update(failure_code=f'{name.upper()}_LANE_{status}',severity='MEDIUM',expected='HEALTHY',actual=status,recommended_action='CHECK_LANE_SOURCE_HEALTH_AND_LAST_SUCCESSFUL_FETCH')
    elif name == 'holder_cluster_fail_closed':
        diag.update(failure_code='HOLDER_CLUSTER_FAIL_CLOSED_DISABLED',severity='CRITICAL',blocks_production=True,expected='PRODUCTION_FAIL_CLOSED',actual=check.get('mode'),recommended_action='RESTORE_FAIL_CLOSED_BEFORE_PRODUCTION')
    elif name == 'liquidity_policy':
        diag.update(failure_code='LIQUIDITY_POLICY_BELOW_VERIFIED_MIN',severity='CRITICAL',blocks_production=True,expected={'min_usd':check.get('configured_min_usd')},actual={'qualification_min_liquidity_usd':check.get('qualification_min_usd'),'production_min_usd':check.get('production_min_usd')},recommended_action='RESTORE_MINIMUM_LIQUIDITY_POLICY')
    elif name == 'holder_cluster_evidence_coverage':
        if status == 'FAILED':
            diag.update(failure_code='HOLDER_CLUSTER_ACCOUNTING_MISMATCH',severity='CRITICAL',blocks_production=True,expected={'accounted_count':check.get('input_count')},actual={'accounted_count':check.get('promoted_count',0)+check.get('quarantine_count',0)+check.get('blocked_count',0)},recommended_action='INSPECT_HOLDER_CLUSTER_ACCOUNTING_INVARIANT')
        else:
            diag.update(failure_code=check.get('reason') or 'HOLDER_CLUSTER_EVIDENCE_INCOMPLETE',severity='HIGH',blocks_production=False,expected={'promoted_count_min':1,'verification_complete':True},actual={'input_count':check.get('input_count',0),'promoted_count':check.get('promoted_count',0),'quarantine_count':check.get('quarantine_count',0),'blocked_count':check.get('blocked_count',0)},recommended_action='INSPECT_QUARANTINE_REASONS_AND_MISSING_HOLDER_CLUSTER_EVIDENCE')
    elif name == 'wallet_forensics':
        diag.update(failure_code='WALLET_FORENSICS_STALE_OR_COVERAGE_GAP',severity='MEDIUM',expected={'source':'active-qualified-candidates.json','max_age_seconds':3600,'coverage':'active=0 OR seen>0'},actual={'source':check.get('source'),'age_seconds':check.get('age_seconds'),'active_expected':check.get('active_candidates_expected'),'active_seen':check.get('active_candidates_seen')},recommended_action='CHECK_WALLET_EVIDENCE_GATHERING')
    elif name == 'wallet_forensics_capability':
        diag.update(failure_code='WALLET_FORENSICS_CAPABILITY_GAP',severity='HIGH',blocks_production=False,expected={'when_active':'at least one supported-chain candidate scanned and no universal EVM deferral'},actual={'active_expected':check.get('active_candidates_expected'),'active_seen':check.get('active_candidates_seen'),'solana_candidates_scanned':check.get('solana_candidates_scanned'),'evm_candidates_scanned':check.get('evm_candidates_scanned'),'evm_candidates_deferred':check.get('evm_candidates_deferred')},recommended_action='RESTORE_SUPPORTED_CHAIN_FORENSICS_COVERAGE')
    elif name == 'wallet_forensics_evidence_yield':
        diag.update(failure_code='WALLET_FORENSICS_ZERO_VERIFIED_EVIDENCE',severity='MEDIUM',blocks_production=False,expected={'when_active':'verified_wallet_candidates>0'},actual={'active_expected':check.get('active_candidates_expected'),'verified_wallet_candidates':check.get('verified_wallet_candidates'),'evm_verified_wallet_candidates':check.get('evm_verified_wallet_candidates')},recommended_action='INSPECT_EXACT_PAIR_ACTIVITY_WINDOW_OR_RPC_EVIDENCE_YIELD')
    else:
        diag.update(failure_code=f'{name.upper()}_{status}',severity='MEDIUM',actual=status,recommended_action='INSPECT_COMPONENT')
    return {**check, **diag}


def build_health(output_dir='data', now=None):
    cfg=Settings(); out=Path(output_dir); now=now or datetime.now(timezone.utc)
    summary=_load(out/'run-summary.json',{}); holder=_load(out/'holder-cluster-production-report.json',{}); wallet=_load(out/'wallet-forensics-summary.json',{}); publish=_load(out/'publish-evidence.json',{})
    primary_age=_age_seconds(summary.get('updated_at') if isinstance(summary,dict) else None,now); wallet_age=_age_seconds(wallet.get('updated_at') if isinstance(wallet,dict) else None,now); publish_age=_age_seconds(publish.get('created_at') if isinstance(publish,dict) else None,now)
    lane=(summary.get('lane_health') or {}) if isinstance(summary,dict) else {}; prod=(summary.get('production_risk_gate') or {}) if isinstance(summary,dict) else {}
    qualification_floor=float(summary.get('qualification_min_liquidity_usd') or 0) if isinstance(summary,dict) else 0.0; production_floor=float(prod.get('min_live_liquidity_usd') or 0) if isinstance(prod,dict) else 0.0; active=int(summary.get('active_qualified',0) or 0) if isinstance(summary,dict) else 0
    publish_max_age=max(1800,int(cfg.workflow_degraded_seconds)*2)
    checks={'primary_scan':{'status':'HEALTHY' if primary_age is not None and primary_age<=cfg.workflow_degraded_seconds else 'DEGRADED','age_seconds':round(primary_age,1) if primary_age is not None else None,'max_age_seconds':cfg.workflow_degraded_seconds},'publish_pipeline':{'status':'HEALTHY' if publish_age is not None and publish_age<=publish_max_age and publish.get('status')=='READY_TO_PUBLISH' and publish.get('strict_validation')=='PASS' else 'DEGRADED','age_seconds':round(publish_age,1) if publish_age is not None else None,'max_age_seconds':publish_max_age,'evidence_status':publish.get('status'),'strict_validation':publish.get('strict_validation'),'source_sha':publish.get('source_sha'),'run_id':publish.get('run_id'),'proof_rule':'IF_THIS_FILE_IS_VISIBLE_ON_MAIN_THE_VALIDATED_DATA_COMMIT_WAS_PUSHED_SUCCESSFULLY'},'old_coin_revival':{'status':lane.get('old_coin_revival') or 'DEGRADED'},'new_token_lab':{'status':lane.get('new_token_lab') or 'DEGRADED'},'holder_cluster_fail_closed':{'status':'HEALTHY' if holder.get('mode')=='PRODUCTION_FAIL_CLOSED' else 'FAILED','mode':holder.get('mode')}}
    floor_ok=qualification_floor>=cfg.verified_min_liquidity_usd and production_floor>=cfg.verified_min_liquidity_usd
    checks['liquidity_policy']={'status':'HEALTHY' if floor_ok else 'FAILED','configured_min_usd':cfg.verified_min_liquidity_usd,'qualification_min_usd':qualification_floor or None,'production_min_usd':production_floor or None}
    hinput=int(holder.get('input_count',0) or 0); hprom=int(holder.get('promoted_count',0) or 0); hqua=int(holder.get('quarantine_count',0) or 0); hblock=int(holder.get('blocked_count',0) or 0); accounted=hprom+hqua+hblock; evidence_status='FAILED' if hinput!=accounted else ('DEGRADED' if hinput>0 and hqua==hinput else 'HEALTHY')
    checks['holder_cluster_evidence_coverage']={'status':evidence_status,'input_count':hinput,'promoted_count':hprom,'quarantine_count':hqua,'blocked_count':hblock,'reason':'ALL_ACTIVE_CANDIDATES_QUARANTINED_FOR_INCOMPLETE_EVIDENCE' if hinput>0 and hqua==hinput else None}
    source=wallet.get('source') if isinstance(wallet,dict) else None; seen=int(wallet.get('active_candidates_seen',0) or 0) if isinstance(wallet,dict) else 0; verified=int(wallet.get('verified_wallet_candidates',0) or 0) if isinstance(wallet,dict) else 0; sol_scanned=int(wallet.get('solana_candidates_scanned',0) or 0) if isinstance(wallet,dict) else 0; evm_scanned=int(wallet.get('evm_candidates_scanned',0) or 0) if isinstance(wallet,dict) else 0; evm_verified=int(wallet.get('evm_verified_wallet_candidates',0) or 0) if isinstance(wallet,dict) else 0; evm_deferred=int(wallet.get('evm_candidates_deferred',0) or 0) if isinstance(wallet,dict) else 0
    wallet_ok=wallet_age is not None and wallet_age<=3600 and source=='active-qualified-candidates.json' and wallet.get('lane')=='PRE_PRODUCTION_EVIDENCE_GATHERING' and wallet.get('production_authorization') is False and (active==0 or seen>0)
    base_metrics={'active_candidates_expected':active,'active_candidates_seen':seen,'verified_wallet_candidates':verified,'solana_candidates_scanned':sol_scanned,'evm_candidates_scanned':evm_scanned,'evm_verified_wallet_candidates':evm_verified,'evm_candidates_deferred':evm_deferred}
    checks['wallet_forensics']={'status':'HEALTHY' if wallet_ok else 'DEGRADED','age_seconds':round(wallet_age,1) if wallet_age is not None else None,'source':source,**base_metrics}
    supported_scanned=sol_scanned+evm_scanned
    capability_ok=(active==0) or (seen>0 and supported_scanned>0 and evm_deferred<seen)
    checks['wallet_forensics_capability']={'status':'HEALTHY' if capability_ok else 'DEGRADED',**base_metrics,'supported_candidates_scanned':supported_scanned,'interpretation':'PIPELINE_RUNNING_IS_NOT_THE_SAME_AS_SUPPORTED_CHAIN_COVERAGE'}
    yield_ok=(active==0) or verified>0
    checks['wallet_forensics_evidence_yield']={'status':'HEALTHY' if yield_ok else 'DEGRADED',**base_metrics,'interpretation':'SUPPORTED_SCAN_CAN_SUCCEED_WHILE_VERIFIED_WALLET_EVIDENCE_YIELD_IS_ZERO'}
    checks={name:_diagnose(name,check,now) for name,check in checks.items()}
    pipeline_names={'primary_scan','publish_pipeline','old_coin_revival','new_token_lab','holder_cluster_fail_closed','liquidity_policy','holder_cluster_evidence_coverage','wallet_forensics'}; capability_names={'wallet_forensics_capability','wallet_forensics_evidence_yield'}
    def _status(names):
        vals=[checks[n].get('status') for n in names if n in checks]; return 'FAILED' if 'FAILED' in vals else 'DEGRADED' if 'DEGRADED' in vals else 'HEALTHY'
    pipeline_health=_status(pipeline_names); capability_health=_status(capability_names); overall='FAILED' if 'FAILED' in {pipeline_health,capability_health} else 'DEGRADED' if 'DEGRADED' in {pipeline_health,capability_health} else 'HEALTHY'
    failures=[{'component':name,**check} for name,check in checks.items() if check.get('status')!='HEALTHY']; system_blockers=sum(1 for x in failures if x.get('blocks_production')); candidate_gate_blocks=hblock+hqua
    failure_summary={'count':len(failures),'production_blockers':system_blockers,'system_production_blockers':system_blockers,'candidate_gate_blocks':candidate_gate_blocks,'codes':[x.get('failure_code') for x in failures]}; gate_summary={'holder_cluster_input':hinput,'verified_promoted':hprom,'quarantined':hqua,'blocked':hblock,'candidate_gate_blocks':candidate_gate_blocks,'production_authorized_candidates':hprom,'interpretation':'Candidate gate blocks are correct fail-closed decisions and are separate from system health failures.'}
    market_scan=int(summary.get('market_scan',0) or 0) if isinstance(summary,dict) else 0; qualified=int(summary.get('qualified',0) or 0) if isinstance(summary,dict) else 0; revival_qualified=int(summary.get('revival_qualified',0) or 0) if isinstance(summary,dict) else 0; cex_alerts=int(summary.get('cex_revival_alerts',0) or 0) if isinstance(summary,dict) else 0
    lane_metrics={'policy_target_attention_pct':((summary.get('intelligence_policy') or {}).get('target_attention_pct') or {'old_coin_revival':90,'new_token_research':10}) if isinstance(summary,dict) else {'old_coin_revival':90,'new_token_research':10},'new_token':{'market_scan':market_scan,'qualified':qualified,'qualification_rate':round(qualified/market_scan,6) if market_scan else None},'revival':{'qualified':revival_qualified,'cex_revival_alerts':cex_alerts},'allocation_decision':'HOLD_CURRENT_POLICY_UNTIL_FORWARD_OUTCOME_SAMPLE_IS_LARGE_ENOUGH'}
    return {'version':6,'diagnostic_contract':'FAIL_LOUD_FAIL_SPECIFIC_FAIL_TRACEABLE','updated_at':now.isoformat(),'overall':overall,'pipeline_health':pipeline_health,'capability_health':capability_health,'failure_summary':failure_summary,'gate_summary':gate_summary,'failures':failures,'checks':checks,'lane_metrics':lane_metrics}


def run(output_dir='data'):
    out=Path(output_dir); health=build_health(output_dir); _write(out/'system-health.json',health); summary=_load(out/'run-summary.json',{})
    if isinstance(summary,dict): summary['system_health']={'overall':health['overall'],'pipeline_health':health['pipeline_health'],'capability_health':health['capability_health'],'failure_summary':health['failure_summary'],'gate_summary':health['gate_summary'],'failures':health['failures'],'checks':health['checks'],'lane_metrics':health['lane_metrics']}; _write(out/'run-summary.json',summary)
    print(json.dumps({'overall':health['overall'],'pipeline_health':health['pipeline_health'],'capability_health':health['capability_health'],'failure_summary':health['failure_summary'],'gate_summary':health['gate_summary'],'failures':[{'component':x['component'],'failure_code':x['failure_code'],'severity':x['severity'],'blocks_production':x['blocks_production'],'recommended_action':x['recommended_action']} for x in health['failures']]},indent=2)); return health


if __name__=='__main__': run()
