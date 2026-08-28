"""Immutable rejected-candidate learning ledger.

Every rejected/quarantined candidate remains observable for later outcome learning.
No record is deleted. First rejection is immutable; later observations append.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA=Path('data')
LEDGER=DATA/'rejected-candidate-ledger.json'
SUMMARY=DATA/'rejected-candidate-learning-summary.json'
SOURCES={
    'PRODUCTION_RISK_BLOCK': DATA/'production-risk-blocked.json',
    'HOLDER_CLUSTER_BLOCK': DATA/'holder-cluster-production-blocked.json',
    'HOLDER_CLUSTER_REVIEW': DATA/'holder-cluster-quarantine.json',
}


def _load(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text()) if path.exists() else default
    except Exception: return default


def _rows(x: Any) -> list[dict[str,Any]]:
    if isinstance(x,list): return [r for r in x if isinstance(r,dict)]
    if isinstance(x,dict):
        for k in ('rows','blocked','review','candidates'):
            if isinstance(x.get(k),list): return [r for r in x[k] if isinstance(r,dict)]
    return []


def _identity(row: dict[str,Any]) -> tuple[str,str,str]:
    chain=str(row.get('chain') or '').lower()
    token=str(row.get('token') or row.get('token_address') or row.get('mint') or '').lower() if chain in {'ethereum','eth','bsc','bnb'} else str(row.get('token') or row.get('token_address') or row.get('mint') or '')
    pair=str(row.get('pair_address') or row.get('locked_pair_address') or row.get('pair') or '')
    if chain in {'ethereum','eth','bsc','bnb'}: pair=pair.lower()
    return chain,token,pair


def _key(row: dict[str,Any]) -> str:
    chain,token,pair=_identity(row)
    return f'{chain}|{token}|{pair}'


def _snapshot(row: dict[str,Any], source: str, now: str) -> dict[str,Any]:
    chain,token,pair=_identity(row)
    return {
        'observed_at': row.get('observed_at') or row.get('updated_at') or now,
        'chain':chain,'token':token,'pair_address':pair,
        'source':source,
        'price_usd':row.get('price_usd'),
        'liquidity_usd':row.get('live_liquidity_usd') or row.get('liquidity_usd'),
        'market_cap_usd':row.get('market_cap_usd') or row.get('market_cap'),
        'fdv_usd':row.get('fdv_usd') or row.get('fdv'),
        'volume_h1':row.get('live_volume_h1') or row.get('volume_h1'),
        'buys_h1':row.get('buys_h1'), 'sells_h1':row.get('sells_h1'),
        'anomaly_score':row.get('anomaly_score'),
        'qualification':row.get('qualification'),
        'live_survival_gate':row.get('live_survival_gate'),
        'production_risk_reasons':row.get('production_risk_reasons') or [],
        'holder_cluster_status':row.get('holder_cluster_production_status') or row.get('holder_cluster_status'),
        'holder_cluster_reasons':row.get('holder_cluster_reasons') or [],
    }


def update() -> dict[str,Any]:
    now=datetime.now(timezone.utc).isoformat()
    old=_load(LEDGER,{})
    records=old.get('records') if isinstance(old,dict) and isinstance(old.get('records'),dict) else {}
    created=0; observations_added=0
    current_seen=set()
    for source,path in SOURCES.items():
        for row in _rows(_load(path,[])):
            key=_key(row)
            if key.startswith('||'): continue
            current_seen.add(key)
            snap=_snapshot(row,source,now)
            rec=records.get(key)
            if not isinstance(rec,dict):
                records[key]={
                    'identity':{'chain':snap['chain'],'token':snap['token'],'pair_address':snap['pair_address']},
                    'first_rejected_at':now,
                    'first_reject_source':source,
                    'first_reject_snapshot':snap,
                    'observations':[snap],
                    'latest_observation':snap,
                    'classification':'UNRESOLVED_REJECT',
                }
                created+=1; observations_added+=1; continue
            obs=rec.get('observations') if isinstance(rec.get('observations'),list) else []
            fingerprint=(snap.get('observed_at'),source,snap.get('price_usd'),snap.get('liquidity_usd'))
            existing={(x.get('observed_at'),x.get('source'),x.get('price_usd'),x.get('liquidity_usd')) for x in obs if isinstance(x,dict)}
            if fingerprint not in existing:
                obs.append(snap); observations_added+=1
            rec['observations']=obs[-500:]
            rec['latest_observation']=snap
            records[key]=rec
    payload={'schema_version':1,'policy':'IMMUTABLE_FIRST_REJECT_APPEND_ONLY_OBSERVATIONS_EXACT_PAIR_LOCKED','updated_at':now,'records_count':len(records),'created_this_run':created,'observations_added_this_run':observations_added,'records':records}
    LEDGER.write_text(json.dumps(payload,indent=2))
    summary={'updated_at':now,'records':len(records),'created_this_run':created,'observations_added_this_run':observations_added,'currently_rejected_or_quarantined':len(current_seen),'unresolved':sum(1 for r in records.values() if r.get('classification')=='UNRESOLVED_REJECT')}
    SUMMARY.write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2)); return payload


if __name__=='__main__': update()
