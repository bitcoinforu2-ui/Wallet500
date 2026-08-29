from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import cash_verified as cv

TOKEN0_SELECTOR = '0x0dfe1681'
TOKEN1_SELECTOR = '0xd21220a7'
RESERVES_SELECTOR = '0x0902f1ac'

# Only fee schedules we explicitly know and are willing to verify.
# Unknown DEX/version => no verified quote.
FEE_BPS_BY_DEX = {
    'pancakeswap': 25,   # PancakeSwap V2 style pool
    'pancakeswapv2': 25,
    'uniswap': 30,       # Uniswap V2 style pool
    'uniswapv2': 30,
}


@dataclass(frozen=True)
class PairState:
    pair: str
    token0: str
    token1: str
    reserve0: int
    reserve1: int


def _norm(value: Any) -> str:
    return str(value or '').lower()


def _rpc_eth_call(rpc_url: str, to: str, data: str) -> str:
    payload = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'eth_call',
        'params': [{'to': to, 'data': data}, 'latest'],
    }
    response = cv._post_json(rpc_url, payload)
    if not isinstance(response, dict) or response.get('error'):
        raise RuntimeError('RPC_ETH_CALL_FAILED')
    result = response.get('result')
    if not isinstance(result, str) or not result.startswith('0x'):
        raise RuntimeError('RPC_ETH_CALL_EMPTY')
    return result


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


def read_v2_pair_state(chain: str, pair: str) -> tuple[PairState | None, str | None]:
    cid = cv.CHAIN_IDS.get(str(chain).upper())
    rpc = cv.EVM_RPC.get(cid)
    if not cid or not rpc:
        return None, 'EVM_RPC_UNAVAILABLE'
    if not pair:
        return None, 'PAIR_MISSING'
    try:
        token0 = _decode_address(_rpc_eth_call(rpc, pair, TOKEN0_SELECTOR))
        token1 = _decode_address(_rpc_eth_call(rpc, pair, TOKEN1_SELECTOR))
        reserve0, reserve1 = _decode_reserves(_rpc_eth_call(rpc, pair, RESERVES_SELECTOR))
    except Exception as exc:
        return None, 'PAIR_V2_STATE_UNVERIFIED:' + type(exc).__name__
    if reserve0 <= 0 or reserve1 <= 0:
        return None, 'PAIR_ZERO_RESERVES'
    return PairState(pair=pair, token0=token0, token1=token1, reserve0=reserve0, reserve1=reserve1), None


def _fee_bps(row: dict[str, Any]) -> int | None:
    dex = _norm(row.get('dex')).replace('-', '').replace('_', '').replace(' ', '')
    if dex in FEE_BPS_BY_DEX:
        return FEE_BPS_BY_DEX[dex]
    # DexScreener commonly reports just "pancakeswap" / "uniswap".
    if 'pancake' in dex:
        return 25
    if dex == 'uniswap':
        return 30
    return None


def constant_product_amount_out(amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int) -> int:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    if fee_bps < 0 or fee_bps >= 10_000:
        return 0
    amount_in_after_fee = amount_in * (10_000 - fee_bps)
    numerator = amount_in_after_fee * reserve_out
    denominator = reserve_in * 10_000 + amount_in_after_fee
    return numerator // denominator if denominator > 0 else 0


def _pair_direction(state: PairState, sell_token: str, buy_token: str) -> tuple[int, int] | None:
    s, b = _norm(sell_token), _norm(buy_token)
    if _norm(state.token0) == s and _norm(state.token1) == b:
        return state.reserve0, state.reserve1
    if _norm(state.token1) == s and _norm(state.token0) == b:
        return state.reserve1, state.reserve0
    return None


def entry_quote(row: dict[str, Any], position_size_usd: float = 1.0) -> tuple[dict[str, Any] | None, str | None]:
    chain = str(row.get('chain') or '').upper()
    token = str(row.get('token') or row.get('mint') or '')
    pair = str(row.get('pair_address') or row.get('locked_pair_address') or '')
    cid = cv.CHAIN_IDS.get(chain)
    fee_bps = _fee_bps(row)
    if not cid:
        return None, 'CHAIN_NOT_SUPPORTED_BY_EXACT_PAIR_V2'
    if fee_bps is None:
        return None, 'DEX_FEE_SCHEDULE_UNVERIFIED'
    stable, stable_decimals, stable_symbol = cv.STABLE[cid]
    state, err = read_v2_pair_state(chain, pair)
    if err or not state:
        return None, err or 'PAIR_STATE_UNAVAILABLE'
    direction = _pair_direction(state, stable, token)
    if not direction:
        return None, 'LOCKED_PAIR_DOES_NOT_CONTAIN_TOKEN_AND_STABLE'
    reserve_in, reserve_out = direction
    sell_amount = int(round(position_size_usd * (10 ** stable_decimals)))
    out = constant_product_amount_out(sell_amount, reserve_in, reserve_out, fee_bps)
    if out <= 0:
        return None, 'EXACT_PAIR_ENTRY_ZERO_OUTPUT'
    dec, dec_err = cv.evm_token_decimals(chain, token)
    if dec is None:
        return None, dec_err or 'TOKEN_DECIMALS_UNVERIFIED'
    qty = out / (10 ** int(dec))
    if qty <= 0:
        return None, 'EXACT_PAIR_ENTRY_QUANTITY_INVALID'
    return {
        'status': 'VERIFIED',
        'token_amount_base_units': out,
        'token_decimals': int(dec),
        'quantity': qty,
        'cost_usd': float(position_size_usd),
        'effective_entry_price_usd': float(position_size_usd) / qty,
        'stable_symbol': stable_symbol,
        'exact_pair_constrained': True,
        'quoted_pair_address': pair,
        'fee_bps': fee_bps,
        'reserve0': state.reserve0,
        'reserve1': state.reserve1,
        'proof_level': 'LOCKED_PAIR_ONCHAIN_V2_RESERVE_QUOTE_NOT_EXECUTED',
    }, None


def exit_quote(position: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    chain = str(position.get('chain') or '').upper()
    token = str(position.get('token') or '')
    pair = str(position.get('pair_address') or position.get('locked_pair_address') or '')
    cid = cv.CHAIN_IDS.get(chain)
    fee_bps = _fee_bps(position)
    if not cid:
        return None, 'CHAIN_NOT_SUPPORTED_BY_EXACT_PAIR_V2'
    if fee_bps is None:
        return None, 'DEX_FEE_SCHEDULE_UNVERIFIED'
    stable, stable_decimals, stable_symbol = cv.STABLE[cid]
    try:
        amount = int(position.get('token_amount_base_units') or 0)
    except Exception:
        amount = 0
    if amount <= 0:
        return None, 'TOKEN_OR_ENTRY_AMOUNT_MISSING'
    state, err = read_v2_pair_state(chain, pair)
    if err or not state:
        return None, err or 'PAIR_STATE_UNAVAILABLE'
    direction = _pair_direction(state, token, stable)
    if not direction:
        return None, 'LOCKED_PAIR_DOES_NOT_CONTAIN_TOKEN_AND_STABLE'
    reserve_in, reserve_out = direction
    out = constant_product_amount_out(amount, reserve_in, reserve_out, fee_bps)
    if out <= 0:
        return None, 'EXACT_PAIR_EXIT_ZERO_OUTPUT'
    value = out / (10 ** stable_decimals)
    return {
        'status': 'VERIFIED',
        'quoted_exit_value_usd': value,
        'stable_symbol': stable_symbol,
        'exact_pair_constrained': True,
        'quoted_pair_address': pair,
        'fee_bps': fee_bps,
        'reserve0': state.reserve0,
        'reserve1': state.reserve1,
        'proof_level': 'LOCKED_PAIR_ONCHAIN_V2_RESERVE_QUOTE_NOT_EXECUTED',
    }, None
