from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA = Path('data')
EVIDENCE = DATA / 'discovery-evidence-ledger.json'
BACKFILL = DATA / 'historical-backfill-state.json'
ONCHAIN = DATA / 'onchain-historical-reconstruction-state.json'
PERFORMANCE = DATA / 'cash-verified-performance.json'
OUT = DATA / 'historical-truth-backtest.json'
WINDOWS = (7, 30, 90)
MIN_LIQUIDITY_USD = 50_000.0


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)
    except ValueError:
        return None


def _key(chain: str, token: str, pair: str) -> str:
    c = chain.lower()
    if c in {'ethereum', 'eth', 'bsc', 'bnb'}:
        token, pair = token.lower(), pair.lower()
    return f'{c}:{token}:{pair}'


def _verified_status(value: Any) -> bool:
    s = str(value or '').upper()
    if not s:
        return False
    bad = ('NO_VERIFIED', 'UNVERIFIED', 'UNAVAILABLE', 'PENDING', 'RESEARCH', 'UNKNOWN', 'MISSING')
    return not any(x in s for x in bad)


def _record_check(rec: dict[str, Any], backfill_row: dict[str, Any] | None, onchain_row: dict[str, Any] | None) -> dict[str, Any]:
    ident = rec.get('identity') or {}
    market = rec.get('market') or {}
    holder = rec.get('holder_intelligence') or {}
    security = rec.get('security') or rec.get('lp_security') or rec.get('security_intelligence') or {}
    execution = rec.get('execution') or rec.get('exact_pair_execution') or {}

    chain = str(ident.get('chain') or '')
    token = str(ident.get('token') or '')
    pair = str(ident.get('locked_pair_address') or ident.get('pair_address') or '')
    discovery_liquidity = float(market.get('liquidity_usd') or 0.0)
    onchain_ok = isinstance(onchain_row, dict) and onchain_row.get('status') == 'ONCHAIN_RECONSTRUCTED'
    historical_liquidity = float((onchain_row or {}).get('historical_liquidity_usd') or 0.0) if onchain_ok else 0.0
    liquidity_for_gate = historical_liquidity if onchain_ok else discovery_liquidity

    checks = {
        'identity_locked': bool(chain and token and pair),
        'liquidity_gte_50k_at_discovery': liquidity_for_gate >= MIN_LIQUIDITY_USD,
        'holder_cluster_verified_at_discovery': _verified_status(holder.get('status')),
        'lp_security_verified_at_discovery': bool(
            security.get('verified') is True or _verified_status(security.get('status'))
        ),
        'exact_pair_entry_quote_verified': bool(
            execution.get('entry_quote_verified') is True
            or execution.get('exact_pair_quote_verified') is True
            or (onchain_ok and onchain_row.get('historical_exact_pair_entry_quote_verified') is True)
        ),
        'historical_price_available': bool(
            onchain_ok and onchain_row.get('historical_spot_price_usd')
        ) or bool(
            isinstance(backfill_row, dict)
            and backfill_row.get('status') == 'FETCHED'
            and backfill_row.get('candles')
        ),
        'historical_liquidity_verified': bool(
            onchain_ok and onchain_row.get('historical_liquidity_verified') is True
        ) or bool((backfill_row or {}).get('historical_liquidity_verified')),
        'historical_holder_cluster_verified': bool((backfill_row or {}).get('historical_holder_cluster_verified')),
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        'chain': chain,
        'token': token,
        'pair_address': pair,
        'observed_at': rec.get('observed_at'),
        'entry_price_usd': market.get('price_usd'),
        'entry_liquidity_usd': market.get('liquidity_usd'),
        'onchain_historical_liquidity_usd': historical_liquidity if onchain_ok else None,
        'onchain_historical_spot_price_usd': (onchain_row or {}).get('historical_spot_price_usd') if onchain_ok else None,
        'onchain_effective_1usd_entry_price_usd': (onchain_row or {}).get('effective_one_dollar_entry_price_usd') if onchain_ok else None,
        'onchain_target_block_number': (onchain_row or {}).get('target_block_number') if onchain_ok else None,
        'onchain_proof_level': (onchain_row or {}).get('proof_level') if onchain_ok else None,
        'checks': checks,
        'blockers': blockers,
        'backtest_verified': not blockers,
    }


def build(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    evidence = _load(EVIDENCE, {})
    backfill = _load(BACKFILL, {})
    onchain = _load(ONCHAIN, {})
    perf = _load(PERFORMANCE, {})
    records = evidence.get('records', {}) if isinstance(evidence, dict) else {}
    backfill_pairs = backfill.get('pairs', {}) if isinstance(backfill, dict) else {}
    onchain_rows = onchain.get('records', {}) if isinstance(onchain, dict) else {}
    perf_rows = perf.get('rows', []) if isinstance(perf, dict) else []

    perf_by_key: dict[str, dict[str, Any]] = {}
    for row in perf_rows if isinstance(perf_rows, list) else []:
        if not isinstance(row, dict):
            continue
        chain, token, pair = str(row.get('chain') or ''), str(row.get('token') or ''), str(row.get('pair_address') or '')
        if chain and token and pair:
            perf_by_key[_key(chain, token, pair)] = row

    audited: list[dict[str, Any]] = []
    observed_times: list[datetime] = []
    for raw_key, rec in records.items() if isinstance(records, dict) else []:
        if not isinstance(rec, dict):
            continue
        ident = rec.get('identity') or {}
        chain = str(ident.get('chain') or '')
        token = str(ident.get('token') or '')
        pair = str(ident.get('pair_address') or '')
        k = _key(chain, token, pair) if chain and token and pair else str(raw_key)
        row = _record_check(
            rec,
            backfill_pairs.get(k) if isinstance(backfill_pairs, dict) else None,
            onchain_rows.get(k) if isinstance(onchain_rows, dict) else None,
        )
        observed = _dt(rec.get('observed_at'))
        if observed:
            observed_times.append(observed)
        p = perf_by_key.get(k, {})
        row['key'] = k
        row['performance_proof_level'] = p.get('proof_level')
        row['cash_status'] = p.get('cash_status')
        audited.append(row)

    earliest = min(observed_times) if observed_times else None
    windows: dict[str, Any] = {}
    for days in WINDOWS:
        start = now - timedelta(days=days)
        cohort = [r for r in audited if (_dt(r.get('observed_at')) or datetime.min.replace(tzinfo=timezone.utc)) >= start]
        verified = [r for r in cohort if r.get('backtest_verified')]
        full_window_coverage = bool(earliest and earliest <= start)
        blocker_counts: dict[str, int] = {}
        for r in cohort:
            for blocker in r.get('blockers', []):
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        status = 'BACKTEST_VERIFIED' if full_window_coverage and len(verified) == len(cohort) else 'UNVERIFIED_INCOMPLETE_POINT_IN_TIME_COVERAGE'
        windows[str(days)] = {
            'days': days,
            'window_start': start.isoformat(),
            'full_window_observation_coverage': full_window_coverage,
            'records_observed': len(cohort),
            'records_backtest_verified': len(verified),
            'records_unverified': len(cohort) - len(verified),
            'blocker_counts': dict(sorted(blocker_counts.items(), key=lambda x: (-x[1], x[0]))),
            'verified_portfolio_start_usd': 100.0,
            'verified_position_size_usd': 1.0,
            'verified_pnl_usd': None,
            'verified_roi_pct': None,
            'status': status,
        }

    out = {
        'schema_version': 2,
        'generated_at': now.isoformat(),
        'mode': 'STRICT_NO_HINDSIGHT_BACKTEST_VERIFIER',
        'lookahead_policy': 'FORBIDDEN',
        'pair_identity_policy': 'EXACT_LOCKED_PAIR_ONLY',
        'minimum_entry_liquidity_usd': MIN_LIQUIDITY_USD,
        'missing_data_policy': 'UNVERIFIED_NEVER_INFERRED',
        'portfolio_policy': '$100_START_$1_PER_VERIFIED_CALL',
        'onchain_reconstruction_source': ONCHAIN.name,
        'earliest_immutable_evidence_at': earliest.isoformat() if earliest else None,
        'windows': windows,
        'records': sorted(audited, key=lambda r: str(r.get('observed_at') or ''), reverse=True),
        'truth_rule': 'On-chain reconstruction may satisfy historical exact-pair price, reserve, liquidity and $1 quote proof. It never substitutes for holder/cluster or LP/security proof. ROI is emitted only after complete point-in-time observation coverage and every counted record passes all checks.',
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    return out


def main() -> None:
    out = build()
    print(json.dumps({'generated_at': out['generated_at'], 'windows': out['windows']}, indent=2))


if __name__ == '__main__':
    main()
