from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .main import run as run_core
from .cex_revival import run_cex_revival


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _load(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return default


def run():
    cfg=Settings(); out=Path(cfg.output_dir); out.mkdir(parents=True,exist_ok=True)

    # Keep the existing DEX/new-token engine alive as a research laboratory.
    # Its outcomes remain valuable for pump/dump and wallet learning, but it is
    # no longer the primary production-intelligence cohort.
    core=run_core()
    now=datetime.now(timezone.utc).isoformat()

    # Established-token CEX revival is the primary opportunity-discovery lane.
    cex=run_cex_revival(out,now)

    summary_path=out/'run-summary.json'; summary=_load(summary_path,{})
    summary['intelligence_policy']={
        'mode':'OLD_COIN_REVIVAL_FIRST',
        'production_primary':'ESTABLISHED_TOKEN_REVIVAL',
        'new_token_lane':'RESEARCH_ONLY',
        'target_attention_pct':{'old_coin_revival':80,'new_token_research':20},
        'old_coin_min_age_days':7,
        'preferred_old_coin_age_days':30,
        'new_token_research_only_hours':48,
        'minimum_exchange_confirmations':2,
        'strong_exchange_confirmations':4,
    }
    summary['cex']={
        'healthy_sources':cex.get('healthy_sources',0),
        'requested_sources':len(cex.get('requested_sources',[])),
        'contracts_seen':cex.get('contracts_seen',0),
        'symbols_seen':cex.get('symbols_seen',0),
        'alerts':cex.get('alerts_count',0),
        'errors':len(cex.get('errors',[])),
    }
    summary['cex_revival_alerts']=cex.get('alerts_count',0)
    summary['updated_at']=now
    summary['mode']='OLD_COIN_REVIVAL_FIRST+NEW_TOKEN_LAB'
    _write(summary_path,summary)

    # Explicitly separate the new-token cohort so dashboards/learning cannot
    # accidentally present it as equivalent production alpha.
    new_lab={
        'version':1,'updated_at':now,'lane':'NEW_TOKEN_LAB','production_status':'RESEARCH_ONLY',
        'purpose':'learn pump/dump signatures, wallet behavior and post-discovery outcomes without competing with established-token revival qualification',
        'anomalies':summary.get('anomalies',0),'qualified_by_legacy_gate':summary.get('qualified',0),
        'outcome_tracked':summary.get('outcome_tracked',0),
        'note':'legacy qualification is retained for research continuity; it is not a production Old-Coin Revival call under the current policy.'
    }
    _write(out/'new-token-lab.json',new_lab)

    learning={
        'version':2,'updated_at':now,
        'objective':'optimize early detection of established-token revival using only information available at each observation time',
        'rules':[
            'old-coin revival is the primary production intelligence cohort',
            'new tokens are research-only unless policy is explicitly changed',
            'never count user case studies as Wallet500 calls',
            'never invent historical entry prices or baselines',
            'no hindsight feature leakage in historical review',
            'retain failures and dumps in the complete track record',
            'version threshold changes before evaluating them',
        ],
        'current_run':{
            'new_token_anomalies_research':summary.get('anomalies',0),
            'new_token_legacy_qualified_research':summary.get('qualified',0),
            'onchain_revival_alerts':summary.get('revival_alerts',0),
            'onchain_revival_qualified':summary.get('revival_qualified',0),
            'cex_revival_alerts':cex.get('alerts_count',0),
            'cex_healthy_sources':cex.get('healthy_sources',0),
            'cex_symbols_seen':cex.get('symbols_seen',0),
            'outcome_tracked':summary.get('outcome_tracked',0),
        },
        'revival_watch_parameters':[
            'price acceleration >=2% per scan; stronger >=5%',
            'volume acceleration >=8% per scan; stronger >=25%',
            'OI acceleration >=5% per scan; stronger >=15%',
            'absolute funding >=0.05%; extreme >=0.30%',
            'minimum 2 exchange confirmations; strong >=4; exceptional >=6',
            'personal baseline deviation and quiet-to-active transition',
            'cross-exchange lead/lag and momentum dispersion',
            'spot/perpetual confirmation when available',
            'on-chain wallet/holder/buyer accumulation when available',
            'liquidity/turnover quality and pump-dump risk',
        ],
        'next_learning_targets':[
            'historically replay stored observations without future-data leakage',
            'find score bands that predict 15m/30m/1h/4h continuation',
            'measure OI incremental predictive value beyond price and volume',
            'measure funding archetypes by follow-through and drawdown',
            'find minimum exchange confirmations that reduce false positives',
            'measure whether CEX revival leads on-chain revival',
            'build robust per-symbol median/percentile baselines after sufficient observations',
        ],
    }
    _write(out/'learning-observations.json',learning)
    return {'core':core,'cex':cex,'summary':summary,'new_token_lab':new_lab}


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
