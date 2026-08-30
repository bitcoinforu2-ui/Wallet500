from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

DATA = Path('data')
OUT = DATA / 'hot-healthy-radar.json'
MIN_LIQ = 50000.0
MIN_VOL = 15000.0
MIN_TX = 50


def _load(path, default):
    try:
        if not path.exists() or path.stat().st_size == 0:
            return default
        return json.loads(path.read_text())
    except Exception:
        return default


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _same(a, b):
    return str(a or '').lower() == str(b or '').lower()


def _is_stable_or_wrapped(r):
    text = ' '.join(str(r.get(k) or '').upper() for k in ('symbol', 'name', 'token_symbol'))
    banned = ('USDT', 'USDC', 'DAI', 'FDUSD', 'BUSD', 'USDE', 'WSOL', 'WETH', 'WBTC')
    return any(x in text for x in banned)


def _exact_history(r):
    pair = r.get('entry_pair_address')
    out = []
    for h in r.get('history') or []:
        if not isinstance(h, dict):
            continue
        hp = h.get('pair_address')
        if hp and not _same(hp, pair):
            continue
        px = _f(h.get('price_usd'))
        liq = _f(h.get('liquidity_usd'))
        if px <= 0 or liq <= 0:
            continue
        out.append(h)
    return out


def _score(r):
    hist = _exact_history(r)
    if not hist:
        return None
    last = hist[-1]
    price = _f(r.get('current_price_usd')) or _f(last.get('price_usd'))
    liq = _f(last.get('liquidity_usd'))
    vol = _f(last.get('volume_h1'))
    buys = _i(last.get('buys_h1'))
    sells = _i(last.get('sells_h1'))
    tx = buys + sells
    if price <= 0 or liq < MIN_LIQ or vol < MIN_VOL or tx < MIN_TX:
        return None

    # Require current exact-pair verification. This radar must never create a
    # tradability claim from a different pool.
    if r.get('measurement_status') != 'VERIFIED_EXACT_PAIR':
        return None
    if not _same(r.get('current_pair_address'), r.get('entry_pair_address')):
        return None

    recent = hist[-4:]
    liqs = [_f(x.get('liquidity_usd')) for x in recent if _f(x.get('liquidity_usd')) > 0]
    prior_liq = median(liqs[:-1]) if len(liqs) > 1 else liq
    liq_retention = liq / prior_liq if prior_liq > 0 else 1.0

    total = max(1, tx)
    buy_share = buys / total
    buy_sell_ratio = buys / max(1, sells)
    turnover = vol / liq if liq > 0 else 99.0

    prev_price = _f(recent[-2].get('price_usd')) if len(recent) > 1 else price
    short_momentum = ((price / prev_price) - 1.0) * 100 if prev_price > 0 else 0.0
    discovery = _f(r.get('entry_price_usd'))
    runup = ((price / discovery) - 1.0) * 100 if discovery > 0 else None

    score = 0.0
    reasons = []

    # Liquidity survival: largest weight. Hot without surviving liquidity is not healthy.
    if liq_retention >= 1.00:
        score += 30; reasons.append('LIQUIDITY_STABLE_OR_GROWING')
    elif liq_retention >= 0.95:
        score += 26; reasons.append('LIQUIDITY_RETENTION_GE_95PCT')
    elif liq_retention >= 0.90:
        score += 20; reasons.append('LIQUIDITY_RETENTION_GE_90PCT')
    elif liq_retention >= 0.80:
        score += 10

    # Buy pressure rewards demand, but not alone.
    if buy_share >= 0.58:
        score += 24; reasons.append('STRONG_BUY_PRESSURE')
    elif buy_share >= 0.53:
        score += 20; reasons.append('POSITIVE_BUY_PRESSURE')
    elif buy_share >= 0.48:
        score += 13
    else:
        score += 5

    # Healthy heat: activity relative to pool size. Extreme turnover is penalized.
    if 0.10 <= turnover <= 0.75:
        score += 20; reasons.append('HEALTHY_TURNOVER')
    elif 0.05 <= turnover <= 1.25:
        score += 16
    elif turnover <= 2.0:
        score += 9
    else:
        score += 2; reasons.append('OVERHEATED_TURNOVER')

    # Prefer early controlled momentum over chasing a vertical move.
    if 0 <= short_momentum <= 8:
        score += 16; reasons.append('CONTROLLED_POSITIVE_MOMENTUM')
    elif -3 <= short_momentum < 0:
        score += 10
    elif 8 < short_momentum <= 15:
        score += 9
    else:
        score += 3

    # Anti-chase context. Missing run-up is neutral rather than rewarded.
    if runup is not None:
        if runup <= 10:
            score += 10; reasons.append('EARLY_NOT_CHASED')
        elif runup <= 25:
            score += 7
        elif runup <= 50:
            score += 2
        else:
            score -= 8; reasons.append('CHASE_RISK')

    # One mark cannot prove survival/retention. Keep it visible, but never call it HOT_HEALTHY.
    has_survival_proof = len(recent) >= 2
    if not has_survival_proof:
        reasons.append('INSUFFICIENT_SURVIVAL_HISTORY')
        score = min(score, 77.0)

    score = max(0.0, min(100.0, score))
    anti_chase_ok = runup is not None and runup <= 25.0
    if score >= 78 and has_survival_proof and anti_chase_ok and liq_retention >= 0.90 and buy_share >= 0.50 and turnover <= 2.0:
        label = 'HOT_HEALTHY'
    elif score >= 65 and liq_retention >= 0.85:
        label = 'HEALTHY_WATCH'
    else:
        label = 'OBSERVE'

    return {
        'chain': r.get('chain'),
        'token': r.get('token'),
        'pair_address': r.get('entry_pair_address'),
        'dex': r.get('entry_dex'),
        'score': round(score, 2),
        'label': label,
        'price_usd': price,
        'liquidity_usd': round(liq, 2),
        'liquidity_retention': round(liq_retention, 4),
        'volume_h1': round(vol, 2),
        'txns_h1': tx,
        'buys_h1': buys,
        'sells_h1': sells,
        'buy_share': round(buy_share, 4),
        'buy_sell_ratio': round(buy_sell_ratio, 4),
        'turnover_h1': round(turnover, 4),
        'short_momentum_pct': round(short_momentum, 4),
        'runup_since_discovery_pct': round(runup, 4) if runup is not None else None,
        'survival_marks': len(recent),
        'anti_chase_ok': anti_chase_ok,
        'reasons': reasons,
        'history_marks_used': len(recent),
    }


def run():
    tracker = _load(DATA / 'outcome-tracker.json', {})
    records = tracker.get('tokens') if isinstance(tracker, dict) else {}
    rows = []
    if isinstance(records, dict):
        for r in records.values():
            if not isinstance(r, dict) or _is_stable_or_wrapped(r):
                continue
            z = _score(r)
            if z:
                rows.append(z)
    rows.sort(key=lambda x: (x['score'], x['liquidity_retention'], x['buy_share']), reverse=True)
    hot = [x for x in rows if x['label'] == 'HOT_HEALTHY']
    watch = [x for x in rows if x['label'] == 'HEALTHY_WATCH']
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'method': 'HOT_HEALTHY_EARLY_RADAR_V2',
        'production_change': False,
        'hard_rules_preserved': {'liquidity_min_usd': MIN_LIQ, 'volume_h1_min_usd': MIN_VOL, 'txns_h1_min': MIN_TX, 'exact_pair_required': True},
        'hot_healthy_rules': {'min_score': 78, 'min_exact_pair_marks': 2, 'max_runup_since_discovery_pct': 25.0, 'min_liquidity_retention': 0.90, 'min_buy_share': 0.50, 'max_turnover_h1': 2.0},
        'scored_exact_pair_candidates': len(rows),
        'hot_healthy_count': len(hot),
        'healthy_watch_count': len(watch),
        'hot_healthy': hot[:50],
        'healthy_watch': watch[:100],
        'top_ranked': rows[:100],
        'note': 'Research/radar ranking only. HOT_HEALTHY requires exact pair, base market gate, >=2 exact-pair marks, <=25% same-pair run-up since discovery, liquidity retention, balanced-positive buy pressure and non-overheated turnover. It does not bypass LP/ownership/cluster verification or create a production tradability claim.'
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: payload[k] for k in ('scored_exact_pair_candidates','hot_healthy_count','healthy_watch_count')}, indent=2))
    return payload


if __name__ == '__main__':
    run()
