from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA = Path('data')
CONFIG = DATA / 'profile5-long-horizon-config.json'
OUTPUT = DATA / 'profile5-long-horizon-report.json'
BASE = 'https://api.geckoterminal.com/api/v2'
NETWORK = {'ethereum': 'eth', 'bsc': 'bsc', 'solana': 'solana'}
UA = {'User-Agent': 'Wallet500-Profile5-Research/1.0', 'Accept': 'application/json;version=20230203'}


def _load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def _fetch_daily(network: str, pair: str, limit: int = 370):
    params = urlencode({'aggregate': 1, 'limit': limit, 'currency': 'usd'})
    url = f'{BASE}/networks/{network}/pools/{pair}/ohlcv/day?{params}'
    req = Request(url, headers=UA)
    with urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    rows = (((d.get('data') or {}).get('attributes') or {}).get('ohlcv_list') or [])
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        out.append({
            'timestamp': int(row[0]),
            'open': float(row[1]),
            'high': float(row[2]),
            'low': float(row[3]),
            'close': float(row[4]),
            'volume_usd': float(row[5]),
        })
    out.sort(key=lambda x: x['timestamp'])
    return out


def _max_drawdown(closes):
    peak = None
    worst = 0.0
    for x in closes:
        if x <= 0:
            continue
        peak = x if peak is None else max(peak, x)
        dd = (x / peak - 1.0) * 100.0
        worst = min(worst, dd)
    return worst


def _window_profile(candles, days: int):
    rows = candles[-days:] if len(candles) >= days else candles[:]
    if not rows:
        return {'status': 'UNAVAILABLE', 'requested_days': days, 'available_days': 0}
    closes = [r['close'] for r in rows if r['close'] > 0]
    highs = [r['high'] for r in rows]
    lows = [r['low'] for r in rows if r['low'] > 0]
    vols = [r['volume_usd'] for r in rows]
    returns = []
    for a, b in zip(closes, closes[1:]):
        if a > 0 and b > 0:
            returns.append(math.log(b / a))
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = sum((x - mean) ** 2 for x in returns) / len(returns) if returns else 0.0
    first = closes[0] if closes else None
    last = closes[-1] if closes else None
    descriptive_return = ((last / first) - 1.0) * 100.0 if first and last else None
    positive_days = sum(1 for a, b in zip(closes, closes[1:]) if b > a)
    return {
        'status': 'COMPLETE' if len(rows) >= days else 'PARTIAL_HISTORY',
        'requested_days': days,
        'available_days': len(rows),
        'first_timestamp': rows[0]['timestamp'],
        'last_timestamp': rows[-1]['timestamp'],
        'first_close_usd': first,
        'last_close_usd': last,
        'descriptive_price_change_pct': descriptive_return,
        'period_high_usd': max(highs) if highs else None,
        'period_low_usd': min(lows) if lows else None,
        'max_close_drawdown_pct': _max_drawdown(closes),
        'volume_total_usd': sum(vols),
        'volume_avg_daily_usd': sum(vols) / len(vols) if vols else None,
        'positive_close_days': positive_days,
        'log_return_volatility_daily': math.sqrt(variance) if returns else None,
        'roi_status': 'NOT_ENGINE_ROI_DESCRIPTIVE_HISTORY_ONLY',
    }


def run():
    cfg = _load(CONFIG)
    assert cfg['mode'] == 'RESEARCH_ONLY_FIXED_5_EXACT_PAIRS'
    assert cfg['lookahead_policy'] == 'FORBIDDEN'
    assert cfg['pair_identity_policy'] == 'EXACT_LOCKED_PAIR_ONLY'
    assert cfg['production_portfolio_impact'] == 'NONE'
    tokens = cfg.get('tokens') or []
    assert len(tokens) == 5
    windows = [7, 30, 90, 270, 365]
    assert cfg.get('windows_days') == windows

    now = datetime.now(timezone.utc).isoformat()
    profiles = []
    for item in tokens:
        chain = str(item['chain']).lower()
        token = str(item['token'])
        pair = str(item['pair_address'])
        if chain not in NETWORK or not token or not pair:
            raise RuntimeError('Invalid locked identity in profile5 config')
        try:
            candles = _fetch_daily(NETWORK[chain], pair)
            profiles.append({
                'chain': chain,
                'token': token,
                'pair_address': pair,
                'pair_identity_locked': True,
                'provider': 'GECKOTERMINAL_PUBLIC_API',
                'candles_count': len(candles),
                'oldest_timestamp': candles[0]['timestamp'] if candles else None,
                'newest_timestamp': candles[-1]['timestamp'] if candles else None,
                'windows': {str(d): _window_profile(candles, d) for d in windows},
                'historical_liquidity_verified': False,
                'historical_holder_cluster_verified': False,
                'verified_tradable_claim': False,
                'engine_roi_claim': False,
            })
        except Exception as e:
            profiles.append({
                'chain': chain,
                'token': token,
                'pair_address': pair,
                'pair_identity_locked': True,
                'status': 'FETCH_FAILED',
                'error': f'{type(e).__name__}: {e}'[:300],
                'windows': {str(d): {'status': 'UNAVAILABLE', 'requested_days': d, 'available_days': 0} for d in windows},
                'verified_tradable_claim': False,
                'engine_roi_claim': False,
            })

    report = {
        'version': 1,
        'generated_at': now,
        'mode': 'RESEARCH_ONLY_FIXED_5_EXACT_PAIRS',
        'purpose': 'Deep descriptive token-profile discovery across 7/30/90/270/365-day windows; hypothesis generation only.',
        'selection_locked_at': cfg['selection_locked_at'],
        'selection_policy': cfg['selection_policy'],
        'pair_identity_policy': 'EXACT_LOCKED_PAIR_ONLY',
        'lookahead_policy': 'FORBIDDEN',
        'production_portfolio_impact': 'NONE',
        'verified_tradable_policy_unchanged': 'Liquidity >= $50K plus all existing production truth gates; this report cannot promote a token.',
        'roi_policy': 'NO_ENGINE_ROI_OR_PNL_IS_CALCULATED. Price changes are descriptive history, not hypothetical Wallet500 returns.',
        'missing_data_policy': 'MISSING_OR_PARTIAL_HISTORY_IS EXPLICIT; NEVER INFERRED',
        'tokens_requested': 5,
        'tokens_fetched': sum(1 for p in profiles if p.get('status') != 'FETCH_FAILED'),
        'profiles': profiles,
    }
    _write(OUTPUT, report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    run()
