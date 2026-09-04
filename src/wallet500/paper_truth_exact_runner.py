from __future__ import annotations

import json
from typing import Any

from . import exact_pair_quote as epq
from . import paper_truth_portfolio as ptp
from . import solana_exact_pair_quote as seq

EVM_CHAINS = {'BSC', 'BNB', 'ETH', 'ETHEREUM'}
SOLANA_CHAINS = {'SOL', 'SOLANA'}


def _entry_quote(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    chain = str(row.get('chain') or '').upper()
    if chain in EVM_CHAINS:
        return epq.entry_quote(row, ptp.POSITION_SIZE)
    if chain in SOLANA_CHAINS:
        return seq.entry_quote(row, ptp.POSITION_SIZE)
    return None, 'EXACT_PAIR_EXECUTION_VERIFIER_NOT_IMPLEMENTED_FOR_CHAIN'


def _exit_quote(position: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    chain = str(position.get('chain') or '').upper()
    if chain in EVM_CHAINS:
        return epq.exit_quote(position)
    if chain in SOLANA_CHAINS:
        return seq.exit_quote(position)
    return None, 'EXACT_PAIR_EXECUTION_VERIFIER_NOT_IMPLEMENTED_FOR_CHAIN'


def main() -> None:
    rows = ptp._load(ptp.SOURCE, [])
    if not isinstance(rows, list):
        rows = []
    ledger = ptp._load(ptp.LEDGER, ptp.initial_ledger())

    active = {
        ptp._key(r): r
        for r in rows
        if isinstance(r, dict) and ptp._safe(r)
    }
    existing = {ptp._key(p): p for p in (ledger.get('positions') or [])}

    entry_quotes: dict[str, dict[str, Any]] = {}
    for key, row in active.items():
        if key in existing:
            continue
        q, err = _entry_quote(row)
        entry_quotes[key] = q or {'status': 'UNAVAILABLE', 'reason': err}

    exit_quotes: dict[str, dict[str, Any]] = {}
    for position in ledger.get('positions') or []:
        key = ptp._key(position)
        if position.get('status') == 'OPEN' and key not in active:
            q, err = _exit_quote(position)
            exit_quotes[key] = q or {'status': 'UNAVAILABLE', 'reason': err}

    ledger, summary = ptp.reconcile(ledger, rows, entry_quotes, exit_quotes)
    summary['exact_pair_quote_engine'] = 'EVM_V2_RESERVES_PLUS_SOLANA_0X_SINGLE_LEG_LOCKED_PAIR_ACCOUNT_V1'
    summary['exact_pair_supported_chains'] = ['BSC', 'BNB', 'ETH', 'ETHEREUM', 'SOL', 'SOLANA']
    summary['solana_exact_pair_rule'] = 'SINGLE_DIRECT_ROUTE_LEG + DEX_ADDRESS_EQUALS_LOCKED_PAIR + LOCKED_PAIR_PRESENT_IN_INSTRUCTION_ACCOUNTS'
    summary['generic_router_booking_disabled'] = True
    summary['unsupported_chain_policy'] = 'UNVERIFIED_NO_BOOKING'

    ptp._write(ptp.LEDGER, ledger)
    ptp._write(ptp.SUMMARY, summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
