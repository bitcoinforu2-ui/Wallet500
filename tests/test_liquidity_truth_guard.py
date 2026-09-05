import json
from pathlib import Path

from wallet500.liquidity_truth import liquidity_truth
from wallet500.liquidity_truth_guard import annotate_row, sanitize_real_alerts
from wallet500.production_risk_gate import evaluate


def test_meteora_tvl_is_not_execution_depth():
    row={
        'chain':'solana','token_address':'DrZ26cKJDksVRWib3DVVsjo9eeXccc7hKhDJviiYEEZY',
        'pair_address':'DQ9weJhfiU4iL5LUoeshDrm5KxDHCMiSbnnKJz7buMcf',
        'dex':'meteora','liquidity_usd':37_200_000,
    }
    out=annotate_row(row)
    assert out['pool_tvl_usd']==37_200_000
    assert out['concentrated_liquidity_pool'] is True
    assert out['execution_depth_verified'] is False
    assert out['execution_pool_liquidity_usd'] is None
    assert out['liquidity_execution_gate_eligible'] is False
    assert out['liquidity_execution_gate_status']=='CONCENTRATED_POOL_DEPTH_UNVERIFIED_FAIL_CLOSED'


def test_verified_depth_can_pass_semantics():
    row={
        'dex':'meteora','liquidity_usd':37_200_000,
        'execution_depth_verified':True,
        'execution_depth_usd_1pct':10_000,
        'execution_depth_usd_2pct':25_000,
        'execution_depth_usd_5pct':80_000,
        'execution_depth_source':'ROUTE_SIMULATION_TEST',
    }
    out=liquidity_truth(row)
    assert out['execution_depth_verified'] is True
    assert out['liquidity_execution_gate_eligible'] is True
    assert out['liquidity_execution_gate_usd']==80_000


def test_non_concentrated_pool_gets_proxy_but_not_fake_verified_depth():
    out=liquidity_truth({'dex':'raydium','liquidity_usd':1_000_000})
    assert out['concentrated_liquidity_pool'] is False
    assert out['constant_product_depth_proxy_usd_5pct'] is not None
    assert out['execution_depth_verified'] is False
    assert out['liquidity_execution_gate_eligible'] is False


def test_production_hard_blocks_unverified_meteora_even_with_huge_tvl():
    row={
        'chain':'solana','token':'YZY','dex':'meteora','pair_address':'PAIR',
        'liquidity_usd':37_200_000,'execution_pool_liquidity_usd':37_200_000,
    }
    out=evaluate(row,{})
    assert out['production_risk_blocked'] is True
    assert 'CONCENTRATED_POOL_EXECUTION_DEPTH_UNVERIFIED_HARD_BLOCK' in out['production_risk_critical']
    assert out['production_live_liquidity_usd']==0


def test_real_alert_is_demoted_when_concentrated_depth_is_unverified(tmp_path: Path):
    p=tmp_path/'real-alerts.json'
    p.write_text(json.dumps({
        'counts':{'real_alerts':1,'verified_watch_not_real':0},
        'alerts':[{
            'symbol':'YZY','chain':'solana','token_address':'MINT','pair_address':'PAIR','dex':'meteora',
            'liquidity_usd':37_200_000,'execution_pool_liquidity_usd':37_200_000,
            'blockers':[],'status':'REAL_ALERT','actionable_research_alert':True,
        }],
        'verified_watch':[],
        'truth_contract':{},
    }),encoding='utf-8')
    result=sanitize_real_alerts(p)
    data=json.loads(p.read_text())
    assert result['demoted']==1
    assert data['counts']['real_alerts']==0
    assert data['verified_watch'][0]['actionable_research_alert'] is False
    assert 'EXECUTION_DEPTH_UNVERIFIED_CONCENTRATED_POOL' in data['verified_watch'][0]['blockers']
