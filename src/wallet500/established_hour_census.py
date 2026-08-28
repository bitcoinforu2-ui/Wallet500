from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def _dt(value: str):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except Exception:
        return None


def run_established_hour_census(out: Path, now: str, cex_payload: dict) -> dict:
    path = out / 'established-hour-census.json'
    state = _load(path, {})
    now_dt = _dt(now) or datetime.now(timezone.utc)

    # One fixed, no-hindsight experiment. Once the first full hour is complete,
    # freeze its result so later scans cannot rewrite the conclusion.
    if state.get('completed') and state.get('final'):
        return state

    if not state.get('started_at'):
        state = {
            'version': 1,
            'experiment': 'ESTABLISHED_MARKET_1H_COVERAGE',
            'started_at': now,
            'target_end_at': (now_dt + timedelta(hours=1)).isoformat(),
            'completed': False,
            'runs': [],
            'unique_symbols': [],
            'unique_alert_symbols': [],
            'source_exchanges': [],
            'rules': [
                'real scan observations only',
                'deduplicate by normalized CEX symbol',
                'do not infer token age when age is unavailable',
                'freeze final result after >=60 minutes',
            ],
        }

    cex_state = _load(out / 'cex-state.json', {})
    markets = cex_state.get('markets') if isinstance(cex_state.get('markets'), dict) else {}
    current_symbols = set()
    current_exchanges = set()
    for key, history in markets.items():
        if not isinstance(history, list) or not history:
            continue
        last = history[-1] if isinstance(history[-1], dict) else {}
        observed = _dt(str(last.get('observed_at') or ''))
        if not observed or abs((observed - now_dt).total_seconds()) > 5:
            continue
        if ':' in key:
            ex, sym = key.split(':', 1)
            if sym:
                current_symbols.add(sym)
            if ex:
                current_exchanges.add(ex)

    alert_symbols = {
        str(a.get('symbol')) for a in (cex_payload.get('alerts') or [])
        if isinstance(a, dict) and a.get('symbol')
    }
    all_symbols = set(state.get('unique_symbols') or []) | current_symbols
    all_alerts = set(state.get('unique_alert_symbols') or []) | alert_symbols
    all_exchanges = set(state.get('source_exchanges') or []) | current_exchanges

    state['unique_symbols'] = sorted(all_symbols)
    state['unique_alert_symbols'] = sorted(all_alerts)
    state['source_exchanges'] = sorted(all_exchanges)
    state['runs'].append({
        'at': now,
        'symbols_this_run': len(current_symbols),
        'alerts_this_run': len(alert_symbols),
        'healthy_sources': int(cex_payload.get('healthy_sources', 0) or 0),
        'contracts_seen': int(cex_payload.get('contracts_seen', 0) or 0),
    })
    state['runs'] = state['runs'][-20:]
    state['updated_at'] = now
    state['elapsed_minutes'] = round(max(0.0, (now_dt - (_dt(state['started_at']) or now_dt)).total_seconds() / 60.0), 2)
    state['summary'] = {
        'runs_recorded': len(state['runs']),
        'unique_established_symbols_observed': len(all_symbols),
        'unique_revival_alert_symbols': len(all_alerts),
        'source_exchanges_observed': len(all_exchanges),
        'repeat_observations': max(0, sum(int(r.get('symbols_this_run', 0)) for r in state['runs']) - len(all_symbols)),
    }

    if state['elapsed_minutes'] >= 60:
        state['completed'] = True
        state['completed_at'] = now
        state['final'] = dict(state['summary'])
        state['final']['elapsed_minutes'] = state['elapsed_minutes']
        state['final']['note'] = 'Age buckets are intentionally absent because the current CEX lane does not expose verified token launch age.'

    path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    return state
