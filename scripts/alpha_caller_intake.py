from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
ROOT=Path(__file__).resolve().parents[1];INBOX=ROOT/'data/alpha-caller-inbox.json';EVENTS=ROOT/'data/close-watch-events.json';OUT=ROOT/'data/alpha-caller-candidates.json';UA='Wallet500-AlphaCallerIntel/1.1'
CHAIN={'eth':'ethereum','ethereum':'ethereum','arbitrum':'arbitrum','base':'base','bsc':'bsc','optimism':'optimism','polygon':'polygon','solana':'solana'}
def now():return datetime.now(timezone.utc).isoformat()
def get_json(url,timeout=12):
 try:
  with urlopen(Request(url,headers={'User-Agent':UA,'Accept':'application/json'}),timeout=timeout) as r:return json.loads(r.read().decode())
 except (HTTPError,URLError,TimeoutError,ValueError,OSError):return None
def valid_evm(x):
 x=str(x or '');return x.startswith('0x') and len(x)==42 and all(c in '0123456789abcdefABCDEF' for c in x[2:])
def valid_sol(x):return 32<=len(str(x or ''))<=44 and not str(x).startswith('0x')
def parse_time(x):
 try:return datetime.fromisoformat(str(x).replace('Z','+00:00')).astimezone(timezone.utc)
 except Exception:return None
def main():
 inbox=json.loads(INBOX.read_text()) if INBOX.exists() else {'calls':[]};calls=inbox.get('calls') or [];bus=json.loads(EVENTS.read_text()) if EVENTS.exists() else {'version':2,'events':[]};events=bus.get('events') or [];results=[];added=0
 for c in calls:
  caller=str(c.get('caller') or '').strip();source=str(c.get('source') or '').strip();contract=str(c.get('contract') or '').strip();network=str(c.get('network') or '').lower().strip();ts=parse_time(c.get('called_at'));r={'caller':caller,'source':source,'contract':contract,'network':network,'called_at':c.get('called_at'),'status':'REJECTED','reasons':[],'observed_at':now()}
  if not caller or not source or not ts:r['reasons'].append('MISSING_CALL_IDENTITY_OR_TIMESTAMP')
  if network not in CHAIN:r['reasons'].append('UNSUPPORTED_NETWORK')
  elif network=='solana' and not valid_sol(contract):r['reasons'].append('INVALID_SOLANA_CONTRACT')
  elif network!='solana' and not valid_evm(contract):r['reasons'].append('INVALID_EVM_CONTRACT')
  if not contract:r['reasons'].append('MISSING_CONTRACT')
  ds=get_json('https://api.dexscreener.com/latest/dex/tokens/'+contract) if contract and not r['reasons'] else None;pairs=(ds or {}).get('pairs') or [];wanted=CHAIN.get(network);exact=[]
  for p in pairs:
   if str(p.get('chainId') or '').lower()!=str(wanted or '').lower():continue
   base=str((p.get('baseToken') or {}).get('address','')).lower();quote=str((p.get('quoteToken') or {}).get('address','')).lower()
   if contract.lower() in (base,quote):exact.append(p)
  liquid=[]
  for p in exact:
   try:liq=float((p.get('liquidity') or {}).get('usd') or 0)
   except (TypeError,ValueError):liq=0
   if liq>0:liquid.append((liq,p))
  if not liquid:r['reasons'].append('NO_CHAIN_VERIFIED_LIVE_LIQUID_MARKET')
  if r['reasons']:results.append(r);continue
  liq,p=max(liquid,key=lambda z:z[0]);pair=str(p.get('pairAddress') or '');symbol=str(c.get('symbol') or (p.get('baseToken') or {}).get('symbol') or 'UNKNOWN').upper();r.update({'status':'GATED_RESEARCH_CANDIDATE','pair':pair,'liquidity_usd':liq,'dex_url':p.get('url'),'symbol':symbol,'reasons':['CALLER_SIGNAL_DOES_NOT_BYPASS_WALLET500_GATES']});cid=f"alpha-call:{source}:{caller}:{network}:{contract.lower()}:{ts.isoformat()}"
  if not any(e.get('canonical_event_id')==cid for e in events):events.append({'symbol':symbol,'network':network,'contract':contract,'pair':pair,'family':'attention_social','kind':'verified_alpha_caller_call','direction':1,'strength':float(c.get('caller_strength') or 35),'confidence':float(c.get('caller_confidence') or 55),'source':source,'subject':caller,'source_url':str(c.get('source_url') or ''),'canonical_event_id':cid,'event_time':ts.isoformat(),'observed_at':now(),'free_source':True,'research_only':True,'requires_full_wallet500_gates':True,'liquidity_usd_at_intake':liq,'timestamp_semantics':c.get('timestamp_semantics')});added+=1
  results.append(r)
 EVENTS.write_text(json.dumps({'version':2,'generated_at':now(),'events':events},indent=2,ensure_ascii=False)+'\n');OUT.write_text(json.dumps({'version':2,'generated_at':now(),'candidates':results},indent=2,ensure_ascii=False)+'\n');print(json.dumps({'status':'OK','calls_seen':len(calls),'events_added':added,'gated_candidates':sum(x['status']=='GATED_RESEARCH_CANDIDATE' for x in results),'rejected':sum(x['status']=='REJECTED' for x in results)}))
if __name__=='__main__':main()
