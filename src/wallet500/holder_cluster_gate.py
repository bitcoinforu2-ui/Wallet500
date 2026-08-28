from __future__ import annotations
import json, os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA=Path('data'); TOP_N=20
MAX_TOP1=20.0; MAX_TOP5=50.0; MAX_TOP10=65.0
RPC={'SOLANA':os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com'),'SOL':os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com')}

def _load(p,d):
 try: return json.loads(p.read_text()) if p.exists() else d
 except Exception: return d

def _write(p,x): p.write_text(json.dumps(x,indent=2))
def _rpc(method,params):
 try:
  req=Request(RPC['SOL'],data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers={'Content-Type':'application/json','User-Agent':'Wallet500/1.0'})
  with urlopen(req,timeout=20) as r: return json.loads(r.read().decode()).get('result')
 except Exception: return None

def _sol_holders(token):
 supply=_rpc('getTokenSupply',[token,{'commitment':'confirmed'}]) or {}; total=float((supply.get('value') or {}).get('uiAmount') or 0)
 largest=_rpc('getTokenLargestAccounts',[token,{'commitment':'confirmed'}]) or {}; token_accounts=[]
 for x in (largest.get('value') or [])[:TOP_N]:
  amt=float(x.get('uiAmount') or 0); addr=x.get('address')
  if addr and amt>0: token_accounts.append({'token_account':addr,'amount':amt,'pct_of_supply':amt/total*100 if total else 0})
 if not token_accounts: return [],[],{'supply':total,'largest_accounts_returned':0,'owners_resolved':0}
 infos=_rpc('getMultipleAccounts',[[x['token_account'] for x in token_accounts],{'encoding':'jsonParsed','commitment':'confirmed'}]) or {}
 values=(infos.get('value') or []) if isinstance(infos,dict) else []
 by_owner=defaultdict(float); resolved=[]
 for row,info in zip(token_accounts,values):
  owner=None
  try: owner=((((info or {}).get('data') or {}).get('parsed') or {}).get('info') or {}).get('owner')
  except Exception: owner=None
  item={**row,'owner':owner}
  resolved.append(item)
  if owner: by_owner[owner]+=row['amount']
 owners=[{'owner':o,'amount':a,'pct':a/total*100 if total else 0} for o,a in by_owner.items()]
 owners.sort(key=lambda x:x['amount'],reverse=True)
 return owners,resolved,{'supply':total,'largest_accounts_returned':len(token_accounts),'owners_resolved':sum(1 for x in resolved if x.get('owner'))}

def analyze(chain,token):
 c=str(chain or '').upper(); reasons=[]; token_accounts=[]; meta={}
 if c in ('SOL','SOLANA'):
  holders,token_accounts,meta=_sol_holders(token)
 else:
  holders=[]; reasons.append('EVM_HOLDER_INDEX_NOT_IMPLEMENTED')
 p=sorted((float(x.get('pct') or 0) for x in holders),reverse=True); top1=sum(p[:1]); top5=sum(p[:5]); top10=sum(p[:10])
 if not holders: reasons.append('HOLDER_DATA_UNAVAILABLE')
 if c in ('SOL','SOLANA') and meta.get('owners_resolved',0)<meta.get('largest_accounts_returned',0): reasons.append('SOME_TOKEN_ACCOUNT_OWNERS_UNRESOLVED')
 if top1>MAX_TOP1: reasons.append('TOP1_OWNER_CONCENTRATION_HIGH')
 if top5>MAX_TOP5: reasons.append('TOP5_OWNER_CONCENTRATION_HIGH')
 if top10>MAX_TOP10: reasons.append('TOP10_OWNER_CONCENTRATION_HIGH')
 status='BLOCK' if any(x.endswith('_HIGH') for x in reasons) else 'REVIEW'
 return {'chain':chain,'token':token,'checked_at':datetime.now(timezone.utc).isoformat(),'status':status,'top_holders_count':len(holders),'top1_pct':round(top1,4),'top5_pct':round(top5,4),'top10_pct':round(top10,4),'cluster_verified':False,'reasons':list(dict.fromkeys(reasons)),'evidence_level':'ONCHAIN_OWNER_CONCENTRATION_RESOLVED' if holders else 'INSUFFICIENT_EVIDENCE','solana_metadata':meta if c in ('SOL','SOLANA') else None,'holders':holders,'token_accounts':token_accounts}

def run():
 src=_load(DATA/'active-qualified-candidates.json',{}); rows=src.get('rows',src if isinstance(src,list) else []); rows=rows if isinstance(rows,list) else []
 out=[]; seen=set()
 for r in rows:
  if not isinstance(r,dict): continue
  chain=r.get('chain'); token=r.get('token') or r.get('token_address') or r.get('mint'); key=(str(chain),str(token))
  if not chain or not token or key in seen: continue
  seen.add(key); out.append(analyze(chain,token))
 now=datetime.now(timezone.utc).isoformat(); payload={'updated_at':now,'method':'WALLET500_HOLDER_CLUSTER_PRETRADE_GATE_V1_1_OWNER_RESOLVED','truth_note':'Solana concentration is aggregated by resolved owner wallet, not raw SPL token account. No cluster PASS without independently verified transfer/funding/deployer evidence. EVM holder data is not fabricated.','rows':out}
 _write(DATA/'holder-cluster-gate.json',payload); _write(DATA/'holder-cluster-gate-summary.json',{'updated_at':now,'checked':len(out),'block':sum(x['status']=='BLOCK' for x in out),'review':sum(x['status']=='REVIEW' for x in out),'pass':sum(x['status']=='PASS' for x in out)})
 print(json.dumps(_load(DATA/'holder-cluster-gate-summary.json',{}),indent=2)); return payload

if __name__=='__main__': run()
