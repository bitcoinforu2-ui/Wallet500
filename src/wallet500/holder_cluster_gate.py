from __future__ import annotations
import json, os
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
 largest=_rpc('getTokenLargestAccounts',[token,{'commitment':'confirmed'}]) or {}; out=[]
 for x in (largest.get('value') or [])[:TOP_N]:
  amt=float(x.get('uiAmount') or 0); out.append({'address':x.get('address'),'amount':amt,'pct':amt/total*100 if total else 0})
 return out

def analyze(chain,token):
 c=str(chain or '').upper(); holders=_sol_holders(token) if c in ('SOL','SOLANA') else []
 p=sorted((float(x.get('pct') or 0) for x in holders),reverse=True); top1=sum(p[:1]); top5=sum(p[:5]); top10=sum(p[:10]); reasons=[]
 if not holders: reasons.append('HOLDER_DATA_UNAVAILABLE')
 if top1>MAX_TOP1: reasons.append('TOP1_CONCENTRATION_HIGH')
 if top5>MAX_TOP5: reasons.append('TOP5_CONCENTRATION_HIGH')
 if top10>MAX_TOP10: reasons.append('TOP10_CONCENTRATION_HIGH')
 # Cluster PASS is deliberately impossible until transfer/funding/deployer edges are independently proven.
 status='BLOCK' if any(x.endswith('_HIGH') for x in reasons) else 'REVIEW'
 return {'chain':chain,'token':token,'checked_at':datetime.now(timezone.utc).isoformat(),'status':status,'top_holders_count':len(holders),'top1_pct':round(top1,4),'top5_pct':round(top5,4),'top10_pct':round(top10,4),'cluster_verified':False,'reasons':reasons,'evidence_level':'ONCHAIN_HOLDER_CONCENTRATION_ONLY' if holders else 'INSUFFICIENT_EVIDENCE','holders':holders}

def run():
 src=_load(DATA/'active-qualified-candidates.json',{}); rows=src.get('rows',src if isinstance(src,list) else []); rows=rows if isinstance(rows,list) else []
 out=[]; seen=set()
 for r in rows:
  if not isinstance(r,dict): continue
  chain=r.get('chain'); token=r.get('token') or r.get('token_address') or r.get('mint'); key=(str(chain),str(token))
  if not chain or not token or key in seen: continue
  seen.add(key); out.append(analyze(chain,token))
 now=datetime.now(timezone.utc).isoformat(); payload={'updated_at':now,'method':'WALLET500_HOLDER_CLUSTER_PRETRADE_GATE_V1','truth_note':'No cluster PASS without independently verified transfer/funding/deployer evidence. EVM holder data is not fabricated.','rows':out}
 _write(DATA/'holder-cluster-gate.json',payload); _write(DATA/'holder-cluster-gate-summary.json',{'updated_at':now,'checked':len(out),'block':sum(x['status']=='BLOCK' for x in out),'review':sum(x['status']=='REVIEW' for x in out),'pass':sum(x['status']=='PASS' for x in out)})
 print(json.dumps(_load(DATA/'holder-cluster-gate-summary.json',{}),indent=2)); return payload

if __name__=='__main__': run()
