from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA = Path('data')
EVIDENCE = DATA / 'discovery-evidence-ledger.json'
STATE = DATA / 'historical-backfill-state.json'
REPORT = DATA / 'historical-backfill-report.json'
BASE = 'https://api.geckoterminal.com/api/v2'
NETWORK = {'ethereum': 'eth', 'bsc': 'bsc', 'solana': 'solana'}
WINDOWS = (7, 30, 90)
MAX_PAIRS_PER_RUN = 6
UA = {'User-Agent': 'Wallet500-Historical-Research/1.0', 'Accept': 'application/json;version=20230203'}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def _key(chain: str, token: str, pair: str) -> str:
    if chain.lower() in {'ethereum', 'bsc'}:
        token, pair = token.lower(), pair.lower()
    return f'{chain.lower()}:{token}:{pair}'


def _http_json(url: str) -> dict[str, Any]:
    req = Request(url, headers=UA)
    with urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def _ohlcv(network: str, pair: str, days: int) -> list[list[Any]]:
    # One request is enough for 7/30/90 day daily reconstruction and is deliberately
    # conservative with the public API rate limit. Exact pair identity is preserved.
    params = urlencode({'aggregate': 1, 'limit': min(1000, days + 2), 'currency': 'usd'})
    url = f'{BASE}/networks/{network}/pools/{pair}/ohlcv/day?{params}'
    d = _http_json(url)
    rows = (((d.get('data') or {}).get('attributes') or {}).get('ohlcv_list') or [])
    return rows if isinstance(rows, list) else []


def _evidence_pairs() -> list[dict[str, Any]]:
    d = _load(EVIDENCE, {})
    records = d.get('records', {}) if isinstance(d, dict) else {}
    out = []
    for raw_key, rec in records.items():
        if not isinstance(rec, dict):
            continue
        ident = rec.get('identity') or {}
        market = rec.get('market') or {}
        chain = str(ident.get('chain') or '').lower()
        token = str(ident.get('token') or '')
        pair = str(ident.get('pair_address') or '')
        if chain not in NETWORK or not token or not pair:
            continue
        out.append({
            'key': _key(chain, token, pair),
            'chain': chain,
            'network': NETWORK[chain],
            'token': token,
            'pair_address': pair,
            'discovery_observed_at': rec.get('observed_at'),
            'discovery_price_usd': market.get('price_usd'),
            'discovery_liquidity_usd': market.get('liquidity_usd'),
            'source_record_key': raw_key,
        })
    out.sort(key=lambda x: str(x.get('discovery_observed_at') or ''))
    return out


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    pairs = _evidence_pairs()
    state = _load(STATE, {})
    done = state.get('pairs', {}) if isinstance(state, dict) and isinstance(state.get('pairs'), dict) else {}

    pending = [p for p in pairs if p['key'] not in done or done[p['key']].get('status') != 'FETCHED']
    batch = pending[:MAX_PAIRS_PER_RUN]
    errors = []

    for idx, p in enumerate(batch):
        try:
            candles = _ohlcv(p['network'], p['pair_address'], 90)
            normalized = []
            for row in candles:
                if not isinstance(row, list) or len(row) < 6:
                    continue
                normalized.append({
                    'timestamp': int(row[0]),
                    'open': float(row[1]),
                    'high': float(row[2]),
                    'low': float(row[3]),
                    'close': float(row[4]),
                    'volume_usd': float(row[5]),
                })
            normalized.sort(key=lambda x: x['timestamp'])
            done[p['key']] = {
                **p,
                'status': 'FETCHED',
                'fetched_at': now,
                'provider': 'GECKOTERMINAL_PUBLIC_API',
                'granularity': '1D',
                'candles': normalized,
                'oldest_timestamp': normalized[0]['timestamp'] if normalized else None,
                'newest_timestamp': normalized[-1]['timestamp'] if normalized else None,
                'candles_count': len(normalized),
                'historical_liquidity_verified': False,
                'historical_holder_cluster_verified': False,
                'countable_as_full_wallet500_backtest': False,
            }
        except Exception as e:
            errors.append({'key': p['key'], 'error': f'{type(e).__name__}: {e}'[:300]})
            done[p['key']] = {**p, 'status': 'RETRY', 'last_attempt_at': now, 'last_error': errors[-1]['error']}
        if idx + 1 < len(batch):
            time.sleep(7.0)

    fetched = sum(1 for x in done.values() if x.get('status') == 'FETCHED')
    retry = sum(1 for x in done.values() if x.get('status') == 'RETRY')
    state_out = {
        'version': 1,
        'updated_at': now,
        'mode': 'RESEARCH_ONLY_INCREMENTAL_BACKFILL',
        'lookahead_policy': 'FORBIDDEN',
        'production_portfolio_impact': 'NONE',
        'provider_policy': 'PUBLIC_POINT_IN_TIME_MARKET_DATA_ONLY; NEVER INVENT MISSING FIELDS',
        'max_pairs_per_run': MAX_PAIRS_PER_RUN,
        'pairs': done,
    }
    _write(STATE, state_out)

    window_coverage = {}
    now_ts = int(datetime.now(timezone.utc).timestamp())
    for days in WINDOWS:
        cutoff = now_ts - days * 86400
        usable = 0
        for x in done.values():
            cs = x.get('candles') or []
            if any(int(c.get('timestamp') or 0) <= cutoff + 86400 for c in cs):
                usable += 1
        window_coverage[str(days)] = {
            'days': days,
            'known_exact_pairs_with_price_history': usable,
            'full_wallet500_decision_coverage': 0,
            'status': 'PRICE_BACKFILL_ONLY_NOT_FULL_DECISION_REPLAY',
        }

    report = {
        'version': 1,
        'generated_at': now,
        'mode': 'RESEARCH_ONLY_INCREMENTAL_BACKFILL',
        'lookahead_policy': 'FORBIDDEN',
        'production_portfolio_impact': 'NONE',
        'known_exact_pairs': len(pairs),
        'fetched_pairs': fetched,
        'retry_pairs': retry,
        'remaining_pairs': max(0, len(pairs) - fetched),
        'processed_this_run': len(batch),
        'errors_this_run': errors,
        'windows': window_coverage,
        'important_limit': 'Phase 2a reconstructs historical OHLCV for exact pairs already known to Wallet500. It does not yet claim that Wallet500 would have discovered those pairs in the past. Historical liquidity, holder/cluster state, and full historical discovery universe must be reconstructed before any 7/30/90-day result is labeled BACKTEST VERIFIED.',
        'next_required_layers': [
            'historical discovery universe reconstruction',
            'point-in-time liquidity >= $50K verification',
            'point-in-time holder/cluster reconstruction',
            'exact timestamp decision replay',
            '$100 / $1 immutable historical portfolio ledger',
        ],
    }
    _write(REPORT, report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    run()
