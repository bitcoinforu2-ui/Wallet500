"""Wallet500 Fundamental Network Valuation — research only, never a BUY gate."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Optional

@dataclass(frozen=True)
class Inputs:
 symbol:str; chain:str; token_address:str; observed_at:str
 price_usd:Optional[float]=None; circulating_supply:Optional[float]=None; total_supply:Optional[float]=None
 annualized_fees_usd:Optional[float]=None; annualized_revenue_usd:Optional[float]=None
 tvl_usd:Optional[float]=None; active_users:Optional[float]=None; tx_volume_30d_usd:Optional[float]=None
 peer_ps_median:Optional[float]=None; peer_pf_median:Optional[float]=None
 projected_supply_12m:Optional[float]=None

def _pos(v): return v is not None and v>0

def evaluate(x:Inputs)->dict:
 if not x.chain or not x.token_address or not x.observed_at: raise ValueError('VALUATION_FAIL_CLOSED_EXACT_IDENTITY_AND_TIME_REQUIRED')
 market_cap=x.price_usd*x.circulating_supply if _pos(x.price_usd) and _pos(x.circulating_supply) else None
 fdv=x.price_usd*x.total_supply if _pos(x.price_usd) and _pos(x.total_supply) else None
 ps=fdv/x.annualized_revenue_usd if _pos(fdv) and _pos(x.annualized_revenue_usd) else None
 pf=fdv/x.annualized_fees_usd if _pos(fdv) and _pos(x.annualized_fees_usd) else None
 peer_rev_value=x.annualized_revenue_usd*x.peer_ps_median if _pos(x.annualized_revenue_usd) and _pos(x.peer_ps_median) else None
 peer_fee_value=x.annualized_fees_usd*x.peer_pf_median if _pos(x.annualized_fees_usd) and _pos(x.peer_pf_median) else None
 vals=[v for v in (peer_rev_value,peer_fee_value) if _pos(v)]
 base=sum(vals)/len(vals) if vals else None
 projected_price=base/x.projected_supply_12m if _pos(base) and _pos(x.projected_supply_12m) else None
 evidence={'supply':_pos(x.circulating_supply) and _pos(x.total_supply),'fees':_pos(x.annualized_fees_usd),'revenue':_pos(x.annualized_revenue_usd),'usage':_pos(x.active_users) or _pos(x.tx_volume_30d_usd),'tvl':_pos(x.tvl_usd),'peers':_pos(x.peer_ps_median) or _pos(x.peer_pf_median),'future_supply':_pos(x.projected_supply_12m)}
 confidence=round(100*sum(evidence.values())/len(evidence))
 blockers=[k.upper()+'_UNVERIFIED' for k,v in evidence.items() if not v]
 return {'schema_version':1,'mode':'FUNDAMENTAL_VALUATION_RESEARCH_ONLY','actionable':False,'automatic_buy':False,'inputs':asdict(x),'market_cap_usd':market_cap,'fdv_usd':fdv,'fdv_to_revenue':ps,'fdv_to_fees':pf,'peer_implied_revenue_value_usd':peer_rev_value,'peer_implied_fee_value_usd':peer_fee_value,'base_implied_value_usd':base,'projected_price_12m_usd':projected_price,'evidence_confidence_pct':confidence,'blockers':blockers,'evidence':evidence}
