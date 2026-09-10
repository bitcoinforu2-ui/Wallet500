import json
from wallet500 import rejected_candidate_learning as r


def test_reject_key_is_exact_pair_locked():
    a={'chain':'ethereum','token_address':'0xAbC','pair_address':'0xPAIR1'}
    b={'chain':'ethereum','token_address':'0xabc','pair_address':'0xpair2'}
    assert r._key(a)=='ethereum|0xabc|0xpair1'
    assert r._key(a)!=r._key(b)


def test_snapshot_preserves_reject_source_and_market_state():
    row={'chain':'solana','mint':'Mint1','pair_address':'Pair1','price_usd':1.2,'liquidity_usd':45000,'anomaly_score':92,'production_risk_reasons':['LIVE_LIQUIDITY_BELOW_15K_HARD_BLOCK']}
    s=r._snapshot(row,'PRODUCTION_RISK_BLOCK','2026-01-01T00:00:00+00:00')
    assert s['source']=='PRODUCTION_RISK_BLOCK'
    assert s['pair_address']=='Pair1'
    assert s['price_usd']==1.2
    assert s['liquidity_usd']==45000
    assert s['production_risk_reasons']==['LIVE_LIQUIDITY_BELOW_15K_HARD_BLOCK']


def test_snapshot_preserves_age_and_identity_provenance_when_available():
    row={
        'chain':'solana','mint':'Mint1','pair_address':'Pair1',
        'market_age_verified':True,'market_age_min_days':217,
        'market_age_evidence_at':'2026-02-05T00:00:00+00:00',
        'market_age_evidence_source':'COINGECKO_EXACT_ID',
        'exact_identity_verified':True,'exact_pair_verified':True,
    }
    s=r._snapshot(row,'LIVE_SURVIVAL_FAILED','2026-09-10T00:00:00+00:00')
    assert s['market_age_verified'] is True
    assert s['market_age_min_days']==217
    assert s['market_age_evidence_at']=='2026-02-05T00:00:00+00:00'
    assert s['market_age_evidence_source']=='COINGECKO_EXACT_ID'
    assert s['exact_identity_verified'] is True
    assert s['exact_pair_verified'] is True


def test_snapshot_accepts_locked_pair_as_exact_pair_truth():
    s=r._snapshot({'chain':'bsc','token':'0xabc','pair_address':'0xdef','pair_identity_locked':True},'LIVE_SURVIVAL_FAILED','2026-09-10T00:00:00+00:00')
    assert s['exact_pair_verified'] is True


def test_snapshot_never_invents_age_truth():
    s=r._snapshot({'chain':'bsc','token':'0xabc','pair_address':'0xdef'},'LIVE_SURVIVAL_FAILED','2026-09-10T00:00:00+00:00')
    assert s['market_age_verified'] is False
    assert s['market_age_min_days'] is None


def test_decision_rows_ingests_canonical_multichain_survival(monkeypatch, tmp_path):
    bsc={'chain':'bsc','token':'0xabc','pair_address':'0x111','live_survival_gate':'FAILED'}
    eth={'chain':'ethereum','token':'0xdef','pair_address':'0x222','live_survival_gate':'PENDING'}
    (tmp_path/'live-survival-failed.json').write_text(json.dumps([bsc]))
    (tmp_path/'live-survival-pending.json').write_text(json.dumps([eth]))
    (tmp_path/'fresh-solana-survival.json').write_text('[]')
    for filename in ('production-risk-blocked.json','holder-cluster-production-blocked.json','holder-cluster-quarantine.json'):
        (tmp_path/filename).write_text('[]')
    monkeypatch.setattr(r,'DATA',tmp_path)
    monkeypatch.setattr(r,'STATIC_SOURCES',{
        'PRODUCTION_RISK_BLOCK':tmp_path/'production-risk-blocked.json',
        'HOLDER_CLUSTER_BLOCK':tmp_path/'holder-cluster-production-blocked.json',
        'HOLDER_CLUSTER_REVIEW':tmp_path/'holder-cluster-quarantine.json',
    })
    monkeypatch.setattr(r,'SURVIVAL_SOURCES',{
        'LIVE_SURVIVAL_FAILED':tmp_path/'live-survival-failed.json',
        'LIVE_SURVIVAL_PENDING':tmp_path/'live-survival-pending.json',
    })
    rows=r._decision_rows()
    assert ('LIVE_SURVIVAL_FAILED',bsc) in rows
    assert ('LIVE_SURVIVAL_PENDING',eth) in rows
