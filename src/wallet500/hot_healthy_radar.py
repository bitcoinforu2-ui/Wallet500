from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from .market_data import _pair_to_snapshot, pair_lookup, token_pairs

DATA = Path('data')
OUT = DATA / 'hot-healthy-radar.json'
MIN_LIQ = 50000.0
MIN_VOL = 15000.0
MIN_TX = 50
MIN_MARKET_AGE_DAYS = 180
EVM_CHAINS = {'ethereum', 'eth', 'bsc', 'bnb', 'base', 'arbitrum', 'polygon', 'optimism', 'avalanche'}


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


def _norm(chain, value):
    value = str(value or '')
    return value.lower() if str(chain or '').lower() in EVM_CHAINS else value


def _same(chain, a, b):
    return bool(a and b) and _norm(chain, a) == _norm(chain, b)


def _is_stable_or_wrapped(r):
    text = ' '.join(str(r.get(k) or '').upper() for k in ('symbol', 'name', 'token_symbol'))
    banned = ('USDT', 'USDC', 'DAI', 'FDUSD', 'BUSD', 'USDE', 'WSOL', 'WETH', 'WBTC')
    return any(x in text for x in banned)


def _created_ms(value):
    try:
        value = float(value)
        if value <= 0:
            return None
        return value * 1000.0 if value < 10_000_000_000 else value
    except (TypeError, ValueError):
        return None


def _exact_history(r):
    chain = r.get('chain')
    pair = r.get('entry_pair_address')
    out = []
    for h in r.get('history') or []:
        if not isinstance(h, dict):
            continue
        hp = h.get('pair_address')
        if hp and not _same(chain, hp, pair):
            continue
        px = _f(h.get('price_usd'))
        liq = _f(h.get('liquidity_usd'))
        if px <= 0 or liq <= 0:
            continue
        out.append(h)
    return out


def _preeligible(r):
    """Cheap historical prefilter only; never sufficient for ranking."""
    chain = r.get('chain')
    pair = r.get('entry_pair_address')
    token = r.get('token')
    if not chain or not token or not pair:
        return False
    hist = _exact_history(r)
    if not hist:
        return False
    last = hist[-1]
    tx = _i(last.get('buys_h1')) + _i(last.get('sells_h1'))
    return (
        _f(last.get('price_usd')) > 0
        and _f(last.get('liquidity_usd')) >= MIN_LIQ
        and _f(last.get('volume_h1')) >= MIN_VOL
        and tx >= MIN_TX
    )


def _live_exact_pair_truth(r):
    """Return a fresh, identity-proven live snapshot plus veteran-age proof.

    Historical outcome marks are never allowed to stand in for current market
    truth. Solana addresses remain case-sensitive. The veteran rule is based on
    the oldest currently discoverable pair that proves the exact token is one
    side of the pair; the selected execution pair itself may be newer.
    """
    chain = str(r.get('chain') or '')
    token = str(r.get('token') or '')
    pair = str(r.get('entry_pair_address') or '')
    if not chain or not token or not pair:
        return None, 'MISSING_CHAIN_TOKEN_OR_PAIR'

    pairs = token_pairs(chain, token)
    if not pairs:
        return None, 'LIVE_TOKEN_PAIRS_UNAVAILABLE'

    now_ms = datetime.now(timezone.utc).timestamp() * 1000.0
    oldest_ms = None
    exact_raw = None
    for p in pairs:
        if not isinstance(p, dict):
            continue
        base = (p.get('baseToken') or {}).get('address')
        quote = (p.get('quoteToken') or {}).get('address')
        if not (_same(chain, token, base) or _same(chain, token, quote)):
            continue
        created = _created_ms(p.get('pairCreatedAt'))
        if created is not None and (oldest_ms is None or created < oldest_ms):
            oldest_ms = created
        if _same(chain, p.get('pairAddress'), pair):
            exact_raw = p

    if oldest_ms is None:
        return None, 'VETERAN_AGE_UNVERIFIED'
    age_days = (now_ms - oldest_ms) / 86_400_000.0
    if age_days < MIN_MARKET_AGE_DAYS:
        return None, f'UNDER_{MIN_MARKET_AGE_DAYS}D_MARKET_AGE'

    if exact_raw is None:
        exact_raw = pair_lookup(chain, pair)
    live = _pair_to_snapshot(chain, token, exact_raw)
    if not live or not _same(chain, live.get('pair_address'), pair):
        return None, 'LIVE_EXACT_PAIR_OR_TOKEN_IDENTITY_UNVERIFIED'
    if not live.get('token_identity_verified'):
        return None, 'LIVE_TOKEN_IDENTITY_UNVERIFIED'

    liq = _f(live.get('liquidity_usd'))
    vol = _f(live.get('volume_h1'))
    buys = _i(live.get('buys_h1'))
    sells = _i(live.get('sells_h1'))
    tx = buys + sells
    if liq < MIN_LIQ:
        return None, 'LIVE_LIQUIDITY_BELOW_50K'
    if vol < MIN_VOL:
        return None, 'LIVE_VOLUME_H1_BELOW_15K'
    if tx < MIN_TX:
        return None, 'LIVE_TXNS_H1_BELOW_50'

    live = dict(live)
    live['market_age_days'] = round(age_days, 2)
    live['veteran_age_verified'] = True
    return live, None


def _score(r, live):
    hist = _exact_history(r)
    if not hist or not isinstance(live, dict):
        return None

    price = _f(live.get('price_usd'))
    liq = _f(live.get('liquidity_usd'))
    vol = _f(live.get('volume_h1'))
    buys = _i(live.get('buys_h1'))
    sells = _i(live.get('sells_h1'))
    tx = buys + sells
    if price <= 0 or liq < MIN_LIQ or vol < MIN_VOL or tx < MIN_TX:
        return None

    chain = r.get('chain')
    if not _same(chain, live.get('pair_address'), r.get('entry_pair_address')):
        return None

    # Historical marks provide the pre-move baseline; the final mark is always
    # a fresh live exact-pair observation, never a stale tracker value.
    prior = hist[-3:]
    recent = prior + [{
        'price_usd': price,
        'liquidity_usd': liq,
        'volume_h1': vol,
        'buys_h1': buys,
        'sells_h1': sells,
        'pair_address': live.get('pair_address'),
    }]
    liqs = [_f(x.get('liquidity_usd')) for x in prior if _f(x.get('liquidity_usd')) > 0]
    prior_liq = median(liqs) if liqs else liq
    liq_retention = liq / prior_liq if prior_liq > 0 else 1.0

    total = max(1, tx)
    buy_share = buys / total
    buy_sell_ratio = buys / max(1, sells)
    turnover = vol / liq if liq > 0 else 99.0

    prev_price = _f(prior[-1].get('price_usd')) if prior else price
    short_momentum = ((price / prev_price) - 1.0) * 100 if prev_price > 0 else 0.0
    discovery = _f(r.get('entry_price_usd'))
    runup = ((price / discovery) - 1.0) * 100 if discovery > 0 else None

    score = 0.0
    reasons = ['LIVE_EXACT_PAIR_REVERIFIED', 'VETERAN_AGE_VERIFIED']

    if liq_retention >= 1.00:
        score += 30; reasons.append('LIQUIDITY_STABLE_OR_GROWING')
    elif liq_retention >= 0.95:
        score += 26; reasons.append('LIQUIDITY_RETENTION_GE_95PCT')
    elif liq_retention >= 0.90:
        score += 20; reasons.append('LIQUIDITY_RETENTION_GE_90PCT')
    elif liq_retention >= 0.80:
        score += 10

    if buy_share >= 0.58:
        score += 24; reasons.append('STRONG_BUY_PRESSURE')
    elif buy_share >= 0.53:
        score += 20; reasons.append('POSITIVE_BUY_PRESSURE')
    elif buy_share >= 0.48:
        score += 13
    else:
        score += 5

    if 0.10 <= turnover <= 0.75:
        score += 20; reasons.append('HEALTHY_TURNOVER')
    elif 0.05 <= turnover <= 1.25:
        score += 16
    elif turnover <= 2.0:
        score += 9
    else:
        score += 2; reasons.append('OVERHEATED_TURNOVER')

    if 0 <= short_momentum <= 8:
        score += 16; reasons.append('CONTROLLED_POSITIVE_MOMENTUM')
    elif -3 <= short_momentum < 0:
        score += 10
    elif 8 < short_momentum <= 15:
        score += 9
    else:
        score += 3

    if runup is not None:
        if runup <= 10:
            score += 10; reasons.append('EARLY_NOT_CHASED')
        elif runup <= 25:
            score += 7
        elif runup <= 50:
            score += 2
        else:
            score -= 8; reasons.append('CHASE_RISK')

    # At least one historical exact-pair mark plus the fresh live mark is needed.
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
        'dex': live.get('dex') or r.get('entry_dex'),
        'dex_url': live.get('url'),
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
        'market_age_days': live.get('market_age_days'),
        'veteran_age_verified': True,
        'live_token_identity_verified': True,
        'target_token_side': live.get('target_token_side'),
        'survival_marks': len(recent),
        'anti_chase_ok': anti_chase_ok,
        'reasons': reasons,
        'history_marks_used': len(prior),
    }


def run():
    tracker = _load(DATA / 'outcome-tracker.json', {})
    records = tracker.get('tokens') if isinstance(tracker, dict) else {}
    rows = []
    quarantine = []
    preeligible = 0
    if isinstance(records, dict):
        for r in records.values():
            if not isinstance(r, dict) or _is_stable_or_wrapped(r) or not _preeligible(r):
                continue
            preeligible += 1
            live, reason = _live_exact_pair_truth(r)
            if not live:
                quarantine.append({
                    'chain': r.get('chain'),
                    'token': r.get('token'),
                    'pair_address': r.get('entry_pair_address'),
                    'reason': reason,
                })
                continue
            z = _score(r, live)
            if z:
                rows.append(z)
            else:
                quarantine.append({
                    'chain': r.get('chain'),
                    'token': r.get('token'),
                    'pair_address': r.get('entry_pair_address'),
                    'reason': 'LIVE_SCORE_REJECTED',
                })

    rows.sort(key=lambda x: (x['score'], x['liquidity_retention'], x['buy_share']), reverse=True)
    hot = [x for x in rows if x['label'] == 'HOT_HEALTHY']
    watch = [x for x in rows if x['label'] == 'HEALTHY_WATCH']
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'method': 'HOT_HEALTHY_EARLY_RADAR_V3_LIVE_VETERAN_TRUTH',
        'production_change': False,
        'hard_rules_preserved': {
            'liquidity_min_usd': MIN_LIQ,
            'volume_h1_min_usd': MIN_VOL,
            'txns_h1_min': MIN_TX,
            'exact_pair_required': True,
            'live_exact_pair_recheck_required': True,
            'token_identity_required': True,
            'veteran_market_age_min_days': MIN_MARKET_AGE_DAYS,
            'solana_address_case_sensitive': True,
        },
        'hot_healthy_rules': {
            'min_score': 78,
            'min_exact_pair_marks_including_live': 2,
            'max_runup_since_discovery_pct': 25.0,
            'min_liquidity_retention': 0.90,
            'min_buy_share': 0.50,
            'max_turnover_h1': 2.0,
        },
        'historical_preeligible_candidates': preeligible,
        'scored_live_verified_candidates': len(rows),
        'quarantined_fail_closed_count': len(quarantine),
        'hot_healthy_count': len(hot),
        'healthy_watch_count': len(watch),
        'hot_healthy': hot[:50],
        'healthy_watch': watch[:100],
        'top_ranked': rows[:100],
        'quarantined_fail_closed': quarantine[:200],
        'note': 'Research/radar ranking only. V3 rechecks the exact pair live, proves target-token identity/side, requires current $50K/$15K/50 activity gates, and requires >=180-day veteran-market proof before ranking. Historical outcome marks are baseline evidence only and can never substitute for current market truth. It does not bypass LP/ownership/cluster verification or create a production tradability claim.'
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: payload[k] for k in ('historical_preeligible_candidates','scored_live_verified_candidates','quarantined_fail_closed_count','hot_healthy_count','healthy_watch_count')}, indent=2))
    return payload


if __name__ == '__main__':
    run()
