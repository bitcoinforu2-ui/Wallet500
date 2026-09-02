from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .adapters.solana import SolanaAdapter
from .config import Settings
from .evm_deployment_enrichment import RPC as EVM_RPC, _logs_resilient, _rpc_any


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


def _evm_chain(chain: str) -> str | None:
    c=str(chain or "").lower()
    if c in {"ethereum","eth"}: return "ethereum"
    if c in {"bsc","bnb"}: return "bsc"
    return None


def discover_evm_candidate_wallets(candidate: dict, transactions_limit: int = 12, block_lookback: int | None = None) -> dict:
    """Gather verified transaction senders from logs emitted by the exact EVM pair.

    Evidence is fail-closed: the pair must be identity-locked and the log query must
    succeed for the exact pair address. `transaction.from` is recorded only after
    its tx hash was observed in a log emitted by that exact pair. No address is
    inferred from token holders, routers, labels, or a substituted pool.
    """
    chain=_evm_chain(candidate.get("chain")); token=candidate.get("token") or candidate.get("token_address") or ""
    pair=str(candidate.get("pair_address") or "").lower(); locked=str(candidate.get("locked_pair_address") or "").lower()
    lookback=max(100,int(block_lookback if block_lookback is not None else os.getenv("WALLET500_EVM_FORENSICS_BLOCK_LOOKBACK","2500")))
    base={"chain":chain or str(candidate.get("chain") or "").lower(),"token":token,"pair_address":pair or None,"method":"VERIFIED_EXACT_PAIR_LOG_TRANSACTION_SENDERS","transactions_requested":transactions_limit,"logs_seen":0,"transactions_loaded":0,"blocks_scanned":0,"wallets":[],"error":None}
    if chain not in EVM_RPC:return {**base,"error":"UNSUPPORTED_EVM_CHAIN"}
    if not pair or not locked or pair!=locked or candidate.get("pair_identity_locked") is not True:
        return {**base,"error":"EXACT_PAIR_IDENTITY_NOT_LOCKED"}
    urls=EVM_RPC[chain]
    latest_raw,_=_rpc_any(urls,"eth_blockNumber",[])
    if latest_raw is None:return {**base,"error":"EVM_RPC_UNAVAILABLE"}
    try: latest=int(latest_raw,16)
    except Exception:return {**base,"error":"LATEST_BLOCK_INVALID"}
    start=max(0,latest-lookback+1)
    logs,meta=_logs_resilient(urls,{"address":pair},start,latest)
    if logs is None:
        return {**base,"blocks_scanned":latest-start+1,"error":"EXACT_PAIR_LOG_RANGE_UNAVAILABLE","rpc_meta":meta}
    ordered=sorted((x for x in logs if isinstance(x,dict) and x.get("transactionHash")),key=lambda x:(int(x.get("blockNumber","0x0"),16),int(x.get("logIndex","0x0"),16)),reverse=True)
    tx_hashes=[]; block_by_tx={}
    for log in ordered:
        txh=str(log.get("transactionHash"))
        if txh in block_by_tx:continue
        tx_hashes.append(txh);block_by_tx[txh]=int(log.get("blockNumber","0x0"),16)
        if len(tx_hashes)>=transactions_limit:break
    counts=Counter(); first_block={}; last_block={}; tx_refs=defaultdict(list); loaded=0; used=set()
    for txh in tx_hashes:
        tx,url=_rpc_any(urls,"eth_getTransactionByHash",[txh])
        if url:used.add(url)
        if not isinstance(tx,dict):continue
        sender=str(tx.get("from") or "").lower()
        if not sender:continue
        # A top-level EVM transaction sender is cryptographically authenticated by
        # the transaction signature. The exact-pair log binds this sender's tx to
        # activity that actually touched the locked pair, without claiming the
        # sender is necessarily the economic beneficiary behind a router call.
        loaded+=1; block=block_by_tx.get(txh)
        counts[sender]+=1;tx_refs[sender].append(txh)
        if block is not None:
            first_block[sender]=min(first_block.get(sender,block),block);last_block[sender]=max(last_block.get(sender,block),block)
    wallets=[]
    for wallet,appearances in counts.most_common(25):
        wallets.append({"address":wallet,"signer_appearances":appearances,"first_block":first_block.get(wallet),"last_block":last_block.get(wallet),"sample_transaction_hashes":tx_refs[wallet][:5],"candidate_reason":"SIGNED_TX_WITH_LOG_FROM_LOCKED_EXACT_PAIR","verified":True,"economic_owner_inference":False})
    return {**base,"logs_seen":len(logs),"transactions_loaded":loaded,"blocks_scanned":latest-start+1,"wallets":wallets,"rpc_endpoints_used":len(used),"rpc_meta":meta}


def _candidate_source(out: Path) -> tuple[list[dict], str]:
    """Forensics is evidence gathering, so it must run before the production holder gate.

    Production authorization still remains fail-closed elsewhere. This function only
    decides which already-active exact-pair candidates receive wallet investigation.
    """
    requested=os.getenv("WALLET500_FORENSICS_INPUT","active-qualified-candidates.json").strip() or "active-qualified-candidates.json"
    data=_load(out/requested,[])
    if isinstance(data,list):
        return [x for x in data if isinstance(x,dict)], requested
    return [], requested


def run(output_dir: str = "data", max_tokens: int | None = None, signatures_limit: int | None = None) -> dict:
    out=Path(output_dir); active,source=_candidate_source(out)
    now=datetime.now(timezone.utc).isoformat(); cfg=Settings()
    max_tokens=cfg.wallet_forensics_max_tokens if max_tokens is None else max_tokens
    signatures_limit=cfg.wallet_forensics_signatures if signatures_limit is None else signatures_limit
    adapter=SolanaAdapter(cfg.solana_rpc_url); sol_rows=[]; evm_rows=[]; deferred=[]
    solana=[x for x in active if str(x.get("chain") or "").lower()=="solana"][:max_tokens]
    for candidate in solana: sol_rows.append(discover_solana_candidate_wallets(adapter,candidate,signatures_limit))
    remaining=max(0,max_tokens-len(sol_rows))
    evm=[x for x in active if _evm_chain(x.get("chain"))][:remaining]
    for candidate in evm:
        row=discover_evm_candidate_wallets(candidate,signatures_limit);evm_rows.append(row)
        if row.get("error"):
            deferred.append({"chain":candidate.get("chain"),"token":candidate.get("token") or candidate.get("mint"),"pair_address":candidate.get("pair_address"),"status":"EVIDENCE_UNAVAILABLE_FAIL_CLOSED","reason":row.get("error")})
    all_rows=sol_rows+evm_rows
    unique_wallets={w.get("address") for row in all_rows for w in (row.get("wallets") or []) if w.get("address")}
    evm_wallets={w.get("address") for row in evm_rows for w in (row.get("wallets") or []) if w.get("address")}
    status={"version":4,"updated_at":now,"method":"VERIFIED_EXACT_PAIR_TRANSACTION_SIGNERS","source":source,"lane":"PRE_PRODUCTION_EVIDENCE_GATHERING","production_authorization":False,"active_candidates_seen":len(active),"solana_candidates_scanned":len(sol_rows),"evm_candidates_scanned":len(evm_rows),"verified_wallet_candidates":len(unique_wallets),"evm_verified_wallet_candidates":len(evm_wallets),"raw_wallet_appearances":sum(len(x.get("wallets") or []) for x in all_rows),"evm_candidates_deferred":len(deferred),"limits":{"max_tokens":max_tokens,"transactions_per_pool":signatures_limit},"solana":sol_rows,"evm":evm_rows,"deferred":deferred}
    _write(out/"wallet-candidates.json",status)
    summary_keys=("version","updated_at","method","source","lane","production_authorization","active_candidates_seen","solana_candidates_scanned","evm_candidates_scanned","verified_wallet_candidates","evm_verified_wallet_candidates","raw_wallet_appearances","evm_candidates_deferred","limits")
    _write(out/"wallet-forensics-summary.json",{k:status[k] for k in summary_keys})
    if os.getenv("WALLET500_FORENSICS_UPDATE_RUN_SUMMARY","1") != "0":
        summary=_load(out/"run-summary.json",{})
        if isinstance(summary,dict):
            summary["wallet_forensics"]={k:status[k] for k in summary_keys if k not in {"version","updated_at"}}; _write(out/"run-summary.json",summary)
    print(json.dumps({"source":source,"active_candidates_seen":len(active),"solana_candidates_scanned":len(sol_rows),"evm_candidates_scanned":len(evm_rows),"verified_wallet_candidates":len(unique_wallets),"evm_verified_wallet_candidates":len(evm_wallets),"evm_candidates_deferred":len(deferred)},indent=2)); return status


if __name__ == "__main__":
    run()
