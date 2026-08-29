from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .adapters.solana import SolanaAdapter
from .config import Settings


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def extract_signers(tx: dict | None) -> list[str]:
    """Return only accounts explicitly marked as transaction signers."""
    if not isinstance(tx, dict):
        return []
    message = (((tx.get("transaction") or {}).get("message")) or {})
    keys = message.get("accountKeys") or []
    out = []
    for item in keys:
        if isinstance(item, dict):
            pubkey = item.get("pubkey")
            if item.get("signer") is True and pubkey:
                out.append(str(pubkey))
    return list(dict.fromkeys(out))


def discover_solana_candidate_wallets(adapter, candidate: dict, signatures_limit: int = 10) -> dict:
    token = candidate.get("token") or candidate.get("mint") or ""
    pair = candidate.get("pair_address") or candidate.get("pool_address") or ""
    base = {"chain":"solana","token":token,"pair_address":pair or None,"method":"VERIFIED_POOL_TRANSACTION_SIGNERS","signatures_requested":signatures_limit,"signatures_seen":0,"transactions_loaded":0,"wallets":[],"error":None}
    if not pair:
        return {**base, "error": "MISSING_PAIR_ADDRESS"}
    try:
        signatures = adapter.signatures_for_address(pair, limit=signatures_limit)
    except Exception as e:
        return {**base, "error": f"SIGNATURE_LOOKUP_FAILED: {type(e).__name__}: {e}"[:300]}
    counts=Counter(); first_seen={}; last_seen={}; tx_refs=defaultdict(list); loaded=0
    for row in signatures:
        sig=row.get("signature") if isinstance(row,dict) else None
        if not sig: continue
        try: tx=adapter.transaction(sig)
        except Exception: continue
        if not tx: continue
        loaded+=1; block_time=tx.get("blockTime") or row.get("blockTime")
        for wallet in extract_signers(tx):
            if wallet==pair: continue
            counts[wallet]+=1; tx_refs[wallet].append(sig)
            if block_time is not None:
                first_seen[wallet]=min(first_seen.get(wallet,block_time),block_time)
                last_seen[wallet]=max(last_seen.get(wallet,block_time),block_time)
    wallets=[]
    for wallet,appearances in counts.most_common(25):
        wallets.append({"address":wallet,"signer_appearances":appearances,"first_block_time":first_seen.get(wallet),"last_block_time":last_seen.get(wallet),"sample_signatures":tx_refs[wallet][:5],"candidate_reason":"SIGNED_RECENT_ACTIVE_POOL_TRANSACTION","verified":True})
    return {**base,"signatures_seen":len(signatures),"transactions_loaded":loaded,"wallets":wallets}


def run(output_dir: str = "data", max_tokens: int | None = None, signatures_limit: int | None = None) -> dict:
    out=Path(output_dir); active=_load(out/"holder-cluster-production-qualified.json",None)
    source="holder-cluster-production-qualified.json"
    if not isinstance(active,list):
        active=_load(out/"active-qualified-candidates.json",[]); source="active-qualified-candidates.json"
    now=datetime.now(timezone.utc).isoformat(); cfg=Settings()
    max_tokens=cfg.wallet_forensics_max_tokens if max_tokens is None else max_tokens
    signatures_limit=cfg.wallet_forensics_signatures if signatures_limit is None else signatures_limit
    adapter=SolanaAdapter(cfg.solana_rpc_url); rows=[]; skipped=[]
    solana=[x for x in active if x.get("chain")=="solana"][:max_tokens]
    for candidate in solana: rows.append(discover_solana_candidate_wallets(adapter,candidate,signatures_limit))
    for candidate in active:
        if candidate.get("chain") in {"ethereum","bsc"}:
            skipped.append({"chain":candidate.get("chain"),"token":candidate.get("token") or candidate.get("mint"),"status":"ADAPTER_NOT_YET_AVAILABLE","reason":"No verified EVM transaction adapter is deployed yet; no wallet data fabricated."})
    unique_wallets={w.get("address") for row in rows for w in (row.get("wallets") or []) if w.get("address")}
    status={"version":2,"updated_at":now,"method":"VERIFIED_POOL_TRANSACTION_SIGNERS","source":source,"active_candidates_seen":len(active),"solana_candidates_scanned":len(rows),"verified_wallet_candidates":len(unique_wallets),"raw_wallet_appearances":sum(len(x.get("wallets") or []) for x in rows),"evm_candidates_deferred":len(skipped),"limits":{"max_tokens":max_tokens,"signatures_per_pool":signatures_limit},"solana":rows,"deferred":skipped}
    _write(out/"wallet-candidates.json",status)
    _write(out/"wallet-forensics-summary.json",{k:status[k] for k in ("version","updated_at","method","source","active_candidates_seen","solana_candidates_scanned","verified_wallet_candidates","raw_wallet_appearances","evm_candidates_deferred","limits")})
    summary=_load(out/"run-summary.json",{})
    if isinstance(summary,dict):
        summary["wallet_forensics"]={k:status[k] for k in ("method","source","solana_candidates_scanned","verified_wallet_candidates","raw_wallet_appearances","evm_candidates_deferred","limits")}; _write(out/"run-summary.json",summary)
    print(json.dumps({"solana_candidates_scanned":len(rows),"verified_wallet_candidates":len(unique_wallets),"evm_candidates_deferred":len(skipped)},indent=2)); return status


if __name__ == "__main__":
    run()
