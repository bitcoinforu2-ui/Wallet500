from __future__ import annotations
import json, os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA=Path('data'); TOP_N=20
MAX_TOP1=20.0; MAX_TOP5=50.0; MAX_TOP10=65.0
TRANSFER_TOPIC='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
ZERO='0x0000000000000000000000000000000000000000'
RPC={
 'SOLANA':os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com'),
 'SOL':os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com'),
 'ETHEREUM':os.getenv('ETH_RPC_URL',''), 'ETH':os.getenv('ETH_RPC_URL',''),
 'BSC':os.getenv('BSC_RPC_URL',''), 'BNB':os.getenv('BSC_RPC_URL','')}
INPUT_FILE=os.getenv('HOLDER_CLUSTER_INPUT','active-qualified-candidates.json')
EVM_LOOKBACK=int(os.getenv('HOLDER_EVM_LOOKBACK_BLOCKS','50000'))
EVM_CHUNK=max(100,int(os.getenv('HOLDER_EVM_LOG_CHUNK','5000')))

def _load(p,d):
 try: return json.loads(p.read_text()) if p.exists() else d
 except Exception: return d

def _write(p,x): p.write_text(json.dumps(x,indent=2))
def _rpc_url(url,method,params):
 if not url: return None
 try:
  req=Request(url,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers={'Content-Type':'application/json','User-Agent':'Wallet500/1.0'})
  with urlopen(req,timeout=25) as r:
   x=json.loads(r.read().decode()); return None if x.get('error') else x.get('result')
 except Exception: return None

def _rpc(method,params): return _rpc_url(RPC['SOL'],method,params)
def _addr(topic): return ('0x'+str(topic)[-40:]).lower() if topic else ''

def _sol_holders(token):
 supply=_rpc('getTokenSupply',[token,{'commitment':'confirmed'}]) or {}; total=float((supply.get('value') or {}).get('uiAmount') or 0)
 largest=_rpc('getTokenLargestAccounts',[token,{'commitment':'confirmed'}]) or {}; token_accounts=[]
 for x in (largest.get('value') or [])[:TOP_N]:
  amt=float(x.get('uiAmount') or 0); addr=x.get('address')
  if addr and amt>0: token_accounts.append({'token_account':addr,'amount':amt,'pct_of_supply':amt/total*100 if total else 0})
 if not token_accounts: return [],[],{'supply':total,'largest_accounts_returned':0,'owners_resolved':0}
 infos=_rpc('getMultipleAccounts',[[x['token_account'] for x in token_accounts],{'encoding':'jsonParsed','commitment':'confirmed'}]) or {}; values=(infos.get('value') or []) if isinstance(infos,dict) else []
 by_owner=defaultdict(float); resolved=[]
 for row,info in zip(token_accounts,values):
  try: owner=((((info or {}).get('data') or {}).get('parsed') or {}).get('info') or {}).get('owner')
  except Exception: owner=None
  resolved.append({**row,'owner':owner})
  if owner: by_owner[owner]+=row['amount']
 owners=[{'owner':o,'amount':a,'pct':a/total*100 if total else 0} for o,a in by_owner.items()]; owners.sort(key=lambda x:x['amount'],reverse=True)
 return owners,resolved,{'supply':total,'largest_accounts_returned':len(token_accounts),'owners_resolved':sum(1 for x in resolved if x.get('owner'))}

def _evm_holders(chain,token):
 url=RPC.get(chain,''); latest=_rpc_url(url,'eth_blockNumber',[])
 if not latest: return [],[],{'complete':False,'reason':'EVM_RPC_UNAVAILABLE'}
 latest_i=int(latest,16); start=max(0,latest_i-EVM_LOOKBACK); balances=defaultdict(int); edges=defaultdict(int); logs_seen=0; chunks=0
 for a in range(start,latest_i+1,EVM_CHUNK):
  b=min(latest_i,a+EVM_CHUNK-1); chunks+=1
  logs=_rpc_url(url,'eth_getLogs',[{'fromBlock':hex(a),'toBlock':hex(b),'address':token,'topics':[TRANSFER_TOPIC]}])
  if logs is None: return [],[],{'complete':False,'reason':'EVM_LOG_RANGE_UNAVAILABLE','from_block':start,'to_block':latest_i,'failed_chunk':[a,b],'chunks_completed':chunks-1}
  for log in logs:
   topics=log.get('topics') or []
   if len(topics)<3: continue
   f=_addr(topics[1]); t=_addr(topics[2])
   try: value=int(log.get('data') or '0x0',16)
   except Exception: continue
   logs_seen+=1
   if f and f!=ZERO: balances[f]-=value
   if t and t!=ZERO: balances[t]+=value
   if f and t and f!=ZERO and t!=ZERO: edges[(f,t)]+=1
 positive=[(o,a) for o,a in balances.items() if a>0]; total=sum(a for _,a in positive)
 holders=[{'owner':o,'raw_amount':str(a),'pct':a/total*100 if total else 0} for o,a in positive]; holders.sort(key=lambda x:int(x['raw_amount']),reverse=True)
 graph=[{'from':f,'to':t,'transfer_count':n} for (f,t),n in sorted(edges.items(),key=lambda x:x[1],reverse=True)[:200]]
 return holders[:TOP_N],graph,{'complete':False,'reason':'BOUNDED_LOOKBACK_RECONSTRUCTION','from_block':start,'to_block':latest_i,'logs_seen':logs_seen,'chunks':chunks,'lookback_blocks':EVM_LOOKBACK,'observed_positive_holders':len(positive)}

def analyze(chain,token):
 c=str(chain or '').upper(); reasons=[]; token_accounts=[]; graph=[]; meta={}
 if c in ('SOL','SOLANA'):
  holders,token_accounts,meta=_sol_holders(token)
 elif c in ('ETH','ETHEREUM','BSC','BNB'):
  holders,graph,meta=_evm_holders(c,token.lower()); reasons.append(meta.get('reason','EVM_EVIDENCE_INCOMPLETE'))
 else: holders=[]; reasons.append('UNSUPPORTED_CHAIN')
 p=sorted((float(x.get('pct') or 0) for x in holders),reverse=True); top1=sum(p[:1]); top5=sum(p[:5]); top10=sum(p[:10])
 if not holders: reasons.append('HOLDER_DATA_UNAVAILABLE')
 if c in ('SOL','SOLANA') and meta.get('owners_resolved',0)<meta.get('largest_accounts_returned',0): reasons.append('SOME_TOKEN_ACCOUNT_OWNERS_UNRESOLVED')
 if top1>MAX_TOP1: reasons.append('TOP1_OWNER_CONCENTRATION_HIGH')
 if top5>MAX_TOP5: reasons.append('TOP5_OWNER_CONCENTRATION_HIGH')
 if top10>MAX_TOP10: reasons.append('TOP10_OWNER_CONCENTRATION_HIGH')
 status='BLOCK' if any(x.endswith('_HIGH') for x in reasons) else 'REVIEW'
 level='ONCHAIN_OWNER_CONCENTRATION_RESOLVED' if c in ('SOL','SOLANA') and holders else ('BOUNDED_ONCHAIN_TRANSFER_LEDGER' if holders else 'INSUFFICIENT_EVIDENCE')
 return {'chain':chain,'token':token,'checked_at':datetime.now(timezone.utc).isoformat(),'status':status,'top_holders_count':len(holders),'top1_pct':round(top1,4),'top5_pct':round(top5,4),'top10_pct':round(top10,4),'cluster_verified':False,'reasons':list(dict.fromkeys(reasons)),'evidence_level':level,'metadata':meta,'holders':holders,'token_accounts':token_accounts,'transfer_graph':graph}

def run():
 src=_load(DATA/INPUT_FILE,{}); rows=src.get('rows',src if isinstance(src,list) else []); rows=rows if isinstance(rows,list) else []; out=[]; seen=set()
 for r in rows:
  if not isinstance(r,dict): continue
  chain=r.get('chain'); token=r.get('token') or r.get('token_address') or r.get('mint'); key=(str(chain),str(token))
  if not chain or not token or key in seen: continue
  seen.add(key); out.append(analyze(chain,token))
 now=datetime.now(timezone.utc).isoformat(); payload={'updated_at':now,'method':'WALLET500_HOLDER_CLUSTER_PRETRADE_GATE_V1_2_EVM_LEDGER','input_file':INPUT_FILE,'truth_note':'Solana concentration is owner-resolved. EVM reconstruction uses bounded ERC20 Transfer logs and therefore remains REVIEW until full-history/deployment boundary and cluster evidence are verified. No incomplete evidence can PASS.','rows':out}
 _write(DATA/'holder-cluster-gate.json',payload); _write(DATA/'holder-cluster-gate-summary.json',{'updated_at':now,'input_file':INPUT_FILE,'checked':len(out),'block':sum(x['status']=='BLOCK' for x in out),'review':sum(x['status']=='REVIEW' for x in out),'pass':sum(x['status']=='PASS' for x in out)})
 print(json.dumps(_load(DATA/'holder-cluster-gate-summary.json',{}),indent=2)); return payload

if __name__=='__main__': run()
