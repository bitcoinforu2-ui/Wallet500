from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import cash_verified as cv
from .exact_pair_quote import FEE_BPS_BY_DEX, constant_product_amount_out

DATA = Path('data')
EVIDENCE = DATA / 'discovery-evidence-ledger.json'
STATE = DATA / 'onchain-historical-reconstruction-state.json'
REPORT = DATA / 'onchain-historical-reconstruction.json'
MAX_RECORDS_PER_RUN = 8
TOKEN0_SELECTOR = '0x0dfe1681'
TOKEN1_SELECTOR = '0xd21220a7'
RESERVES_SELECTOR = '0x0902f1ac'
DECIMALS_SELECTOR = '0x313ce567'


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)
    except ValueError:
        return None


def _key(chain: str, token: str, pair: str) -> str:
    c = chain.lower()
    if c in {'ethereum', 'eth', 'bsc', 'bnb'}:
        token, pair = token.lower(), pair.lower()
    return f'{c}:{token}:{pair}'


def _rpc(rpc_url: str, method: str, params: list[Any]) -> Any:
    d = cv._post_json(rpc_url, {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
    if not isinstance(d, dict) or d.get('error'):
        err = (d or {}).get('error') if isinstance(d, dict) else None
        raise RuntimeError(f'RPC_{method}_FAILED:{err}')
    return d.get('result')


def _block(rpc_url: str, n: int) -> dict[str, Any]:
    x = _rpc(rpc_url, 'eth_getBlockByNumber', [hex(n), False])
    if not isinstance(x, dict) or not x.get('timestamp'):
        raise RuntimeError('BLOCK_UNAVAILABLE')
    return x


def _nearest_block_at_or_before(rpc_url: str, target_ts: int) -> tuple[int, int]:
    latest_raw = _rpc(rpc_url, 'eth_blockNumber', [])
    latest = int(str(latest_raw), 16)
    lo, hi = 0, latest
    best_n, best_ts = 0, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        b = _block(rpc_url, mid)
        ts = int(str(b['timestamp']), 16)
        if ts <= target_ts:
            best_n, best_ts = mid, ts
            lo = mid + 1
        else:
            hi = mid - 1
    if best_n <= 0:
        raise RuntimeError('TARGET_BLOCK_NOT_FOUND')
    return best_n, best_ts


def _eth_call(rpc_url: str, to: str, data: str, block_number: int) -> str:
    raw = _rpc(rpc_url, 'eth_call', [{'to': to, 'data': data}, hex(block_number)])
    if not isinstance(raw, str) or not raw.startswith('0x') or raw == '0x':
        raise RuntimeError('HISTORICAL_ETH_CALL_EMPTY')
    return raw


def _decode_address(raw: str) -> str:
    h = raw[2:] if raw.startswith('0x') else raw
    if len(h) < 64:
        raise ValueError('ADDRESS_DECODE_SHORT')
    return '0x' + h[-40:]


def _decode_reserves(raw: str) -> tuple[int, int]:
    h = raw[2:] if raw.startswith('0x') else raw
    if len(h) < 128:
        raise ValueError('RESERVES_DECODE_SHORT')
    return int(h[:64], 16), int(h[64:128], 16)


def _decimals(rpc_url: str, token: str, block_number: int) -> int:
    raw = _eth_call(rpc_url, token, DECIMALS_SELECTOR, block_number)
    dec = int(raw, 16)
    if not 0 <= dec <= 36:
        raise ValueError('DECIMALS_OUT_OF_RANGE')
    return dec


def _fee_bps(dex: Any) -> int | None:
    d = str(dex or '').lower().replace('-', '').replace('_', '').replace(' ', '')
    if d in FEE_BPS_BY_DEX:
        return FEE_BPS_BY_DEX[d]
    if 'pancake' in d:
        return 25
    if d == 'uniswap':
        return 30
    return None


def _reconstruct_evm(rec: dict[str, Any]) -> dict[str, Any]:
    ident = rec.get('identity') or {}
    chain = str(ident.get('chain') or '').upper()
    token = str(ident.get('token') or '')
    pair = str(ident.get('locked_pair_address') or ident.get('pair_address') or '')
    dex = ident.get('dex')
    observed = _dt(rec.get('observed_at'))
    cid = cv.CHAIN_IDS.get(chain)
    rpc_url = cv.EVM_RPC.get(cid)
    if not cid or not rpc_url:
        raise RuntimeError('EVM_RPC_UNAVAILABLE')
    if not token or not pair or not observed:
        raise RuntimeError('IDENTITY_OR_TIMESTAMP_MISSING')
    fee_bps = _fee_bps(dex)
    if fee_bps is None:
        raise RuntimeError('DEX_FEE_SCHEDULE_UNVERIFIED')

    block_number, block_ts = _nearest_block_at_or_before(rpc_url, int(observed.timestamp()))
    token0 = _decode_address(_eth_call(rpc_url, pair, TOKEN0_SELECTOR, block_number))
    token1 = _decode_address(_eth_call(rpc_url, pair, TOKEN1_SELECTOR, block_number))
    reserve0, reserve1 = _decode_reserves(_eth_call(rpc_url, pair, RESERVES_SELECTOR, block_number))
    if reserve0 <= 0 or reserve1 <= 0:
        raise RuntimeError('PAIR_ZERO_RESERVES_AT_TARGET_BLOCK')

    stable, stable_decimals, stable_symbol = cv.STABLE[cid]
    t0, t1 = token0.lower(), token1.lower()
    stable_l, token_l = stable.lower(), token.lower()
    if {t0, t1} != {stable_l, token_l}:
        raise RuntimeError('PAIR_NOT_DIRECT_STABLE_TOKEN_POOL')

    token_decimals = _decimals(rpc_url, token, block_number)
    if t0 == stable_l:
        stable_reserve, token_reserve = reserve0, reserve1
    else:
        stable_reserve, token_reserve = reserve1, reserve0

    stable_units = stable_reserve / (10 ** stable_decimals)
    token_units = token_reserve / (10 ** token_decimals)
    if stable_units <= 0 or token_units <= 0:
        raise RuntimeError('NORMALIZED_RESERVES_INVALID')

    spot_price_usd = stable_units / token_units
    liquidity_usd = stable_units * 2.0
    one_dollar_in = 10 ** stable_decimals
    out_base = constant_product_amount_out(one_dollar_in, stable_reserve, token_reserve, fee_bps)
    if out_base <= 0:
        raise RuntimeError('ONE_DOLLAR_QUOTE_ZERO_OUTPUT')
    qty = out_base / (10 ** token_decimals)
    if qty <= 0:
        raise RuntimeError('ONE_DOLLAR_QUOTE_INVALID_QTY')

    return {
        'status': 'ONCHAIN_RECONSTRUCTED',
        'chain': chain.lower(),
        'token': token,
        'pair_address': pair,
        'observed_at': observed.isoformat(),
        'target_block_number': block_number,
        'target_block_timestamp': datetime.fromtimestamp(block_ts, tz=timezone.utc).isoformat(),
        'target_block_timestamp_delta_seconds': int(observed.timestamp()) - block_ts,
        'token0': token0,
        'token1': token1,
        'reserve0_base_units': reserve0,
        'reserve1_base_units': reserve1,
        'token_decimals': token_decimals,
        'stable_symbol': stable_symbol,
        'stable_decimals': stable_decimals,
        'historical_spot_price_usd': spot_price_usd,
        'historical_liquidity_usd': liquidity_usd,
        'historical_liquidity_verified': True,
        'historical_pair_state_verified': True,
        'historical_exact_pair_entry_quote_verified': True,
        'one_dollar_token_amount_base_units': out_base,
        'one_dollar_token_quantity': qty,
        'effective_one_dollar_entry_price_usd': 1.0 / qty,
        'fee_bps': fee_bps,
        'proof_class': 'ONCHAIN_VERIFIED',
        'proof_level': 'EVM_ARCHIVE_BLOCK_EXACT_PAIR_V2_STATE_AND_1USD_QUOTE',
        'lookahead_used': False,
    }


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    evidence = _load(EVIDENCE, {})
    records = evidence.get('records', {}) if isinstance(evidence, dict) else {}
    state = _load(STATE, {})
    previous = state.get('records', {}) if isinstance(state, dict) and isinstance(state.get('records'), dict) else {}

    candidates: list[tuple[str, dict[str, Any]]] = []
    for raw_key, rec in records.items() if isinstance(records, dict) else []:
        if not isinstance(rec, dict):
            continue
        ident = rec.get('identity') or {}
        chain = str(ident.get('chain') or '').lower()
        token = str(ident.get('token') or '')
        pair = str(ident.get('pair_address') or '')
        key = _key(chain, token, pair) if chain and token and pair else str(raw_key)
        if chain in {'bsc', 'bnb', 'ethereum', 'eth'} and (previous.get(key) or {}).get('status') != 'ONCHAIN_RECONSTRUCTED':
            candidates.append((key, rec))

    processed = 0
    for key, rec in candidates[:MAX_RECORDS_PER_RUN]:
        try:
            previous[key] = _reconstruct_evm(rec)
        except Exception as exc:
            previous[key] = {
                'status': 'UNVERIFIED_RETRY',
                'last_attempt_at': now,
                'reason': f'{type(exc).__name__}:{exc}'[:500],
                'proof_class': 'UNAVAILABLE',
                'lookahead_used': False,
            }
        processed += 1

    verified = sum(1 for x in previous.values() if isinstance(x, dict) and x.get('status') == 'ONCHAIN_RECONSTRUCTED')
    retry = sum(1 for x in previous.values() if isinstance(x, dict) and x.get('status') == 'UNVERIFIED_RETRY')
    unsupported_solana = sum(1 for rec in records.values() if isinstance(rec, dict) and str((rec.get('identity') or {}).get('chain') or '').lower() == 'solana')

    state_out = {
        'schema_version': 1,
        'updated_at': now,
        'mode': 'ONCHAIN_POINT_IN_TIME_RECONSTRUCTION',
        'lookahead_policy': 'FORBIDDEN',
        'pair_identity_policy': 'EXACT_LOCKED_PAIR_ONLY',
        'missing_data_policy': 'UNVERIFIED_NEVER_INFERRED',
        'records': previous,
    }
    _write(STATE, state_out)

    report = {
        'schema_version': 1,
        'generated_at': now,
        'mode': 'ONCHAIN_POINT_IN_TIME_RECONSTRUCTION',
        'production_portfolio_impact': 'NONE',
        'lookahead_policy': 'FORBIDDEN',
        'pair_identity_policy': 'EXACT_LOCKED_PAIR_ONLY',
        'processed_this_run': processed,
        'onchain_reconstructed_records': verified,
        'retry_unverified_records': retry,
        'solana_records_pending_program_specific_replay': unsupported_solana,
        'evm_scope': 'V2_STYLE_DIRECT_STABLE_TOKEN_POOLS_ONLY',
        'solana_scope': 'NOT_MARKED_VERIFIED_UNTIL_PROGRAM_SPECIFIC_ACCOUNT_AND_TRANSACTION_REPLAY_EXISTS',
        'truth_note': 'Historical EVM values come from exact-pair contract state at the nearest block at or before discovery timestamp. No current pool state is substituted for missing archive data.',
        'records': previous,
    }
    _write(REPORT, report)
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}, indent=2))
    return report


if __name__ == '__main__':
    run()
