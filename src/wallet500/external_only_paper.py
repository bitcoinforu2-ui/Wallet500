from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from wallet500.entry_quality import evaluate_entry_quality

DATA=Path('data'); LEDGER=DATA/'external-only-paper-ledger.json'; SUMMARY=DATA/'external-only-paper-summary.json'; POS=1.0
EVM={'ethereum','eth','bsc','bnb','base','arbitrum','polygon','optimism','avalanche'}; IDV=2

def load(p,d):
    try:return json.loads(p.read_text()) if p.exists() and p.stat().st_size else d
    except:return d

def write(p,d): p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
def norm(chain,x): return str(x or '').lower() if str(chain or '').lower() in EVM else str(x or '')
def key(chain,token,pair): return f'{str(chain or "").lower()}:{norm(chain,token)}:{norm(chain,pair)}'
def same(chain,a,b): return bool(a and b) and norm(chain,a)==norm(chain,b)

def current_v2_mark(r,pair):
    if not isinstance(r,dict) or r.get('measurement_status')!='VERIFIED_EXACT_PAIR' or r.get('price_identity_contract_version')!=IDV:return None
    chain=r.get('chain')
    if not same(chain,r.get('current_pair_address'),pair):return None
    hist=r.get('history') if isinstance(r.get('history'),list) else []
    h=hist[-1] if hist and isinstance(hist[-1],dict) else None
    if not h or h.get('token_identity_verified') is not True or h.get('price_identity_contract_version')!=IDV:return None
    try:
        price=float(r.get('current_price_usd') or 0); liq=float(h.get('liquidity_usd') or h.get('live_liquidity_usd') or 0); vol=float(h.get('volume_h1') or h.get('live_volume_h1') or 0); buys=int(h.get('buys_h1') or 0); sells=int(h.get('sells_h1') or 0)
    except:return None
    if not all(math.isfinite(x) for x in (price,liq,vol)) or price<=0:return None
    return {'price_usd':price,'liquidity_usd':liq,'volume_h1':vol,'buys_h1':buys,'sells_h1':sells,'target_token_side':h.get('target_token_side'),'token_identity_verified':True,'price_identity_contract_version':IDV}

def run():
    t=datetime.now(timezone.utc); now=t.isoformat(); ext=load(DATA/'external-signal-cohort.json',{}); tracker=load(DATA/'outcome-tracker.json',{}); records=(tracker.get('tokens') or {}) if isinstance(tracker,dict) else {}
    state=load(LEDGER,{})
    if not state: state={'version':'EXTERNAL_ONLY_PAPER_V3_IDENTITY','created_at':now,'position_size_usd':POS,'max_positions':None,'production_change':False,'entries':[]}
    else:
        state['version']='EXTERNAL_ONLY_PAPER_V3_IDENTITY'; state['max_positions']=None
    entries=state.setdefault('entries',[]); existing={e.get('key') for e in entries if isinstance(e,dict)}
    sources={}
    for r in (ext.get('records') or {}).values():
        if not isinstance(r,dict):continue
        k=(str(r.get('chain') or '').lower(),norm(r.get('chain'),r.get('token')))
        sources.setdefault(k,[]).append(r)
    candidates=[]
    for r in records.values():
        if not isinstance(r,dict):continue
        chain=r.get('chain'); token=r.get('token'); pair=r.get('entry_pair_address'); sk=(str(chain or '').lower(),norm(chain,token))
        if sk not in sources or not pair:continue
        snap=current_v2_mark(r,pair)
        if not snap:continue
        if snap['price_usd']<=0 or snap['liquidity_usd']<50000 or snap['volume_h1']<15000 or snap['buys_h1']+snap['sells_h1']<50:continue
        q=evaluate_entry_quality(r,snap)
        if not q.get('pass'):continue
        candidates.append((key(chain,token,pair),r,snap,q,sources[sk]))
    for k,r,s,q,srcs in candidates:
        if k in existing:continue
        px=s['price_usd']; names=sorted(set(x.get('source') for x in srcs if x.get('source')))
        entries.append({'key':k,'chain':r.get('chain'),'token':r.get('token'),'pair_address':r.get('entry_pair_address'),'entry_at':now,'entry_price_usd':px,'entry_liquidity_usd':s['liquidity_usd'],'entry_volume_h1':s['volume_h1'],'entry_txns_h1':s['buys_h1']+s['sells_h1'],'entry_target_token_side':s.get('target_token_side'),'entry_token_identity_verified':True,'price_identity_contract_version':IDV,'quantity':POS/px,'cost_usd':POS,'current_price_usd':px,'current_value_usd':POS,'return_pct':0.0,'status':'LIVE','valuation_status':'FRESH_IDENTITY_VERIFIED_EXACT_PAIR','external_sources':names,'source_consensus_count':len(names),'source_first_seen_at':min((x.get('first_seen_at') for x in srcs if x.get('first_seen_at')),default=None),'entry_quality_policy':'ANTI_CHASE_V1'})
        existing.add(k)
    current={key(r.get('chain'),r.get('token'),r.get('entry_pair_address')):r for r in records.values() if isinstance(r,dict) and r.get('entry_pair_address')}
    upgraded_legacy_base=0; quarantined_legacy_entry=0
    for e in entries:
        r=current.get(e.get('key')); mark=current_v2_mark(r,e.get('pair_address')) if r else None
        if e.get('price_identity_contract_version')!=IDV:
            # Pair base/quote side is immutable. A current V2 BASE proof can
            # therefore validate the old entry's use of DexScreener priceUsd
            # without rewriting its historical price. Quote-side legacy entry
            # prices cannot be reconstructed safely and remain quarantined.
            if mark and str(mark.get('target_token_side') or '').upper().startswith('BASE'):
                e['price_identity_contract_version']=IDV; e['entry_token_identity_verified']=True; e['entry_target_token_side']='BASE'; e['entry_identity_upgrade']='RETRO_BASE_SIDE_IDENTITY_PROVEN_NO_PRICE_REWRITE'; upgraded_legacy_base+=1
            else:
                e['status']='UNRESOLVED'; e['valuation_status']='LEGACY_ENTRY_TOKEN_SIDE_UNVERIFIED'; e['current_price_usd']=None; e['current_value_usd']=None; e['return_pct']=None; quarantined_legacy_entry+=1; continue
        if not mark:
            e['status']='UNRESOLVED'; e['valuation_status']='NO_CURRENT_IDENTITY_VERIFIED_MARK'; e['current_price_usd']=None; e['current_value_usd']=None; e['return_pct']=None; continue
        px=mark['price_usd']
        try:val=float(e['quantity'])*px
        except:val=float('nan')
        if not math.isfinite(val) or val<0:
            e['status']='UNRESOLVED'; e['valuation_status']='QUARANTINED_NONFINITE_VALUE'; e['current_price_usd']=None; e['current_value_usd']=None; e['return_pct']=None; continue
        e['current_price_usd']=px; e['current_value_usd']=round(val,10); e['return_pct']=round((val/POS-1)*100,6); e['status']='LIVE'; e['valuation_status']='FRESH_IDENTITY_VERIFIED_EXACT_PAIR'; e['last_mark_at']=now
    state['updated_at']=now; state['price_identity_contract_version']=IDV; write(LEDGER,state)
    invested=sum(float(e.get('cost_usd') or 0) for e in entries); verified=[e for e in entries if e.get('price_identity_contract_version')==IDV and e.get('valuation_status')=='FRESH_IDENTITY_VERIFIED_EXACT_PAIR' and e.get('current_value_usd') is not None]; covered_inv=sum(float(e.get('cost_usd') or 0) for e in verified); covered_value=sum(float(e.get('current_value_usd') or 0) for e in verified); complete=len(verified)==len(entries)
    value=covered_value if complete else None; pnl=(value-invested) if value is not None else None; roi=((value/invested)-1)*100 if value is not None and invested else None; by={}
    for e in entries:
        for s in e.get('external_sources') or []: by[s]=by.get(s,0)+1
    summary={'updated_at':now,'method':'EXTERNAL_ONLY_PAPER_V3_TOKEN_IDENTITY_FAIL_CLOSED','price_identity_contract_version':IDV,'max_positions':None,'positions':len(entries),'paper_invested_usd':round(invested,6),'paper_current_value_usd':round(value,6) if value is not None else None,'paper_pnl_usd':round(pnl,6) if pnl is not None else None,'paper_roi_pct':round(roi,4) if roi is not None else None,'aggregate_current_roi_status':'VERIFIED_COMPLETE_CURRENT_COVERAGE' if complete else 'WITHHELD_PARTIAL_OR_UNVERIFIED_COVERAGE','verified_current_count':len(verified),'verified_current_investment_usd':round(covered_inv,6),'verified_current_value_usd':round(covered_value,6),'verified_current_roi_pct':round(((covered_value/covered_inv)-1)*100,4) if covered_inv else None,'upgraded_legacy_base_entries':upgraded_legacy_base,'quarantined_legacy_entry_count':quarantined_legacy_entry,'live':sum(e.get('status')=='LIVE' for e in entries),'failed':sum(e.get('status')=='FAILED_SURVIVAL' for e in entries),'unresolved':sum(e.get('status')=='UNRESOLVED' for e in entries),'source_attribution':by,'production_change':False,'truth_note':'Isolated external-source paper cohort. Aggregate current ROI is withheld unless every historical entry has proven token-side identity and every position has a current identity-verified exact-pair mark. No historical entry price is rewritten.'}; write(SUMMARY,summary); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__':run()
