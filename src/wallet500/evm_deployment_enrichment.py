from __future__ import annotations

"""Fail-closed EVM deployment-block enrichment.

Primary proof: archive eth_getCode boundary (empty at N-1, code at N).
Fallback proof for fresh ERC-20s: locate a zero-address mint Transfer near pair creation,
then verify that the mint transaction itself created this exact token contract
(tx.to is null and receipt.contractAddress == token). Only then is the block trusted.
Unknown evidence always stays unresolved.
"""

import json, os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA=Path('data')
INPUT=DATA/os.getenv('EVM_DEPLOYMENT_INPUT','active-qualified-candidates.json')
REPORT=DATA/'evm-deployment-enrichment-report.json'
TRANSFER_TOPIC='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
ZERO_TOPIC='0x'+'0'*64
MINT_SEARCH_BACK=max(5000,int(os.getenv('EVM_MINT_SEARCH_BACK_BLOCKS','120000')))
MINT_LOG_CHUNK=max(100,int(os.getenv('EVM_MINT_LOG_CHUNK','3000')))
DEFAULT_RPC={
 'ethereum':['https://ethereum-rpc.publicnode.com','https://eth.llamarpc.com'],
 'bsc':['https://bsc-rpc.publicnode.com','https://bsc-dataseed.binance.org'],
}

def _urls(*values):
 out=[]
 for value in values:
  for raw in str(value or '').split(','):
   u=raw.strip()
   if u and u not in out:out.append(u)
 return out

RPC={
 'ethereum':_urls(os.getenv('ETHEREUM_RPC_URL'),os.getenv('ETH_RPC_URL'),os.getenv('ETH_RPC_FALLBACK_URLS'),*DEFAULT_RPC['ethereum']),
 'bsc':_urls(os.getenv('BSC_RPC_URL'),os.getenv('BNB_RPC_URL'),os.getenv('BSC_RPC_FALLBACK_URLS'),*DEFAULT_RPC['bsc']),
}

def _rpc_url(url,method,params):
 try:
  req=Request(url,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers={'Content-Type':'application/json','User-Agent':'Wallet500/1.0'})
  with urlopen(req,timeout=20) as r:payload=json.loads(r.read().decode())
  return None if payload.get('error') else payload.get('result')
 except Exception:return None

def _rpc_any(urls,method,params):
 for url in urls:
  result=_rpc_url(url,method,params)
  if result is not None:return result,url
 return None,None

def _has_code_at(urls,token,block):
 result,used=_rpc_any(urls,'eth_getCode',[token,hex(block)])
 if result is None:return None,used
 return str(result).lower() not in ('0x','0x0',''),used

def _block(urls,n):return _rpc_any(urls,'eth_getBlockByNumber',[hex(n),False])

def _block_for_timestamp(urls,target_ts,latest):
 lo,hi=0,latest; used=set(); queries=0
 while lo<hi:
  mid=(lo+hi)//2; b,url=_block(urls,mid); queries+=1
  if url:used.add(url)
  if not isinstance(b,dict) or b.get('timestamp') is None:return None,{'verified':False,'reason':'BLOCK_TIMESTAMP_QUERY_UNAVAILABLE','queries':queries}
  ts=int(b['timestamp'],16)
  if ts<target_ts:lo=mid+1
  else:hi=mid
 return lo,{'verified':True,'reason':'BLOCK_BY_TIMESTAMP_RESOLVED','queries':queries,'rpc_endpoints_used':len(used)}

def _mint_deployment_fallback(urls,token,row,latest):
 try:pair_ms=int(row.get('pair_created_at') or 0)
 except Exception:pair_ms=0
 if pair_ms<=0:return None,{'verified':False,'reason':'PAIR_CREATION_TIME_UNAVAILABLE_FOR_MINT_FALLBACK'}
 anchor,anchor_ev=_block_for_timestamp(urls,pair_ms//1000,latest)
 if anchor is None:return None,anchor_ev
 hi=min(latest,anchor+3000); floor=max(0,anchor-MINT_SEARCH_BACK); used=set(); chunks=0; mint_logs=[]
 for b in range(hi,floor-1,-MINT_LOG_CHUNK):
  a=max(floor,b-MINT_LOG_CHUNK+1); chunks+=1
  logs,url=_rpc_any(urls,'eth_getLogs',[{'fromBlock':hex(a),'toBlock':hex(b),'address':token,'topics':[TRANSFER_TOPIC,ZERO_TOPIC]}])
  if url:used.add(url)
  if logs is None:
   return None,{'verified':False,'reason':'MINT_LOG_RANGE_UNAVAILABLE','failed_chunk':[a,b],'chunks_completed':chunks-1,'anchor_block':anchor}
  mint_logs.extend(x for x in logs if isinstance(x,dict) and x.get('transactionHash'))
 if not mint_logs:
  return None,{'verified':False,'reason':'NO_ZERO_ADDRESS_MINT_IN_VERIFIED_SEARCH_WINDOW','anchor_block':anchor,'from_block':floor,'to_block':hi,'chunks':chunks}
 mint_logs.sort(key=lambda x:int(x.get('blockNumber','0x0'),16))
 for log in mint_logs:
  txh=log.get('transactionHash'); block=int(log.get('blockNumber','0x0'),16)
  tx,txurl=_rpc_any(urls,'eth_getTransactionByHash',[txh]); receipt,rcurl=_rpc_any(urls,'eth_getTransactionReceipt',[txh])
  if txurl:used.add(txurl)
  if rcurl:used.add(rcurl)
  created=str((receipt or {}).get('contractAddress') or '').lower()
  direct=isinstance(tx,dict) and tx.get('to') is None and created==token.lower()
  if direct:
   return block,{'verified':True,'reason':'DIRECT_DEPLOYMENT_TX_PROVEN_FROM_ZERO_ADDRESS_MINT','deployment_block':block,'mint_tx_hash':txh,'pair_anchor_block':anchor,'search_from_block':floor,'search_to_block':hi,'mint_logs_found':len(mint_logs),'chunks':chunks,'rpc_endpoints_used':len(used)}
 return None,{'verified':False,'reason':'ZERO_MINT_FOUND_BUT_DIRECT_DEPLOYMENT_TX_NOT_PROVEN','pair_anchor_block':anchor,'search_from_block':floor,'search_to_block':hi,'mint_logs_found':len(mint_logs),'chunks':chunks,'rpc_endpoints_used':len(used)}

def discover_deployment_block(urls,token,row=None):
 row=row or {}; latest_raw,latest_url=_rpc_any(urls,'eth_blockNumber',[])
 if latest_raw is None:return None,{'verified':False,'reason':'EVM_RPC_UNAVAILABLE'}
 latest=int(latest_raw,16); latest_has_code,code_url=_has_code_at(urls,token,latest)
 if latest_has_code is not True:return None,{'verified':False,'reason':'NO_CURRENT_CONTRACT_CODE_OR_RPC_UNAVAILABLE','latest_block':latest}
 lo,hi=0,latest;queries=1;used={x for x in (latest_url,code_url) if x}; archive_failed=None
 while lo<hi:
  mid=(lo+hi)//2;has_code,url=_has_code_at(urls,token,mid);queries+=1
  if url:used.add(url)
  if has_code is None:
   archive_failed={'failed_block':mid,'queries':queries,'rpc_endpoints_used':len(used)};break
  if has_code:hi=mid
  else:lo=mid+1
 if archive_failed is None:
  first=lo;has_first,url1=_has_code_at(urls,token,first)
  if url1:used.add(url1)
  if has_first is True:
   if first==0:
    return first,{'verified':True,'reason':'ONCHAIN_ETH_GETCODE_BOUNDARY_VERIFIED','deployment_block':first,'latest_block':latest,'queries':queries+1,'rpc_endpoints_used':len(used)}
   has_prev,url2=_has_code_at(urls,token,first-1)
   if url2:used.add(url2)
   if has_prev is False:
    return first,{'verified':True,'reason':'ONCHAIN_ETH_GETCODE_BOUNDARY_VERIFIED','deployment_block':first,'latest_block':latest,'queries':queries+2,'rpc_endpoints_used':len(used)}
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
  if block is not None and evidence.get('verified') is True:
   item['deployment_block']=block;item['deployment_block_source']=evidence.get('reason');enriched+=1;methods[item['deployment_block_source']]=methods.get(item['deployment_block_source'],0)+1
  else:unresolved.append({'chain':chain,'token':token,'reason':evidence.get('reason')})
  out.append(item)
 INPUT.write_text(json.dumps(out,indent=2))
 report={'updated_at':now,'mode':'FAIL_CLOSED_ONCHAIN_DEPLOYMENT_ENRICHMENT_V2','input_count':len(rows),'enriched_count':enriched,'already_had_start_block':already_verified,'unresolved_count':len(unresolved),'verification_methods':methods,'unresolved':unresolved,'truth_rule':'deployment/start block is written only from an eth_getCode deployment boundary or a direct contract-creation transaction independently proven from a zero-address ERC20 mint; all other cases remain unresolved'}
 REPORT.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));return report

if __name__=='__main__':run()
