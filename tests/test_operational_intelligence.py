import json
from pathlib import Path

from wallet500.operational_intelligence import build
from wallet500.prospective_benchmark import run


def put(root: Path, name: str, payload: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root/name).write_text(json.dumps(payload), encoding='utf-8')


def test_split_state_is_visible_and_fail_closed(tmp_path):
    common={'network':'solana','no_hindsight':True,'production_portfolio_impact':'NONE','automatic_buy':False}
    put(tmp_path,'revival-pre-t0-evidence.json',{**common,'generated_at':'2026-09-11T10:00:00+00:00'})
    put(tmp_path,'waking-pre-t0-confirmation.json',{**common,'generated_at':'2026-09-11T10:00:00+00:00'})
    put(tmp_path,'waking-confirmation-latest.json',{**common,'generated_at':'2026-09-11T11:00:00+00:00'})
    put(tmp_path,'real-alerts.json',{'generated_at':'2026-09-11T11:00:00+00:00','truth_contract':{'minimum_verified_execution_liquidity_usd':50000},'alerts':[]})
    out=build(tmp_path,'2026-09-11T11:05:00+00:00')
    assert any(x['code']=='WAKING_SPLIT_STATE' for x in out['findings'])
    assert out['production_effect'] is False


def test_prospective_first_seen_is_immutable_and_exact_pair(tmp_path):
    put(tmp_path,'waking-confirmation-latest.json',{'generated_at':'2026-09-11T10:00:00+00:00','targets':[{'network':'solana','token_address':'T','pair_address':'P'}]})
    put(tmp_path,'waking-pre-t0-confirmation.json',{'generated_at':'2026-09-11T10:10:00+00:00','targets':[]})
    put(tmp_path,'real-alerts.json',{'generated_at':'2026-09-11T10:20:00+00:00','alerts':[]})
    first=run(tmp_path,'2026-09-11T10:30:00+00:00')
    key='solana|T|p'
    ledger=json.loads((tmp_path/'prospective-benchmark-ledger.json').read_text())
    assert ledger['records'][key]['stages']['WAKING']['first_seen_at']=='2026-09-11T10:00:00+00:00'
    put(tmp_path,'waking-confirmation-latest.json',{'generated_at':'2026-09-11T12:00:00+00:00','targets':[{'network':'solana','token_address':'T','pair_address':'P'}]})
    run(tmp_path,'2026-09-11T12:01:00+00:00')
    ledger=json.loads((tmp_path/'prospective-benchmark-ledger.json').read_text())
    assert ledger['records'][key]['stages']['WAKING']['first_seen_at']=='2026-09-11T10:00:00+00:00'
    assert first['production_effect'] is False
