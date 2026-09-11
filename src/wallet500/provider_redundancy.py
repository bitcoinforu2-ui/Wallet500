from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VERSION="WALLET500_PROVIDER_REDUNDANCY_V1"


def _load(path: Path, default: Any):
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, payload: dict):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    tmp.replace(path)


def run(data_dir: str|Path="data") -> dict:
    data=Path(data_dir)
    waking=_load(data/"waking-confirmation-latest.json",{})
    families={"holders":set(),"wallets":set(),"social":set(),"news":set(),"distribution":set()}
    degraded=set()
    for row in waking.get("targets") or []:
        if not isinstance(row,dict): continue
        for name,ch in (row.get("channels") or {}).items():
            if name not in families or not isinstance(ch,dict): continue
            source=str(ch.get("source") or "").strip()
            if source and ch.get("verified") is True:
                families[name].add(source)
        for item in row.get("provider_status") or []:
            if not isinstance(item,dict): continue
            provider=str(item.get("provider") or "").lower().strip()
            status=str(item.get("status") or "UNKNOWN").upper()
            if provider and status not in {"OK","SUCCESS","AVAILABLE"}:
                degraded.add(provider)
    detail={}
    single=[]
    missing=[]
    for family,sources in families.items():
        n=len(sources)
        state="REDUNDANT" if n>=2 else "SINGLE_SOURCE" if n==1 else "NO_VERIFIED_SOURCE"
        detail[family]={"state":state,"verified_sources":sorted(sources),"verified_source_count":n}
        if n==1: single.append(family)
        if n==0: missing.append(family)
    payload={
        "version":VERSION,
        "mode":"RESEARCH_ONLY_PROVIDER_REDUNDANCY_DIAGNOSTIC",
        "production_effect":False,
        "automatic_buy":False,
        "failed_provider_counts_as_positive_evidence":False,
        "families":detail,
        "single_source_families":single,
        "missing_verified_source_families":missing,
        "degraded_providers":sorted(degraded),
        "safe_action":"KEEP_FAIL_CLOSED_AND_ROUTE_EXISTING_FALLBACKS_ONLY; DO_NOT FABRICATE REDUNDANCY",
    }
    _write(data/"provider-redundancy.json",payload)
    return payload


def main():
    print(json.dumps(run(),ensure_ascii=False))

if __name__=="__main__": main()
