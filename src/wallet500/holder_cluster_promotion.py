from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

DATA=Path('data')
ACTIVE=DATA/'active-qualified-candidates.json'
GATE=DATA/'holder-cluster-gate.json'
PROMOTED=DATA/'holder-cluster-promoted.json'
REVIEW=DATA/'holder-cluster-review.json'
BLOCKED=DATA/'holder-cluster-blocked.json'
SUMMARY=DATA/'holder-cluster-promotion-summary.json'


def _load(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def _rows(src):
    if isinstance(src, list):
        return src
    if isinstance(src, dict):
        rows=src.get('rows', [])
        return rows if isinstance(rows, list) else []
    return []


def _key(row):
    chain=str(row.get('chain') or '').lower()
    token=str(row.get('token') or row.get('token_address') or row.get('mint') or '').lower()
    pair=str(row.get('pair_address') or row.get('locked_pair_address') or '').lower()
    return chain, token, pair


def classify(active_rows, gate_rows):
    gate_by_key={_key(r):r for r in gate_rows if isinstance(r,dict)}
    gate_by_token={(str(r.get('chain') or '').lower(),str(r.get('token') or '').lower()):r for r in gate_rows if isinstance(r,dict)}
    promoted=[]; review=[]; blocked=[]
    for row in active_rows:
        if not isinstance(row,dict):
            continue
        k=_key(row)
        g=gate_by_key.get(k) or gate_by_token.get((k[0],k[1]))
        if not g:
            review.append({**row,'holder_cluster_promotion':'REVIEW','holder_cluster_reason':'GATE_EVIDENCE_MISSING'})
            continue
        status=str(g.get('status') or '').upper()
        verified=bool(g.get('cluster_verified'))
        evidence_level=g.get('evidence_level')
        reasons=g.get('reasons') or []
        enriched={**row,'holder_cluster_status':status,'holder_cluster_verified':verified,'holder_cluster_evidence_level':evidence_level,'holder_cluster_reasons':reasons}
        if status=='BLOCK':
            blocked.append({**enriched,'holder_cluster_promotion':'BLOCK'})
        elif status=='PASS' and verified:
            promoted.append({**enriched,'holder_cluster_promotion':'PASS'})
        else:
            review.append({**enriched,'holder_cluster_promotion':'REVIEW'})
    return promoted,review,blocked


def run():
    active=_rows(_load(ACTIVE,[])); gate=_rows(_load(GATE,{}))
    promoted,review,blocked=classify(active,gate)
    now=datetime.now(timezone.utc).isoformat()
    PROMOTED.write_text(json.dumps(promoted,indent=2))
    REVIEW.write_text(json.dumps(review,indent=2))
    BLOCKED.write_text(json.dumps(blocked,indent=2))
    summary={'updated_at':now,'mode':'SHADOW_FAIL_CLOSED','active_input':len(active),'promoted':len(promoted),'review':len(review),'blocked':len(blocked),'truth_note':'Only PASS with cluster_verified=true can be promoted. REVIEW is quarantined. BLOCK is excluded. This shadow gate does not overwrite active-qualified-candidates.json.'}
    SUMMARY.write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':
    run()
