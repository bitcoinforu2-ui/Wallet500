from __future__ import annotations
from collections import defaultdict

ZERO='0x0000000000000000000000000000000000000000'


def _norm(x):
    return str(x or '').lower()


def verify_evm_deployer(rpc_call, token: str, row: dict) -> dict:
    """Verify deployer only from an explicit contract-creation transaction hash.

    We deliberately do not infer a deployer from token transfers, pair creators,
    or API labels. The receipt must prove that the transaction created `token`,
    and the transaction must expose the sender.
    """
    tx_hash=None
    for key in ('deployment_tx_hash','contract_creation_tx_hash','token_creation_tx_hash'):
        if row.get(key):
            tx_hash=str(row[key]); break
    if not tx_hash:
        return {'verified':False,'reason':'DEPLOYMENT_TX_HASH_UNAVAILABLE','deployer':None,'tx_hash':None}
    receipt=rpc_call('eth_getTransactionReceipt',[tx_hash])
    tx=rpc_call('eth_getTransactionByHash',[tx_hash])
    if not isinstance(receipt,dict) or not isinstance(tx,dict):
        return {'verified':False,'reason':'DEPLOYMENT_TRANSACTION_UNAVAILABLE','deployer':None,'tx_hash':tx_hash}
    contract=_norm(receipt.get('contractAddress'))
    deployer=_norm(tx.get('from'))
    tx_to=tx.get('to')
    if contract!=_norm(token):
        return {'verified':False,'reason':'DEPLOYMENT_RECEIPT_CONTRACT_MISMATCH','deployer':deployer or None,'tx_hash':tx_hash,'receipt_contract':contract or None}
    if tx_to not in (None,'','0x'):
        return {'verified':False,'reason':'DEPLOYMENT_TX_NOT_CONTRACT_CREATION','deployer':deployer or None,'tx_hash':tx_hash}
    if not deployer or deployer==ZERO:
        return {'verified':False,'reason':'DEPLOYER_ADDRESS_UNAVAILABLE','deployer':None,'tx_hash':tx_hash}
    return {'verified':True,'reason':'VERIFIED_CONTRACT_CREATION_TRANSACTION','deployer':deployer,'tx_hash':tx_hash}


def verified_native_funding_edges(row: dict) -> list[dict]:
    """Accept only explicitly verified native-funding evidence from an upstream adapter.

    This prevents user/API hints from silently becoming on-chain facts. An edge
    must carry source, destination, transaction hash and verified=true.
    """
    out=[]
    edges=row.get('verified_native_funding_edges')
    if not isinstance(edges,list): return out
    for e in edges:
        if not isinstance(e,dict) or e.get('verified') is not True: continue
        source=_norm(e.get('source') or e.get('from')); target=_norm(e.get('to') or e.get('target')); tx_hash=str(e.get('tx_hash') or '')
        if not source or not target or not tx_hash or source==ZERO or target==ZERO: continue
        out.append({'source':source,'to':target,'tx_hash':tx_hash,'verified':True,'asset':e.get('asset') or 'NATIVE'})
    return out


def corroborate_clusters(clusters: list[dict], transfer_graph: list[dict], deployer_evidence: dict, funding_edges: list[dict]) -> list[dict]:
    """Corroborate linked-holder components without claiming common ownership.

    Strong corroboration currently means either:
    - a verified contract deployer directly distributed the token to >=2 wallets
      in the component, or
    - the same independently verified native funder funded >=2 wallets in it.
    """
    deployer=_norm((deployer_evidence or {}).get('deployer')) if (deployer_evidence or {}).get('verified') else ''
    token_targets=defaultdict(int)
    if deployer:
        for e in transfer_graph or []:
            if _norm(e.get('from'))==deployer:
                t=_norm(e.get('to'))
                if t: token_targets[t]+=int(e.get('transfer_count') or 0)
    funders=defaultdict(set)
    funding_tx=defaultdict(list)
    for e in funding_edges or []:
        s=_norm(e.get('source')); t=_norm(e.get('to'))
        if s and t:
            funders[s].add(t); funding_tx[(s,t)].append(e.get('tx_hash'))
    out=[]
    for c in clusters or []:
        wallets={_norm(x) for x in c.get('wallets') or [] if x}
        deployer_targets=sorted(w for w in wallets if token_targets.get(w,0)>0)
        common=[]
        for source,targets in funders.items():
            hits=sorted(wallets & targets)
            if len(hits)>=2:
                common.append({'source':source,'targets':hits,'verified_transactions':sum((funding_tx.get((source,t),[]) for t in hits),[])})
        deployer_link=bool(deployer and len(deployer_targets)>=2)
        funding_link=bool(common)
        corroborated=deployer_link or funding_link
        evidence=[]
        if deployer_link: evidence.append('VERIFIED_DEPLOYER_DIRECT_DISTRIBUTION_TO_MULTIPLE_CLUSTER_WALLETS')
        if funding_link: evidence.append('VERIFIED_COMMON_NATIVE_FUNDER_TO_MULTIPLE_CLUSTER_WALLETS')
        out.append({**c,
            'risk_corroborated':corroborated,
            'ownership_claim':False,
            'deployer':deployer or None,
            'deployer_distribution_targets':deployer_targets,
            'common_native_funders':common,
            'corroboration_evidence':evidence,
        })
    return out
