"""Wallet500 production holder/cluster quarantine gate.

Truth-first policy:
- BLOCK: remove from live path.
- REVIEW or missing evidence: quarantine; never Live/Alert.
- PASS is allowed only with verification_complete=true.

Risk-cluster corroboration and holder/cluster verification completeness are
separate concepts. A clean token does not need a suspicious cluster to exist.
"""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT=Path(os.getenv('HOLDER_CLUSTER_PRODUCTION_INPUT','data/active-qualified-candidates.json')); GATE=Path(os.getenv('HOLDER_CLUSTER_GATE_INPUT','data/holder-cluster-gate.json')); OUTPUT=Path(os.getenv('HOLDER_CLUSTER_PRODUCTION_OUTPUT','data/holder-cluster-production-qualified.json')); QUARANTINE=Path(os.getenv('HOLDER_CLUSTER_QUARANTINE_OUTPUT','data/holder-cluster-quarantine.json')); BLOCKED=Path(os.getenv('HOLDER_CLUSTER_BLOCKED_OUTPUT','data/holder-cluster-production-blocked.json')); REPORT=Path(os.getenv('HOLDER_CLUSTER_PRODUCTION_REPORT','data/holder-cluster-production-report.json'))

def _load(path:Path)->Any:
 if not path.exists():return []
 return json.loads(path.read_text())

def _rows(data:Any)->list[dict[str,Any]]:
 if isinstance(data,list):return [x for x in data if isinstance(x,dict)]
 if isinstance(data,dict):
  for key in ('rows','candidates','active','qualified'):
   value=data.get(key)
   if isinstance(value,list):return [x for x in value if isinstance(x,dict)]
 return []

def _key(row:dict[str,Any])->str:
 chain=str(row.get('chain') or '').strip().lower();token=str(row.get('token_address') or row.get('token') or row.get('mint') or row.get('address') or '').strip();pair=str(row.get('pair_address') or row.get('locked_pair_address') or row.get('pair') or '').strip()
 if chain in {'ethereum','eth','bsc','bnb'}:token=token.lower();pair=pair.lower()
 return f'{chain}|{token}|{pair}'

def apply_gate(candidates:list[dict[str,Any]],gate_rows:list[dict[str,Any]])->tuple[list[dict[str,Any]],list[dict[str,Any]],list[dict[str,Any]]]:
 by_key={_key(r):r for r in gate_rows if _key(r)!='||'};promoted=[];quarantine=[];blocked=[]
 for candidate in candidates:
  evidence=by_key.get(_key(candidate))
  if evidence is None:
   quarantine.append({**candidate,'holder_cluster_production_status':'REVIEW','holder_cluster_reason':'HOLDER_CLUSTER_EVIDENCE_MISSING','holder_cluster_verification_complete':False});continue
  status=str(evidence.get('status') or 'REVIEW').upper();complete=evidence.get('verification_complete') is True;reasons=evidence.get('reasons') or [];enriched={**candidate,'holder_cluster_production_status':status,'holder_cluster_verification_complete':complete,'holder_cluster_risk_cluster_verified':evidence.get('cluster_verified') is True,'holder_cluster_reasons':reasons,'holder_cluster_checked_at':evidence.get('checked_at')}
  if status=='BLOCK':blocked.append(enriched)
  elif status=='PASS' and complete:promoted.append(enriched)
  else:
   enriched['holder_cluster_production_status']='REVIEW'
   if status=='PASS' and not complete:enriched['holder_cluster_reason']='PASS_WITHOUT_COMPLETE_HOLDER_CLUSTER_VERIFICATION'
   quarantine.append(enriched)
 return promoted,quarantine,blocked

def main()->None:
 candidates=_rows(_load(INPUT));gate_rows=_rows(_load(GATE));promoted,quarantine,blocked=apply_gate(candidates,gate_rows);now=datetime.now(timezone.utc).isoformat();OUTPUT.write_text(json.dumps(promoted,indent=2));QUARANTINE.write_text(json.dumps(quarantine,indent=2));BLOCKED.write_text(json.dumps(blocked,indent=2));report={'updated_at':now,'mode':'PRODUCTION_FAIL_CLOSED','input_count':len(candidates),'promoted_count':len(promoted),'quarantine_count':len(quarantine),'blocked_count':len(blocked),'downstream_input':str(OUTPUT),'policy':'Only PASS + verification_complete=true may reach Live/Alert; REVIEW/missing evidence quarantined; BLOCK rejected.'};REPORT.write_text(json.dumps(report,indent=2));print('HOLDER CLUSTER PRODUCTION:',report)

if __name__=='__main__':main()
