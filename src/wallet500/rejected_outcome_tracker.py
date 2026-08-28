"""Track later outcomes of rejected candidates and surface false negatives.

Uses only exact-pair observations already produced by Wallet500. It never
rewrites the immutable first reject snapshot.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA=Path('data'); LEDGER=DATA/'rejected-candidate-ledger.json'; REPORT=DATA/'rejected-outcome-report.json'; FILTER_REPORT=DATA/'rejected-filter-attribution.json'
MARKET_SOURCES=(DATA/'active-qualified-candidates.json',DATA/'production-risk-evaluations.json',DATA/'qualified-candidates.json',DATA/'watchlist.json')


def _load(p:Path,d:Any)->Any:
 try:return json.loads(p.read_text()) if p.exists() else d
 except Exception:return d

def _rows(x:Any)->list[dict]:
 if isinstance(x,list):return [r for r in x if isinstance(r,dict)]
 if isinstance(x,dict):
  for k in ('rows','candidates','active','qualified'):
   if isinstance(x.get(k),list):return [r for r in x[k] if isinstance(r,dict)]
 return []

def _key(row:dict)->str:
 chain=str(row.get('chain') or '').lower();token=str(row.get('token') or row.get('token_address') or row.get('mint') or '');pair=str(row.get('pair_address') or row.get('locked_pair_address') or row.get('pair') or '')
 if chain in {'ethereum','eth','bsc','bnb'}:token=token.lower();pair=pair.lower()
 return f'{chain}|{token}|{pair}'

def _market_snapshot(row:dict,source:str,now:str)->dict:
 return {'observed_at':row.get('observed_at') or row.get('updated_at') or now,'source':source,'price_usd':row.get('price_usd'),'liquidity_usd':row.get('live_liquidity_usd') or row.get('liquidity_usd'),'market_cap_usd':row.get('market_cap_usd') or row.get('market_cap'),'fdv_usd':row.get('fdv_usd') or row.get('fdv'),'volume_h1':row.get('live_volume_h1') or row.get('volume_h1')}

def _gain(first_price,observations:list[dict])->tuple[float|None,float|None]:
 try:entry=float(first_price)
 except Exception:return None,None
 if entry<=0:return None,None
 prices=[]
 for o in observations:
  try:p=float(o.get('price_usd'))
  except Exception:continue
  if p>0:prices.append(p)
 if not prices:return None,None
 peak=max(prices);current=prices[-1];return (peak/entry-1)*100,(current/entry-1)*100

def update()->dict:
 now=datetime.now(timezone.utc).isoformat();ledger=_load(LEDGER,{})
 records=ledger.get('records') if isinstance(ledger,dict) and isinstance(ledger.get('records'),dict) else {}
 market={}
 for path in MARKET_SOURCES:
  for row in _rows(_load(path,[])):
   key=_key(row)
   if key!='||':market[key]=_market_snapshot(row,path.name,now)
 appended=0;false_negatives=[];by_filter={}
 for key,rec in records.items():
  if not isinstance(rec,dict):continue
  obs=rec.get('observations') if isinstance(rec.get('observations'),list) else []
  snap=market.get(key)
  if snap:
   fp=(snap.get('observed_at'),snap.get('source'),snap.get('price_usd'),snap.get('liquidity_usd'));existing={(x.get('observed_at'),x.get('source'),x.get('price_usd'),x.get('liquidity_usd')) for x in obs if isinstance(x,dict)}
   if fp not in existing:obs.append(snap);appended+=1
  rec['observations']=obs[-500:]
  peak_gain,current_gain=_gain((rec.get('first_reject_snapshot') or {}).get('price_usd'),obs)
  rec['peak_gain_since_reject_pct']=round(peak_gain,4) if peak_gain is not None else None;rec['current_gain_since_reject_pct']=round(current_gain,4) if current_gain is not None else None
  if peak_gain is not None and peak_gain>=400:classification='FALSE_NEGATIVE_MAJOR_WINNER'
  elif peak_gain is not None and peak_gain>=100:classification='FALSE_NEGATIVE_WINNER'
  else:classification='UNRESOLVED_REJECT'
  rec['classification']=classification
  source=str(rec.get('first_reject_source') or 'UNKNOWN');stats=by_filter.setdefault(source,{'records':0,'false_negative_winners':0,'false_negative_major_winners':0,'max_peak_gain_pct':None});stats['records']+=1
  if classification.startswith('FALSE_NEGATIVE'):
   stats['false_negative_winners']+=1
   if classification=='FALSE_NEGATIVE_MAJOR_WINNER':stats['false_negative_major_winners']+=1
   false_negatives.append({'identity':rec.get('identity'),'first_reject_source':source,'classification':classification,'peak_gain_since_reject_pct':rec.get('peak_gain_since_reject_pct'),'current_gain_since_reject_pct':rec.get('current_gain_since_reject_pct')})
  if peak_gain is not None:stats['max_peak_gain_pct']=round(max(float(stats['max_peak_gain_pct'] or peak_gain),peak_gain),4)
  records[key]=rec
 ledger['records']=records;ledger['records_count']=len(records);ledger['updated_at']=now;LEDGER.write_text(json.dumps(ledger,indent=2))
 for stats in by_filter.values():stats['false_negative_rate_pct']=round(stats['false_negative_winners']/stats['records']*100,4) if stats['records'] else 0
 report={'updated_at':now,'records':len(records),'market_observations_appended':appended,'false_negative_winners':len(false_negatives),'major_false_negatives':sum(x['classification']=='FALSE_NEGATIVE_MAJOR_WINNER' for x in false_negatives),'thresholds':{'winner_peak_gain_pct':100,'major_winner_peak_gain_pct':400},'false_negatives':sorted(false_negatives,key=lambda x:x.get('peak_gain_since_reject_pct') or 0,reverse=True)};REPORT.write_text(json.dumps(report,indent=2));FILTER_REPORT.write_text(json.dumps({'updated_at':now,'filters':by_filter},indent=2));print(json.dumps({'records':len(records),'false_negative_winners':len(false_negatives),'observations_added':appended},indent=2));return report

if __name__=='__main__':update()
