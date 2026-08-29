from __future__ import annotations

import json
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import cash_verified as cv

DATA = Path('data')
LEDGER = DATA / 'paper-truth-ledger.json'
SUMMARY = DATA / 'paper-truth-summary.json'
SOURCE = DATA / 'holder-cluster-production-qualified.json'
OLD_LEDGER = DATA / 'paper-portfolio-ledger.json'
STARTING_CASH = 100.0
POSITION_SIZE = 1.0
MIN_LIQUIDITY = 50_000.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def _norm(chain: str, value: Any) -> str:
    s = str(value or '')
    return s.lower() if str(chain).lower() in {'bsc', 'ethereum'} else s


def _key(row: dict[str, Any]) -> str:
    chain = str(row.get('chain') or '').lower()
    token = _norm(chain, row.get('token') or row.get('mint'))
    pair = _norm(chain, row.get('pair_address') or row.get('locked_pair_address'))
    return f'{chain}|{token}|{pair}'


def _num(row: dict[str, Any], *names: str) -> float:
    for name in names:
        try:
            return float(row.get(name))
        except (TypeError, ValueError):
            pass
    return 0.0


def _safe(row: dict[str, Any]) -> bool:
    return bool(
        row.get('holder_cluster_production_status') == 'PASS'
        and row.get('holder_cluster_verification_complete') is True
        and (row.get('pair_address') or row.get('locked_pair_address'))
        and _num(row, 'live_price_usd', 'price_usd', 'current_price_usd') > 0
        and _num(row, 'live_liquidity_usd', 'liquidity_usd') >= MIN_LIQUIDITY
    )


def initial_ledger(now: str | None = None) -> dict[str, Any]:
    ts = now or _now()
    return {
        'version': 1,
        'mode': 'PAPER_TRUTH_QUOTE_VERIFIED_NO_REAL_MONEY',
        'created_at': ts,
        'updated_at': ts,
        'starting_cash_usd': STARTING_CASH,
        'position_size_usd': POSITION_SIZE,
        'cash_usd': STARTING_CASH,
        'positions': [],
        'events': [],
        'truth_policy': 'BOOK ENTRY/EXIT ONLY FROM SAME-CYCLE FIRM ROUTER QUOTES. NO RETROACTIVE EXECUTION CLAIMS.',
    }


def _evm_entry_quote(chain: str, token: str) -> tuple[dict[str, Any] | None, str | None]:
    cid = cv.CHAIN_IDS.get(chain.upper())
    if not cid:
        return None, 'CHAIN_NOT_SUPPORTED_BY_EVM_QUOTER'
    if not cv.KEY:
        return None, 'ZEROX_API_KEY_MISSING'
    stable, stable_decimals, stable_symbol = cv.STABLE[cid]
    params = urllib.parse.urlencode({
        'chainId': cid,
        'sellToken': stable,
        'buyToken': token,
        'sellAmount': str(10 ** stable_decimals),
        'taker': cv.EVM_TAKER,
    })
    req = urllib.request.Request(
        cv.EVM_API + '?' + params,
        headers={'0x-api-key': cv.KEY, '0x-version': 'v2', 'Accept': 'application/json', 'User-Agent': 'Wallet500/0.3'},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            q = json.loads(r.read())
        raw = int(q.get('buyAmount') or 0)
        if raw <= 0:
            return None, 'ENTRY_QUOTE_ZERO_OUTPUT'
        dec, err = cv.evm_token_decimals(chain, token)
        if dec is None:
            return None, err or 'TOKEN_DECIMALS_UNVERIFIED'
        qty = raw / (10 ** int(dec))
        if qty <= 0:
            return None, 'ENTRY_QUANTITY_INVALID'
        return {
            'status': 'VERIFIED',
            'token_amount_base_units': raw,
            'token_decimals': int(dec),
            'quantity': qty,
            'cost_usd': POSITION_SIZE,
            'effective_entry_price_usd': POSITION_SIZE / qty,
            'stable_symbol': stable_symbol,
            'liquidity_available': q.get('liquidityAvailable'),
            'issues': q.get('issues'),
            'route': q.get('route'),
            'proof_level': '0X_FIRM_ENTRY_QUOTE_NOT_EXECUTED_NOT_EXACT_PAIR_CONSTRAINED',
        }, None
    except urllib.error.HTTPError as e:
        return None, cv._http_error('ENTRY_QUOTE', e)
    except Exception as e:
        return None, 'ENTRY_QUOTE_ERROR:' + type(e).__name__


def _solana_entry_quote(token: str) -> tuple[dict[str, Any] | None, str | None]:
    if not cv.KEY:
        return None, 'ZEROX_API_KEY_MISSING'
    payload = {
        'token_in': cv.SOLANA_USDC,
        'token_out': token,
        'amount_in': 10 ** cv.SOLANA_USDC_DECIMALS,
        'taker': cv.SOLANA_TAKER,
        'slippage_bps': 50,
    }
    try:
        q = cv._post_json(cv.SOLANA_API, payload, {'0x-api-key': cv.KEY})
        raw = int(q.get('amount_out') or 0)
        if raw <= 0:
            return None, 'SOLANA_ENTRY_QUOTE_ZERO_OUTPUT'
        dec, err = cv.solana_token_decimals(token)
        if dec is None:
            return None, err or 'TOKEN_DECIMALS_UNVERIFIED'
        qty = raw / (10 ** int(dec))
        if qty <= 0:
            return None, 'ENTRY_QUANTITY_INVALID'
        return {
            'status': 'VERIFIED',
            'token_amount_base_units': raw,
            'token_decimals': int(dec),
            'quantity': qty,
            'cost_usd': POSITION_SIZE,
            'effective_entry_price_usd': POSITION_SIZE / qty,
            'stable_symbol': 'USDC',
            'route': q.get('route_plan'),
            'proof_level': '0X_FIRM_ENTRY_QUOTE_NOT_EXECUTED_NOT_EXACT_PAIR_CONSTRAINED',
        }, None
    except urllib.error.HTTPError as e:
        return None, cv._http_error('SOLANA_ENTRY_QUOTE', e)
    except Exception as e:
        return None, 'SOLANA_ENTRY_QUOTE_ERROR:' + type(e).__name__


def live_entry_quote(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    chain = str(row.get('chain') or '').upper()
    token = str(row.get('token') or row.get('mint') or '')
    if not token:
        return None, 'TOKEN_MISSING'
    return _solana_entry_quote(token) if chain in {'SOL', 'SOLANA'} else _evm_entry_quote(chain, token)


def live_exit_quote(position: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    chain = str(position.get('chain') or '').upper()
    token = str(position.get('token') or '')
    try:
        amount = int(position.get('token_amount_base_units') or 0)
    except Exception:
        amount = 0
    if not token or amount <= 0:
        return None, 'TOKEN_OR_ENTRY_AMOUNT_MISSING'
    result, err = cv.solana_quote(token, amount) if chain in {'SOL', 'SOLANA'} else cv.evm_quote(chain, token, amount)
    if err or not result:
        return None, err or 'EXIT_QUOTE_EMPTY'
    q = result['quote']
    raw = int(q.get('amount_out') or 0) if chain in {'SOL', 'SOLANA'} else int(q.get('buyAmount') or 0)
    dec = int(result['stable_decimals'])
    if raw <= 0:
        return None, 'EXIT_QUOTE_ZERO_OUTPUT'
    value = raw / (10 ** dec)
    return {
        'status': 'VERIFIED',
        'quoted_exit_value_usd': value,
        'stable_symbol': result['stable_symbol'],
        'liquidity_available': q.get('liquidityAvailable') if isinstance(q, dict) else None,
        'issues': q.get('issues') if isinstance(q, dict) else None,
        'route': q.get('route') if chain not in {'SOL', 'SOLANA'} else q.get('route_plan'),
        'proof_level': '0X_FIRM_EXIT_QUOTE_NOT_EXECUTED_NOT_EXACT_PAIR_CONSTRAINED',
    }, None


def reconcile(
    ledger: dict[str, Any],
    production_rows: list[dict[str, Any]],
    entry_quotes: dict[str, dict[str, Any]],
    exit_quotes: dict[str, dict[str, Any]],
    now: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = now or _now()
    ledger = dict(ledger or initial_ledger(ts))
    positions = list(ledger.get('positions') or [])
    events = list(ledger.get('events') or [])
    cash = float(ledger.get('cash_usd', STARTING_CASH))
    active = {_key(r): r for r in production_rows if _safe(r)}
    existing = {_key(p): p for p in positions}

    for p in positions:
        if p.get('status') != 'OPEN':
            continue
        key = _key(p)
        if key in active:
            row = active[key]
            market_px = _num(row, 'live_price_usd', 'price_usd', 'current_price_usd')
            p['last_market_mark_price_usd'] = market_px
            p['last_market_mark_value_usd'] = float(p.get('quantity') or 0) * market_px
            p['last_market_mark_at'] = ts
            p['last_market_mark_proof'] = 'EXACT_PAIR_MARKET_MARK_NOT_EXECUTION_QUOTE'
            continue
        q = exit_quotes.get(key) or {}
        if q.get('status') == 'VERIFIED':
            proceeds = float(q.get('quoted_exit_value_usd') or 0)
            p.update({
                'status': 'CLOSED_QUOTE_VERIFIED',
                'exit_signal_time': ts,
                'exit_quote_time': ts,
                'exit_value_usd': proceeds,
                'realized_quote_pnl_usd': proceeds - float(p.get('cost_usd') or POSITION_SIZE),
                'exit_reason': 'NO_LONGER_PRODUCTION_QUALIFIED',
                'exit_quote_proof_level': q.get('proof_level'),
                'exit_quote_stable_symbol': q.get('stable_symbol'),
                'exit_pending': False,
            })
            cash += proceeds
            events.append({'at': ts, 'type': 'EXIT_QUOTE_VERIFIED', 'key': key, 'quoted_value_usd': proceeds, 'proof_level': q.get('proof_level')})
        else:
            p['exit_pending'] = True
            p['exit_signal_time'] = p.get('exit_signal_time') or ts
            p['exit_last_attempt_at'] = ts
            p['exit_last_error'] = q.get('reason') or 'FIRM_EXIT_QUOTE_UNAVAILABLE'

    for key, row in active.items():
        if key in existing or cash < POSITION_SIZE:
            continue
        q = entry_quotes.get(key) or {}
        if q.get('status') != 'VERIFIED':
            events.append({'at': ts, 'type': 'ENTRY_NOT_BOOKED', 'key': key, 'reason': q.get('reason') or 'FIRM_ENTRY_QUOTE_UNAVAILABLE'})
            continue
        qty = float(q.get('quantity') or 0)
        base_units = int(q.get('token_amount_base_units') or 0)
        if qty <= 0 or base_units <= 0:
            continue
        market_px = _num(row, 'live_price_usd', 'price_usd', 'current_price_usd')
        pos = {
            'chain': str(row.get('chain') or '').lower(),
            'token': row.get('token') or row.get('mint'),
            'pair_address': row.get('pair_address') or row.get('locked_pair_address'),
            'dex': row.get('dex'),
            'status': 'OPEN',
            'entry_signal_time': ts,
            'entry_quote_time': ts,
            'cost_usd': POSITION_SIZE,
            'token_amount_base_units': base_units,
            'token_decimals_verified': int(q.get('token_decimals')),
            'quantity': qty,
            'entry_market_price_usd': market_px,
            'effective_entry_quote_price_usd': float(q.get('effective_entry_price_usd') or 0),
            'entry_liquidity_usd': _num(row, 'live_liquidity_usd', 'liquidity_usd'),
            'entry_quote_proof_level': q.get('proof_level'),
            'entry_quote_stable_symbol': q.get('stable_symbol'),
            'last_market_mark_price_usd': market_px,
            'last_market_mark_value_usd': qty * market_px,
            'paper_only': True,
        }
        positions.append(pos)
        existing[key] = pos
        cash -= POSITION_SIZE
        events.append({'at': ts, 'type': 'ENTRY_QUOTE_VERIFIED', 'key': key, 'cost_usd': POSITION_SIZE, 'proof_level': q.get('proof_level')})

    open_pos = [p for p in positions if p.get('status') == 'OPEN']
    closed = [p for p in positions if p.get('status') == 'CLOSED_QUOTE_VERIFIED']
    open_mark = sum(float(p.get('last_market_mark_value_usd') or 0) for p in open_pos)
    open_cost = sum(float(p.get('cost_usd') or 0) for p in open_pos)
    realized_quote_pnl = sum(float(p.get('realized_quote_pnl_usd') or 0) for p in closed)
    total_equity_marked = cash + open_mark
    legacy = _load(OLD_LEDGER, {})
    legacy_positions = len(legacy.get('positions') or []) if isinstance(legacy, dict) else 0

    ledger.update({'updated_at': ts, 'cash_usd': cash, 'positions': positions, 'events': events[-5000:]})
    summary = {
        'updated_at': ts,
        'mode': 'PAPER_TRUTH_QUOTE_VERIFIED_NO_REAL_MONEY',
        'starting_cash_usd': STARTING_CASH,
        'position_size_usd': POSITION_SIZE,
        'cash_usd': round(cash, 8),
        'open_positions': len(open_pos),
        'closed_quote_verified_positions': len(closed),
        'exit_pending': sum(1 for p in open_pos if p.get('exit_pending')),
        'entry_quote_verified_positions': sum(1 for p in positions if p.get('entry_quote_proof_level')),
        'exit_quote_verified_positions': sum(1 for p in closed if p.get('exit_quote_proof_level')),
        'realized_quote_pnl_usd': round(realized_quote_pnl, 8),
        'closed_quote_wins': sum(1 for p in closed if float(p.get('realized_quote_pnl_usd') or 0) > 0),
        'closed_quote_losses': sum(1 for p in closed if float(p.get('realized_quote_pnl_usd') or 0) < 0),
        'open_cost_usd': round(open_cost, 8),
        'open_market_mark_usd': round(open_mark, 8),
        'total_equity_market_mark_usd': round(total_equity_marked, 8),
        'market_mark_total_pnl_usd': round(total_equity_marked - STARTING_CASH, 8),
        'legacy_old_paper_positions_count': legacy_positions,
        'legacy_execution_status': 'NOT_RETROACTIVELY_VERIFIED',
        'historical_backfill_policy': 'NO RETROACTIVE ENTRY OR EXIT EXECUTION CLAIM WITHOUT A POINT-IN-TIME FIRM QUOTE',
        'truth_note': 'Realized quote P&L uses only same-cycle firm router quotes captured when the engine entry/exit decision existed. It is paper evidence, not a broadcast trade.',
        'important_limit': '0x router quotes are not claimed to be constrained to the discovery pair. Exact pair remains locked for signal identity and production qualification; execution routing is reported separately.',
    }
    return ledger, summary


def main() -> None:
    rows = _load(SOURCE, [])
    if not isinstance(rows, list):
        rows = []
    ledger = _load(LEDGER, initial_ledger())
    active = {_key(r): r for r in rows if isinstance(r, dict) and _safe(r)}
    existing = {_key(p): p for p in (ledger.get('positions') or [])}

    entry_quotes: dict[str, dict[str, Any]] = {}
    for key, row in active.items():
        if key in existing:
            continue
        q, err = live_entry_quote(row)
        entry_quotes[key] = q or {'status': 'UNAVAILABLE', 'reason': err}

    exit_quotes: dict[str, dict[str, Any]] = {}
    for p in ledger.get('positions') or []:
        if p.get('status') == 'OPEN' and _key(p) not in active:
            q, err = live_exit_quote(p)
            exit_quotes[_key(p)] = q or {'status': 'UNAVAILABLE', 'reason': err}

    ledger, summary = reconcile(ledger, rows, entry_quotes, exit_quotes)
    _write(LEDGER, ledger)
    _write(SUMMARY, summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
