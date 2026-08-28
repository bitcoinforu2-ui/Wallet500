from __future__ import annotations
import json, os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from .cluster_corroboration import verify_evm_deployer, verified_native_funding_edges, corroborate_clusters

DATA=Path('data'); TOP_N=20
MAX_TOP1=20.0; MAX_TOP5=50.0; MAX_TOP10=65.0
CLUSTER_REVIEW_PCT=float(os.getenv('HOLDER_CLUSTER_REVIEW_PCT','10'))
CLUSTER_BLOCK_PCT=float(os.getenv('HOLDER_CLUSTER_BLOCK_PCT','20'))
TRANSFER_TOPIC='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
TOTAL_SUPPLY_SELECTOR='0x18160ddd'; ZERO='0x0000000000000000000000000000000000000000'
RPC={'SOLANA':os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com'),'SOL':os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com'),'ETHEREUM':os.getenv('ETHEREUM_RPC_URL') or os.getenv('ETH_RPC_URL',''),'ETH':os.getenv('ETHEREUM_RPC_URL') or os.getenv('ETH_RPC_URL',''),'BSC':os.getenv('BSC_RPC_URL') or os.getenv('BNB_RPC_URL',''),'BNB':os.getenv('BSC_RPC_URL') or os.getenv('BNB_RPC_URL','')}
INPUT_FILE=os.getenv('HOLDER_CLUSTER_INPUT','active-qualified-candidates.json'); EVM_LOOKBACK=int(os.getenv('HOLDER_EVM_LOOKBACK_BLOCKS','50000')); EVM_CHUNK=max(100,int(os.getenv('HOLDER_EVM_LOG_CHUNK','5000'))); INFRA_EXCLUSIONS={x.strip().lower() for x in os.getenv('HOLDER_CLUSTER_INFRA_EXCLUSIONS','').split(',') if x.strip()}

def _load(p,d):
 try:return json.loads(p.read_text()) if p.exists() else d
 except Exception:return d

def _write(p,x):p.write_text(json.dumps(x,indent=2))
def _rpc_url(url,method,params):
 if not url:return None
 try:
  req=Request(url,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers={'Content-Type':'application/json','User-Agent':'Wallet500/1.0'})
  with urlopen(req,timeout=25) as r:
   x=json.loads(r.read().decode());return None if x.get('error') else x.get('result')
 except Exception:return None

def _rpc(method,params):return _rpc_url(RPC['SOL'],method,params)
def _addr(topic):return ('0x'+str(topic)[-40:]).lower() if topic else ''
def _as_int_hex(x):
 try:return int(x,16) if isinstance(x,str) else int(x)
 except Exception:return 0

def _sol_holders(token):
 supply=_rpc('getTokenSupply',[token,{'commitment':'confirmed'}]) or {}; total=float((supply.get('value') or {}).get('uiAmount') or 0); largest=_rpc('getTokenLargestAccounts',[token,{'commitment':'confirmed'}]) or {}; token_accounts=[]
 for x in (largest.get('value') or [])[:TOP_N]:
  amt=float(x.get('uiAmount') or 0); addr=x.get('address')
  if addr and amt>0:token_accounts.append({'token_account':addr,'amount':amt,'pct_of_supply':amt/total*100 if total else 0})
 if not token_accounts:return [],[],{'supply':total,'largest_accounts_returned':0,'owners_resolved':0,'owner_resolution_complete':False}
 infos=_rpc('getMultipleAccounts',[[x['token_account'] for x in token_accounts],{'encoding':'jsonParsed','commitment':'confirmed'}]) or {}; values=(infos.get('value') or []) if isinstance(infos,dict) else []; by_owner=defaultdict(float); resolved=[]
 for row,info in zip(token_accounts,values):
  try:owner=((((info or {}).get('data') or {}).get('parsed') or {}).get('info') or {}).get('owner')
  except Exception:owner=None
  resolved.append({**row,'owner':owner})
  if owner:by_owner[owner]+=row['amount']
 owners=[{'owner':o,'amount':a,'pct':a/total*100 if total else 0} for o,a in by_owner.items()]; owners.sort(key=lambda x:x['amount'],reverse=True); rc=sum(1 for x in resolved if x.get('owner'))
 return owners,resolved,{'supply':total,'largest_accounts_returned':len(token_accounts),'owners_resolved':rc,'owner_resolution_complete':rc==len(token_accounts) and rc>0}

def _evm_total_supply(url,token):
 x=_rpc_url(url,'eth_call',[{'to':token,'data':TOTAL_SUPPLY_SELECTOR},'latest']); return _as_int_hex(x) if x else 0

def _evm_start_block(row,latest_i):
 for k in ('deployment_block','contract_creation_block','token_creation_block','start_block'):
  v=row.get(k)
  if v is not None:
   try:
    n=int(v,16) if isinstance(v,str) and v.startswith('0x') else int(v)
    if 0<=n<=latest_i:return n,k,True
   except Exception:pass
 return max(0,latest_i-EVM_LOOKBACK),'bounded_lookback',False

def _components(holders,graph,exclusions):
 pct={str(h.get('owner') or '').lower():float(h.get('pct') or 0) for h in holders if h.get('owner')}; nodes=set(pct)-set(exclusions); adj=defaultdict(set); edge_counts=defaultdict(int)
 for e in graph:
  a=str(e.get('from') or '').lower(); b=str(e.get('to') or '').lower(); n=int(e.get('transfer_count') or 0)
  if not a or not b or a==b or a not in nodes or b not in nodes:continue
  adj[a].add(b);adj[b].add(a);edge_counts[tuple(sorted((a,b)))]+=n
 seen=set();out=[]
 for root in sorted(nodes):
  if root in seen or not adj.get(root):continue
  q=deque([root]);seen.add(root);comp=[]
  while q:
   cur=q.popleft();comp.append(cur)
   for nxt in adj.get(cur,()):
    if nxt not in seen:seen.add(nxt);q.append(nxt)
  if len(comp)<2:continue
  comp_set=set(comp); transfers=sum(n for (a,b),n in edge_counts.items() if a in comp_set and b in comp_set); out.append({'wallets':sorted(comp),'wallet_count':len(comp),'combined_pct':round(sum(pct.get(x,0) for x in comp),4),'direct_transfer_count':transfers,'evidence':'DIRECT_TOKEN_TRANSFERS_AMONG_CURRENT_TOP_HOLDERS','ownership_claim':False})
 out.sort(key=lambda x:(x['combined_pct'],x['direct_transfer_count']),reverse=True);return out

def _evm_holders(chain,token,row):
 url=RPC.get(chain,''); latest=_rpc_url(url,'eth_blockNumber',[])
 if not latest:return [],[],[],{'complete':False,'reason':'EVM_RPC_UNAVAILABLE'}
 latest_i=int(latest,16); start,start_source,start_verified=_evm_start_block(row,latest_i); balances=defaultdict(int); edges=defaultdict(int); logs_seen=0; chunks=0
 for a in range(start,latest_i+1,EVM_CHUNK):
  b=min(latest_i,a+EVM_CHUNK-1);chunks+=1; logs=_rpc_url(url,'eth_getLogs',[{'fromBlock':hex(a),'toBlock':hex(b),'address':token,'topics':[TRANSFER_TOPIC]}])
  if logs is None:return [],[],[],{'complete':False,'reason':'EVM_LOG_RANGE_UNAVAILABLE','from_block':start,'to_block':latest_i,'failed_chunk':[a,b],'chunks_completed':chunks-1,'start_block_verified':start_verified,'start_block_source':start_source}
  for log in logs:
   topics=log.get('topics') or []
   if len(topics)<3:continue
   f=_addr(topics[1]);t=_addr(topics[2]);value=_as_int_hex(log.get('data') or '0x0')
   if value<0:continue
   logs_seen+=1
   if f and f!=ZERO:balances[f]-=value
   if t and t!=ZERO:balances[t]+=value
   if f and t and f!=ZERO and t!=ZERO:edges[(f,t)]+=1
 total_supply=_evm_total_supply(url,token); positive=[(o,a) for o,a in balances.items() if a>0]; denom=total_supply if total_supply>0 else 0
 holders=[{'owner':o,'raw_amount':str(a),'pct':a/denom*100 if denom else 0} for o,a in positive]; holders.sort(key=lambda x:int(x['raw_amount']),reverse=True); holders=holders[:TOP_N]; graph=[{'from':f,'to':t,'transfer_count':n} for (f,t),n in sorted(edges.items(),key=lambda x:x[1],reverse=True)[:500]]; exclusions=set(INFRA_EXCLUSIONS)|{ZERO,token.lower(),str(row.get('pair_address') or row.get('locked_pair_address') or '').lower()}; clusters=_components(holders,graph,exclusions); complete=bool(start_verified and total_supply>0)
 reason='FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK' if complete else ('FULL_START_BLOCK_BUT_TOTAL_SUPPLY_UNVERIFIED' if start_verified else 'BOUNDED_LOOKBACK_RECONSTRUCTION')
 return holders,graph,clusters,{'complete':complete,'reason':reason,'from_block':start,'to_block':latest_i,'logs_seen':logs_seen,'chunks':chunks,'lookback_blocks':latest_i-start,'observed_positive_holders':len(positive),'total_supply_raw':str(total_supply) if total_supply else None,'pct_authoritative':bool(total_supply>0),'start_block_verified':start_verified,'start_block_source':start_source,'infrastructure_exclusions':sorted(x for x in exclusions if x)}

def analyze(row):
 chain=row.get('chain'); token=row.get('token') or row.get('token_address') or row.get('mint'); c=str(chain or '').upper(); reasons=[];token_accounts=[];graph=[];clusters=[];meta={};deployer_evidence={'verified':False,'reason':'NOT_APPLICABLE'};funding=[]
 if c in ('SOL','SOLANA'):holders,token_accounts,meta=_sol_holders(token)
 elif c in ('ETH','ETHEREUM','BSC','BNB'):
  holders,graph,clusters,meta=_evm_holders(c,str(token).lower(),row);url=RPC.get(c,'');deployer_evidence=verify_evm_deployer(lambda method,params:_rpc_url(url,method,params),str(token).lower(),row);funding=verified_native_funding_edges(row);clusters=corroborate_clusters(clusters,graph,deployer_evidence,funding);meta={**meta,'deployer_evidence':deployer_evidence,'verified_native_funding_edges':len(funding)}
  if not meta.get('complete'):reasons.append(meta.get('reason','EVM_EVIDENCE_INCOMPLETE'))
 else:holders=[];reasons.append('UNSUPPORTED_CHAIN')
 p=sorted((float(x.get('pct') or 0) for x in holders),reverse=True); top1=sum(p[:1]);top5=sum(p[:5]);top10=sum(p[:10])
 if not holders:reasons.append('HOLDER_DATA_UNAVAILABLE')
 sol_complete=c in ('SOL','SOLANA') and bool(meta.get('owner_resolution_complete')); evm_complete=c in ('ETH','ETHEREUM','BSC','BNB') and bool(meta.get('complete')); verification_complete=bool((sol_complete or evm_complete) and holders)
 if c in ('SOL','SOLANA') and not sol_complete:reasons.append('SOME_TOKEN_ACCOUNT_OWNERS_UNRESOLVED')
 hard_concentration=verification_complete
 if top1>MAX_TOP1:reasons.append('TOP1_OWNER_CONCENTRATION_HIGH' if hard_concentration else 'TOP1_CONCENTRATION_HIGH_REVIEW_ONLY')
 if top5>MAX_TOP5:reasons.append('TOP5_OWNER_CONCENTRATION_HIGH' if hard_concentration else 'TOP5_CONCENTRATION_HIGH_REVIEW_ONLY')
 if top10>MAX_TOP10:reasons.append('TOP10_OWNER_CONCENTRATION_HIGH' if hard_concentration else 'TOP10_CONCENTRATION_HIGH_REVIEW_ONLY')
 linked=[x for x in clusters if x.get('combined_pct',0)>=CLUSTER_REVIEW_PCT]; corroborated=[x for x in linked if x.get('risk_corroborated') and x.get('combined_pct',0)>=CLUSTER_BLOCK_PCT]; blockable=corroborated if evm_complete else []
 if linked:reasons.append('LINKED_TOP_HOLDER_COMPONENT_REQUIRES_CORROBORATION')
 if corroborated:reasons.append('CORROBORATED_LINKED_HOLDER_CLUSTER_GE_20PCT' if evm_complete else 'CORROBORATED_LINKED_HOLDER_CLUSTER_REVIEW_ONLY_INCOMPLETE_LEDGER')
 hard_block=(hard_concentration and any(x in reasons for x in ('TOP1_OWNER_CONCENTRATION_HIGH','TOP5_OWNER_CONCENTRATION_HIGH','TOP10_OWNER_CONCENTRATION_HIGH'))) or bool(blockable)
 needs_review=bool(linked) or not verification_complete or any(x.endswith('REVIEW_ONLY') for x in reasons)
 status='BLOCK' if hard_block else ('REVIEW' if needs_review else 'PASS')
 level='ONCHAIN_OWNER_CONCENTRATION_RESOLVED' if sol_complete and holders else ('FULL_EVM_TRANSFER_LEDGER' if evm_complete and holders else ('BOUNDED_ONCHAIN_TRANSFER_LEDGER' if holders else 'INSUFFICIENT_EVIDENCE'))
 return {'chain':chain,'token':token,'pair_address':row.get('pair_address') or row.get('locked_pair_address'),'checked_at':datetime.now(timezone.utc).isoformat(),'status':status,'verification_complete':verification_complete,'top_holders_count':len(holders),'top1_pct':round(top1,4),'top5_pct':round(top5,4),'top10_pct':round(top10,4),'cluster_verified':bool(corroborated),'linked_cluster_candidates':linked,'corroborated_cluster_risks':corroborated,'blockable_cluster_risks':blockable,'deployer_evidence':deployer_evidence,'verified_native_funding_edges':funding,'reasons':list(dict.fromkeys(reasons)),'evidence_level':level,'metadata':meta,'holders':holders,'token_accounts':token_accounts,'transfer_graph':graph}

def _rows_from_source(src):
 if isinstance(src,list):return src
 if isinstance(src,dict):
  rows=src.get('rows',[]);return rows if isinstance(rows,list) else []
 return []

def run():
 src=_load(DATA/INPUT_FILE,{});rows=_rows_from_source(src);out=[];seen=set()
 for r in rows:
  if not isinstance(r,dict):continue
  chain=r.get('chain');token=r.get('token') or r.get('token_address') or r.get('mint');pair=r.get('pair_address') or r.get('locked_pair_address');key=(str(chain),str(token),str(pair))
  if not chain or not token or key in seen:continue
  seen.add(key);out.append(analyze(r))
 now=datetime.now(timezone.utc).isoformat();payload={'updated_at':now,'method':'WALLET500_HOLDER_CLUSTER_PRETRADE_GATE_V1_5_PRODUCTION_PASS','input_file':INPUT_FILE,'truth_note':'PASS means holder/cluster evidence coverage is complete and no configured concentration or linked-cluster review/block condition was found. Direct token-transfer components remain linkage evidence only; common ownership is never claimed. Incomplete evidence always remains REVIEW.','rows':out}
 _write(DATA/'holder-cluster-gate.json',payload);_write(DATA/'holder-cluster-gate-summary.json',{'updated_at':now,'input_file':INPUT_FILE,'checked':len(out),'block':sum(x['status']=='BLOCK' for x in out),'review':sum(x['status']=='REVIEW' for x in out),'pass':sum(x['status']=='PASS' for x in out),'linked_cluster_candidates':sum(len(x.get('linked_cluster_candidates') or []) for x in out),'corroborated_cluster_risks':sum(len(x.get('corroborated_cluster_risks') or []) for x in out),'blockable_cluster_risks':sum(len(x.get('blockable_cluster_risks') or []) for x in out)});print(json.dumps(_load(DATA/'holder-cluster-gate-summary.json',{}),indent=2));return payload

if __name__=='__main__':run()
