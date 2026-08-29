from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA = Path('data')
OUT = DATA / 'mature-pool-research.json'
BASE = 'https://api.geckoterminal.com/api/v2'
NETWORKS = {'bsc': 'bsc', 'solana': 'solana', 'ethereum': 'eth'}
MIN_AGE_DAYS = 365
MIN_LIQUIDITY_USD = 50_000.0
MAX_PER_CHAIN = 8
PAGES_PER_CHAIN = 3
WINDOWS = (7, 30, 90)
MAX_HTTP_ATTEMPTS = 4
BASE_BACKOFF_SECONDS = 8.0
REQUEST_GAP_SECONDS = 5.0
UA = {'User-Agent': 'Wallet500-MaturePoolResearch/1.1', 'Accept': 'application/json;version=20230203'}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def _http_json(url: str) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(MAX_HTTP_ATTEMPTS):
        try:
            req = Request(url, headers=UA)
            with urlopen(req, timeout=30) as r:
                payload = json.loads(r.read().decode())
            time.sleep(REQUEST_GAP_SECONDS)
            return payload
        except HTTPError as e:
            last = e
            if e.code != 429 or attempt + 1 >= MAX_HTTP_ATTEMPTS:
                raise
            retry_after = e.headers.get('Retry-After') if e.headers else None
            try:
                delay = max(float(retry_after), BASE_BACKOFF_SECONDS * (2 ** attempt)) if retry_after else BASE_BACKOFF_SECONDS * (2 ** attempt)
            except Exception:
                delay = BASE_BACKOFF_SECONDS * (2 ** attempt)
            time.sleep(delay)
        except Exception as e:
            last = e
            if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                raise
            time.sleep(BASE_BACKOFF_SECONDS * (2 ** attempt))
    if last:
        raise last
    raise RuntimeError('HTTP request failed without exception')


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)
    except Exception:
        return None


def _top_pools(network: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = datetime.now(timezone.utc)
    for page in range(1, PAGES_PER_CHAIN + 1):
        d = _http_json(f'{BASE}/networks/{network}/pools?page={page}')
        for item in d.get('data') or []:
            if not isinstance(item, dict):
                continue
            attr = item.get('attributes') or {}
            address = str(attr.get('address') or '')
            if not address or address.lower() in seen:
                continue
            seen.add(address.lower())
            created = _parse_dt(attr.get('pool_created_at'))
            if not created:
                continue
            age_days = (now - created).total_seconds() / 86400
            try:
                liq = float(attr.get('reserve_in_usd') or 0)
            except Exception:
                liq = 0.0
            if age_days < MIN_AGE_DAYS or liq < MIN_LIQUIDITY_USD:
                continue
            rows.append({
                'pool_address': address,
                'name': attr.get('name'),
                'pool_created_at': created.isoformat(),
                'age_days': round(age_days, 1),
                'current_liquidity_usd': liq,
                'dex_id': (((item.get('relationships') or {}).get('dex') or {}).get('data') or {}).get('id'),
            })
        if len(rows) >= MAX_PER_CHAIN:
            break
    rows.sort(key=lambda x: (-x['current_liquidity_usd'], -x['age_days']))
    return rows[:MAX_PER_CHAIN]


def _ohlcv(network: str, pool: str) -> list[dict[str, Any]]:
    params = urlencode({'aggregate': 1, 'limit': 100, 'currency': 'usd'})
    d = _http_json(f'{BASE}/networks/{network}/pools/{pool}/ohlcv/day?{params}')
    raw = (((d.get('data') or {}).get('attributes') or {}).get('ohlcv_list') or [])
    out = []
    for r in raw:
        if not isinstance(r, list) or len(r) < 6:
            continue
        try:
            out.append({'timestamp': int(r[0]), 'open': float(r[1]), 'high': float(r[2]), 'low': float(r[3]), 'close': float(r[4]), 'volume_usd': float(r[5])})
        except Exception:
            continue
    out.sort(key=lambda x: x['timestamp'])
    return out


def _window_return(candles: list[dict[str, Any]], days: int, now_ts: int) -> dict[str, Any]:
    if not candles:
        return {'status': 'NO_DATA'}
    cutoff = now_ts - days * 86400
    eligible = [c for c in candles if c['timestamp'] <= cutoff + 86400]
    if not eligible:
        return {'status': 'INSUFFICIENT_HISTORY'}
    entry = eligible[-1]
    current = candles[-1]
    if entry['close'] <= 0:
        return {'status': 'INVALID_ENTRY_PRICE'}
    ret = (current['close'] / entry['close'] - 1.0) * 100
    return {
        'status': 'PRICE_REPLAY_AVAILABLE',
        'entry_timestamp': entry['timestamp'],
        'entry_close_usd': entry['close'],
        'current_timestamp': current['timestamp'],
        'current_close_usd': current['close'],
        'return_pct': round(ret, 4),
    }


def _complete_90(row: dict[str, Any]) -> bool:
    return ((row.get('windows') or {}).get('90') or {}).get('status') == 'PRICE_REPLAY_AVAILABLE'


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    prior = _load(OUT, {})
    prior_rows = prior.get('rows') if isinstance(prior, dict) else []
    if not isinstance(prior_rows, list):
        prior_rows = []
    cached = {(str(r.get('chain')), str(r.get('pool_address')).lower()): r for r in prior_rows if isinstance(r, dict) and _complete_90(r)}

    rows = list(cached.values())
    errors = []
    cache_hits = len(rows)
    new_rows = 0

    # Missing chains first. Ethereum is intentionally last because the initial run
    # already proved the mechanism there and repeated calls were starving BSC/Solana.
    for chain, network in NETWORKS.items():
        existing_chain = [r for r in rows if r.get('chain') == chain and _complete_90(r)]
        if len(existing_chain) >= MAX_PER_CHAIN:
            continue
        try:
            pools = _top_pools(network)
        except Exception as e:
            errors.append({'chain': chain, 'stage': 'pool_discovery', 'error': f'{type(e).__name__}: {e}'[:300]})
            continue
        for pool in pools:
            key = (chain, str(pool['pool_address']).lower())
            if key in cached:
                continue
            try:
                candles = _ohlcv(network, pool['pool_address'])
                row = {
                    'chain': chain,
                    **pool,
                    'candles_count': len(candles),
                    'oldest_candle_timestamp': candles[0]['timestamp'] if candles else None,
                    'newest_candle_timestamp': candles[-1]['timestamp'] if candles else None,
                    'windows': {str(d): _window_return(candles, d, now_ts) for d in WINDOWS},
                }
                rows.append(row)
                if _complete_90(row):
                    cached[key] = row
                new_rows += 1
            except Exception as e:
                errors.append({'chain': chain, 'pool_address': pool['pool_address'], 'stage': 'ohlcv', 'error': f'{type(e).__name__}: {e}'[:300]})
            if sum(1 for r in rows if r.get('chain') == chain and _complete_90(r)) >= MAX_PER_CHAIN:
                break

    # De-duplicate while keeping the newest result for each exact pool.
    dedup = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        dedup[(str(r.get('chain')), str(r.get('pool_address')).lower())] = r
    rows = list(dedup.values())
    rows.sort(key=lambda r: (str(r.get('chain')), -float(r.get('current_liquidity_usd') or 0)))

    payload = {
        'version': 2,
        'generated_at': now.isoformat(),
        'mode': 'RESEARCH_ONLY_MATURE_POOL_INFRASTRUCTURE_REPLAY',
        'production_portfolio_impact': 'NONE',
        'lookahead_policy': 'NOT_A_STRATEGY_BACKTEST',
        'survivorship_bias_warning': 'CURRENTLY_SURVIVING_1Y_POOLS_ARE_SELECTED TODAY. RESULTS MUST NEVER BE LABELED WALLET500 BACKTEST PERFORMANCE.',
        'purpose': 'Validate 7/30/90 historical data acquisition and replay mechanics on exact pools known to have long records while historical-universe reconstruction is built separately.',
        'selection': {'min_age_days': MIN_AGE_DAYS, 'min_current_liquidity_usd': MIN_LIQUIDITY_USD, 'max_per_chain': MAX_PER_CHAIN, 'pages_per_chain': PAGES_PER_CHAIN},
        'http_policy': {'max_attempts': MAX_HTTP_ATTEMPTS, 'base_backoff_seconds': BASE_BACKOFF_SECONDS, 'request_gap_seconds': REQUEST_GAP_SECONDS, 'incremental_cache': True, 'missing_chains_first': True},
        'rows': rows,
        'errors': errors,
        'counts': {
            'pools': len(rows),
            'cache_hits': cache_hits,
            'new_rows_this_run': new_rows,
            'by_chain': {c: sum(r.get('chain') == c and _complete_90(r) for r in rows) for c in NETWORKS},
            'window_7_available': sum((r.get('windows') or {}).get('7', {}).get('status') == 'PRICE_REPLAY_AVAILABLE' for r in rows),
            'window_30_available': sum((r.get('windows') or {}).get('30', {}).get('status') == 'PRICE_REPLAY_AVAILABLE' for r in rows),
            'window_90_available': sum((r.get('windows') or {}).get('90', {}).get('status') == 'PRICE_REPLAY_AVAILABLE' for r in rows),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in payload.items() if k != 'rows'}, indent=2))
    return payload


if __name__ == '__main__':
    run()
