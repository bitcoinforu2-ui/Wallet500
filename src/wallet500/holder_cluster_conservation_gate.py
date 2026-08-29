from __future__ import annotations

"""Stronger fail-closed EVM holder verification without requiring archive eth_getCode.

This module reuses the existing holder/cluster gate but replaces only the EVM holder
reconstruction routine. It adds two truth-preserving improvements:

1. Adaptive eth_getLogs range splitting. If an RPC rejects a large block range, the
   request is recursively split down to small ranges instead of immediately failing.
2. Supply-conservation proof. A bounded transfer ledger may be treated as complete
   only when every reconstructed balance is non-negative and the sum of all
   reconstructed balances equals the current ERC-20 totalSupply exactly. This proves
   that no currently-active supply is missing from before the bounded window.

If either proof fails or RPC evidence is incomplete, the existing gate remains REVIEW.
"""

from collections import defaultdict
from typing import Any

from . import holder_cluster_gate as base

MIN_LOG_SPAN = 100


def _adaptive_logs(urls: list[str], token: str, start: int, end: int):
    logs, url = base._rpc_any(
        urls,
        'eth_getLogs',
        [{'fromBlock': hex(start), 'toBlock': hex(end), 'address': token, 'topics': [base.TRANSFER_TOPIC]}],
    )
    if logs is not None:
        return logs, {url} if url else set(), 1, None

    if end - start + 1 <= MIN_LOG_SPAN:
        return None, set(), 1, [start, end]

    mid = (start + end) // 2
    left, used_l, calls_l, fail_l = _adaptive_logs(urls, token, start, mid)
    if left is None:
        return None, used_l, calls_l, fail_l
    right, used_r, calls_r, fail_r = _adaptive_logs(urls, token, mid + 1, end)
    if right is None:
        return None, used_l | used_r, calls_l + calls_r, fail_r
    return left + right, used_l | used_r, calls_l + calls_r + 1, None


def _evm_holders(chain: str, token: str, row: dict[str, Any]):
    urls = base.RPC.get(chain, [])
    latest, latest_url = base._rpc_any(urls, 'eth_blockNumber', [])
    if not latest:
        return [], [], [], {'complete': False, 'reason': 'EVM_RPC_UNAVAILABLE', 'rpc_candidates': len(urls)}

    latest_i = int(latest, 16)
    start, start_source, start_verified = base._evm_start_block(row, latest_i)
    balances: defaultdict[str, int] = defaultdict(int)
    edges: defaultdict[tuple[str, str], int] = defaultdict(int)
    logs_seen = 0
    logical_chunks = 0
    rpc_log_calls = 0
    used = {latest_url} if latest_url else set()

    for a in range(start, latest_i + 1, base.EVM_CHUNK):
        b = min(latest_i, a + base.EVM_CHUNK - 1)
        logical_chunks += 1
        logs, log_urls, calls, failed = _adaptive_logs(urls, token, a, b)
        rpc_log_calls += calls
        used |= log_urls
        if logs is None:
            return [], [], [], {
                'complete': False,
                'reason': 'EVM_LOG_RANGE_UNAVAILABLE_AFTER_ADAPTIVE_SPLIT',
                'from_block': start,
                'to_block': latest_i,
                'failed_chunk': failed or [a, b],
                'chunks_completed': logical_chunks - 1,
                'adaptive_rpc_log_calls': rpc_log_calls,
                'min_log_span': MIN_LOG_SPAN,
                'start_block_verified': start_verified,
                'start_block_source': start_source,
                'rpc_candidates': len(urls),
                'rpc_endpoints_used': len(used),
            }

        for log in logs:
            topics = log.get('topics') or []
            if len(topics) < 3:
                continue
            f = base._addr(topics[1])
            t = base._addr(topics[2])
            value = base._as_int_hex(log.get('data') or '0x0')
            if value < 0:
                continue
            logs_seen += 1
            if f and f != base.ZERO:
                balances[f] -= value
            if t and t != base.ZERO:
                balances[t] += value
            if f and t and f != base.ZERO and t != base.ZERO:
                edges[(f, t)] += 1

    total_supply, supply_url = base._evm_total_supply(urls, token)
    if supply_url:
        used.add(supply_url)

    all_balances = list(balances.items())
    negative = [(o, a) for o, a in all_balances if a < 0]
    positive = [(o, a) for o, a in all_balances if a > 0]
    reconstructed_supply = sum(a for _, a in positive)

    conservation_proven = bool(
        total_supply > 0
        and not negative
        and reconstructed_supply == total_supply
    )
    coverage_verified = bool(start_verified or conservation_proven)

    denom = total_supply if total_supply > 0 else 0
    holders = [
        {'owner': o, 'raw_amount': str(a), 'pct': a / denom * 100 if denom else 0}
        for o, a in positive
    ]
    holders.sort(key=lambda x: int(x['raw_amount']), reverse=True)
    holders = holders[:base.TOP_N]

    graph = [
        {'from': f, 'to': t, 'transfer_count': n}
        for (f, t), n in sorted(edges.items(), key=lambda x: x[1], reverse=True)[:500]
    ]
    exclusions = set(base.INFRA_EXCLUSIONS) | {
        base.ZERO,
        token.lower(),
        str(row.get('pair_address') or row.get('locked_pair_address') or '').lower(),
    }
    clusters = base._components(holders, graph, exclusions)

    complete = bool(coverage_verified and total_supply > 0)
    if start_verified:
        reason = 'FULL_TRANSFER_LEDGER_FROM_VERIFIED_START_BLOCK'
    elif conservation_proven:
        reason = 'FULL_TRANSFER_LEDGER_BY_SUPPLY_CONSERVATION_PROOF'
    elif total_supply <= 0:
        reason = 'TOTAL_SUPPLY_UNVERIFIED'
    elif negative:
        reason = 'BOUNDED_LEDGER_HAS_NEGATIVE_BALANCES'
    else:
        reason = 'BOUNDED_LEDGER_SUPPLY_NOT_CONSERVED'

    return holders, graph, clusters, {
        'complete': complete,
        'reason': reason,
        'from_block': start,
        'to_block': latest_i,
        'logs_seen': logs_seen,
        'chunks': logical_chunks,
        'adaptive_rpc_log_calls': rpc_log_calls,
        'min_log_span': MIN_LOG_SPAN,
        'lookback_blocks': latest_i - start,
        'observed_positive_holders': len(positive),
        'observed_negative_holders': len(negative),
        'total_supply_raw': str(total_supply) if total_supply else None,
        'reconstructed_positive_supply_raw': str(reconstructed_supply),
        'supply_conservation_proven': conservation_proven,
        'pct_authoritative': bool(total_supply > 0 and complete),
        'start_block_verified': start_verified,
        'start_block_source': start_source,
        'coverage_verification_method': (
            'VERIFIED_START_BLOCK' if start_verified else
            'EXACT_TOTAL_SUPPLY_CONSERVATION' if conservation_proven else
            'UNVERIFIED'
        ),
        'infrastructure_exclusions': sorted(x for x in exclusions if x),
        'rpc_candidates': len(urls),
        'rpc_endpoints_used': len(used),
    }


def run():
    base._evm_holders = _evm_holders
    return base.run()


if __name__ == '__main__':
    run()
