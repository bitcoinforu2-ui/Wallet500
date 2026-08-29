from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path('data')
STATE = DATA / 'lifecycle-strategy-ledger.json'
SUMMARY = DATA / 'lifecycle-strategy-summary.json'
SOURCE = DATA / 'outcome-tracker.json'
POSITION_USD = 1.0
MIN_LIQ = 50_000.0
POLICY_VERSION = 'LIFECYCLE_V1_FORWARD_ONLY'
# Fractions are of the original token quantity. Frozen from first activation.
TAKE_PROFITS = ((100.0, 0.25, 'TP1_2X'), (300.0, 0.25, 'TP2_4X'), (700.0, 0.25, 'TP3_8X'))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text()) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def _key(chain: str, token: str, pair: str) -> str:
    c = str(chain or '').lower()
    t = str(token or '')
    p = str(pair or '')
    if c in {'ethereum', 'bsc'}:
        t, p = t.lower(), p.lower()
    return f'{c}|{t}|{p}'


def _n(v: Any) -> float:
    try: return float(v)
    except Exception: return 0.0


def initial_state(now: str | None = None) -> dict[str, Any]:
    ts = now or _now()
    return {
        'policy_version': POLICY_VERSION,
        'activation_time': ts,
        'position_usd': POSITION_USD,
        'min_liquidity_usd': MIN_LIQ,
        'take_profit_policy': [{'return_pct': r, 'sell_fraction_original': f, 'label': l} for r,f,l in TAKE_PROFITS],
        'mode': 'FORWARD_ONLY_EXACT_PAIR_MARKET_SIGNAL_LEDGER_NOT_EXECUTION_PROOF',
        'positions': {},
        'events': [],
        'updated_at': ts,
    }


def reconcile(state: dict[str, Any], tracker: dict[str, Any], now: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    ts = now or _now()
    state = dict(state or initial_state(ts))
    activation = str(state.get('activation_time') or ts)
    positions = dict(state.get('positions') or {})
    events = list(state.get('events') or [])
    tokens = tracker.get('tokens') if isinstance(tracker, dict) else {}
    tokens = tokens if isinstance(tokens, dict) else {}

    for rec in tokens.values():
        if not isinstance(rec, dict) or rec.get('measurement_status') != 'VERIFIED_EXACT_PAIR':
            continue
        chain = rec.get('chain'); token = rec.get('token'); pair = rec.get('entry_pair_address')
        entry = _n(rec.get('entry_price_usd')); current = _n(rec.get('current_price_usd'))
        if not chain or not token or not pair or entry <= 0 or current <= 0:
            continue
        key = _key(chain, token, pair)
        p = positions.get(key)
        if not isinstance(p, dict):
            # Forward-only: do not manufacture historical sells before this policy existed.
            p = {
                'chain': chain, 'token': token, 'pair_address': pair,
                'entry_reference_price_usd': entry, 'model_cost_usd': POSITION_USD,
                'original_units': POSITION_USD / entry, 'remaining_fraction': 1.0,
                'realized_model_cash_usd': 0.0, 'triggered': [],
                'tracking_from': activation, 'status': 'OPEN_SIGNAL_MODEL',
                'proof_level': 'IMMUTABLE_DISCOVERY_PRICE_PLUS_EXACT_PAIR_MARKS_NOT_EXECUTED',
            }
            positions[key] = p
            events.append({'at': ts, 'type': 'MODEL_POSITION_BASELINED', 'key': key, 'price_usd': current, 'note': 'NO_RETROACTIVE_SELLS'})

        ret = (current / entry - 1.0) * 100.0
        history = rec.get('history') if isinstance(rec.get('history'), list) else []
        latest = history[-1] if history else {}
        liq = _n(latest.get('liquidity_usd'))
        p['last_price_usd'] = current
        p['last_return_pct'] = round(ret, 4)
        p['last_liquidity_usd'] = liq
        p['last_mark_at'] = ts

        triggered = set(p.get('triggered') or [])
        for threshold, fraction, label in TAKE_PROFITS:
            if label in triggered or p.get('remaining_fraction', 0) <= 0:
                continue
            if ret >= threshold:
                sell_fraction = min(fraction, _n(p.get('remaining_fraction')))
                units = _n(p.get('original_units')) * sell_fraction
                proceeds = units * current
                p['remaining_fraction'] = round(_n(p.get('remaining_fraction')) - sell_fraction, 10)
                p['realized_model_cash_usd'] = round(_n(p.get('realized_model_cash_usd')) + proceeds, 10)
                p.setdefault('triggered', []).append(label)
                events.append({'at': ts, 'type': 'PARTIAL_SELL_SIGNAL', 'key': key, 'label': label, 'sell_fraction_original': sell_fraction, 'market_price_usd': current, 'model_proceeds_usd': proceeds, 'proof_level': 'EXACT_PAIR_MARK_SIGNAL_NOT_EXECUTED'})
                triggered.add(label)

        # Liquidity survival override: exit all remaining model exposure once observed < $50K.
        if liq > 0 and liq < MIN_LIQ and _n(p.get('remaining_fraction')) > 0:
            sell_fraction = _n(p.get('remaining_fraction'))
            units = _n(p.get('original_units')) * sell_fraction
            proceeds = units * current
            p['remaining_fraction'] = 0.0
            p['realized_model_cash_usd'] = round(_n(p.get('realized_model_cash_usd')) + proceeds, 10)
            p['status'] = 'CLOSED_LIQUIDITY_EXIT_SIGNAL'
            events.append({'at': ts, 'type': 'LIQUIDITY_HARD_EXIT_SIGNAL', 'key': key, 'sell_fraction_original': sell_fraction, 'market_price_usd': current, 'liquidity_usd': liq, 'model_proceeds_usd': proceeds, 'proof_level': 'EXACT_PAIR_MARK_SIGNAL_NOT_EXECUTED'})

        if _n(p.get('remaining_fraction')) <= 0 and p.get('status') == 'OPEN_SIGNAL_MODEL':
            p['status'] = 'CLOSED_SIGNAL_MODEL'

    invested = len(positions) * POSITION_USD
    realized = 0.0; open_mark = 0.0; closed = 0
    wins = losses = 0
    for p in positions.values():
        realized += _n(p.get('realized_model_cash_usd'))
        open_mark += _n(p.get('original_units')) * _n(p.get('remaining_fraction')) * _n(p.get('last_price_usd'))
        if _n(p.get('remaining_fraction')) <= 0:
            closed += 1
            pnl = _n(p.get('realized_model_cash_usd')) - POSITION_USD
            wins += int(pnl > 0); losses += int(pnl < 0)
    total_value = realized + open_mark
    pnl = total_value - invested
    roi = (pnl / invested * 100.0) if invested else 0.0

    state.update({'positions': positions, 'events': events[-10000:], 'updated_at': ts})
    summary = {
        'updated_at': ts, 'policy_version': POLICY_VERSION, 'activation_time': activation,
        'mode': state['mode'], 'positions_total': len(positions), 'closed_positions': closed,
        'model_invested_usd': round(invested, 8), 'realized_model_cash_usd': round(realized, 8),
        'open_exact_pair_mark_usd': round(open_mark, 8), 'total_model_value_usd': round(total_value, 8),
        'model_pnl_usd': round(pnl, 8), 'model_roi_pct': round(roi, 4),
        'closed_wins': wins, 'closed_losses': losses,
        'partial_sell_signals': sum(1 for e in events if e.get('type') == 'PARTIAL_SELL_SIGNAL'),
        'liquidity_exit_signals': sum(1 for e in events if e.get('type') == 'LIQUIDITY_HARD_EXIT_SIGNAL'),
        'truth_note': 'This is a forward-only strategy decision ledger. It records exact-pair market sell signals and partial-profit logic, but does not claim an executable or broadcast trade without a same-cycle pair-specific quote.',
        'retroactive_policy': 'NO_RETROACTIVE_SELLS_BEFORE_POLICY_ACTIVATION',
    }
    return state, summary


def main() -> None:
    tracker = _load(SOURCE, {})
    state = _load(STATE, initial_state())
    state, summary = reconcile(state, tracker)
    _write(STATE, state); _write(SUMMARY, summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
