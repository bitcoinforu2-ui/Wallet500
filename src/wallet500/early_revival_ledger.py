"""Append-only storage boundary for Early Revival research checkpoints."""
from __future__ import annotations
from pathlib import Path
import json, os
from typing import Any, Iterable
REQUIRED={"truth_hash_sha256","identity_key","observed_at","semantics","mutable"}
def validate_checkpoint(row:dict[str,Any])->None:
    missing=REQUIRED-set(row)
    if missing: raise ValueError(f"EARLY_REVIVAL_LEDGER_FAIL_CLOSED_MISSING:{sorted(missing)}")
    if row.get("mutable") is not False: raise ValueError("EARLY_REVIVAL_LEDGER_FAIL_CLOSED_MUTABLE")
    if row.get("production_promotion_allowed") is not False: raise ValueError("EARLY_REVIVAL_LEDGER_FAIL_CLOSED_PRODUCTION_LEAK")
def read_hashes(path:Path)->set[str]:
    if not path.exists(): return set()
    hashes=set()
    with path.open("r",encoding="utf-8") as fh:
        for n,line in enumerate(fh,1):
            if not line.strip(): continue
            try: row=json.loads(line)
            except json.JSONDecodeError as exc: raise ValueError(f"EARLY_REVIVAL_LEDGER_CORRUPT_LINE:{n}") from exc
            validate_checkpoint(row); h=row["truth_hash_sha256"]
            if h in hashes: raise ValueError(f"EARLY_REVIVAL_LEDGER_DUPLICATE_HASH:{h}")
            hashes.add(h)
    return hashes
def append_checkpoints(path:str|Path,rows:Iterable[dict[str,Any]])->int:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); seen=read_hashes(path); pending=[]
    for row in rows:
        validate_checkpoint(row); h=row["truth_hash_sha256"]
        if h in seen: continue
        seen.add(h); pending.append(row)
    if not pending:return 0
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o644)
    with os.fdopen(fd,"a",encoding="utf-8") as fh:
        for row in pending: fh.write(json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n")
        fh.flush(); os.fsync(fh.fileno())
    return len(pending)
