from __future__ import annotations

import json
import os
from pathlib import Path
from .config import Settings
from .evidence_engine import build_evidence_snapshot


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def _identity_key(row: dict) -> str | None:
    ident=row.get('identity') if isinstance(row.get('identity'),dict) else row
    chain=ident.get('chain'); token=ident.get('token') or ident.get('mint') or ident.get('token_address'); pair=ident.get('pair_address')
    if not chain or not token or not pair:
        return None
    if str(chain).lower() in {'ethereum','bsc','bnb','eth'}:
        token=str(token).lower(); pair=str(pair).lower()
    return f'{chain}:{token}:{pair}'


def capture() -> dict:
    out=Path(Settings().output_dir); out.mkdir(parents=True,exist_ok=True)
    source_name=os.getenv('WALLET500_EVIDENCE_INPUT','active-qualified-candidates.json')
    candidates=_load(out/source_name,[])
    if not isinstance(candidates,list): candidates=[]
    ledger_path=out/'discovery-evidence-ledger.json'
    ledger=_load(ledger_path,{})
    records=ledger.get('records') if isinstance(ledger,dict) and isinstance(ledger.get('records'),dict) else {}
    added=0; skipped=0
    for candidate in candidates:
        if not isinstance(candidate,dict): continue
        key=_identity_key(candidate)
        if not key: skipped+=1; continue
        if key in records: skipped+=1; continue
        snap=build_evidence_snapshot(candidate)
        records[key]=snap; added+=1
    payload={
        'schema_version':2,
        'policy':'APPEND_ONLY_FIRST_QUALIFIED_EVIDENCE_PAIR_LOCKED_NO_HINDSIGHT',
        'source':source_name,
        'records_count':len(records),
        'added_this_run':added,
        'skipped_this_run':skipped,
        'records':records,
    }
    ledger_path.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    current_keys={_identity_key(x) for x in candidates if isinstance(x,dict)}
    (out/'latest-evidence-snapshots.json').write_text(json.dumps([records[k] for k in records if k in current_keys],indent=2),encoding='utf-8')
    print(json.dumps({'evidence_source':source_name,'evidence_records':len(records),'added':added,'skipped':skipped},indent=2))
    return payload


if __name__ == '__main__':
    capture()
