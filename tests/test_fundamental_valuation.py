from wallet500.fundamental_valuation import Inputs,evaluate

def test_missing_is_not_zero_and_never_actionable():
 r=evaluate(Inputs(symbol='AIN',chain='bsc',token_address='0x9558a9254890b2a8b057a789f413631b9084f4a3',observed_at='2026-09-16T00:00:00+00:00',price_usd=.17,total_supply=1_000_000_000))
 assert r['market_cap_usd'] is None
 assert r['fdv_usd']==170_000_000
 assert r['projected_price_12m_usd'] is None
 assert r['actionable'] is False and r['automatic_buy'] is False
 assert 'REVENUE_UNVERIFIED' in r['blockers']

def test_peer_model_requires_verified_economics_and_future_supply():
 r=evaluate(Inputs(symbol='X',chain='bsc',token_address='0x1',observed_at='2026-09-16T00:00:00+00:00',price_usd=1,circulating_supply=100,total_supply=200,annualized_revenue_usd=10,peer_ps_median=5,projected_supply_12m=125))
 assert r['base_implied_value_usd']==50
 assert r['projected_price_12m_usd']==.4
