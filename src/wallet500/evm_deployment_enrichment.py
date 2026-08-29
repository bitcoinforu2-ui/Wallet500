from __future__ import annotations

"""Fail-closed EVM contract deployment-block enrichment.

For active Ethereum/BSC candidates that do not already carry a verified deployment
block, locate the first block at which eth_getCode returns non-empty bytecode.
Only a boundary proven on-chain (empty at N-1, code at N) is written back.
Unavailable archive RPC evidence never becomes an inferred deployment block.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATA = Path('data')
INPUT = DATA / os.getenv('EVM_DEPLOYMENT_INPUT', 'active-qualified-candidates.json')
REPORT = DATA / 'evm-deployment-enrichment-report.json'
DEFAULT_RPC = {
    'ethereum': ['https://ethereum-rpc.publicnode.com', 'https://eth.llamarpc.com'],
    'bsc': ['https://bsc-rpc.publicnode.com', 'https://bsc-dataseed.binance.org'],
}


def _urls(*values):
    out = []
    for value in values:
        for raw in str(value or '').split(','):
            u = raw.strip()
            if u and u not in out:
                out.append(u)
    return out


RPC = {
    'ethereum': _urls(os.getenv('ETHEREUM_RPC_URL'), os.getenv('ETH_RPC_URL'), os.getenv('ETH_RPC_FALLBACK_URLS'), *DEFAULT_RPC['ethereum']),
    'bsc': _urls(os.getenv('BSC_RPC_URL'), os.getenv('BNB_RPC_URL'), os.getenv('BSC_RPC_FALLBACK_URLS'), *DEFAULT_RPC['bsc']),
}


def _rpc_url(url, method, params):
    try:
        req = Request(
            url,
            data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
            headers={'Content-Type': 'application/json', 'User-Agent': 'Wallet500/1.0'},
        )
        with urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode())
        return None if payload.get('error') else payload.get('result')
    except Exception:
        return None


def _rpc_any(urls, method, params):
    for url in urls:
        result = _rpc_url(url, method, params)
        if result is not None:
            return result, url
    return None, None


def _has_code_at(urls, token, block):
    result, used = _rpc_any(urls, 'eth_getCode', [token, hex(block)])
    if result is None:
        return None, used
    code = str(result).lower()
    return code not in ('0x', '0x0', ''), used


def discover_deployment_block(urls, token):
    latest_raw, latest_url = _rpc_any(urls, 'eth_blockNumber', [])
    if latest_raw is None:
        return None, {'verified': False, 'reason': 'EVM_RPC_UNAVAILABLE'}
    latest = int(latest_raw, 16)
    latest_has_code, code_url = _has_code_at(urls, token, latest)
    if latest_has_code is not True:
        return None, {'verified': False, 'reason': 'NO_CURRENT_CONTRACT_CODE_OR_RPC_UNAVAILABLE', 'latest_block': latest}

    lo, hi = 0, latest
    queries = 1
    used = {x for x in (latest_url, code_url) if x}
    while lo < hi:
        mid = (lo + hi) // 2
        has_code, url = _has_code_at(urls, token, mid)
        queries += 1
        if url:
            used.add(url)
        if has_code is None:
            return None, {
                'verified': False,
                'reason': 'ARCHIVE_CODE_QUERY_UNAVAILABLE',
                'failed_block': mid,
                'latest_block': latest,
                'queries': queries,
                'rpc_endpoints_used': len(used),
            }
        if has_code:
            hi = mid
        else:
            lo = mid + 1

    first = lo
    has_first, url1 = _has_code_at(urls, token, first)
    if url1:
        used.add(url1)
    if has_first is not True:
        return None, {'verified': False, 'reason': 'DEPLOYMENT_BOUNDARY_NOT_PROVEN', 'candidate_block': first}
    if first > 0:
        has_prev, url2 = _has_code_at(urls, token, first - 1)
        if url2:
            used.add(url2)
        if has_prev is not False:
            return None, {'verified': False, 'reason': 'PRE_DEPLOYMENT_EMPTY_CODE_NOT_PROVEN', 'candidate_block': first}

    return first, {
        'verified': True,
        'reason': 'ONCHAIN_ETH_GETCODE_BOUNDARY_VERIFIED',
        'deployment_block': first,
        'latest_block': latest,
        'queries': queries + (2 if first > 0 else 1),
        'rpc_endpoints_used': len(used),
    }


def run():
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = json.loads(INPUT.read_text()) if INPUT.exists() else []
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []

    enriched = 0
    already_verified = 0
    unresolved = []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        chain = str(item.get('chain') or '').lower()
        token = str(item.get('token') or item.get('token_address') or '').lower()
        existing = item.get('deployment_block') or item.get('contract_creation_block') or item.get('token_creation_block') or item.get('start_block')
        if chain not in RPC or not token:
            out.append(item)
            continue
        if existing is not None:
            already_verified += 1
            out.append(item)
            continue
        block, evidence = discover_deployment_block(RPC[chain], token)
        item['deployment_block_evidence'] = evidence
        if block is not None and evidence.get('verified') is True:
            item['deployment_block'] = block
            item['deployment_block_source'] = 'ONCHAIN_ETH_GETCODE_BOUNDARY_VERIFIED'
            enriched += 1
        else:
            unresolved.append({'chain': chain, 'token': token, 'reason': evidence.get('reason')})
        out.append(item)

    INPUT.write_text(json.dumps(out, indent=2))
    report = {
        'updated_at': now,
        'mode': 'FAIL_CLOSED_ONCHAIN_DEPLOYMENT_ENRICHMENT',
        'input_count': len(rows),
        'enriched_count': enriched,
        'already_had_start_block': already_verified,
        'unresolved_count': len(unresolved),
        'unresolved': unresolved,
        'truth_rule': 'deployment_block is written only when eth_getCode proves empty code at N-1 and contract code at N; RPC/archive uncertainty remains unresolved',
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    run()
