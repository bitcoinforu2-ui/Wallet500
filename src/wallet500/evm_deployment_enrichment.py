from __future__ import annotations

"""Fail-closed EVM deployment-block enrichment with adaptive RPC log ranges."""
import json, os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA=Path('data'); INPUT=DATA/os.getenv('EVM_DEPLOYMENT_INPUT','active-qualified-candidates.json'); REPORT=DATA/'evm-deployment-enrichment-report.json'
TRANSFER_TOPIC='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'; ZERO_TOPIC='0x'+'0'*64
MINT_SEARCH_BACK=max(5000,int(os.getenv('EVM_MINT_SEARCH_BACK_BLOCKS','120000'))); MINT_LOG_CHUNK=max(100,int(os.getenv('EVM_MINT_LOG_CHUNK','2000'))); MIN_LOG_SPAN=max(10,int(os.getenv('EVM_MIN_LOG_SPAN','100')))
DEFAULT_RPC={'ethereum':['https://ethereum-rpc.publicnode.com','https://eth.llamarpc.com'],'bsc':['https://bsc-rpc.publicnode.com','https://bsc-dataseed.binance.org']}

def _urls(*values):
 out=[]
 for value in values:
  for raw in str(value or '').split(','):
   u=raw.strip()
   if u and u not in out:out.append(u)
 return out
RPC={'ethereum':_urls(os.getenv('ETHEREUM_RPC_URL'),os.getenv('ETH_RPC_URL'),os.getenv('ETH_RPC_FALLBACK_URLS'),*DEFAULT_RPC['ethereum']),'bsc':_urls(os.getenv('BSC_RPC_URL'),os.getenv('BNB_RPC_URL'),os.getenv('BSC_RPC_FALLBACK_URLS'),*DEFAULT_RPC['bsc'])}

def _rpc_url(url,method,params):
 try:
  req=Request(url,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers={'Content-Type':'application/json','User-Agent':'Wallet500/1.0'})
  with urlopen(req,timeout=20) as r: payload=json.loads(r.read().decode())
  return None if payload.get('error') else payload.get('result')
 except Exception:return None

def _rpc_any(urls,method,params):
 for url in urls:
  result=_rpc_url(url,method,params)
  if result is not None:return result,url
 return None,None

def _logs_resilient(urls,flt,a,b):
 """Fetch an exact log range; split only on RPC failure. Never treats failure as empty."""
 params={**flt,'fromBlock':hex(a),'toBlock':hex(b)}; logs,url=_rpc_any(urls,'eth_getLogs',[params])
 if logs is not None:return logs,{'queries':1,'splits':0,'rpc_endpoints_used':1 if url else 0,'failed_range':None}
 if b-a+1<=MIN_LOG_SPAN:return None,{'queries':1,'splits':0,'rpc_endpoints_used':0,'failed_range':[a,b]}
 mid=(a+b)//2; left,lm=_logs_resilient(urls,flt,a,mid); right,rm=_logs_resilient(urls,flt,mid+1,b)
 meta={'queries':lm['queries']+rm['queries']+1,'splits':lm['splits']+rm['splits']+1,'rpc_endpoints_used':max(lm['rpc_endpoints_used'],rm['rpc_endpoints_used']),'failed_range':lm.get('failed_range') or rm.get('failed_range')}
 if left is None or right is None:return None,meta
 return left+right,meta

def _has_code_at(urls,token,block):
 result,used=_rpc_any(urls,'eth_getCode',[token,hex(block)])
 if result is None:return None,used
 return str(result).lower() not in ('0x','0x0',''),used

def _block(urls,n):return _rpc_any(urls,'eth_getBlockByNumber',[hex(n),False])
def _block_for_timestamp(urls,target_ts,latest):
 lo,hi=0,latest;used=set();queries=0
 while lo<hi:
  mid=(lo+hi)//2;b,url=_block(urls,mid);queries+=1
  if url:used.add(url)
  if not isinstance(b,dict) or b.get('timestamp') is None:return None,{'verified':False,'reason':'BLOCK_TIMESTAMP_QUERY_UNAVAILABLE','queries':queries}
  if int(b['timestamp'],16)<target_ts:lo=mid+1
  else:hi=mid
 return lo,{'verified':True,'reason':'BLOCK_BY_TIMESTAMP_RESOLVED','queries':queries,'rpc_endpoints_used':len(used)}

def _prove_direct_creation(urls,token,logs,used):
 for log in sorted((x for x in logs if isinstance(x,dict) and x.get('transactionHash')),key=lambda x:int(x.get('blockNumber','0x0'),16)):
  txh=log['transactionHash'];block=int(log.get('blockNumber','0x0'),16);tx,tu=_rpc_any(urls,'eth_getTransactionByHash',[txh]);receipt,ru=_rpc_any(urls,'eth_getTransactionReceipt',[txh])
  if tu:used.add(tu)
  if ru:used.add(ru)
  if isinstance(tx,dict) and tx.get('to') is None and str((receipt or {}).get('contractAddress') or '').lower()==token.lower():return block,txh
 return None,None

def _mint_deployment_fallback(urls,token,row,latest):
 try:pair_ms=int(row.get('pair_created_at') or 0)
 except Exception:pair_ms=0
 if pair_ms<=0:return None,{'verified':False,'reason':'PAIR_CREATION_TIME_UNAVAILABLE_FOR_MINT_FALLBACK'}
 anchor,anchor_ev=_block_for_timestamp(urls,pair_ms//1000,latest)
 if anchor is None:return None,anchor_ev
 hi=min(latest,anchor+3000);floor=max(0,anchor-MINT_SEARCH_BACK);used=set();chunks=0;queries=0;splits=0;mint_logs_found=0
 # Search newest-to-oldest but prove immediately when a mint log is found, avoiding a brittle full-window read.
 b=hi
 while b>=floor:
  a=max(floor,b-MINT_LOG_CHUNK+1);chunks+=1;logs,meta=_logs_resilient(urls,{'address':token,'topics':[TRANSFER_TOPIC,ZERO_TOPIC]},a,b);queries+=meta['queries'];splits+=meta['splits']
  if logs is None:return None,{'verified':False,'reason':'MINT_LOG_RANGE_UNAVAILABLE','failed_chunk':meta.get('failed_range') or [a,b],'chunks_completed':chunks-1,'adaptive_log_queries':queries,'adaptive_splits':splits,'anchor_block':anchor}
  mint_logs_found+=len(logs);block,txh=_prove_direct_creation(urls,token,logs,used)
  if block is not None:return block,{'verified':True,'reason':'DIRECT_DEPLOYMENT_TX_PROVEN_FROM_ZERO_ADDRESS_MINT','deployment_block':block,'mint_tx_hash':txh,'pair_anchor_block':anchor,'search_from_block':a,'search_to_block':hi,'mint_logs_found':mint_logs_found,'chunks':chunks,'adaptive_log_queries':queries,'adaptive_splits':splits,'rpc_endpoints_used':len(used)}
  b=a-1
 return None,{'verified':False,'reason':'NO_DIRECT_DEPLOYMENT_TX_PROVEN_IN_MINT_WINDOW','anchor_block':anchor,'from_block':floor,'to_block':hi,'chunks':chunks,'mint_logs_found':mint_logs_found,'adaptive_log_queries':queries,'adaptive_splits':splits}

def discover_deployment_block(urls,token,row=None):
 row=row or {};latest_raw,latest_url=_rpc_any(urls,'eth_blockNumber',[])
 if latest_raw is None:return None,{'verified':False,'reason':'EVM_RPC_UNAVAILABLE'}
 latest=int(latest_raw,16);latest_has_code,code_url=_has_code_at(urls,token,latest)
 if latest_has_code is not True:return None,{'verified':False,'reason':'NO_CURRENT_CONTRACT_CODE_OR_RPC_UNAVAILABLE','latest_block':latest}
 lo,hi=0,latest;queries=1;used={x for x in (latest_url,code_url) if x};archive_failed=None
 while lo<hi:
  mid=(lo+hi)//2;has_code,url=_has_code_at(urls,token,mid);queries+=1
  if url:used.add(url)
  if has_code is None:archive_failed={'failed_block':mid,'queries':queries,'rpc_endpoints_used':len(used)};break
  if has_code:hi=mid
  else:lo=mid+1
 if archive_failed is None:
  first=lo;has_first,url1=_has_code_at(urls,token,first)
  if url1:used.add(url1)
  if has_first is True:
   if first==0:return first,{'verified':True,'reason':'ONCHAIN_ETH_GETCODE_BOUNDARY_VERIFIED','deployment_block':first,'latest_block':latest,'queries':queries+1,'rpc_endpoints_used':len(used)}
   has_prev,url2=_has_code_at(urls,token,first-1)
   if url2:used.add(url2)
   if has_prev is False:return first,{'verified':True,'reason':'ONCHAIN_ETH_GETCODE_BOUNDARY_VERIFIED','deployment_block':first,'latest_block':latest,'queries':queries+2,'rpc_endpoints_used':len(used)}
 fallback,ev=_mint_deployment_fallback(urls,token,row,latest)
 if fallback is not None:return fallback,{**ev,'archive_boundary_available':False}
 return None,{**ev,'archive_boundary_available':False,'archive_failure':archive_failed or {'reason':'DEPLOYMENT_BOUNDARY_NOT_PROVEN'},'latest_block':latest}

def run():
 now=datetime.now(timezone.utc).isoformat()
 try:rows=json.loads(INPUT.read_text()) if INPUT.exists() else []
 except Exception:rows=[]
 if not isinstance(rows,list):rows=[]
 enriched=0;already_verified=0;unresolved=[];out=[];methods={}
 for row in rows:
  if not isinstance(row,dict):continue
  item=dict(row);chain=str(item.get('chain') or '').lower();token=str(item.get('token') or item.get('token_address') or '').lower();existing=item.get('deployment_block') or item.get('contract_creation_block') or item.get('token_creation_block') or item.get('start_block')
  if chain not in RPC or not token:out.append(item);continue
  if existing is not None:already_verified+=1;out.append(item);continue
  block,evidence=discover_deployment_block(RPC[chain],token,item);item['deployment_block_evidence']=evidence
  if block is not None and evidence.get('verified') is True:item['deployment_block']=block;item['deployment_block_source']=evidence.get('reason');enriched+=1;methods[item['deployment_block_source']]=methods.get(item['deployment_block_source'],0)+1
  else:unresolved.append({'chain':chain,'token':token,'reason':evidence.get('reason'),'evidence':evidence})
  out.append(item)
 INPUT.write_text(json.dumps(out,indent=2));report={'updated_at':now,'mode':'FAIL_CLOSED_ONCHAIN_DEPLOYMENT_ENRICHMENT_V3_ADAPTIVE_LOGS','input_count':len(rows),'enriched_count':enriched,'already_had_start_block':already_verified,'unresolved_count':len(unresolved),'verification_methods':methods,'unresolved':unresolved,'truth_rule':'deployment/start block is written only from an eth_getCode deployment boundary or a direct contract-creation transaction independently proven from a zero-address ERC20 mint; adaptive RPC splitting improves evidence availability but never converts unavailable evidence into proof'}
 REPORT.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));return report

if __name__=='__main__':run()
