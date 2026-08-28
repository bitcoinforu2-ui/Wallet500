from __future__ import annotations
import json
from pathlib import Path

MIN_TRADABLE_LIQUIDITY_USD = 50_000.0
MAX_LIQUIDITY_DROP_FROM_PREV = 0.45
MAX_LIQUIDITY_DROP_FROM_OBSERVED_PEAK = 0.70


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _key(chain: str, token: str) -> str:
    token = token or ''
    if chain in {'ethereum', 'bsc'}:
        token = token.lower()
    return f'{chain}:{token}'


def _history_metrics(candidate: dict, outcomes: dict) -> dict:
    chain = candidate.get('chain')
    token = candidate.get('token') or candidate.get('mint') or ''
    rec = ((outcomes or {}).get('tokens') or {}).get(_key(chain, token), {}) or {}
    history = rec.get('history') if isinstance(rec.get('history'), list) else []
    liquidities = []
    for row in history:
        try:
            v = float(row.get('liquidity_usd') or 0)
        except Exception:
            v = 0.0
        if v > 0:
            liquidities.append(v)
    current = float(candidate.get('liquidity_usd') or 0)
    previous = liquidities[-2] if len(liquidities) >= 2 else (liquidities[-1] if liquidities else 0.0)
    peak = max(liquidities + ([current] if current > 0 else []), default=0.0)
    return {'current': current, 'previous': previous, 'peak': peak, 'history_points': len(history)}


def evaluate(candidate: dict, outcomes: dict) -> dict:
    m = _history_metrics(candidate, outcomes)
    current, previous, peak = m['current'], m['previous'], m['peak']
    critical = []
    reasons = []

    # Wallet500 iron rule: no production/tradable status below $50K live liquidity.
    if current < MIN_TRADABLE_LIQUIDITY_USD:
        critical.append('LIVE_LIQUIDITY_BELOW_50K_HARD_BLOCK')

    # Detect evacuation before momentum/price/volume can mask the loss of executable depth.
    if previous >= MIN_TRADABLE_LIQUIDITY_USD and current > 0:
        retention_prev = current / previous
        if retention_prev <= MAX_LIQUIDITY_DROP_FROM_PREV:
            critical.append('LIQUIDITY_EVACUATION_GT_55PCT_ONE_OBSERVATION')
        elif retention_prev < 0.70:
            reasons.append('LIQUIDITY_RETENTION_LT_70PCT_ONE_OBSERVATION')
    elif previous >= MIN_TRADABLE_LIQUIDITY_USD and current <= 0:
        critical.append('LIQUIDITY_EVACUATION_TO_ZERO')

    if peak >= MIN_TRADABLE_LIQUIDITY_USD and current > 0:
        retention_peak = current / peak
        if retention_peak <= 0.10:
            critical.append('LIQUIDITY_COLLAPSE_GT_90PCT_FROM_OBSERVED_PEAK')
        elif retention_peak < MAX_LIQUIDITY_DROP_FROM_OBSERVED_PEAK:
            reasons.append('LIQUIDITY_RETENTION_LT_70PCT_FROM_OBSERVED_PEAK')
    else:
        retention_peak = None

    # If a token once crossed the tradable threshold and later falls below it,
    # it loses tradable status immediately. Historical qualification remains immutable.
    if peak >= MIN_TRADABLE_LIQUIDITY_USD and current < MIN_TRADABLE_LIQUIDITY_USD:
        if 'LIVE_LIQUIDITY_BELOW_50K_HARD_BLOCK' not in critical:
            critical.append('TRADABLE_LIQUIDITY_LOST_BELOW_50K')
        else:
            reasons.append('TRADABLE_LIQUIDITY_LOST_AFTER_PREVIOUS_50K_PLUS')

    blocked = bool(critical)
    return {
        **candidate,
        'production_risk_gate': 'BLOCKED' if blocked else ('CAUTION' if reasons else 'PASS'),
        'production_risk_blocked': blocked,
        'production_risk_critical': list(dict.fromkeys(critical)),
        'production_risk_reasons': list(dict.fromkeys(critical + reasons)),
        'production_live_liquidity_usd': current,
        'production_previous_liquidity_usd': previous or None,
        'production_peak_observed_liquidity_usd': peak or None,
        'production_liquidity_retention_from_peak': round(retention_peak, 6) if retention_peak is not None else None,
        'production_history_points': m['history_points'],
    }


def apply(output_dir: str = 'data') -> dict:
    out = Path(output_dir)
    outcomes = _load(out / 'outcome-tracker.json', {})
    active = _load(out / 'active-qualified-candidates.json', [])
    watch = _load(out / 'watchlist.json', [])
    existing_risk = _load(out / 'pump-dump-risk.json', [])
    summary = _load(out / 'run-summary.json', {})

    evaluations = [evaluate(x, outcomes) for x in active]
    passed = [x for x in evaluations if not x.get('production_risk_blocked')]
    blocked = [x for x in evaluations if x.get('production_risk_blocked')]

    passed_keys = set()
    for x in passed:
        token = x.get('token') or x.get('mint') or ''
        if x.get('chain') in {'ethereum', 'bsc'}:
            token = token.lower()
        passed_keys.add((x.get('chain'), token))

    filtered_watch = []
    for x in watch:
        if x.get('watch_source') != 'QUALIFIED_ANOMALY':
            filtered_watch.append(x)
            continue
        token = x.get('token') or x.get('mint') or ''
        if x.get('chain') in {'ethereum', 'bsc'}:
            token = token.lower()
        if (x.get('chain'), token) in passed_keys:
            filtered_watch.append(x)

    # Preserve existing pump/dump records; append production hard-block evidence by token.
    merged = {}
    for x in (existing_risk if isinstance(existing_risk, list) else []) + blocked:
        chain = x.get('chain')
        token = x.get('token') or x.get('mint') or ''
        if chain and token:
            merged[_key(chain, token)] = x

    _write(out / 'active-qualified-candidates.json', passed)
    _write(out / 'watchlist.json', filtered_watch)
    _write(out / 'production-risk-evaluations.json', evaluations)
    _write(out / 'production-risk-blocked.json', blocked)
    _write(out / 'pump-dump-risk.json', list(merged.values()))

    if isinstance(summary, dict):
        summary['production_risk_gate'] = {
            'min_live_liquidity_usd': int(MIN_TRADABLE_LIQUIDITY_USD),
            'active_before_gate': len(active),
            'active_after_gate': len(passed),
            'blocked_now': len(blocked),
            'hard_rule': 'CURRENT_LIQUIDITY_MUST_REMAIN_GE_50K',
            'evacuation_rule': 'LOSS_OF_EXECUTABLE_LIQUIDITY_OVERRIDES_PRICE_VOLUME_BUYS_AND_ANOMALY_SCORE',
        }
        summary['active_qualified'] = len(passed)
        summary['watchlist'] = len(filtered_watch)
        _write(out / 'run-summary.json', summary)

    result = {'active_before_gate': len(active), 'active_after_gate': len(passed), 'blocked_now': len(blocked), 'watchlist': len(filtered_watch)}
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    apply()
