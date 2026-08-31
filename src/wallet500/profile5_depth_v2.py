from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA = Path('data')
CONFIG = DATA / 'profile5-depth-v2-config.json'
OUTPUT = DATA / 'profile5-depth-v2-report.json'
BASE = 'https://api.geckoterminal.com/api/v2'
NETWORK = {'ethereum': 'eth', 'bsc': 'bsc', 'solana': 'solana'}
UA = {'User-Agent': 'Wallet500-Profile5-Depth-V2/1.0', 'Accept': 'application/json;version=20230203'}
PAGE_SIZE = 100
TARGET_CANDLES = 370
MAX_PAGES = 5
REQUEST_GAP_SECONDS = 1.5


def _load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def _request_page(network: str, pair: str, before_timestamp: int | None = None):
    params = {'aggregate': 1, 'limit': PAGE_SIZE, 'currency': 'usd'}
    if before_timestamp is not None:
        params['before_timestamp'] = int(before_timestamp)
    url = f"{BASE}/networks/{network}/pools/{pair}/ohlcv/day?{urlencode(params)}"
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


def _fetch_daily_history(network: str, pair: str):
    by_ts = {}
    before = None
    pages = 0
    while pages < MAX_PAGES and len(by_ts) < TARGET_CANDLES:
        rows = _request_page(network, pair, before)
        pages += 1
        if not rows:
            break
        prior_count = len(by_ts)
        for row in rows:
            by_ts[row['timestamp']] = row
        oldest = min(r['timestamp'] for r in rows)
        if len(by_ts) == prior_count:
            break
        before = oldest - 1
        if len(rows) < PAGE_SIZE:
            break
        time.sleep(REQUEST_GAP_SECONDS)
    candles = sorted(by_ts.values(), key=lambda x: x['timestamp'])
    return candles[-TARGET_CANDLES:], pages


def _max_drawdown(closes):
    peak = None
    worst = 0.0
    for x in closes:
        if x <= 0:
            continue
        peak = x if peak is None else max(peak, x)
        worst = min(worst, (x / peak - 1.0) * 100.0)
    return worst


def _window_profile(candles, days: int):
    rows = candles[-days:] if len(candles) >= days else candles[:]
    if not rows:
        return {'status': 'UNAVAILABLE', 'requested_days': days, 'available_days': 0}
    closes = [r['close'] for r in rows if r['close'] > 0]
    highs = [r['high'] for r in rows]
    lows = [r['low'] for r in rows if r['low'] > 0]
    vols = [r['volume_usd'] for r in rows]
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    mean = sum(returns) / len(returns) if returns else 0.0
    variance = sum((x - mean) ** 2 for x in returns) / len(returns) if returns else 0.0
    first = closes[0] if closes else None
    last = closes[-1] if closes else None
    return {
        'status': 'COMPLETE_PRICE_HISTORY' if len(rows) >= days else 'PARTIAL_HISTORY',
        'requested_days': days,
        'available_days': len(rows),
        'first_timestamp': rows[0]['timestamp'],
        'last_timestamp': rows[-1]['timestamp'],
        'first_close_usd': first,
        'last_close_usd': last,
        'descriptive_price_change_pct': ((last / first) - 1.0) * 100.0 if first and last else None,
        'period_high_usd': max(highs) if highs else None,
        'period_low_usd': min(lows) if lows else None,
        'max_close_drawdown_pct': _max_drawdown(closes),
        'volume_total_usd': sum(vols),
        'volume_avg_daily_usd': sum(vols) / len(vols) if vols else None,
        'positive_close_days': sum(1 for a, b in zip(closes, closes[1:]) if b > a),
        'log_return_volatility_daily': math.sqrt(variance) if returns else None,
        'roi_status': 'NOT_ENGINE_ROI_DESCRIPTIVE_HISTORY_ONLY',
    }


def run():
    cfg = _load(CONFIG)
    assert cfg['mode'] == 'RESEARCH_ONLY_MATURE_SURVIVOR_PROFILE5'
    assert cfg['pair_identity_policy'] == 'EXACT_LOCKED_PAIR_ONLY'
    assert cfg['production_portfolio_impact'] == 'NONE'
    pairs = cfg.get('pairs') or []
    windows = [7, 30, 90, 270, 365]
    assert len(pairs) == 5
    assert cfg.get('windows_days') == windows

    profiles = []
    for item in pairs:
        chain = str(item['chain']).lower()
        pair = str(item['pair_address'])
        label = str(item['label'])
        if chain not in NETWORK or not pair:
            raise RuntimeError('Invalid locked exact-pair identity in profile5 v2 config')
        try:
            candles, pages = _fetch_daily_history(NETWORK[chain], pair)
            profiles.append({
                'chain': chain,
                'label': label,
                'pair_address': pair,
                'pair_identity_locked': True,
                'provider': 'GECKOTERMINAL_PUBLIC_API',
                'pages_fetched': pages,
                'candles_count': len(candles),
                'oldest_timestamp': candles[0]['timestamp'] if candles else None,
                'newest_timestamp': candles[-1]['timestamp'] if candles else None,
                'windows': {str(d): _window_profile(candles, d) for d in windows},
                'historical_liquidity_verified': False,
                'historical_holder_cluster_verified': False,
                'verified_tradable_claim': False,
                'engine_roi_claim': False,
                'wallet500_backtest_claim': False,
            })
        except Exception as e:
            profiles.append({
                'chain': chain,
                'label': label,
                'pair_address': pair,
                'pair_identity_locked': True,
                'status': 'FETCH_FAILED',
                'error': f'{type(e).__name__}: {e}'[:300],
                'windows': {str(d): {'status': 'UNAVAILABLE', 'requested_days': d, 'available_days': 0} for d in windows},
                'verified_tradable_claim': False,
                'engine_roi_claim': False,
                'wallet500_backtest_claim': False,
            })
        time.sleep(REQUEST_GAP_SECONDS)

    report = {
        'version': 2,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'mode': cfg['mode'],
        'purpose': 'Descriptive long-horizon DNA discovery on five mature exact pools; hypothesis generation only.',
        'selection_locked_at': cfg['selection_locked_at'],
        'selection_policy': cfg['selection_policy'],
        'selection_bias_warning': cfg['selection_bias_warning'],
        'pair_identity_policy': 'EXACT_LOCKED_PAIR_ONLY',
        'lookahead_policy': cfg['lookahead_policy'],
        'production_portfolio_impact': 'NONE',
        'verified_tradable_policy_unchanged': 'Liquidity >= $50K plus all existing production truth gates; this report cannot promote a token.',
        'roi_policy': 'NO_ENGINE_ROI_OR_PNL_IS_CALCULATED. Price changes are descriptive history only.',
        'missing_data_policy': cfg['missing_data_policy'],
        'pairs_requested': 5,
        'pairs_fetched': sum(1 for p in profiles if p.get('status') != 'FETCH_FAILED'),
        'profiles': profiles,
    }
    _write(OUTPUT, report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    run()
