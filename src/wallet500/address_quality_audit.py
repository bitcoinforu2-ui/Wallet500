from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path('data')
OUT = DATA / 'address-quality-audit.json'


def load(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() and path.stat().st_size else default
    except Exception:
        return default


def same(a, b):
    return bool(a) and bool(b) and str(a).lower() == str(b).lower()


def classify(r):
    chain = str(r.get('chain') or 'unknown').lower()
    dex = str(r.get('entry_dex') or r.get('dex') or 'unknown').lower()
    token = r.get('token') or r.get('token_address')
    entry_pair = r.get('entry_pair_address') or r.get('pair_address')
    current_pair = r.get('current_pair_address')
    status = str(r.get('measurement_status') or 'UNKNOWN')
    history = r.get('history') if isinstance(r.get('history'), list) else []
    exact_marks = [h for h in history if isinstance(h, dict) and (not h.get('pair_address') or same(h.get('pair_address'), entry_pair))]

    reasons = []
    if not token: reasons.append('MISSING_TOKEN_ID')
    if not entry_pair: reasons.append('MISSING_PAIR_ID')
    if current_pair and entry_pair and not same(current_pair, entry_pair): reasons.append('WRONG_POOL_OR_PAIR_MISMATCH')
    if status == 'VERIFIED_EXACT_PAIR' and entry_pair and same(current_pair, entry_pair):
        quality = 'VERIFIED_EXACT_PAIR'
    elif 'UNAVAILABLE' in status or 'MISSING' in status or not current_pair:
        quality = 'CURRENT_PAIR_UNAVAILABLE'
    elif current_pair and entry_pair and not same(current_pair, entry_pair):
        quality = 'PAIR_MISMATCH'
    else:
        quality = 'UNVERIFIED_CURRENT_PAIR'

    if not exact_marks: reasons.append('NO_EXACT_PAIR_HISTORY_MARK')
    elif len(exact_marks) == 1: reasons.append('SINGLE_EXACT_PAIR_MARK')

    return {
        'chain': chain, 'dex': dex, 'token': token, 'entry_pair_address': entry_pair,
        'current_pair_address': current_pair, 'measurement_status': status,
        'quality': quality, 'exact_history_marks': len(exact_marks), 'reasons': reasons,
    }


def run():
    tracker = load(DATA / 'outcome-tracker.json', {})
    records = tracker.get('tokens') if isinstance(tracker, dict) else {}
    rows = [classify(r) for r in records.values() if isinstance(r, dict)] if isinstance(records, dict) else []
    qc = Counter(r['quality'] for r in rows)
    by_chain = defaultdict(Counter); by_dex = defaultdict(Counter)
    for r in rows:
        by_chain[r['chain']][r['quality']] += 1
        by_dex[f"{r['chain']}:{r['dex']}"][r['quality']] += 1
    total = len(rows); verified = qc['VERIFIED_EXACT_PAIR']
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'method': 'ADDRESS_QUALITY_AUDIT_V1',
        'production_change': False,
        'total_records_audited': total,
        'verified_exact_pair_count': verified,
        'verified_exact_pair_coverage_pct': round(100*verified/total, 4) if total else 0,
        'quality_counts': dict(qc),
        'by_chain': {k: dict(v) for k,v in sorted(by_chain.items())},
        'by_chain_dex': {k: dict(v) for k,v in sorted(by_dex.items())},
        'bottleneck_priority': [
            {'quality': k, 'count': v} for k,v in qc.most_common() if k != 'VERIFIED_EXACT_PAIR'
        ],
        'problem_samples': [r for r in rows if r['quality'] != 'VERIFIED_EXACT_PAIR'][:100],
        'rule': 'Never substitute best pool for immutable exact pair. Availability failures remain unresolved rather than fabricated.',
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: payload[k] for k in ('total_records_audited','verified_exact_pair_count','verified_exact_pair_coverage_pct','quality_counts')}, indent=2))
    return payload

if __name__ == '__main__': run()
