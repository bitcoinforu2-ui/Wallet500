from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from .config import Settings
from .main import run as run_core
from .cex_revival import run_cex_revival


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def run():
    cfg=Settings(); out=Path(cfg.output_dir); out.mkdir(parents=True,exist_ok=True)
    core=run_core()
    now=datetime.now(timezone.utc).isoformat()
    cex=run_cex_revival(out,now)

    summary_path=out/'run-summary.json'
    summary={}
    if summary_path.exists():
        try: summary=json.loads(summary_path.read_text(encoding='utf-8'))
        except Exception: summary={}
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
    summary['mode']='market-first+onchain-revival+cex-revival'
    _write(summary_path,summary)

    learning={
        'version':1,
        'updated_at':now,
        'objective':'measure which discovery and revival signals produce verified post-detection follow-through',
        'rules':[
            'never count case studies as Wallet500 calls',
            'never invent historical entry prices',
            'compare candidates by verified price after detection',
            'learn separately from early-token, on-chain revival, and CEX revival cohorts',
        ],
        'current_run':{
            'early_anomalies':summary.get('anomalies',0),
            'early_qualified':summary.get('qualified',0),
            'onchain_revival_alerts':summary.get('revival_alerts',0),
            'onchain_revival_qualified':summary.get('revival_qualified',0),
            'cex_revival_alerts':cex.get('alerts_count',0),
            'cex_healthy_sources':cex.get('healthy_sources',0),
            'cex_symbols_seen':cex.get('symbols_seen',0),
            'outcome_tracked':summary.get('outcome_tracked',0),
        },
        'next_learning_targets':[
            'which CEX score bands predict 15m/30m/1h continuation',
            'whether OI acceleration adds predictive value beyond price and volume',
            'which funding archetype has best risk-adjusted continuation',
            'minimum number of exchange confirmations that reduces false positives',
            'whether CEX revival leads on-chain revival or follows it',
        ],
    }
    _write(out/'learning-observations.json',learning)
    return {'core':core,'cex':cex,'summary':summary}


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
