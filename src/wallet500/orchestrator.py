from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .main import run as run_core
from .cex_revival import run_cex_revival
from .catalyst_dna import run_catalyst_dna
from .time_machine import run_time_machine


def _write(path: Path, payload): path.write_text(json.dumps(payload,indent=2),encoding='utf-8')
def _load(path: Path,default):
    if not path.exists():return default
    try:return json.loads(path.read_text(encoding='utf-8'))
    except:return default

def run():
    cfg=Settings();out=Path(cfg.output_dir);out.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc).isoformat()

    # PRIMARY LANE: established-token CEX revival intelligence runs first and
    # independently. A DEX/new-token failure must never block this lane.
    cex=run_cex_revival(out,now)
    dna=run_catalyst_dna(out,now)
    tm=run_time_machine(out,now)

    core=None;core_error=None
    try:
        core=run_core()
    except Exception as e:
        core_error=f'{type(e).__name__}: {e}'[:500]

    summary_path=out/'run-summary.json';summary=_load(summary_path,{})
    summary['intelligence_policy']={'mode':'OLD_COIN_REVIVAL_FIRST','production_primary':'ESTABLISHED_TOKEN_REVIVAL','new_token_lane':'RESEARCH_ONLY','target_attention_pct':{'old_coin_revival':90,'new_token_research':10},'old_coin_min_age_days':7,'preferred_old_coin_age_days':30,'new_token_research_only_hours':48,'minimum_exchange_confirmations':2,'strong_exchange_confirmations':4}
    summary['lane_health']={'old_coin_revival':'HEALTHY' if cex.get('healthy_sources',0)>=2 and cex.get('contracts_seen',0)>0 else 'DEGRADED','new_token_lab':'HEALTHY' if core_error is None else 'DEGRADED','new_token_error':core_error}
    summary['cex']={'healthy_sources':cex.get('healthy_sources',0),'requested_sources':len(cex.get('requested_sources',[])),'contracts_seen':cex.get('contracts_seen',0),'symbols_seen':cex.get('symbols_seen',0),'alerts':cex.get('alerts_count',0),'errors':len(cex.get('errors',[]))}
    summary['catalyst_dna']={'profiles':dna.get('profiles_count',0),'source_attribution_sources':len(dna.get('source_attribution',{})),'archetypes':len(dna.get('archetype_frequency',{}))}
    summary['time_machine']={'patterns_tested':tm.get('patterns_tested',0),'source_forward_stats':len(tm.get('source_forward_hit_rates',{})),'method':tm.get('method')}
    summary['cex_revival_alerts']=cex.get('alerts_count',0);summary['updated_at']=now;summary['mode']='OLD_COIN_REVIVAL_FIRST_90+CATALYST_DNA+TIME_MACHINE+NEW_TOKEN_LAB_10';_write(summary_path,summary)

    new_lab={'version':3,'updated_at':now,'lane':'NEW_TOKEN_LAB','production_status':'RESEARCH_ONLY','lane_health':'HEALTHY' if core_error is None else 'DEGRADED','error':core_error,'attention_budget_pct':10,'purpose':'learn pump/dump signatures, wallet behavior and post-discovery outcomes without competing with established-token revival qualification','anomalies':summary.get('anomalies',0),'qualified_by_legacy_gate':summary.get('qualified',0),'outcome_tracked':summary.get('outcome_tracked',0),'note':'legacy qualification is retained for research continuity; it is not a production Old-Coin Revival call under the current policy.'};_write(out/'new-token-lab.json',new_lab)
    learning={'version':6,'updated_at':now,'objective':'optimize early established-token revival detection and learn recurring historical catalyst DNA with sequential no-hindsight replay','attention_budget_pct':{'old_coin_revival':90,'new_token_research':10},'rules':['old-coin revival is primary production intelligence','new tokens are research-only and may degrade without blocking revival','case studies are never counted as Wallet500 calls','never invent historical catalysts, entry prices or baselines','no hindsight feature leakage','retain failures and dumps','version threshold changes'],'current_run':{'cex_revival_alerts':cex.get('alerts_count',0),'cex_healthy_sources':cex.get('healthy_sources',0),'cex_symbols_seen':cex.get('symbols_seen',0),'catalyst_dna_profiles':dna.get('profiles_count',0),'catalyst_archetypes':len(dna.get('archetype_frequency',{})),'time_machine_patterns_tested':tm.get('patterns_tested',0),'new_token_lane_health':'HEALTHY' if core_error is None else 'DEGRADED','new_token_anomalies_research':summary.get('anomalies',0),'outcome_tracked':summary.get('outcome_tracked',0)},'next_learning_targets':['replace cadence assumptions with timestamp-exact horizons','rank DNA patterns by verified forward hit rate and drawdown','rank exchanges/sources by verified early-warning contribution','add event/listing/unlock/news datasets only with timestamped provenance','learn per-symbol catalyst DNA and cross-token family DNA','compare source combinations, not isolated indicators']};_write(out/'learning-observations.json',learning)
    return {'core':core,'core_error':core_error,'cex':cex,'catalyst_dna':dna,'time_machine':tm,'summary':summary,'new_token_lab':new_lab}

if __name__=='__main__':print(json.dumps(run(),indent=2))
